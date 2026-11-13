"""Synthetic v2 source, privacy, durability and notification regressions."""
import copy
import io
import json
import os
from pathlib import Path
import socket
import struct
import sys
from tempfile import TemporaryDirectory
from datetime import datetime,timedelta,timezone
from unittest import TestCase
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'linux'))
from agents_projection import project_agents,tool_liveness
from agents_service import AgentsService,DEFAULTS,JOURNAL
from agent_notifications import NotificationConsumer
from nagi_links import thread_links,open_thread
from t3_reader import NotConfigured,Unavailable,Unsupported,T3Reader,OwnerConnection,read_frame,send_frame

NOW=datetime(2026,11,12,12,tzinfo=timezone.utc)
def row(identity='a',state='running',**changes):
    return dict(id=identity,projectId='p',title='Agent '+identity,status=state,updatedAt=NOW.isoformat(),
        latestRunId='r',latestRunStartedAt=NOW.isoformat(),providerInstanceId='c',
        modelSelection={'model':'sol'},**changes)
def detail(items=None):return {'hasMoreHistory':False,'projection':{'turnItems':items or []}}
class Reader:
    def __init__(self):self.rows=[row()];self.providers=[];self.failure=None;self.details={}
    def shell(self):
        if self.failure:raise self.failure()
        return {'environmentId':'local:1'},{'projects':[{'id':'p','title':'Project'}],'threads':copy.deepcopy(self.rows)}
    def config(self):return {'providers':self.providers}
    def detail(self,identity):return self.details.get(identity,detail())
class AgentsV2(TestCase):
    def setUp(self):
        self.directory=Path(self.enterContext(TemporaryDirectory()));self.reader=Reader();self.now=NOW
        self.enterContext(patch('agents_service.AgentsService.read_machine',lambda s,a:setattr(s,'machine',{'status':'unsupported'})))
        self.service=self.new()
    def new(self):return AgentsService(self.directory,lambda _:self.reader,lambda:self.now)
    def poll(self):self.service.poll(force=True);return self.service.agents
    def test_outcomes_quiet_setup_unavailable_unsupported_and_dated_restart_cache(self):
        for failure,status in ((NotConfigured,'not_set_up'),(Unavailable,'unavailable'),(Unsupported,'unsupported')):
            self.reader.failure=failure;self.assertEqual(self.poll()['status'],status)
        self.reader.failure=None;self.reader.rows=[];self.assertEqual(self.poll()['status'],'quiet')
        checked=self.service.agents['checkedAt'];self.now+=timedelta(seconds=30)
        self.service=self.new();self.reader.failure=Unavailable
        cached=self.poll();self.assertEqual(cached['status'],'last_known');self.assertEqual(cached['checkedAt'],checked)
        self.assertNotEqual(cached['attemptedAt'],checked)
    def test_group_parent_context_ended_window_provider_and_no_source_bodies(self):
        self.reader.providers=[{'instanceId':'c','driver':'codex','enabled':False}]
        parent=row('parent','completed',latestRunCompletedAt=(NOW-timedelta(days=2)).isoformat())
        child=row('child',lineage={'parentThreadId':'parent'},prompt='private prompt',messages=['transcript'])
        ended=row('done','interrupted',latestRunCompletedAt=NOW.isoformat())
        self.reader.rows=[parent,child,ended]
        data=self.poll()['data'];root=data['projects'][0]['agents'][0]
        self.assertTrue(root['contextOnly']);self.assertEqual(root['children'][0]['id'],'child')
        self.assertEqual(root['children'][0]['provider'],'codex');self.assertEqual(data['counts']['ended'],1)
        self.assertNotIn('private prompt',json.dumps(data));self.assertNotIn('transcript',json.dumps(data))
        self.assertIn('local%3A1',root['links']['desktop'])
    def test_stuck_silent_tool_waiting_child_and_unknown_are_distinct(self):
        self.reader.rows[0]['updatedAt']=(NOW-timedelta(minutes=16)).isoformat()
        self.assertTrue(self.poll()['data']['projects'][0]['agents'][0]['stuck'])
        self.reader.details['a']=detail([{'runId':'r','type':'command_execution','status':'running'}])
        self.assertIsNone(self.poll()['data']['projects'][0]['agents'][0]['stuck'])
        self.reader.details['a']={'hasMoreHistory':True,'projection':{'turnItems':[]}}
        self.assertIsNone(self.poll()['data']['projects'][0]['agents'][0]['stuck'])
        for key,value,expected in [('pendingRuntimeRequest',{'kind':'user_input'},'waiting_on_you'),('blockedOnThreadWait',True,'child_wait')]:
            self.reader.rows[0][key]=value
            agent=self.poll()['data']['projects'][0]['agents'][0];self.assertFalse(agent['stuck']);self.assertEqual(agent['liveness'],expected)
            self.reader.rows[0].pop(key)
    def test_failure_transition_claim_restart_and_reentry_are_deduplicated(self):
        self.poll();self.reader.rows[0].update(status='failed',latestRunCompletedAt=NOW.isoformat())
        self.poll();events=self.service.notifications();self.assertEqual(len(events),1)
        self.service=self.new();self.poll();self.assertEqual(self.service.notifications(),events)
        lease=self.service.reserve(events[0]['id'])['reservation']
        self.assertIsNotNone(self.service.claim(events[0]['id'],lease));self.assertIsNone(self.new().claim(events[0]['id'],lease))
        self.reader.rows[0]['status']='running';self.poll();self.reader.rows[0]['status']='failed';self.poll()
        self.assertNotEqual(self.service.notifications()[0]['id'],events[0]['id'])
    def test_startup_failed_baseline_source_loss_and_disappearing_rows_never_replay(self):
        self.reader.rows[0].update(status='failed',latestRunCompletedAt=NOW.isoformat());self.poll()
        self.assertEqual(self.service.notifications(),[])
        saved=self.reader.rows;self.reader.rows=[];self.poll();self.reader.rows=saved
        self.reader.failure=Unavailable;self.poll();self.reader.failure=None;self.poll()
        self.assertEqual(self.service.notifications(),[])
    def test_stuck_unknown_recovery_and_settings_do_not_repeat(self):
        self.poll();self.reader.rows[0]['updatedAt']=(NOW-timedelta(minutes=16)).isoformat();self.poll()
        self.assertEqual(len(self.service.notifications()),1)
        self.reader.details['a']=None;self.poll();self.reader.details.clear();self.poll()
        self.assertEqual(len(self.service.notifications()),1)
        self.service.save_settings({'stuckMinutes':5,'endedExpiryHours':48});self.poll()
        self.assertEqual(len(self.service.notifications()),1)
        self.assertEqual(self.new().settings()['endedExpiryHours'],48)
        self.assertEqual((self.directory/'nagi-settings.json').stat().st_mode&0o777,0o600)
        for invalid in ({},dict(DEFAULTS,endedExpiryHours=True),dict(DEFAULTS,stuckMinutes=5.5)):
            with self.assertRaises(ValueError):self.service.save_settings(invalid)
    def test_limits_windows_expiry_stale_last_known_and_unsupported(self):
        provider={'instanceId':'c','driver':'claudeAgent','installed':True,'enabled':True,
            'usageLimits':{'checkedAt':NOW.isoformat(),'windows':[{'id':'five_hour','windowDurationMins':300,'usedPercent':23.5,'resetsAt':(NOW+timedelta(hours=1)).isoformat()}]}}
        self.reader.providers=[provider];self.poll();source=self.service.providers['claude']
        self.assertEqual(source['data']['accounts'][0]['windows'][0]['remainingPercent'],76.5)
        self.assertEqual(self.service.providers['codex']['status'],'not_set_up')
        self.now+=timedelta(minutes=10);self.poll();self.assertEqual(self.service.providers['claude']['status'],'ok')
        self.now+=timedelta(minutes=6);self.poll();self.assertEqual(self.service.providers['claude']['status'],'last_known')
        self.now+=timedelta(minutes=45);self.poll();self.assertEqual(self.service.providers['claude']['status'],'unavailable')
        provider['usageLimits']={'unavailable':{'reason':'unsupported'}};self.poll()
        self.assertEqual(self.service.providers['claude']['status'],'unsupported')
    def test_notification_expiry_and_local_write_failure_are_explicit(self):
        self.poll();self.reader.rows[0].update(status='failed',latestRunCompletedAt=NOW.isoformat());self.poll()
        self.now+=timedelta(days=1);self.assertEqual(self.service.notifications(),[])
        with patch.object(self.service.store,'mutate',side_effect=OSError('disk')):
            with self.assertRaises(OSError):self.poll()
    def test_invalid_rows_are_isolated_and_cycles_reject_the_snapshot(self):
        self.reader.rows=[row('ok'),{**row('bad'),'projectId':'missing'}]
        self.assertEqual(self.poll()['status'],'ok')
        # A cyclic lineage is rejected outright (contract), never silently detached.
        self.reader.rows=[row('x',lineage={'parentThreadId':'y'}),row('y',lineage={'parentThreadId':'x'})]
        agents=self.poll()
        self.assertEqual((agents['status'],agents['reason']),('last_known','cyclic_lineage'))
        self.assertEqual([a['id'] for a in agents['data']['projects'][0]['agents']],['ok'])  # the last good read, dated
        self.service=self.new();self.reader.rows=[row(lineage={'parentThreadId':'a'})]
        fresh=AgentsService(Path(self.enterContext(TemporaryDirectory())),lambda _:self.reader,lambda:self.now)
        fresh.poll(force=True)
        self.assertEqual((fresh.agents['status'],fresh.agents['reason'],fresh.agents['data']),('unavailable','cyclic_lineage',None))
    def test_one_failed_account_keeps_its_line_dated_cache_and_label(self):
        def account(instance,used,checked):
            return {'instanceId':instance,'driver':'codex','installed':True,'enabled':True,'usageLimits':{'checkedAt':checked.isoformat(),
                'windows':[{'id':'primary','windowDurationMins':10080,'usedPercent':used,'resetsAt':(NOW+timedelta(days=2)).isoformat()}]}}
        self.reader.providers=[account('a',100,NOW),account('b',33,NOW)];self.poll()
        self.assertEqual([(a['id'],a['label'],a['status']) for a in self.service.providers['codex']['data']['accounts']],[('a','Codex 1','ok'),('b','Codex 2','ok')])
        # B's probe fails while A succeeds: B keeps its own dated line and the provider says coverage is partial.
        self.reader.providers[1]['usageLimits']={'unavailable':{'reason':'probe_failed'}};self.now+=timedelta(minutes=1);self.poll()
        codex=self.service.providers['codex']
        self.assertEqual(codex['status'],'ok');self.assertIn('account_unavailable',codex['warnings'])
        b=codex['data']['accounts'][1]
        self.assertEqual((b['id'],b['label'],b['status'],b['reason'],b['checkedAt']),('b','Codex 2','last_known','probe_failed',NOW.isoformat()))
        self.assertEqual(b['windows'][0]['remainingPercent'],67)
        # The durable cache still holds B after a restart.
        self.service=self.new();self.now+=timedelta(minutes=1);self.poll()
        self.assertEqual(self.service.providers['codex']['data']['accounts'][1]['status'],'last_known')
        # A fails, B recovers: labels follow the account, not the success order.
        self.reader.providers=[{**account('a',100,self.now),'usageLimits':{'unavailable':{'reason':'probe_failed'}}},account('b',40,self.now)];self.poll()
        self.assertEqual([(a['id'],a['label'],a['status']) for a in self.service.providers['codex']['data']['accounts']],[('a','Codex 1','last_known'),('b','Codex 2','ok')])
    def test_notifier_multiple_consumers_restart_and_os_failure_are_at_most_once(self):
        self.poll();self.reader.rows[0].update(status='failed',latestRunCompletedAt=NOW.isoformat());self.poll()
        class Consumer(NotificationConsumer):
            def request(c,path,body=None):
                if body is None:return {'version':1,'events':[{'sourceId':'legacy-t3','event':e} for e in self.new().notifications()]}
                self.assertEqual(body['sourceId'],'legacy-t3')
                if path.endswith('/reserve'):
                    lease=self.new().reserve(body['id']);return {'version':1,'reserved':lease is not None,'lease':lease}
                event=self.new().claim(body['id'],body['reservation'],release=path.endswith('/release'));return {'claimed':event is not None,'event':event}
        sent=[];clicked=[]
        one=Consumer('local',lambda e,fn:(sent.append((e,fn)) or True),clicked.append)
        one.poll();Consumer('local',Mock(),clicked.append).poll();self.assertEqual(len(sent),1)
        sent[0][1]();self.assertTrue(clicked[0].startswith('t3code://threads/'))
        self.reader.rows[0]['status']='running';self.poll();self.reader.rows[0]['status']='failed';self.poll()
        broken=Mock(side_effect=OSError());Consumer('local',broken,clicked.append).poll()
        self.assertEqual(broken.call_count,1);self.assertEqual(len(self.new().notifications()),1)
    def test_thread_link_canonicalization_fallback_and_rejection(self):
        opened=[];self.assertTrue(open_thread('t3code://threads/e/a%3Ab',opened.append,lambda _:False))
        self.assertEqual(opened,['https://app.t3.codes/threads/e/a%3Ab'])
        for value in ('file:///tmp/x','t3code://threads/e/a?x=1','t3code://threads/e/a\n','t3code://threads/e/a%ZZ','https://evil/threads/e/a'):
            self.assertIsNone(thread_links(value))
    def test_source_transport_rejects_foreign_listener_before_any_credential(self):
        with patch('http.client.HTTPConnection.connect') as connect,patch('t3_reader.peer_uid',return_value=os.getuid()+1),patch('sys.platform','linux'):
            conn=OwnerConnection('127.0.0.1',3773);sock=Mock();conn.sock=sock
            with self.assertRaises(Unavailable):conn.connect()
            sock.sendall.assert_not_called();sock.close.assert_called_once()
    def test_source_policy_requires_private_read_only_scope(self):
        credential=self.directory/'credential';credential.write_text(json.dumps({'token':'synthetic-placeholder','scopes':['orchestration:read']}));credential.chmod(0o600)
        policy=self.directory/'nagi-t3.json';policy.write_text(json.dumps({'version':1,'origin':'http://127.0.0.1:3773','credentialFile':str(credential)}));policy.chmod(0o600)
        self.assertEqual(T3Reader(self.directory).port,3773)
        credential.chmod(0o644)
        with self.assertRaises(ValueError):T3Reader(self.directory)
    def test_websocket_frames_mask_client_payload_and_bound_server_input(self):
        sock=Mock();send_frame(sock,1,b'config');wire=sock.sendall.call_args.args[0]
        self.assertTrue(wire[1]&128);self.assertEqual(bytes(v^wire[2+i%4] for i,v in enumerate(wire[6:])),b'config')
        self.assertEqual(read_frame(io.BytesIO(b'\x81\x02{}')),(1,True,b'{}'))
        for value in (b'\x81\x80',b'\x81\x7f'+struct.pack('!Q',9*1024*1024),b'\x81\x03x'):
            with self.assertRaises(Unavailable):read_frame(io.BytesIO(value))

    def test_websocket_config_exchange_only_emits_read_only_method(self):
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        from threading import Thread
        import hashlib,base64
        captured=[]
        class Fake(BaseHTTPRequestHandler):
            protocol_version='HTTP/1.1'
            def log_message(self,*_):pass
            def do_GET(h):
                captured.append(h.path)
                key=h.headers['Sec-WebSocket-Key']
                accept=base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
                h.send_response(101);h.send_header('Upgrade','websocket');h.send_header('Connection','Upgrade');h.send_header('Sec-WebSocket-Accept',accept);h.end_headers()
                first,second=h.rfile.read(2);size=second&127
                if size==126:size=struct.unpack('!H',h.rfile.read(2))[0]
                mask=h.rfile.read(4);raw=h.rfile.read(size)
                value=json.loads(bytes(v^mask[i%4] for i,v in enumerate(raw)));captured.append(value)
                payload=json.dumps({'_tag':'Exit','requestId':value['id'],'exit':{'_tag':'Success','value':{'providers':[]}}}).encode()
                h.wfile.write(bytes([0x81,len(payload)])+payload);h.wfile.flush();h.close_connection=True
        with ThreadingHTTPServer(('127.0.0.1',0),Fake) as http:
            worker=Thread(target=http.serve_forever);worker.start()
            try:
                client=object.__new__(T3Reader);client.port=http.server_port;client._token='synthetic-transport-fixture'
                self.assertEqual(client.config(),{'providers':[]})
            finally:http.shutdown();worker.join(5)
        self.assertEqual(captured[0],'/ws?orchestrationProtocol=2')
        self.assertEqual(captured[1],{'_tag':'Request','id':'1','tag':'server.getConfig','payload':{},'headers':[]})

    def test_concurrent_journal_claims_have_one_winner(self):
        from concurrent.futures import ThreadPoolExecutor
        self.poll();self.reader.rows[0].update(status='failed',latestRunCompletedAt=NOW.isoformat());self.poll()
        identity=self.service.notifications()[0]['id']
        lease=self.service.reserve(identity)['reservation']
        with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(lambda _:self.new().claim(identity,lease),range(8)))
        self.assertEqual(sum(item is not None for item in results),1)

    def test_malformed_limits_do_not_take_agents_offline(self):
        self.reader.providers=[{'instanceId':'c','driver':'claudeAgent','enabled':True,'installed':True,'usageLimits':{'checkedAt':'bad'}}]
        self.assertEqual(self.poll()['status'],'ok');self.assertEqual(self.service.providers['claude']['status'],'unavailable')

    def test_gio_banner_action_dispatches_closed_thread_link(self):
        from agent_notifications import start_gio
        self.poll();self.reader.rows[0].update(status='failed',latestRunCompletedAt=NOW.isoformat());self.poll()
        event=self.service.notifications()[0]
        gio=Mock();glib=Mock();application=gio.Application.return_value;application.get_is_remote.return_value=False
        glib.idle_add.side_effect=lambda fn:fn();opened=[]
        gio.AppInfo.get_default_for_uri_scheme.return_value=object()
        with patch('agent_notifications.threading.Thread'):
            app,consumer,timer=start_gio(glib,gio,opened.append)
        consumer.send(event,lambda:open_thread(event['links']['desktop'],opened.append))
        self.assertEqual(application.get_dbus_connection.return_value.call_sync.call_args.args[3],'AddNotification')
        action=gio.SimpleAction.new.return_value
        self.assertEqual(action.connect.call_args.args[0],'activate')
        target=Mock();target.get_string.return_value=event['links']['desktop']
        action.connect.call_args_list[0].args[1](action,target)
        self.assertEqual(opened,[event['links']['desktop']])
        self.assertEqual(gio.Application.call_args.kwargs['application_id'],'local.nagi.notifications')

    def test_waiting_tool_and_streaming_evidence_suppress_inactivity_alarm(self):
        self.assertEqual(tool_liveness(detail([{'runId':'r','type':'command_execution','status':'waiting'}]),'r'),'unknown')
        self.assertEqual(tool_liveness(detail([{'runId':'r','type':'reasoning','streaming':True}]),'r'),'unknown')

    def test_deep_agent_trees_survive_strict_journal_readback(self):
        self.reader.rows=[row(str(i),lineage={'parentThreadId':str(i-1) if i else None}) for i in range(30)]
        self.poll();self.service=self.new();self.poll()
        self.assertEqual(self.service.agents['status'],'ok')
        from jsonio import strict_json_loads
        nested='['*30+'0'+']'*30
        with self.assertRaises(ValueError):strict_json_loads(nested,1000)
        self.assertIsInstance(strict_json_loads(nested,1000,max_depth=160),list)

    def test_unavailable_notification_bus_does_not_abort_glance_startup(self):
        from agent_notifications import start_gio
        gio=Mock();gio.DesktopAppInfo.new.return_value=None
        self.assertIsNone(start_gio(Mock(),gio,Mock()))

    def test_settings_default_clamp_validation_and_restart_persistence(self):
        self.assertEqual(self.service.settings_resource(),{'version':2,'settings':DEFAULTS,'defaults':DEFAULTS,'warnings':[]})
        for submitted,expected in [({'endedExpiryHours':-8,'stuckMinutes':0},{'endedExpiryHours':1,'stuckMinutes':5}),
                                   ({'endedExpiryHours':999,'stuckMinutes':999},{'endedExpiryHours':168,'stuckMinutes':120}),
                                   ({'endedExpiryHours':48,'stuckMinutes':20},{'endedExpiryHours':48,'stuckMinutes':20})]:
            expected=dict(expected,limitAlertPercent=10)
            self.assertEqual(self.service.save_settings(submitted),expected)
            self.assertEqual(self.new().settings(),expected)
            self.assertEqual(json.loads((self.directory/'nagi-settings.json').read_text()),expected)
        for submitted in ({'stuckMinutes':15},dict(DEFAULTS,unknown=1),dict(DEFAULTS,stuckMinutes=True),
                          dict(DEFAULTS,endedExpiryHours='24'),dict(DEFAULTS,stuckMinutes=None),dict(DEFAULTS,stuckMinutes=5.5)):
            with self.assertRaises(ValueError):self.service.save_settings(submitted)
        self.assertEqual(self.new().settings(),{'endedExpiryHours':48,'stuckMinutes':20,'limitAlertPercent':10})
        self.assertEqual(self.service.settings_resource()['defaults'],DEFAULTS)
        self.assertEqual((self.directory/'nagi-settings.json').stat().st_mode&0o777,0o600)

    def test_legacy_preference_read_is_compatible_without_automatic_write(self):
        path=self.directory/'nagi-settings.json'
        original=json.dumps({'stuckAfterSeconds':901,'endedWithinHours':48})
        path.write_text(original);path.chmod(0o600)
        self.assertEqual(self.service.settings(),{'stuckMinutes':16,'endedExpiryHours':48,'limitAlertPercent':10})
        self.assertEqual(path.read_text(),original)
        self.service.save_settings(self.service.settings());self.assertEqual(set(json.loads(path.read_text())),set(DEFAULTS))
        with self.assertRaises(ValueError):self.service.save_settings({'stuckAfterSeconds':900,'endedWithinHours':24})

    def test_ended_expiry_applies_on_next_poll_without_restart_or_time_advance(self):
        self.reader.rows=[row('ended','completed',latestRunCompletedAt=(NOW-timedelta(hours=25)).isoformat())]
        self.service.poll();self.assertEqual(self.service.agents['data']['counts']['ended'],0)
        self.service.save_settings({'endedExpiryHours':48,'stuckMinutes':15})
        self.service.poll();self.assertEqual(self.service.agents['data']['counts']['ended'],1)
        self.service.save_settings(DEFAULTS);self.service.poll()
        self.assertEqual(self.service.agents['data']['counts']['ended'],0)

    def test_running_notifier_observes_new_threshold_without_restart(self):
        from agent_notifications import NotificationConsumer
        service=self.service;sent=[]
        class Consumer(NotificationConsumer):
            def request(c,path,body=None):
                service.poll()
                if body is None:return {'version':1,'events':[{'sourceId':'legacy-t3','event':e} for e in service.notifications()]}
                self.assertEqual(body['sourceId'],'legacy-t3')
                if path.endswith('/reserve'):
                    lease=service.reserve(body['id']);return {'version':1,'reserved':lease is not None,'lease':lease}
                event=service.claim(body['id'],body['reservation'],release=path.endswith('/release'));return {'claimed':event is not None,'event':event}
        consumer=Consumer('local',lambda event,clicked:(sent.append(event) or True),Mock())
        self.poll();consumer.poll();self.assertEqual(sent,[])
        self.service.save_settings({'endedExpiryHours':24,'stuckMinutes':5})
        self.service.poll() # Baseline the preference change at the existing activity time.
        self.now+=timedelta(minutes=6);consumer.poll()
        self.assertEqual(self.service.agents['data']['counts']['stuck'],1)
        self.assertEqual([event['kind'] for event in sent],['stuck'])
        consumer.poll();self.assertEqual(len(sent),1)
        self.service.save_settings({'endedExpiryHours':24,'stuckMinutes':30})
        self.service.poll();self.assertEqual(self.service.agents['data']['counts']['stuck'],0)
        consumer.poll();self.assertEqual(len(sent),1)

    def test_ended_expiry_change_does_not_suppress_real_stuck_transition(self):
        self.poll();self.now+=timedelta(minutes=16)
        self.service.save_settings({'endedExpiryHours':48,'stuckMinutes':15})
        self.service.poll();self.assertEqual(len(self.service.notifications()),1)
