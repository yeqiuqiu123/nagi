"""No real credentials, real settings or harness startup in this suite."""
import copy
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

from agents_service import AgentsService, outcome
from claude_hook import capture
from claude_hooks import edit, settings
from claude_source import ClaudeReadError, credential, fetch_usage, usage_provider
from source_adapters import ADAPTERS
from sources_service import SourcesService
from sources_transport import SourceError

NOW=datetime(2026,11,13,12,tzinfo=timezone.utc)
TOKEN='synthetic-claude-access-token'


def usage(now=NOW):
    reset=(now+timedelta(days=1)).isoformat()
    return {'five_hour':{'utilization':20.0,'resets_at':reset},
            'seven_day':{'utilization':30,'resets_at':reset},
            'seven_day_fable':{'utilization':40,'resets_at':reset},'seven_day_sonnet':None,
            'extra_usage':{'account_email':'do-not-export@example.invalid'}}


class DirectClaude(TestCase):
    def setUp(self):
        self.home=Path(self.enterContext(TemporaryDirectory()))
        (self.home/'.claude').mkdir(mode=0o700)
        self.directory=self.home/'nagi';self.directory.mkdir(mode=0o700)
        self.now=NOW
        self.legacy=AgentsService(self.directory,clock=lambda:self.now)
        self.legacy.read_machine=lambda _:None
        self.sources=SourcesService(self.legacy,local_home=self.home)
        self.addCleanup(self.sources.close)

    def configure(self):
        return {'configuration':{'adapterId':'claude','label':'This computer','placement':{'kind':'this_computer'},'mode':'direct','options':{}}}

    def connect(self):
        tested=self.sources.test(self.configure(),'owner')
        self.assertIsNotNone(tested['testId'])
        result=self.sources.connect({'testId':tested['testId'],'expectedRevision':0},'owner')
        entry=self.sources.registry()['sources'][0];service=self.sources.service_for(entry)
        service.usage_fetcher=Mock(return_value=usage())
        service.monotonic=lambda:self.now.timestamp()
        return result,service

    def login(self,**override):
        oauth={'accessToken':TOKEN,'expiresAt':int((NOW+timedelta(hours=1)).timestamp()*1000),
               'subscriptionType':'synthetic','rateLimitTier':'synthetic'}|override
        path=self.home/'.claude/.credentials.json'
        path.write_text(json.dumps({'claudeAiOauth':oauth}));path.chmod(0o600)
        return path

    def test_credential_expired_malformed_and_keychain_fallback(self):
        with self.assertRaisesRegex(ClaudeReadError,'claude_login_missing'):credential(self.home,NOW,platform='linux')
        self.login();command=Mock(side_effect=OSError('private error'))
        self.assertEqual(credential(self.home,NOW,platform='darwin',command=command),TOKEN)
        args=command.call_args
        self.assertEqual(args.args[0],['/usr/bin/security','find-generic-password','-s','Claude Code-credentials','-w'])
        self.assertNotIn('NODE_OPTIONS',args.kwargs['env']);self.assertEqual(args.kwargs['seconds'],2)
        command.return_value=json.dumps({'claudeAiOauth':{'accessToken':TOKEN,'expiresAt':NOW.timestamp()*1000+1000}}).encode()
        command.side_effect=None
        self.assertEqual(credential(self.home,NOW,platform='darwin',command=command),TOKEN)
        self.login(expiresAt=0)
        with self.assertRaisesRegex(ClaudeReadError,'claude_login_expired'):credential(self.home,NOW,platform='linux')
        self.login(accessToken='bad\nheader')
        with self.assertRaisesRegex(ClaudeReadError,'claude_login_invalid'):credential(self.home,NOW,platform='linux')
        self.login().write_text('{bad')
        with self.assertRaisesRegex(ClaudeReadError,'claude_login_invalid'):credential(self.home,NOW,platform='linux')

    def test_http_fixed_host_headers_errors_and_no_redirect(self):
        self.login()
        for status,reason in [(401,'claude_login_expired'),(429,'provider_rate_limited'),(500,'provider_unavailable'),(302,'provider_unavailable')]:
            connection=Mock();connection.getresponse.return_value.status=status
            with patch('claude_source.http.client.HTTPSConnection',return_value=connection) as factory,patch('claude_source.IODeadline'):
                with self.assertRaisesRegex(ClaudeReadError,reason) as caught:fetch_usage(self.home,NOW)
                self.assertNotIn(TOKEN,str(caught.exception));factory.assert_called_once_with('api.anthropic.com',timeout=8)
                call=connection.request.call_args
                self.assertEqual(call.args,('GET','/api/oauth/usage'))
                self.assertEqual(call.kwargs['headers']['Authorization'],'Bearer '+TOKEN)
                connection.close.assert_called_once()
        connection=Mock();response=connection.getresponse.return_value;response.status=200;response.read.return_value=json.dumps(usage()).encode()
        with patch('claude_source.http.client.HTTPSConnection',return_value=connection),patch('claude_source.IODeadline'):
            self.assertEqual(fetch_usage(self.home,NOW),usage())

    def test_opt_in_preserves_hooks_and_disconnect_only_removes_owned(self):
        original={'env':{'OTHER':'keep'},'hooks':{'Stop':[{'matcher':'','hooks':[{'type':'command','command':'existing-hook'}]}]}}
        path=self.home/'.claude/settings.json';path.write_text(json.dumps(original))
        self.sources.discover({'adapterIds':['claude'],'placement':{'kind':'this_computer'}},'owner')
        self.sources.test(self.configure(),'owner')
        self.assertEqual(json.loads(path.read_text()),original)
        result,service=self.connect();connected=json.loads(path.read_text())
        self.assertEqual(connected['env'],original['env'])
        self.assertEqual(connected['hooks']['Stop'][0],original['hooks']['Stop'][0])
        backups=list(path.parent.glob('settings.nagi-backup-*'));self.assertTrue(backups)
        self.assertTrue(all(p.stat().st_mode&0o777==0o600 for p in backups))
        self.sources.poll(force=True)
        self.assertNotIn(TOKEN,json.dumps(self.sources.glance('linux')))
        self.sources.disconnect({'sourceId':result['source']['id'],'expectedRevision':1})
        self.assertEqual(json.loads(path.read_text()),original)
        self.assertFalse(service.journal_name in [p.name for p in self.directory.iterdir()])

    def test_unsafe_settings_and_failed_commit_rolls_back_hooks(self):
        target=self.home/'elsewhere';target.write_text('{}')
        (self.home/'.claude/settings.json').symlink_to(target)
        self.assertIsNone(self.sources.test(self.configure(),'owner')['testId'])
        (self.home/'.claude/settings.json').unlink()
        tested=self.sources.test(self.configure(),'owner')
        with patch.object(self.sources,'persist',side_effect=OSError()):
            with self.assertRaises(OSError):self.sources.connect({'testId':tested['testId'],'expectedRevision':0},'owner')
        self.assertEqual(settings(self.home)[2],{})

    def test_poll_floor_backoff_restart_and_windows(self):
        _,service=self.connect()
        self.sources.poll(force=True)
        self.assertEqual(service.providers['claude']['status'],'ok')
        account=service.providers['claude']['data']['accounts'][0]
        self.assertEqual(account['label'],'Claude 1')
        self.assertEqual([w['label'] for w in account['windows']],['Session','Weekly'])
        self.assertEqual(account['secondaryWindows'][0]['label'],'Weekly · Fable')
        for _ in range(3):self.sources.poll(force=True)
        self.assertEqual(service.usage_fetcher.call_count,1)
        self.now+=timedelta(minutes=5)
        service.usage_fetcher.side_effect=ClaudeReadError('provider_rate_limited')
        self.sources.poll(force=True)
        self.assertEqual(service.providers['claude']['reason'],'provider_rate_limited')
        service.claude_result=None
        self.now+=timedelta(minutes=5)
        self.sources.poll(force=True)
        self.assertEqual(service.usage_fetcher.call_count,2)
        self.assertEqual(service.providers['claude']['status'],'unavailable')
        self.now+=timedelta(minutes=5);self.sources.poll(force=True)
        self.assertEqual(service.usage_fetcher.call_count,3)
        for path in self.directory.glob('*.json'):self.assertNotIn(TOKEN,path.read_text())

    def test_disconnect_storage_failure_restores_hooks_and_connection(self):
        result,_=self.connect();path=self.home/'.claude/settings.json'
        before=json.loads(path.read_text())
        with patch.object(self.sources,'persist',side_effect=OSError()):
            with self.assertRaises(OSError):
                self.sources.disconnect({'sourceId':result['source']['id'],'expectedRevision':1})
        self.assertEqual(json.loads(path.read_text()),before)
        self.assertEqual(self.sources.registry()['revision'],1)

    def test_bad_usage_and_expired_login_never_return_cached_percentage(self):
        _,service=self.connect();self.sources.poll(force=True)
        self.now+=timedelta(minutes=5);service.usage_fetcher.side_effect=ClaudeReadError('claude_login_expired')
        self.sources.poll(force=True)
        self.assertEqual(service.providers['claude']['status'],'unavailable');self.assertIsNone(service.providers['claude']['data'])
        for bad in ({'five_hour':{'utilization':True,'resets_at':NOW.isoformat()}}, {'five_hour':{'utilization':float('nan')}}, {'seven_day':[]}):
            with self.assertRaises(ClaudeReadError):usage_provider(bad,NOW.isoformat())

    def test_hook_sink_is_silent_sanitized_bounded_and_discards_t3(self):
        event={'hook_event_name':'UserPromptSubmit','session_id':'s','cwd':'/private/project',
               'prompt':'PRIVATE PROMPT','tool_input':{'secret':TOKEN}}
        sanitized=capture(event,{})
        self.assertNotIn('PRIVATE',json.dumps(sanitized));self.assertNotIn(TOKEN,json.dumps(sanitized))
        self.assertEqual(sanitized['titleSource'],'neutral')
        self.assertIsNone(capture(event,{'CLAUDE_CODE_ENTRYPOINT':'t3-code'}))
        self.assertIsNone(capture(event,{'CLAUDE_CODE_ENTRYPOINT':'sdk-unknown'}))
        self.assertIsNone(capture(event,{'CLAUDE_CODE_ENTRYPOINT':'cli','CLAUDE_AGENT_SDK_VERSION':'synthetic'}))
        for notification,ask in [('idle_prompt',None),('permission_prompt','approval'),
                                 ('elicitation_dialog','question'),('elicitation_response','clear')]:
            captured=capture(dict(event,hook_event_name='Notification',notification_type=notification),{})
            self.assertEqual(captured['askKind'],ask)
        path=Path(__file__).resolve().parents[1]/'claude_hook.py'
        for raw in (json.dumps(event).encode(),b'invalid',b'x'*150000):
            result=subprocess.run([sys.executable,'-I',str(path),str(self.directory),'a'*32],input=raw,capture_output=True,timeout=2,env={'PATH':'/usr/bin:/bin'})
            self.assertEqual((result.returncode,result.stdout,result.stderr),(0,b'',b''))
        output=self.directory/('claude-'+'a'*32+'.jsonl')
        self.assertEqual(output.stat().st_mode&0o777,0o600)
        self.assertNotIn(TOKEN,output.read_text())

    def test_lineage_ask_completion_and_silence(self):
        result,service=self.connect();identity=result['source']['id']
        events=[]
        def event(kind,**kw):
            events.append({'sessionId':'s','agentId':None,'project':'Project','title':'Claude session',
                           'event':kind,'timestamp':self.now.isoformat(),**kw})
        event('UserPromptSubmit');event('SubagentStart',agentId='child',title='Explore')
        event('Notification',asksYou=True)
        path=self.directory/('claude-'+identity+'.jsonl')
        def save():path.write_text(''.join(json.dumps(e)+'\n' for e in events));path.chmod(0o600)
        save();self.sources.poll(force=True)
        data=service.agents['data'];self.assertEqual(data['counts']['running'],2);self.assertEqual(data['counts']['waitingOnYou'],1)
        row=data['projects'][0]['agents'][0];self.assertEqual(row['children'][0]['parentId'],'s');self.assertIsNone(row['stuck']);self.assertEqual(row['links'],{'desktop':None,'web':None})
        event('SubagentStop',agentId='child');event('Stop');save();self.sources.poll(force=True)
        self.assertEqual(service.agents['data']['counts']['ended'],2)
        self.now+=timedelta(seconds=1);event('UserPromptSubmit');save();self.sources.poll(force=True)
        self.now+=timedelta(minutes=16);self.sources.poll(force=True)
        # A quiet session drops out on its own and flags the gap; it never blanks the source.
        self.assertIn(service.agents['status'],('ok','quiet'))
        self.assertEqual(service.agents['data']['counts']['running'],0)
        self.assertIn('stale_source',service.agents['data']['warnings'])

    def test_hook_log_rotation_never_outgrows_the_reader(self):
        from claude_hook import MAX_BYTES, append
        directory=self.home/'sink';directory.mkdir(mode=0o700);source='a'*32
        event={'sessionId':'s','event':'PreToolUse','timestamp':NOW.isoformat(),'pad':'x'*400}
        for _ in range(MAX_BYTES//400*2+50):append(directory,source,event)
        for name in ('claude-'+source+'.jsonl','claude-'+source+'.jsonl.1'):
            self.assertLessEqual((directory/name).stat().st_size,MAX_BYTES)

    def test_disconnect_finds_its_hooks_after_python_moved(self):
        from claude_hooks import ours
        source='b'*32
        self.assertTrue(ours({'type':'command','command':'/old/python3 -I -B /old/app/claude_hook.py /data '+source},source))
        self.assertFalse(ours({'type':'command','command':'/x/claude_hook.py /data '+'c'*32},source))
        self.assertFalse(ours({'type':'command','command':'echo claude_hook.py '+source},source))

    def test_settings_rewrite_keeps_mode_and_few_backups(self):
        path=self.home/'.claude'/'settings.json';path.write_text('{"theme":"dark"}\n');path.chmod(0o644)
        for _ in range(5):
            edit(self.home,self.directory,'d'*32);edit(self.home,self.directory,'d'*32,remove=True)
        self.assertEqual(path.stat().st_mode&0o777,0o644)
        self.assertEqual(json.loads(path.read_text()),{'theme':'dark'})
        self.assertLessEqual(len(list((self.home/'.claude').glob('settings.nagi-backup-*.json'))),3)

    def test_direct_precedence_is_local_fresh_and_falls_back(self):
        result,service=self.connect();self.sources.poll(force=True)
        direct={'source':result['source'],'limits':copy.deepcopy(service.providers),'warnings':[]}
        local={'source':{'harness':'t3','placement':'local'},'limits':copy.deepcopy(service.providers),'warnings':[]}
        remote={'source':{'harness':'t3','placement':'tailscale'},'limits':copy.deepcopy(service.providers),'warnings':[]}
        with patch.object(self.sources,'read_sources',return_value={'sources':[direct,local,remote]}):
            glance=self.sources.glance('linux')
        self.assertEqual(glance['sources'][1]['limits']['claude']['reason'],'preferred_direct_source')
        self.assertEqual(glance['sources'][2]['limits']['claude']['status'],'ok')
        direct['limits']['claude']['status']='unavailable';local['limits']=copy.deepcopy(service.providers)
        with patch.object(self.sources,'read_sources',return_value={'sources':[direct,local]}):
            self.assertEqual(self.sources.glance('linux')['sources'][1]['limits']['claude']['status'],'ok')


class QuietRows(TestCase):
    def test_a_row_asking_the_owner_outlives_the_silence_limit(self):
        from local_sources import native_row, project_rows
        at=(NOW-timedelta(minutes=40)).isoformat()
        asking=native_row('s1','proj','Claude session','claude',at);asking['waitingOnYou']={'question':False,'approval':True,'blocking':True}
        quiet=native_row('s2','proj','Claude session','claude',at)
        data,_,modes=project_rows({'s1':asking,'s2':quiet},'e'*32,NOW,{'endedExpiryHours':24})
        self.assertEqual((modes['s1'],modes['s2']),('active',None))
        self.assertEqual(data['counts']['waitingOnYou'],1)
