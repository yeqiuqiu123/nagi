"""Synthetic sign-ins, fake transport and temporary homes only."""
import base64
import copy
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch
from agents_projection import stamp
from agents_service import AgentsService, DEFAULTS
from codex_source import CodexAdapter, project_rollouts, rollout_files
from codex_usage import (CodexReadError, account_key, codex_home, credential, fetch_usage,
                         limits_outcome, read_limits, unchanged, usage_windows)
from sources_service import SourcesService

ACCOUNT='synthetic-account-id'


def jwt(expires):
    payload=base64.urlsafe_b64encode(json.dumps({'exp':expires,'email':'never-export@example.invalid'}).encode()).decode().rstrip('=')
    return 'eyJhbGciOiJub25lIn0.'+payload+'.synthetic'


def usage(now, used=92):
    return {'account_id':ACCOUNT,'rate_limit':{
        'primary_window':{'used_percent':used,'limit_window_seconds':18000,'reset_at':int((now+timedelta(hours=1)).timestamp())},
        'secondary_window':{'used_percent':30,'limit_window_seconds':604800,'reset_at':int((now+timedelta(days=1)).timestamp())}},
        'additional_rate_limits':[{'private':'ignored'}],'credits':{'private':'ignored'}}


class CodexSignin(TestCase):
    def setUp(self):
        self.home=Path(self.enterContext(TemporaryDirectory()))
        self.root=self.home/'.codex';self.root.mkdir(mode=0o700)
        self.enterContext(patch.dict(os.environ,{'HOME':str(self.home),'CODEX_HOME':str(self.root)}))
        self.now=datetime.now(timezone.utc)+timedelta(seconds=2)
        self.directory=self.home/'nagi';self.directory.mkdir(mode=0o700)
        self.service=AgentsService(self.directory,clock=lambda:self.now,source_id='a'*32)
        self.service.read_machine=lambda _:None
        self.service.policy={'version':2,'home':str(self.home),'usageOptIn':True}
        self.service.monotonic=lambda:self.now.timestamp()
        self.service.codex_usage_fetcher=Mock(side_effect=lambda login,now:usage_windows(usage(now),now))
        self.fallback=Mock(return_value={'status':'unavailable','attemptedAt':self.now.isoformat(),
                                         'checkedAt':None,'reason':'account_unverified','data':None})

    def login(self, account=ACCOUNT, *, expires=None):
        token=jwt(expires if expires is not None else (self.now+timedelta(hours=1)).timestamp())
        value={'tokens':{'access_token':token,'account_id':account,'refresh_token':'never-read-refresh',
                         'id_token':'never-read-id-token'},'last_refresh':(self.now-timedelta(hours=1)).isoformat()}
        path=self.root/'auth.json';path.write_text(json.dumps(value));path.chmod(0o600)
        return path,token

    def read(self):return read_limits(self.service,self.now,self.fallback)

    def test_missing_malformed_expired_and_private_file(self):
        with self.assertRaisesRegex(CodexReadError,'codex_login_missing'):credential(self.home,self.now)
        path,token=self.login(expires=self.now.timestamp())
        with self.assertRaisesRegex(CodexReadError,'codex_login_expired'):credential(self.home,self.now)
        path,token=self.login();self.assertEqual(credential(self.home,self.now).token,token)
        self.assertNotIn(token,repr(credential(self.home,self.now)))
        for raw in ('{bad','{}','{"tokens":null}',json.dumps({'tokens':{'access_token':'bad\nheader','account_id':ACCOUNT},'last_refresh':self.now.isoformat()})):
            path.write_text(raw)
            with self.assertRaisesRegex(CodexReadError,'codex_login_invalid'):credential(self.home,self.now)
        path,_=self.login();path.chmod(0o644)
        with self.assertRaisesRegex(CodexReadError,'codex_login_invalid'):credential(self.home,self.now)

    def test_symlink_fifo_ancestor_foreign_and_oversized_denied(self):
        path,_=self.login();saved=self.root/'saved';path.rename(saved);path.symlink_to(saved)
        with self.assertRaisesRegex(CodexReadError,'codex_login_invalid'):credential(self.home,self.now)
        path.unlink();os.mkfifo(path,0o600)
        with self.assertRaisesRegex(CodexReadError,'codex_login_invalid'):credential(self.home,self.now)
        path.unlink();self.login();alias=self.home/'alias';alias.symlink_to(self.root,target_is_directory=True)
        with patch.dict(os.environ,{'CODEX_HOME':str(alias)}):
            with self.assertRaisesRegex(CodexReadError,'codex_login_invalid'):credential(self.home,self.now)
        with patch('codex_usage.os.getuid',return_value=os.getuid()+1):
            with self.assertRaisesRegex(CodexReadError,'codex_login_invalid'):credential(self.home,self.now)
        path.write_text('x'*(64*1024+1))
        with self.assertRaisesRegex(CodexReadError,'codex_login_invalid'):credential(self.home,self.now)

    def test_override_and_default_share_auth_and_rollout_root(self):
        custom=self.home/'custom';custom.mkdir(mode=0o700)
        with patch.dict(os.environ,{'CODEX_HOME':str(custom)}):
            self.assertEqual(codex_home(self.home),custom)
            (custom/'sessions').mkdir()
            self.assertEqual(rollout_files(self.home,self.now)[0],[])
            with self.assertRaisesRegex(CodexReadError,'codex_login_missing'):credential(self.home,self.now)
        with patch.dict(os.environ,{'CODEX_HOME':''}):self.assertEqual(codex_home(self.home),self.root)
        for value in ('relative','/tmp/../elsewhere'):
            with patch.dict(os.environ,{'CODEX_HOME':value}):
                with self.assertRaisesRegex(CodexReadError,'codex_login_invalid'):credential(self.home,self.now)

    def test_jwt_and_refresh_validation(self):
        path,_=self.login();value=json.loads(path.read_text())
        for expires in (True,'later',None):
            value['tokens']['access_token']=jwt(expires);path.write_text(json.dumps(value))
            with self.assertRaisesRegex(CodexReadError,'codex_login_invalid'):credential(self.home,self.now)
        for account in ('bad\rheader','',None):
            self.login();value=json.loads(path.read_text());value['tokens']['account_id']=account;path.write_text(json.dumps(value))
            with self.assertRaisesRegex(CodexReadError,'codex_login_invalid'):credential(self.home,self.now)
        self.login();value=json.loads(path.read_text());value['last_refresh']='bad';path.write_text(json.dumps(value))
        with self.assertRaisesRegex(CodexReadError,'codex_login_invalid'):credential(self.home,self.now)

    def test_mapping_matches_t3_dto_and_missing_is_not_zero(self):
        windows=usage_windows(usage(self.now),self.now)
        self.assertEqual([(w['id'],w['label'],w['kind'],w['remainingPercent']) for w in windows],
                         [('primary','Session','five_hour',8),('secondary','Weekly','weekly',70)])
        providers=[{'driver':'codex','instanceId':'opaque','installed':True,'enabled':True,'usageLimits':{
            'checkedAt':self.now.isoformat(),'windows':[{'id':key,'label':label,'usedPercent':used,'resetsAt':windows[i]['resetsAt'],
            'windowDurationMins':mins} for i,(key,label,used,mins) in enumerate([('primary','Session',92,300),('secondary','Weekly',30,10080)])]}}]
        t3=self.service.provider_limits('codex',providers,self.now.isoformat(),self.now,{},True,[])
        self.assertEqual(t3['data']['accounts'][0]['windows'],windows)
        self.assertEqual(usage_windows({'rate_limit':None},self.now),[])
        for bad in ({},{'rate_limit':[]},{'rate_limit':{'primary_window':{}}}):
            with self.assertRaisesRegex(CodexReadError,'invalid_usage'):usage_windows(bad,self.now)
        for used in (True,-1,101,float('nan')):
            value=usage(self.now);value['rate_limit']['primary_window']['used_percent']=used
            with self.assertRaisesRegex(CodexReadError,'invalid_usage'):usage_windows(value,self.now)
        value=usage(self.now);value['rate_limit']['primary_window']['reset_at']=1
        self.assertEqual(len(usage_windows(value,self.now)),1)

    def test_http_fixed_destination_auth_and_closed_failures(self):
        _,token=self.login();login=credential(self.home,self.now)
        for status,reason in [(401,'codex_login_expired'),(429,'provider_rate_limited'),(503,'provider_unavailable'),(302,'provider_unavailable')]:
            connection=Mock();connection.getresponse.return_value.status=status
            with patch('codex_usage.http.client.HTTPSConnection',return_value=connection) as factory,patch('codex_usage.IODeadline'):
                with self.assertRaisesRegex(CodexReadError,reason) as error:fetch_usage(login,self.now)
                self.assertNotIn(token,str(error.exception));factory.assert_called_once_with('chatgpt.com',timeout=8)
                self.assertEqual(connection.request.call_args.args,('GET','/backend-api/wham/usage'))
                headers=connection.request.call_args.kwargs['headers']
                self.assertEqual(headers['Authorization'],'Bearer '+token);self.assertEqual(headers['ChatGPT-Account-Id'],ACCOUNT)
                connection.close.assert_called_once()
        connection=Mock();connection.getresponse.return_value.status=200
        connection.getresponse.return_value.read.return_value=json.dumps(usage(self.now)).encode()
        with patch('codex_usage.http.client.HTTPSConnection',return_value=connection),patch('codex_usage.IODeadline'):
            self.assertEqual(fetch_usage(login,self.now),usage_windows(usage(self.now),self.now))
            for body,reason in [(b'{bad','invalid_usage'),(json.dumps(usage(self.now)|{'account_id':'different'}).encode(),'codex_account_changed'),(b'x'*(128*1024+1),'invalid_usage')]:
                connection.getresponse.return_value.read.return_value=body
                with self.assertRaisesRegex(CodexReadError,reason):fetch_usage(login,self.now)
        connection=Mock();connection.connect.side_effect=OSError(token)
        with patch('codex_usage.http.client.HTTPSConnection',return_value=connection),patch('codex_usage.IODeadline'):
            with self.assertRaisesRegex(CodexReadError,'provider_unavailable') as error:fetch_usage(login,self.now)
            self.assertNotIn(token,str(error.exception))

    def test_poll_floor_force_restart_backoff_and_expiry(self):
        self.login();first=self.read();self.assertEqual(first['status'],'ok')
        self.read();self.service.codex_usage_fetcher.assert_called_once()
        self.assertEqual(self.service.journal()['codexPoll']['reason'],None)
        self.service.mutate_journal(lambda state:state.update(cache={'codex':first}))
        del self.service.codex_result
        self.assertEqual(self.read(),first)
        self.now+=timedelta(seconds=300)
        self.service.codex_usage_fetcher.side_effect=CodexReadError('provider_rate_limited')
        self.assertEqual(self.read()['reason'],'account_unverified');self.fallback.assert_called_once()
        poll=self.service.journal()['codexPoll'];self.assertEqual(stamp(poll['nextAt']),self.now+timedelta(seconds=600))
        self.now+=timedelta(seconds=300);self.read();self.assertEqual(self.service.codex_usage_fetcher.call_count,2)
        self.now+=timedelta(seconds=300);self.read()
        self.assertEqual(stamp(self.service.journal()['codexPoll']['nextAt']),self.now+timedelta(seconds=1200))
        self.login(expires=self.now.timestamp());self.assertEqual(self.read()['reason'],'codex_login_expired')

    def test_401_and_invalid_usage_never_fallback(self):
        self.login()
        for reason in ('codex_login_expired','invalid_usage'):
            self.service.codex_usage_fetcher.side_effect=CodexReadError(reason)
            self.assertEqual(self.read()['reason'],reason);self.fallback.assert_not_called()
            self.now+=timedelta(seconds=300)

    def test_salt_stability_separate_install_and_account_change_no_cache(self):
        self.login();first=self.read();key=first['data']['accounts'][0]['id']
        self.assertEqual(key,account_key(self.service.store,ACCOUNT));self.assertNotIn(ACCOUNT,key)
        other=AgentsService(self.home/'other',clock=lambda:self.now)
        self.assertNotEqual(key,account_key(other.store,ACCOUNT))
        self.service.mutate_journal(lambda state:state.update(cache={'codex':first}))
        self.login('second-account');result=self.read()
        self.assertEqual(result['reason'],'codex_account_changed');self.assertIsNone(result['data'])
        self.assertNotIn('codex',self.service.journal()['cache']);self.service.codex_usage_fetcher.assert_called_once()
        self.now+=timedelta(seconds=300);second=self.read()
        self.assertNotEqual(key,second['data']['accounts'][0]['id']);self.assertEqual(second['data']['accounts'][0]['label'],'Codex 1')

    def test_midstream_change_discards_result_and_retires_identity(self):
        self.login();login=credential(self.home,self.now)
        def change(*_):
            self.login('second-account')
            return usage_windows(usage(self.now),self.now)
        self.service.codex_usage_fetcher.side_effect=change
        result=self.read();self.assertEqual(result['reason'],'codex_account_changed')
        self.assertFalse(unchanged(login));self.assertIsNone(self.service.codex_account_key)
        self.fallback.assert_not_called();self.assertIsNone(result['data'])

    def test_fallback_newer_than_change_and_midstream_change_denied(self):
        self.login();login=credential(self.home,self.now);key=account_key(self.service.store,ACCOUNT)
        day=self.root/'sessions'/self.now.strftime('%Y/%m/%d');day.mkdir(parents=True)
        path=day/'rollout-test.jsonl'
        def write(at,started=None):
            path.write_text(json.dumps({'type':'session_meta','payload':{'id':'s','originator':'codex_cli_rs','source':'cli',
                                        'timestamp':(started or at).isoformat()}})+'\n'+json.dumps({
                'type':'event_msg','timestamp':at.isoformat(),'payload':{'type':'token_count','rate_limits':{
                    'primary':{'used_percent':92,'window_minutes':300,'resets_at':(self.now+timedelta(hours=1)).timestamp()}}}})+'\n')
        def fallback(identity,changed,account):
            return project_rollouts([path],'source',self.now,DEFAULTS,signed_in=(identity,changed,account))[3]
        self.service.codex_usage_fetcher.side_effect=CodexReadError('provider_unavailable')
        write(datetime.fromtimestamp(login.changed_at,timezone.utc)-timedelta(seconds=1))
        self.assertEqual(read_limits(self.service,self.now,fallback)['reason'],'account_unverified')
        write(self.now)
        result=read_limits(self.service,self.now,fallback)
        self.assertEqual(result['status'],'ok');self.assertEqual(result['data']['accounts'][0]['id'],key)
        self.assertEqual(result['data']['accounts'][0]['windows'][0]['id'],'primary')
        self.assertIn('provider_unavailable',result['warnings'])
        # A session already running before the sign-in changed may still hold the old token.
        write(self.now,started=datetime.fromtimestamp(login.changed_at,timezone.utc)-timedelta(seconds=1))
        self.assertEqual(read_limits(self.service,self.now,fallback)['reason'],'account_unverified')
        write(self.now)
        def changed(*args):
            result=fallback(*args);self.login('other');return result
        self.assertEqual(read_limits(self.service,self.now,changed)['reason'],'codex_account_changed')

    def test_opt_in_discovery_test_no_auth_read_and_no_sessions_required(self):
        self.login();sources=SourcesService(self.service,local_home=self.home);self.addCleanup(sources.close)
        config={'configuration':{'adapterId':'codex','label':'This computer','placement':{'kind':'this_computer'},'mode':'rollouts','options':{}}}
        with patch('codex_usage.credential',side_effect=AssertionError('credential read before connect')) as read:
            sources.discover({'adapterIds':['codex'],'placement':{'kind':'this_computer'}},'owner')
            tested=sources.test(config,'owner');read.assert_not_called()
        self.assertIn('codex_usage_opt_in',tested['requirements'])
        self.assertIsNotNone(tested['testId'])
        connected=sources.connect({'testId':tested['testId'],'expectedRevision':0},'owner')
        entry=sources.registry()['sources'][0];self.assertEqual(entry['policy']['usageOptIn'],True)
        passive=CodexAdapter().configure({'version':1,'home':str(self.home)})
        self.service.policy=passive
        with patch('codex_usage.credential') as read:
            self.assertEqual(self.read()['reason'],'codex_usage_opt_in');read.assert_not_called()

    def test_token_and_account_never_in_written_state_or_dto(self):
        path,token=self.login();before=path.read_bytes();self.read()
        for file in self.directory.rglob('*'):
            if file.is_file():
                raw=file.read_bytes()
                for forbidden in (token,ACCOUNT,'never-read-refresh','never-read-id-token','never-export@example.invalid'):
                    self.assertNotIn(forbidden.encode(),raw)
        self.assertEqual(path.read_bytes(),before)
        self.assertEqual((self.directory/'nagi-codex-identity.json').stat().st_mode&0o777,0o600)
        self.assertNotIn(token,json.dumps(self.read()))


    def test_api_fallback_and_restart_alert_once_per_reset(self):
        self.login();self.service.adapter_id='codex'
        self.service.poll(force=True);self.service.record_limit_alerts(DEFAULTS)
        event=self.service.notifications(include_limits=True)[0]
        lease=self.service.reserve(event['id'],include_limits=True)
        self.service.claim(event['id'],lease['reservation'],include_limits=True)
        first=copy.deepcopy(self.service.providers['codex'])
        self.now+=timedelta(seconds=300)
        # Rollout fallback uses the exact account/window ids as API results.
        windows=copy.deepcopy(first['data']['accounts'][0]['windows'])
        for window in windows:window['checkedAt']=self.now.isoformat()
        fallback=limits_outcome(windows,first['data']['accounts'][0]['id'],self.now)
        self.service.codex_usage_fetcher.side_effect=CodexReadError('provider_unavailable')
        with patch('codex_source.project_rollouts',return_value=({}, {}, {}, fallback)):
            self.service.poll(force=True);self.service.record_limit_alerts(DEFAULTS)
        self.assertEqual(self.service.notifications(include_limits=True),[])
        self.assertEqual(len(self.service.journal()['limitAlerts']),1)
        restarted=AgentsService(self.directory,clock=lambda:self.now,source_id='a'*32)
        restarted.adapter_id='codex';restarted.policy=dict(self.service.policy);restarted.read_machine=lambda _:None
        restarted.monotonic=lambda:self.now.timestamp();restarted.codex_usage_fetcher=Mock(side_effect=AssertionError('backoff bypass'))
        with patch('codex_source.project_rollouts',return_value=({}, {}, {}, fallback)):
            restarted.poll(force=True);restarted.record_limit_alerts(DEFAULTS)
        restarted.codex_usage_fetcher.assert_not_called()
        self.assertEqual(restarted.notifications(include_limits=True),[])

    def test_cross_source_alert_election_and_both_lines_retained(self):
        self.login();first=self.read();self.service.providers={'codex':first}
        window=first['data']['accounts'][0]['windows'][0]
        key=first['data']['accounts'][0]['id']
        self.service.limit_observations={('codex',key,window['id'],window['checkedAt'])}
        self.service.record_limit_alerts(DEFAULTS)
        event=self.service.notifications(include_limits=True)[0]
        sources=SourcesService(self.service,local_home=self.home);self.addCleanup(sources.close)
        local={'id':'legacy-t3','harness':'t3','placement':'local'}
        direct={'id':'a'*32,'harness':'codex','placement':'this_computer','policy':{'usageOptIn':True}}
        remote={'id':'b'*32,'harness':'t3','placement':'tailscale'}
        # A local T3 sees every Codex account it runs, so it keeps Codex alerts and the direct source stays quiet.
        with patch.object(sources,'registry',return_value={'sources':[local,direct]}),patch.object(sources,'service_for',return_value=self.service):
            self.assertTrue(sources.limit_alert_allowed(local,event))
            self.assertFalse(sources.limit_alert_allowed(direct,event))
            self.service.record_limit_alerts=Mock();self.service.poll=Mock()
            sources._read_source(local,self.service,True)
            self.assertNotIn('codex',self.service.record_limit_alerts.call_args.kwargs['suppressed'])
            sources._read_source(direct,self.service,True)
            self.assertIn('codex',self.service.record_limit_alerts.call_args.kwargs['suppressed'])
        del self.service.record_limit_alerts,self.service.poll
        # Without a local T3 the direct source owns its account's alerts; remote T3 keeps its own.
        with patch.object(sources,'registry',return_value={'sources':[direct,remote]}),patch.object(sources,'service_for',return_value=self.service):
            self.assertTrue(sources.limit_alert_allowed(direct,event))
            self.assertTrue(sources.limit_alert_allowed(remote,event))
            self.service.codex_account_key='different'
            self.assertFalse(sources.limit_alert_allowed(direct,event))
        # No email/title join: even fresh direct cannot hide an unrelated T3 line.
        first['status']='ok'
        limits={'codex':first,'claude':{'status':'unsupported','data':None}}
        envelope={'sources':[{'source':local,'limits':copy.deepcopy(limits),'warnings':[]},
                             {'source':direct,'limits':copy.deepcopy(limits),'warnings':[]}]}
        with patch.object(sources,'read_sources',return_value=envelope):
            glance=sources.glance('linux')
            self.assertEqual(len(glance['sources']),2)
            self.assertEqual(glance['sources'][0]['limits']['codex']['data'],first['data'])

    def test_account_change_retires_pending_low_alert(self):
        self.login();first=self.read();self.service.providers={'codex':first}
        window=first['data']['accounts'][0]['windows'][0];key=first['data']['accounts'][0]['id']
        self.service.limit_observations={('codex',key,window['id'],window['checkedAt'])}
        self.service.record_limit_alerts(DEFAULTS)
        self.assertEqual(len(self.service.notifications(include_limits=True)),1)
        self.login('second-account');self.read()
        self.assertEqual(self.service.notifications(include_limits=True),[])
        self.login(expires=self.now.timestamp());self.read()
        self.assertEqual(self.service.notifications(include_limits=True),[])

    def test_a_refresh_for_the_same_account_keeps_its_pending_alert(self):
        self.login();first=self.read();self.service.providers={'codex':first}
        window=first['data']['accounts'][0]['windows'][0];key=first['data']['accounts'][0]['id']
        self.service.limit_observations={('codex',key,window['id'],window['checkedAt'])}
        self.service.record_limit_alerts(DEFAULTS)
        self.assertEqual(len(self.service.notifications(include_limits=True)),1)
        # Codex refreshes: auth.json is rewritten (new token, new stat) for the same account.
        os.utime(self.root/'auth.json',(0,0));self.login()
        self.now+=timedelta(seconds=20)
        self.assertNotEqual(self.read()['reason'],'codex_account_changed')
        self.assertEqual(len(self.service.notifications(include_limits=True)),1)
        self.login('other-account');self.now+=timedelta(seconds=20)
        self.assertEqual(self.read()['reason'],'codex_account_changed')
        self.assertEqual(len(self.service.notifications(include_limits=True)),0)

    def test_a_failing_t3_never_silences_codex_and_a_handover_never_repeats(self):
        self.login();first=self.read();self.service.providers={'codex':first}
        window=first['data']['accounts'][0]['windows'][0];key=first['data']['accounts'][0]['id']
        self.service.limit_observations={('codex',key,window['id'],window['checkedAt'])}
        self.service.record_limit_alerts(DEFAULTS)
        event=self.service.notifications(include_limits=True)[0]
        sources=SourcesService(self.service,local_home=self.home);self.addCleanup(sources.close)
        local={'id':'legacy-t3','harness':'t3','placement':'local'}
        direct={'id':'a'*32,'harness':'codex','placement':'this_computer','policy':{'usageOptIn':True}}
        failing=Mock();failing.providers={'codex':{'status':'unavailable','checkedAt':None,'data':None}}
        failing.journal.return_value={'events':[]}
        services={'legacy-t3':failing,'a'*32:self.service}
        with patch.object(sources,'registry',return_value={'sources':[local,direct]}),patch.object(sources,'service_for',side_effect=lambda e:services[e['id']]):
            # T3 is connected but not reading Codex: the direct source still alerts.
            self.assertTrue(sources.limit_alert_allowed(direct,event))
            # T3 recovers after the direct source delivered: T3 doesn't alert that window again.
            self.service.mutate_journal(lambda state:[e.update(claimed=True) for e in state['events']])
            healthy=Mock();healthy.providers={'codex':copy.deepcopy(first)};healthy.journal.return_value={'events':[]}
            services['legacy-t3']=healthy
            self.assertFalse(sources.limit_alert_allowed(local,dict(event,id='f'*64)))
