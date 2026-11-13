"""Cursor fixtures only. Never open real credentials, hooks, or a provider account."""
import base64
import copy
import fcntl
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

from agents_service import AgentsService
from cursor_hook import EVENTS, MAX_BYTES, append, capture
from cursor_hooks import edit, ours, settings
from cursor_source import (CursorReadError, credential, fetch_usage, jwt_identity,
                           project_events, usage_provider)
from sources_service import SourcesService
from sources_transport import SourceError

NOW=datetime(2026,11,13,12,tzinfo=timezone.utc)


def token(**overrides):
    payload={'sub':'user_fixture','exp':(NOW+timedelta(hours=1)).timestamp()}|overrides
    return 'fake.'+base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')+'.signature'


def usage(**plan):
    return {'individualUsage':{'plan':{'totalPercentUsed':92}|plan},
            'billingCycleEnd':(NOW+timedelta(days=10)).isoformat()}


def event(kind='postToolUse',**kwargs):
    return {'hook_event_name':kind,'conversation_id':'conversation','generation_id':'generation',
            'workspace_roots':['/private/project'],'cursor_version':'fixture',
            'prompt':'do-not-store','output':'do-not-store','user_email':'do-not-store'}|kwargs


class DirectCursor(TestCase):
    def setUp(self):
        self.home=Path(self.enterContext(TemporaryDirectory()))
        (self.home/'.cursor').mkdir(mode=0o700)
        self.directory=self.home/'nagi';self.directory.mkdir(mode=0o700)
        self.now=NOW
        self.legacy=AgentsService(self.directory,clock=lambda:self.now)
        self.legacy.read_machine=lambda _:None
        self.sources=SourcesService(self.legacy,local_home=self.home)
        self.addCleanup(self.sources.close)
        # Every credential path is rooted in this disposable HOME.
        self.enterContext(patch.dict(os.environ,{'HOME':str(self.home),'XDG_CONFIG_HOME':str(self.home/'.config')}))

    def configure(self):
        return {'configuration':{'adapterId':'cursor','label':'This computer','placement':{'kind':'this_computer'},'mode':'hooks','options':{}}}

    def connect(self):
        tested=self.sources.test(self.configure(),'owner')
        self.assertIsNotNone(tested['testId'])
        result=self.sources.connect({'testId':tested['testId'],'expectedRevision':0},'owner')
        service=self.sources.service_for(self.sources.registry()['sources'][0])
        service.usage_fetcher=Mock(return_value=usage());service.monotonic=lambda:self.now.timestamp()
        return result,service

    def login(self,value=None,root=None):
        root=root or self.home/'.config';path=root/'cursor/auth.json';path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        path.write_text(json.dumps({'accessToken':token() if value is None else value}));path.chmod(0o600)
        return path

    def database(self,value=None,platform='linux'):
        root=self.home/'Library/Application Support/Cursor' if platform=='darwin' else self.home/'.config/Cursor'
        path=root/'User/globalStorage/state.vscdb';path.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(path) as c:
            c.execute('CREATE TABLE IF NOT EXISTS ItemTable (key TEXT PRIMARY KEY, value TEXT)')
            c.execute('INSERT OR REPLACE INTO ItemTable VALUES (?,?)',('cursorAuth/accessToken',value or token()))
            c.execute('INSERT OR REPLACE INTO ItemTable VALUES (?,?)',('private-other-key','do-not-read'))
        return path

    def test_catalog_binding_and_credential_free_setup(self):
        item=next(i for i in self.sources.catalog()['harnesses'] if i['id']=='cursor')
        self.assertEqual((item['displayName'],item['copyKey'],item['beta']),('Cursor','cursor_direct',True))
        self.assertTrue(all('beta' not in i for i in self.sources.catalog()['harnesses'] if i['id']!='cursor'))
        with patch('cursor_source.credential',side_effect=AssertionError('must not read')):
            self.sources.discover({'adapterIds':['cursor'],'placement':{'kind':'this_computer'}},'owner')
            tested=self.sources.test(self.configure(),'owner')
        self.assertEqual(tested['requirements'],['cursor_hooks_opt_in','cursor_usage_opt_in'])
        self.assertEqual(set(tested['limits']),{'cursor'})
        self.assertFalse(tested['capabilities']['lineage']);self.assertFalse(tested['capabilities']['asksYou'])
        self.assertFalse((self.home/'.cursor/hooks.json').exists())
        bad=self.configure();bad['configuration']['placement']['kind']='local'
        with self.assertRaises(SourceError):self.sources.test(bad,'owner')

    def test_credentials_paths_missing_invalid_expired_and_safe_sqlite(self):
        with self.assertRaisesRegex(CursorReadError,'cursor_login_missing'):credential(self.home,NOW,platform='linux')
        path=self.login();self.assertEqual(credential(self.home,NOW,platform='linux'),token())
        alt=self.home/'xdg';self.login(root=alt)
        self.assertEqual(credential(self.home,NOW,platform='linux',environ={'XDG_CONFIG_HOME':str(alt)}),token())
        for value,reason in [('malformed','cursor_login_invalid'),(token(exp=0),'cursor_login_expired'),
                              (token(sub='header\ninvalid'),'cursor_login_invalid'),(token(exp=True),'cursor_login_invalid')]:
            self.login(value)
            with self.assertRaisesRegex(CursorReadError,reason):credential(self.home,NOW,platform='linux')
        path.unlink();db=self.database();before=set(db.parent.iterdir());original=db.read_bytes()
        self.assertEqual(credential(self.home,NOW,platform='linux'),token())
        self.assertEqual(set(db.parent.iterdir()),before);self.assertEqual(db.read_bytes(),original)
        self.database('cursor-safe-storage:v1:fake')
        with self.assertRaisesRegex(CursorReadError,'cursor_login_invalid'):credential(self.home,NOW,platform='linux')
        db.unlink();db.symlink_to(self.home/'missing')
        with self.assertRaisesRegex(CursorReadError,'cursor_login_invalid'):credential(self.home,NOW,platform='linux')

    def test_keychain_no_cli_and_ide_fallback(self):
        keychain=Mock(return_value=token())
        self.assertEqual(credential(self.home,NOW,platform='darwin',keychain=keychain),token())
        keychain.assert_called_once_with()
        self.database(platform='darwin')
        keychain.side_effect=OSError('private error')
        self.assertEqual(credential(self.home,NOW,platform='darwin',keychain=keychain),token())
        self.database('cursor-safe-storage:v1:encrypted',platform='darwin')
        with self.assertRaisesRegex(CursorReadError,'cursor_login_invalid') as caught:
            credential(self.home,NOW,platform='darwin',keychain=keychain)
        self.assertNotIn('private',str(caught.exception))

    def test_fixed_http_cookie_no_redirect_and_closed_errors(self):
        self.login()
        for status,reason in [(401,'cursor_login_expired'),(429,'provider_rate_limited'),(302,'provider_unavailable'),(503,'provider_unavailable')]:
            connection=Mock();connection.getresponse.return_value.status=status
            with patch('cursor_source.http.client.HTTPSConnection',return_value=connection) as factory,patch('cursor_source.IODeadline'):
                with self.assertRaisesRegex(CursorReadError,reason) as caught:fetch_usage(self.home,NOW)
            factory.assert_called_once_with('cursor.com',timeout=8)
            call=connection.request.call_args;self.assertEqual(call.args,('GET','/api/usage-summary'))
            self.assertEqual(call.kwargs['headers']['Cookie'],'WorkosCursorSessionToken=user_fixture%3A%3A'+token())
            self.assertNotIn(token(),str(caught.exception));connection.close.assert_called_once()
        connection=Mock();response=connection.getresponse.return_value;response.status=200
        response.read.return_value=json.dumps(usage()).encode()
        with patch('cursor_source.http.client.HTTPSConnection',return_value=connection),patch('cursor_source.IODeadline'):
            self.assertEqual(fetch_usage(self.home,NOW),usage())
            connection.request.side_effect=ValueError(token())
            with self.assertRaisesRegex(CursorReadError,'provider_unavailable') as caught:fetch_usage(self.home,NOW)
            self.assertNotIn(token(),str(caught.exception))

    def test_install_remove_preserve_rollback_modes_and_backups(self):
        original={'version':1,'other':'keep','hooks':{'stop':[{'command':'owner-hook'}],
                   'futureEvent':[{'command':'owner-future'}],
                   'postToolUse':[{'command':'python /old/cursor_hook.py /data '+'b'*32}]}}
        path=self.home/'.cursor/hooks.json';path.write_text(json.dumps(original));path.chmod(0o640)
        result,service=self.connect();identity=result['source']['id']
        installed=json.loads(path.read_text());self.assertEqual(installed['hooks']['stop'][0],original['hooks']['stop'][0])
        self.assertNotIn('subagentStart',installed['hooks']);self.assertNotIn('preToolUse',installed['hooks'])
        self.assertEqual(path.stat().st_mode&0o777,0o640)
        for i in range(4):
            edit(self.home,self.directory,identity,remove=True);edit(self.home,self.directory,identity)
        backups=list(path.parent.glob('hooks.nagi-backup-*'));self.assertLessEqual(len(backups),3)
        self.assertTrue(all(p.stat().st_mode&0o777==0o600 for p in backups))
        log=self.directory/('cursor-'+identity+'.jsonl');log.write_text('{}\n');log.chmod(0o600)
        self.sources.disconnect({'sourceId':identity,'expectedRevision':1})
        self.assertEqual(json.loads(path.read_text()),original);self.assertFalse(log.exists())
        tested=self.sources.test(self.configure(),'owner')
        with patch.object(self.sources,'persist',side_effect=OSError()):
            with self.assertRaises(OSError):self.sources.connect({'testId':tested['testId'],'expectedRevision':2},'owner')
        self.assertEqual(json.loads(path.read_text()),original)

    def test_failed_atomic_replace_leaves_original_and_concurrent_change_survives(self):
        path=self.home/'.cursor/hooks.json';path.write_text('{"version":1,"hooks":{"stop":[{"command":"owner"}]}}')
        original=path.read_bytes()
        with patch('cursor_hooks.os.replace',side_effect=OSError('fixture')):
            with self.assertRaises(OSError):edit(self.home,self.directory,'a'*32)
        self.assertEqual(path.read_bytes(),original)
        from cursor_hooks import read_owned
        def concurrent_read(target,*args,**kwargs):
            if Path(target)==path and len(list(path.parent.glob('.nagi-settings-*'))):
                path.write_text('{"version":1,"owner":"concurrent"}')
            return read_owned(target,*args,**kwargs)
        with patch('cursor_hooks.read_owned',side_effect=concurrent_read):
            with self.assertRaisesRegex(ValueError,'Concurrent'):edit(self.home,self.directory,'a'*32)
        self.assertEqual(json.loads(path.read_text())['owner'],'concurrent')

    def test_post_replace_sync_failure_restores_original(self):
        path=self.home/'.cursor/hooks.json';path.write_text('{"version":1,"owner":"keep"}')
        original=path.read_bytes();real_sync=os.fsync;calls=0
        def sync(fd):
            nonlocal calls
            calls+=1
            if calls==3:raise OSError('fixture directory sync failure')
            return real_sync(fd)
        with patch('cursor_hooks.os.fsync',side_effect=sync):
            with self.assertRaises(OSError):edit(self.home,self.directory,'a'*32)
        self.assertEqual(path.read_bytes(),original)

    def test_remove_registry_failure_restores_and_unsafe_settings_fail(self):
        result,_=self.connect();path=self.home/'.cursor/hooks.json';before=path.read_bytes()
        with patch.object(self.sources,'persist',side_effect=OSError()):
            with self.assertRaises(OSError):self.sources.disconnect({'sourceId':result['source']['id'],'expectedRevision':1})
        self.assertEqual(json.loads(path.read_bytes()),json.loads(before))
        path.unlink();path.symlink_to(self.home/'other')
        with self.assertRaises(Exception):edit(self.home,self.directory,result['source']['id'])
        self.assertTrue(ours({'command':'python /old/cursor_hook.py /data '+'a'*32},'a'*32))
        self.assertFalse(ours({'command':'echo cursor_hook.py '+'a'*32},'a'*32))

    def test_metadata_only_and_conservative_lifecycle(self):
        captured=capture(event(),{})
        self.assertEqual(set(captured),{'conversation_id','generation_id','subagent_id','parent_conversation_id','event','timestamp','project','cursor_version'})
        self.assertNotIn('do-not-store',json.dumps(captured));self.assertEqual(captured['project'],'project')
        def normalized(kind,**kwargs):
            value=capture(event(kind,**kwargs),{});value['timestamp']=NOW.isoformat();return value
        submit=normalized('beforeSubmitPrompt');activity=normalized('postToolUse');stop=normalized('stop')
        self.assertFalse(project_events([submit],'source',NOW,self.legacy.settings())[0]['projects'])
        data,_,_=project_events([submit,activity],'source',NOW,self.legacy.settings())
        self.assertEqual(data['counts']['running'],1)
        self.assertFalse(project_events([submit,activity,stop],'source',NOW,self.legacy.settings())[0]['projects'])
        self.assertEqual(project_events([activity,stop,activity],'source',NOW,self.legacy.settings())[0]['counts']['running'],1)
        late=normalized('stop',generation_id='old')
        self.assertEqual(project_events([activity,late],'source',NOW,self.legacy.settings())[0]['counts']['running'],1)
        data,_,_=project_events([activity],'source',NOW+timedelta(minutes=16),self.legacy.settings())
        self.assertFalse(data['projects']);self.assertIn('stale_source',data['warnings'])
        start=normalized('subagentStart',subagent_id='child',parent_conversation_id='parent')
        self.assertEqual(start['parent_conversation_id'],'parent');self.assertNotIn('subagentStart',EVENTS)
        child=normalized('postToolUse',subagent_id='child')
        parent=normalized('postToolUse',conversation_id='parent')
        data,rows,_=project_events([parent,start,child],'source',NOW,self.legacy.settings())
        self.assertEqual(rows['conversation/child']['parentId'],'parent')
        self.assertEqual(data['counts']['waitingOnYou'],0)

    def test_silent_sink_bounds_slow_input_lock_and_rotation(self):
        script=Path(__file__).resolve().parents[1]/'cursor_hook.py';source='a'*32
        command=[sys.executable,'-I','-B',str(script),str(self.directory),source]
        result=subprocess.run(command,input=json.dumps(event()).encode(),capture_output=True,timeout=3)
        self.assertEqual((result.returncode,result.stdout,result.stderr),(0,b'',b''))
        output=self.directory/('cursor-'+source+'.jsonl')
        self.assertNotIn('do-not-store',output.read_text())
        for raw in (b'invalid',b'x'*(1024*1024+1),b'[]'):
            result=subprocess.run(command,input=raw,capture_output=True,timeout=3)
            self.assertEqual((result.returncode,result.stdout,result.stderr),(0,b'',b''))
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            started=time.monotonic();process.wait(timeout=2)
            self.assertLess(time.monotonic()-started,1.7)
            self.assertEqual((process.returncode,process.stdout.read(),process.stderr.read()),(0,b'',b''))
        finally:
            process.stdin.close();process.stdout.close();process.stderr.close()
            if process.poll() is None:process.kill();process.wait()
        lock=self.directory/('.cursor-'+source+'.lock')
        with lock.open('wb') as stream:
            fcntl.flock(stream,fcntl.LOCK_EX)
            started=time.monotonic();result=subprocess.run(command,input=json.dumps(event()).encode(),capture_output=True,timeout=2)
            self.assertLess(time.monotonic()-started,.6)
            self.assertEqual((result.returncode,result.stdout,result.stderr),(0,b'',b''))
        output.write_bytes(b'x'*MAX_BYTES)
        append(self.directory,source,capture(event(),{}))
        self.assertLessEqual(output.stat().st_size,MAX_BYTES)
        self.assertEqual(Path(str(output)+'.1').stat().st_size,MAX_BYTES)

    def test_usage_mapping_poll_floor_backoff_restart_and_alert_flow(self):
        result,service=self.connect();self.sources.poll(force=True)
        limits=service.providers['cursor'];self.assertEqual(limits['status'],'ok')
        account=limits['data']['accounts'][0];window=account['windows'][0]
        self.assertEqual((account['label'],window['label'],window['kind'],window['remainingPercent']),('Cursor 1','Month','monthly',8))
        alerts=self.sources.notifications()['events'];self.assertEqual(len(alerts),1)
        alert=alerts[0]['event'];self.assertEqual(alert['provider'],'cursor')
        from linux.agent_notifications import valid_event
        self.assertTrue(valid_event(alert))
        reserved=service.reserve(alert['id'],include_limits=True)
        self.assertIsNotNone(reserved)
        service.claim(alert['id'],reserved['reservation'],release=True,include_limits=True)
        reserved=service.reserve(alert['id'],include_limits=True)
        service.claim(alert['id'],reserved['reservation'],include_limits=True)
        self.assertEqual(self.sources.notifications()['events'],[])
        self.sources.poll(force=True);self.assertEqual(service.usage_fetcher.call_count,1)
        self.now+=timedelta(minutes=5);service.usage_fetcher.side_effect=CursorReadError('provider_rate_limited')
        self.sources.poll(force=True);self.assertEqual(service.providers['cursor']['reason'],'provider_rate_limited')
        service.cursor_result=None;self.now+=timedelta(minutes=5);self.sources.poll(force=True)
        self.assertEqual(service.usage_fetcher.call_count,2)
        self.now+=timedelta(minutes=5);self.sources.poll(force=True);self.assertEqual(service.usage_fetcher.call_count,3)
        self.assertEqual(self.sources.notifications()['events'],[])
        for path in self.directory.glob('*.json'):self.assertNotIn(token(),path.read_text())
        # Persisted nextAt also blocks a new service after restart.
        self.sources.services.clear();new=self.sources.service_for(self.sources.registry()['sources'][0])
        new.usage_fetcher=Mock(side_effect=AssertionError('floor'));self.sources.poll(force=True)
        new.usage_fetcher.assert_not_called()
        self.assertEqual(new.providers['cursor']['reason'],'provider_rate_limited')

    def test_cursor_linux_delivery_opens_only_panel_and_tray_recognizes_provider(self):
        _,service=self.connect();self.sources.poll(force=True)
        alert=self.sources.notifications()['events'][0]['event']
        from linux.agent_notifications import NotificationConsumer, banner
        self.assertEqual(banner(alert)[0],'Cursor 1 · 8% left')
        panel=Mock();opener=Mock();send=Mock(side_effect=lambda e,clicked:(clicked(),True)[1])
        consumer=NotificationConsumer('unused',send,opener,on_panel=panel)
        consumer.request=Mock(side_effect=[{'version':1,'events':[{'sourceId':'a'*32,'event':alert}]},
            {'version':1,'reserved':True,'lease':{'reservation':'r'*43,'expiresAt':(NOW+timedelta(seconds=30)).isoformat(),'event':alert}},
            {'version':1,'claimed':True,'event':alert}])
        consumer.poll();panel.assert_called_once();opener.assert_not_called()
        from linux.tray import fresh_empty
        limits=copy.deepcopy(service.providers)
        limits['cursor']['data']['accounts'][0]['windows'][0]['remainingPercent']=0
        self.assertIsNotNone(fresh_empty({'providers':limits},NOW))

    def test_mapping_bad_shapes_expired_reset_and_login_hides_old_values(self):
        for plan,expected in [({'used':92,'limit':100},92),({'remaining':8,'limit':100},92),
                              ({'used':92,'remaining':8,'limit':100},92),({'totalPercentUsed':.36},.36)]:
            raw={'individualUsage':{'plan':plan},'billingCycleEnd':(NOW+timedelta(days=1)).isoformat()}
            self.assertEqual(usage_provider(raw,NOW.isoformat())['usageLimits']['windows'][0]['usedPercent'],expected)
        for plan in ({'used':1,'limit':0},{'totalPercentUsed':True},{'totalPercentUsed':float('nan')},
                     {'used':20,'remaining':20,'limit':100},{'enabled':False}):
            with self.assertRaisesRegex(CursorReadError,'invalid_usage'):usage_provider({'individualUsage':{'plan':plan},'billingCycleEnd':NOW.isoformat()},NOW.isoformat())
        # Past the plan is 0% left, never "invalid": that is when the alert matters most.
        for plan in ({'totalPercentUsed':101},{'used':120,'remaining':0,'limit':100}):
            raw={'individualUsage':{'plan':plan},'billingCycleEnd':(NOW+timedelta(days=1)).isoformat()}
            self.assertEqual(usage_provider(raw,NOW.isoformat())['usageLimits']['windows'][0]['usedPercent'],100.0)
        _,service=self.connect();self.sources.poll(force=True)
        self.now+=timedelta(minutes=5);service.usage_fetcher.side_effect=CursorReadError('cursor_login_expired')
        self.sources.poll(force=True)
        self.assertEqual(service.providers['cursor']['reason'],'cursor_login_expired');self.assertIsNone(service.providers['cursor']['data'])
        self.now+=timedelta(minutes=10);service.usage_fetcher.side_effect=None  # a rejected sign-in backs off
        raw=usage();raw['billingCycleEnd']=NOW.isoformat();service.usage_fetcher.return_value=raw
        self.sources.poll(force=True);self.assertEqual(service.providers['cursor']['reason'],'windows_missing')

    def test_cookie_uses_the_user_id_after_the_provider_prefix(self):
        self.login(token(sub='auth0|user_abc'))
        connection=Mock();connection.getresponse.return_value.status=401
        with patch('cursor_source.http.client.HTTPSConnection',return_value=connection),patch('cursor_source.IODeadline'):
            with self.assertRaises(CursorReadError):fetch_usage(self.home,NOW)
        self.assertTrue(connection.request.call_args.kwargs['headers']['Cookie'].startswith('WorkosCursorSessionToken=user_abc%3A%3A'))

    def test_an_expired_cli_login_falls_through_to_the_ide(self):
        self.login(token(exp=(NOW-timedelta(hours=1)).timestamp()))
        with self.assertRaisesRegex(CursorReadError,'cursor_login_expired'):credential(self.home,NOW,platform='linux')
        self.database(token())
        self.assertEqual(credential(self.home,NOW,platform='linux'),token())
