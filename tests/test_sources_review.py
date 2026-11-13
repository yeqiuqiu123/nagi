"""Independent regressions for the seven phase-1 backend review findings."""
import copy
import json
import os
import plistlib
import shlex
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

from test_source_notifications import event, reservation
from test_sources import ACCESS, BOOTSTRAP, NOW, OWNER, Reader

from agents_service import AgentsService
from linux.agent_notifications import NOTIFICATIONS_API, NotificationConsumer
from sources_service import REGISTRY, SourcesService
from sources_transport import SourceError, issue_local, write_credential


class ReviewRegressions(TestCase):
    def setUp(self):
        self.directory=Path(self.enterContext(TemporaryDirectory()))
        self.legacy=AgentsService(self.directory,lambda _:Reader(),lambda:NOW)
        self.enterContext(patch.object(AgentsService,'read_machine',lambda *_:None))
        self.identities={}
        self.detector=Mock(side_effect=lambda origin:{'environmentId':self.identities.get(origin,origin),
                                                   'orchestrationProtocolVersion':2})
        def reader(policy):
            value=Reader()
            shell=value.shell
            def observed():
                _,snapshot=shell()
                return {'environmentId':self.identities.get(policy['origin'],policy['origin'])},snapshot
            value.shell=observed
            return value
        self.exchange=Mock(return_value=ACCESS)
        self.service=SourcesService(self.legacy,detector=self.detector,inventory=list,
                                    issuer=lambda path:write_credential(path,ACCESS),exchange=self.exchange,
                                    reader_factory=reader)
        self.addCleanup(self.service.close)

    def configuration(self,origin):
        return {'configuration':{'adapterId':'t3','label':'Computer','placement':{'kind':'manual'},
                                'mode':'protocol2','options':{'port':47880,'origin':origin},'pairing':BOOTSTRAP}}

    def connect(self,origin,revision=0):
        tested=self.service.test(self.configuration(origin),OWNER)
        return self.service.connect({'testId':tested['testId'],'expectedRevision':revision},OWNER)

    def policy(self,origin):
        credential=self.directory/'external-legacy-credential'
        if not credential.exists():write_credential(credential,ACCESS)
        self.legacy.store.mutate('nagi-t3.json',{},lambda value:(value.clear(),value.update(
            version=1,origin=origin,credentialFile=str(credential))))

    def test_discovery_io_does_not_hold_glance_lock(self):
        for phase in ('inventory','cli','probe'):
            with self.subTest(phase=phase):
                entered,release=threading.Event(),threading.Event()
                def blocked(*_,entered=entered,release=release,phase=phase):
                    entered.set()
                    if not release.wait(5):raise RuntimeError('fixture timeout')
                    return [] if phase=='inventory' else (['synthetic'],{}) if phase=='cli' else {}
                self.service.inventory=blocked if phase=='inventory' else list
                self.service.detector=blocked if phase=='probe' else self.detector
                with patch('sources_service.local_cli',side_effect=blocked if phase=='cli' else None,
                           return_value=(['synthetic'],{})),ThreadPoolExecutor(max_workers=2) as pool:
                    discover=pool.submit(self.service.discover,{'adapterIds':['t3'],
                                         'placement':{'kind':'tailscale' if phase=='inventory' else 'local'}},OWNER)
                    self.assertTrue(entered.wait(2))
                    glance=pool.submit(self.service.glance,'linux')
                    try:
                        self.assertEqual(glance.result(timeout=1)['sources'],[])
                    finally:
                        release.set()
                        discover.result(timeout=5)
                        glance.result(timeout=5)

    def test_invalid_legacy_policy_does_not_disable_sources_or_recovery(self):
        path=self.directory/'nagi-t3.json'
        for content,mode in (('{bad json',0o600),('{}',0o600),('{}',0o644)):
            path.write_text(content)
            path.chmod(mode)
            self.assertEqual(self.service.read_sources()['sources'],[])
            tested=self.service.test(self.configuration('http://100.80.1.2:47880'),OWNER)
            self.assertIsNotNone(tested['testId'])
            self.assertEqual(path.read_text(),content)
        connected=self.connect('http://100.80.1.2:47880')
        self.assertEqual(connected['revision'],1)

    def test_environment_identity_deduplicates_ip_and_dns_before_exchange(self):
        ip='http://100.80.1.2:47880'
        dns='https://computer.tail.ts.net'
        self.identities.update({ip:'environment-one',dns:'environment-one'})
        self.connect(ip)
        tested=self.service.test(self.configuration(dns),OWNER)
        with self.assertRaises(SourceError) as error:
            self.service.connect({'testId':tested['testId'],'expectedRevision':1},OWNER)
        self.assertEqual(error.exception.code,'source_exists')
        self.assertEqual(self.exchange.call_count,1)
        self.assertEqual(self.service.registry()['sources'][0]['environmentId'],'environment-one')

    def test_duplicate_check_uses_live_legacy_policy_not_registry_snapshot(self):
        old='http://127.0.0.1:47880'
        live='http://100.80.1.3:47880'
        alias='https://live.tail.ts.net'
        self.identities.update({old:'old-environment',live:'live-environment',alias:'live-environment'})
        self.policy(old)
        self.connect('http://100.80.1.2:47880')
        self.policy(live)
        tested=self.service.test(self.configuration(alias),OWNER)
        with self.assertRaises(SourceError) as error:
            self.service.connect({'testId':tested['testId'],'expectedRevision':1},OWNER)
        self.assertEqual(error.exception.code,'source_exists')
        self.assertIn(live,[call.args[0] for call in self.detector.call_args_list])
        # The old origin is no longer the legacy connection; it can be selected.
        self.assertEqual(self.connect(old,1)['revision'],2)

    def test_disconnect_removes_only_selected_private_cache_and_lock(self):
        first=self.connect('http://100.80.1.2:47880')['source']['id']
        second=self.connect('http://100.80.1.3:47880',1)['source']['id']
        self.service.poll(force=True)
        state=self.directory/f'nagi-source-{first}-state.json'
        lock=self.directory/f'.nagi-source-{first}-lock'
        other=self.directory/f'nagi-source-{second}-state.json'
        before=other.read_bytes()
        self.assertTrue(state.exists())
        self.assertTrue(lock.exists())
        self.service.disconnect({'sourceId':first,'expectedRevision':2})
        self.assertFalse(state.exists())
        self.assertFalse(lock.exists())
        self.assertEqual(other.read_bytes(),before)
        with self.assertRaises(SourceError):
            self.service.notification_action('reserve',{'sourceId':first,'id':'a'*64})
        self.assertFalse(lock.exists())

    def test_disconnect_unlinks_own_cache_symlink_without_touching_target(self):
        identity=self.connect('http://100.80.1.2:47880')['source']['id']
        self.service.poll(force=True)
        path=self.directory/f'nagi-source-{identity}-state.json'
        outside=self.directory/'external-data'
        outside.write_text('preserve external data')
        path.unlink()
        path.symlink_to(outside)
        self.service.disconnect({'sourceId':identity,'expectedRevision':1})
        self.assertFalse(path.is_symlink())
        self.assertEqual(outside.read_text(),'preserve external data')

    def test_test_secrets_expire_without_any_further_request(self):
        with patch('sources_service.TEST_SECONDS',.04,create=True):
            tested=self.service.test(self.configuration('http://100.80.1.2:47880'),OWNER)
        configuration=self.service.tests[tested['testId']]['configuration']
        threading.Event().wait(.2)  # No expire(), GET, POST or poll during expiry.
        self.assertNotIn(tested['testId'],self.service.tests)
        self.assertNotEqual(configuration.get('pairing'),BOOTSTRAP)


class ProcessAndNotificationRegressions(TestCase):
    def test_bad_notification_between_valid_events_does_not_suppress_banners(self):
        first,last=event(),event('b','stuck')
        invalid={'sourceId':'legacy-t3','event':dict(event(),kind='invalid')}
        sent=Mock(return_value=True)
        consumer=NotificationConsumer('unused',sent,Mock())
        consumer.request=Mock(side_effect=[{'version':1,'events':[{'sourceId':'legacy-t3','event':first},
                                          invalid,{'sourceId':'c'*32,'event':last}]},reservation(first),{},reservation(last),{}])
        consumer.poll()
        self.assertEqual([call.args[0]['id'] for call in sent.call_args_list],[first['id'],last['id']])
        self.assertEqual(consumer.request.call_args.args[0],NOTIFICATIONS_API+'/claim')

    def test_pairing_cli_and_pipe_writer_do_not_inherit_reader_environment(self):
        directory=Path(self.enterContext(TemporaryDirectory()))
        captured=directory/'environment.json'
        script='import json,os,sys;json.dump(dict(os.environ),open(sys.argv[1],"w"));print("synthetic-observer-access")'
        env={key:str(directory) for key in ('HOME','TMPDIR')}
        env.update(PATH=os.defpath,LANG='C',USER='fixture',NODE_OPTIONS='synthetic',T3_HOME='synthetic',
                   T3_PROFILE='synthetic',READER_SECRET='synthetic',PYTHONPATH='synthetic')
        with patch.dict(os.environ,env,clear=True),patch('sources_transport.subprocess.Popen',wraps=subprocess.Popen) as spawned,patch('sources_transport.local_cli',
                return_value=([sys.executable,'-c',script,str(captured)],copy.deepcopy(env))):
            issue_local(directory/'credential')
        result=json.loads(captured.read_text())
        for key in ('NODE_OPTIONS','T3_HOME','T3_PROFILE','READER_SECRET','PYTHONPATH'):
            self.assertNotIn(key,result)
        self.assertEqual(result['HOME'],str(directory))
        self.assertEqual(spawned.call_count,2)
        for call in spawned.call_args_list:
            self.assertLessEqual(set(call.kwargs['env']),{'HOME','PATH','LANG','USER','TMPDIR'})

    def test_mac_app_pairing_environment_adds_only_the_required_electron_flag(self):
        from sources_transport import local_cli
        directory=Path(self.enterContext(TemporaryDirectory()))
        app=directory/'T3 Code.app'
        executable=app/'Contents/MacOS/T3'
        executable.parent.mkdir(parents=True)
        executable.write_text('synthetic binary')
        executable.chmod(0o700)
        (app/'Contents/Resources').mkdir()
        (app/'Contents/Resources/app.asar').write_text('synthetic archive')
        (app/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleExecutable':'T3'}))
        with patch('sources_transport.shutil.which',return_value=None),patch('sys.platform','darwin'), \
             patch('sources_transport.Path.glob',return_value=[app]), \
             patch.dict(os.environ,{'NODE_OPTIONS':'synthetic','T3_HOME':'synthetic','READER_SECRET':'synthetic'}):
            args,env=local_cli()
        self.assertEqual(args[0],str(executable))
        self.assertEqual(env['ELECTRON_RUN_AS_NODE'],'1')
        self.assertLessEqual(set(env),{'HOME','PATH','LANG','USER','TMPDIR','ELECTRON_RUN_AS_NODE'})

    def test_mac_setup_leaves_policy_alone_when_registry_exists(self):
        root=Path(__file__).resolve().parents[1]
        script=(root/'mac/setup-mac.sh').read_text()
        # Execute just the real source-configuration section with inert helpers;
        # never build, install, issue a T3 session, or access launchd on this host.
        start=script.index('\n}\n\nif [[',script.index('find_local_origin()'))+3
        section=script[start:script.index('# NAGI_SKIP_SERVICES')]
        directory=Path(self.enterContext(TemporaryDirectory()))
        registry=directory/REGISTRY
        registry.write_text('{}')
        policy=directory/'nagi-t3.json'
        policy.write_text('preserve policy')
        prelude='\n'.join([f'DATA_DIR={shlex.quote(str(directory))}',f'PY={shlex.quote(sys.executable)}',
            "T3_LOCAL=0", "T3_ORIGIN=http://100.80.1.2:47880",'TOKEN_STDIN=0','CREDENTIAL=unused',
            'say() { :; }','fail() { exit 13; }',
            'helper() { if [[ "$1" == policy ]]; then printf overwritten > "$DATA_DIR/nagi-t3.json"; elif [[ "$1" == origin-kind ]]; then printf tailnet; fi; }'])
        result=subprocess.run(['bash','-eu','-c',prelude+'\n'+section],capture_output=True,text=True,timeout=5,check=False)
        self.assertEqual(result.returncode,0)
        self.assertEqual(policy.read_text(),'preserve policy')
