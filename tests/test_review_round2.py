"""Final Opus findings: synthetic quotas, current-run coverage and stable activation."""
import copy,configparser,io,json,os,shlex,socket,sys,threading,time,types
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock,patch
from test_agents_v2 import Reader,row,NOW,detail
from agents_service import AgentsService,DEFAULTS,JOURNAL
from agents_projection import tool_liveness,current_run_covered
from t3_reader import T3Reader,Unavailable
from agent_notifications import APP_ID,ACTION,start_gio,activation_main,stop_notifier
import install_reader

RESET=(NOW+timedelta(days=2)).isoformat()
def window(identity,minutes=10080,**changes):
    return {'id':identity,'windowDurationMins':minutes,'usedPercent':25,'resetsAt':RESET,**changes}
# Fixtures name the Nagi provider kind; T3's real drivers are codex and claudeAgent.
T3_DRIVER={'codex':'codex','claude':'claudeAgent'}
def provider(kind,windows):
    return {'instanceId':kind,'driver':T3_DRIVER[kind],'enabled':True,'installed':True,
            'usageLimits':{'checkedAt':NOW.isoformat(),'windows':windows}}
def bounded(items,*,more=True,cursor='opaque',sequence=1):
    return {'snapshotSequence':sequence,'historyCursor':cursor,'hasMoreHistory':more,
        'projection':{'thread':{'id':'a'},'runs':[{'id':'r','userMessageId':'root','requestedAt':(NOW-timedelta(minutes=25)).isoformat(),'status':'running'}],
                      'turnItems':items,'visibleTurnItems':[]}}
def first_item():
    return {'id':'root','messageId':'root','type':'user_message','runId':'r','status':'completed','startedAt':(NOW-timedelta(minutes=25)).isoformat()}
class Variant:
    def __init__(self,signature,value):self.signature,self.value=signature,value
    def get_string(self):return self.value
    def unpack(self):return self.value

class ReviewRoundTwo(TestCase):
    def setUp(self):
        self.directory=Path(self.enterContext(TemporaryDirectory()));self.now=NOW;self.reader=Reader()
        self.enterContext(patch('agents_service.AgentsService.read_machine',lambda s,a:None))
        self.service=self.new()
    def new(self):return AgentsService(self.directory,lambda _:self.reader,lambda:self.now)
    def poll(self):self.service.poll(force=True);return self.service.agents
    def make_failure(self):
        self.poll();self.reader.rows[0].update(status='failed',latestRunCompletedAt=self.now.isoformat());self.poll()
        return self.service.notifications()[0]

    def test_ids_keep_model_scoped_windows_secondary_and_both_providers_available(self):
        self.reader.providers=[provider('codex',[window('primary',300),window('secondary')]),
            provider('claude',[window('five_hour',300),window('seven_day'),window('seven_day_sonnet',label='Weekly · Sonnet'),
                               window('future_bucket'),window('seven_day'),{'id':'broken'}])]
        self.poll();limits=self.service.providers
        self.assertEqual(limits['codex']['status'],'ok');self.assertEqual(limits['claude']['status'],'ok')
        account=limits['claude']['data']['accounts'][0]
        self.assertEqual([w['id'] for w in account['windows']],['five_hour','seven_day'])
        self.assertEqual(account['secondaryWindows'][0]['id'],'seven_day_sonnet')
        self.assertEqual(account['secondaryWindows'][0]['label'],'Weekly · Sonnet')
        self.assertEqual(set(limits['claude']['warnings']),{'unexpected_window','duplicate_window'})
        self.service=self.new();self.reader.failure=Unavailable;self.poll()
        self.assertEqual(self.service.providers['claude']['status'],'last_known')
        self.assertEqual(self.service.providers['claude']['data']['accounts'][0]['secondaryWindows'][0]['id'],'seven_day_sonnet')

    def test_malformed_provider_never_hides_the_other_provider(self):
        for broken,healthy in (('claude','codex'),('codex','claude')):
            with self.subTest(broken=broken):
                self.service=self.new();good_id='primary' if healthy=='codex' else 'five_hour'
                bad=provider(broken,[]);bad['usageLimits']='bad snapshot'
                self.reader.providers=[bad,provider(healthy,[window(good_id,300)])]
                self.poll();self.assertEqual(self.service.providers[healthy]['status'],'ok')
                self.assertNotEqual(self.service.providers[broken]['status'],'ok')
                self.assertIn('invalid_account',self.service.providers[broken]['warnings'])

    def test_one_invalid_extra_window_does_not_erase_known_windows(self):
        self.reader.providers=[provider('claude',[window('five_hour',300),window('seven_day'),window('seven_day_bad',usedPercent='broken'),window('other',300)])]
        self.poll();source=self.service.providers['claude']
        self.assertEqual(source['status'],'ok');self.assertEqual(len(source['data']['accounts'][0]['windows']),2)
        self.assertEqual(set(source['warnings']),{'invalid_window','unexpected_window'})

    def test_long_thread_current_run_inside_last_ten_turns_can_be_stuck(self):
        self.poll();self.reader.rows[0]['updatedAt']=(NOW-timedelta(minutes=20)).isoformat()
        old=[{'id':str(i),'runId':'old'+str(i),'type':'user_message','status':'completed'} for i in range(9)]
        # Older history (>10 total turns) exists, but the first item of this run is present.
        self.reader.details['a']=bounded(old+[first_item(),{'id':'done','runId':'r','type':'command_execution','status':'completed'}])
        self.poll();agent=self.service.agents['data']['projects'][0]['agents'][0]
        self.assertTrue(agent['stuck']);self.assertEqual(len(self.service.notifications()),1)

    def test_long_thread_current_run_inside_window_with_work_is_not_stuck(self):
        self.poll();self.reader.rows[0]['updatedAt']=(NOW-timedelta(minutes=20)).isoformat()
        self.reader.details['a']=bounded([first_item(),{'id':'work','runId':'r','type':'file_change','status':'running'}])
        self.poll();agent=self.service.agents['data']['projects'][0]['agents'][0]
        self.assertIsNone(agent['stuck']);self.assertEqual(self.service.notifications(),[])

    def test_history_pages_cover_only_current_run_with_encoded_opaque_cursor(self):
        client=object.__new__(T3Reader)
        initial=bounded([{'id':'tail','runId':'r','type':'command_execution','status':'completed'}],cursor='c+=?')
        page={'snapshotSequence':1,'hasMoreHistory':True,'nextCursor':'older',
              'items':[{'sourceThreadId':'a','position':100,'item':first_item()}]}
        client.get=Mock(side_effect=[initial,page])
        evidence=client.liveness('a','r')
        self.assertTrue(current_run_covered(evidence,'r'));self.assertEqual(tool_liveness(evidence,'r'),'inactive')
        self.assertEqual(client.get.call_count,2);self.assertIn('cursor=c%2B%3D%3F',client.get.call_args.args[0])
        self.assertLessEqual(client.get.call_args.kwargs['timeout'],8)

    def test_uncovered_run_stops_at_page_budget_and_sequence_mismatch_is_unknown(self):
        for changed in (False,True):
            client=object.__new__(T3Reader);initial=bounded([{'id':'tail','runId':'r','status':'completed'}])
            pages=[{'snapshotSequence':2 if changed else 1,'hasMoreHistory':True,'nextCursor':'cursor'+str(i),
                    'items':[{'sourceThreadId':'a','position':99-i,'item':{'id':'x'+str(i),'runId':'r','status':'completed'}}]} for i in range(3)]
            client.get=Mock(side_effect=[initial,*pages])
            evidence=client.liveness('a','r')
            self.assertEqual(tool_liveness(evidence,'r'),'unknown')
            self.assertLessEqual(client.get.call_count,4)
            if changed:self.assertIsNone(evidence)

    def test_retaining_run_metadata_alone_does_not_prove_item_coverage(self):
        self.assertFalse(current_run_covered(bounded([{'id':'middle','runId':'r','status':'completed'}]),'r'))
        evidence=bounded([first_item()]);self.assertTrue(current_run_covered(evidence,'r'))
        evidence['projection']['runs'][0]['status']='completed'
        self.assertEqual(tool_liveness(evidence,'r'),'unknown')

    def test_lowering_threshold_alerts_existing_silence_once_even_after_failed_poll(self):
        self.service.save_settings({'endedExpiryHours':24,'stuckMinutes':30});self.poll()
        self.now+=timedelta(minutes=20);self.poll();self.assertEqual(self.service.notifications(),[])
        self.service.save_settings(DEFAULTS);self.reader.failure=Unavailable;self.poll()
        self.reader.failure=None;self.poll();self.assertEqual(len(self.service.notifications()),1)
        self.service=self.new();self.now+=timedelta(minutes=20);self.poll();self.assertEqual(len(self.service.notifications()),1)

    def test_omitted_rows_are_counted_and_never_return_silent_quiet(self):
        self.reader.rows=[row('old','completed',latestRunCompletedAt=(NOW-timedelta(days=3)).isoformat()),
                          {**row('bad'),'updatedAt':(NOW+timedelta(seconds=10)).isoformat()},None]
        result=self.poll();self.assertEqual(result['status'],'ok')
        self.assertEqual(result['data']['omittedRows'],2);self.assertEqual(result['data']['warnings'],['rows_omitted'])
        self.reader.rows=[None];result=self.poll()
        self.assertEqual(result['status'],'ok');self.assertEqual(result['data']['omittedRows'],1)

    def test_failed_without_completion_is_ended_with_qualified_activity_time(self):
        self.poll();self.reader.rows[0]['status']='failed';self.now+=timedelta(seconds=30)
        result=self.poll();ended=result['data']['ended'][0]['agents'][0]
        self.assertEqual(ended['endedAt'],NOW.isoformat());self.assertEqual(ended['endedAtSource'],'updatedAt')
        self.assertEqual(len(self.service.notifications()),1)
        self.reader.rows[0]['latestRunCompletedAt']=self.now.isoformat();self.poll()
        self.assertEqual(len(self.service.notifications()),1)

    def test_clock_step_holds_future_events_and_never_prunes_them(self):
        self.now+=timedelta(seconds=20);event=self.make_failure()
        self.now=NOW;self.service.poll();self.assertEqual(self.service.last_poll,NOW);self.assertEqual(self.service.notifications(),[])
        self.assertEqual(len(self.service.journal()['events']),1);self.assertIsNone(self.service.reserve(event['id']))
        self.service=self.new();self.now=NOW+timedelta(seconds=60)
        self.assertEqual([e['id'] for e in self.service.notifications()],[event['id']])
        self.now+=timedelta(days=1);self.poll();self.assertEqual(self.service.journal()['events'],[])

    def test_stable_action_target_from_old_banner_works_after_restart(self):
        event=self.make_failure();opened=[];glib=Mock();glib.Variant=Variant
        gio=Mock();applications=[Mock(),Mock()];actions=[Mock(),Mock(),Mock(),Mock()]
        for application in applications:application.get_is_remote.return_value=False
        gio.Application.side_effect=applications;gio.SimpleAction.new.side_effect=actions
        glib.idle_add.side_effect=lambda fn:fn()
        with patch('agent_notifications.threading.Thread'):
            _,consumer,_=start_gio(glib,gio,opened.append)
            self.assertTrue(consumer.send(event,Mock()))
            payload=applications[0].get_dbus_connection.return_value.call_sync.call_args.args[4].value[2]
            self.assertEqual(payload['default-action'].value,'app.open-thread')
            start_gio(glib,gio,opened.append)
        actions[2].connect.call_args.args[1](actions[2],payload['default-action-target'])
        self.assertEqual(opened,[event['links']['desktop']])
        self.assertEqual([call.args[0] for call in gio.SimpleAction.new.call_args_list],[ACTION,'open-panel',ACTION,'open-panel'])

    def test_installer_prepares_matching_idempotent_dbus_activation_service(self):
        with TemporaryDirectory(prefix='nagi home ') as temporary:
            home=Path(temporary);install_reader.install('linux',home/'data',47841,sys.executable,home)
            path=home/'.local/share/dbus-1/services'/ (APP_ID+'.service');first=path.read_bytes()
            config=configparser.ConfigParser(interpolation=None);config.read(path)
            self.assertEqual(config['D-BUS Service']['Name'],APP_ID)
            command=shlex.split(config['D-BUS Service']['Exec'])
            self.assertIn('agent_notifications.py',command[2]);self.assertEqual(command[-3:],['--activate','--port','47841'])
            desktop=home/'.local/share/applications'/ (APP_ID+'.desktop')
            self.assertIn('DBusActivatable=true',desktop.read_text())
            install_reader.install('linux',home/'data',47841,sys.executable,home);self.assertEqual(path.read_bytes(),first)

    def test_dbus_entrypoint_exports_action_without_creating_a_tray(self):
        gio=Mock();glib=Mock();gio.Application.return_value.get_is_remote.return_value=False
        gi=types.ModuleType('gi');gi.require_version=Mock();repository=types.ModuleType('gi.repository');repository.Gio=gio;repository.GLib=glib
        with patch.dict(sys.modules,{'gi':gi,'gi.repository':repository}),patch('agent_notifications.threading.Thread'):
            self.assertEqual(activation_main(['--activate','--port','47841']),0)
        self.assertEqual([call.args[0] for call in gio.SimpleAction.new.call_args_list],[ACTION,'open-panel'])
        glib.MainLoop.return_value.run.assert_called_once()

    def test_destroy_without_a_notifier_does_not_remove_an_invalid_source(self):
        glib=Mock();stop_notifier(glib,None);glib.source_remove.assert_not_called()
        stop_notifier(glib,(Mock(),Mock(),19));glib.source_remove.assert_called_once_with(19)
        # Invoke the actual nested widget destroy callback without starting GTK.
        import ast,inspect
        import widget
        tree=ast.parse(inspect.getsource(widget.run))
        callback=next(node.args[1] for node in ast.walk(tree) if isinstance(node,ast.Call)
            and isinstance(node.func,ast.Attribute) and node.func.attr=='connect' and len(node.args)>1
            and isinstance(node.args[0],ast.Constant) and node.args[0].value=='destroy'
            and isinstance(node.args[1],ast.Lambda) and any(isinstance(n,ast.Attribute) and n.attr=='notifier' for n in ast.walk(node.args[1])))
        panel=types.SimpleNamespace(notifier=None);glib.reset_mock()
        fn=eval(compile(ast.Expression(callback),'widget-destroy','eval'),{'self':panel,'GLib':glib,'stop_notifier':stop_notifier})
        fn();glib.source_remove.assert_not_called()
        panel.notifier=(None,None,21);fn();glib.source_remove.assert_called_once_with(21)

    def test_http_total_deadline_covers_trickled_headers_and_body(self):
        for body_mode in (False,True):
            listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1)
            def peer():
                connection,_=listener.accept()
                try:
                    raw=b''
                    while b'\r\n\r\n' not in raw:raw+=connection.recv(4096)
                    if body_mode:
                        connection.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 30\r\n\r\n')
                        payload=b' '*28+b'{}'
                    else:payload=b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}'
                    for byte in payload:connection.sendall(bytes([byte]));time.sleep(.02)
                except OSError:pass
                finally:connection.close()
            worker=threading.Thread(target=peer);worker.start()
            client=object.__new__(T3Reader);client.port=listener.getsockname()[1];client._token='synthetic-only'
            at=time.monotonic()
            try:
                with patch('t3_reader.HTTP_SECONDS',.15):
                    with self.assertRaises(Unavailable):client.get('/fixture')
                self.assertLess(time.monotonic()-at,.7)
            finally:listener.close();worker.join(2)

    def test_connect_consumes_the_same_http_budget_before_credentials(self):
        client=object.__new__(T3Reader);client._token='synthetic-only';connection=Mock();client.connection=lambda:connection
        connection.connect.side_effect=lambda:time.sleep(.12)
        with patch('t3_reader.HTTP_SECONDS',.08):
            with self.assertRaises(Unavailable):client.get('/fixture')
        connection.request.assert_not_called();self.assertEqual(connection.timeout,.08)

    def test_legacy_cache_shapes_do_not_erase_transitions_or_invent_window_ids(self):
        self.reader.providers=[provider('codex',[window('primary',300)])]
        event=self.make_failure();journal=self.service.journal()
        data=journal['cache']['agents']['data'];data.pop('omittedRows');data.pop('warnings')
        for group in data['projects']+data['ended']:
            for agent in group['agents']:agent.pop('endedAtSource')
        quota=journal['cache']['codex']['data']['accounts'][0]['windows'][0];quota.pop('id');quota.pop('label')
        (self.directory/JOURNAL).write_text(json.dumps(journal));(self.directory/JOURNAL).chmod(0o600)
        self.service=self.new();self.reader.failure=Unavailable;result=self.poll()
        self.assertEqual(result['status'],'last_known');self.assertEqual(result['data']['omittedRows'],0)
        self.assertIn('endedAtSource',result['data']['ended'][0]['agents'][0])
        self.assertEqual(self.service.providers['codex']['status'],'unavailable')
        self.assertEqual(self.service.notifications()[0]['id'],event['id']);self.assertEqual(self.service.warnings(),[])
