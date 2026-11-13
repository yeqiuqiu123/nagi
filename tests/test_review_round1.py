"""Direct regressions for the fresh Opus round-one findings; synthetic metadata only."""
import io,json,os,sys,time,threading,copy
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import timedelta
from unittest import TestCase
from unittest.mock import Mock,patch
from test_agents_v2 import Reader,row,NOW,detail
from agents_service import AgentsService,DEFAULTS,JOURNAL
from agents_projection import TOOLS,tool_liveness
from nagi_links import thread_links
from t3_reader import T3Reader,Unavailable,read_frame
from agent_notifications import NotificationConsumer,APP_ID,start_gio
import install_reader
import server

class ReviewRoundOne(TestCase):
    def setUp(self):
        self.directory=Path(self.enterContext(TemporaryDirectory()));self.now=NOW;self.reader=Reader()
        self.enterContext(patch('agents_service.AgentsService.read_machine',lambda s,a:None))
        self.service=self.new()
    def new(self):return AgentsService(self.directory,lambda _:self.reader,lambda:self.now)
    def poll(self):self.service.poll(force=True)
    def make_failure(self):
        self.poll();self.reader.rows[0].update(status='failed',latestRunCompletedAt=self.now.isoformat());self.poll()
        return self.service.notifications()[0]
    def consumer(self,send):
        service=self.service
        class Consumer(NotificationConsumer):
            def request(c,path,body=None):
                if body is None:return {'version':1,'events':[{'sourceId':'legacy-t3','event':e} for e in service.notifications()]}
                self.assertEqual(body['sourceId'],'legacy-t3')
                if path.endswith('/reserve'):
                    lease=service.reserve(body['id']);return {'version':1,'reserved':lease is not None,'lease':lease}
                event=service.claim(body['id'],body['reservation'],release=path.endswith('/release'))
                return {'claimed':event is not None,'event':event}
        return Consumer('local',send,Mock())

    def test_stable_application_id_matches_idempotently_installed_desktop_entry(self):
        self.assertEqual(APP_ID,'local.nagi.notifications')
        with TemporaryDirectory() as temporary:
            home=Path(temporary)
            install_reader.install('linux',home/'data',47841,sys.executable,home)
            desktop=home/'.local/share/applications'/ (APP_ID+'.desktop')
            first=desktop.read_bytes();self.assertIn(b'X-GNOME-UsesNotifications=true',first)
            self.assertIn(b'linux/tray.py',first);self.assertIn(b'47841',first)
            install_reader.install('linux',home/'data',47841,sys.executable,home)
            self.assertEqual(desktop.read_bytes(),first)

    def test_failed_send_keeps_pending_and_success_is_claimed_after_ack(self):
        event=self.make_failure();order=[]
        def send(item,clicked):order.append('send');return len(order)>1
        consumer=self.consumer(send);request=consumer.request
        def observed(path,body=None):
            if path.endswith('/claim'):order.append('claim')
            return request(path,body)
        consumer.request=observed
        consumer.poll();self.assertEqual(len(self.service.notifications()),1)
        self.assertEqual(order,['send'])
        consumer.poll();self.assertEqual(order,['send','send','claim']);self.assertEqual(self.new().notifications(),[])
        consumer.poll();self.assertEqual(order,['send','send','claim'])

    def test_reservations_prevent_concurrent_sends_and_expire_after_restart(self):
        event=self.make_failure();lease=self.service.reserve(event['id']);self.assertIsNone(self.new().reserve(event['id']))
        sent=Mock(return_value=True);self.consumer(sent).poll();sent.assert_not_called()
        self.assertIsNone(self.service.claim(event['id'],'x'*43))
        self.now+=timedelta(seconds=31);self.assertIsNone(self.service.claim(event['id'],lease['reservation']))
        self.assertEqual(len(self.new().notifications()),1)
        self.consumer(sent).poll();sent.assert_called_once();self.assertEqual(self.new().notifications(),[])

    def test_gnome_rejection_is_observed_and_missing_desktop_does_not_send(self):
        self.make_failure();event=self.service.notifications()[0]
        gio=Mock();glib=Mock();application=gio.Application.return_value;application.get_is_remote.return_value=False
        bus=application.get_dbus_connection.return_value;glib.idle_add.side_effect=lambda fn:fn()
        def reply(*args):
            if args[3]=='AddNotification':raise OSError('InvalidApp')
        bus.call_sync.side_effect=reply
        with patch('agent_notifications.threading.Thread'):
            app,consumer,timer=start_gio(glib,gio,Mock())
        self.assertFalse(consumer.send(event,Mock()))
        self.consumer(consumer.send).poll();self.assertEqual(len(self.service.notifications()),1)
        bus.call_sync.side_effect=None;self.consumer(consumer.send).poll()
        self.assertEqual(self.service.notifications(),[])
        self.assertEqual(gio.Application.call_args.kwargs['application_id'],APP_ID)
        gio.DesktopAppInfo.new.return_value=None
        self.assertIsNone(start_gio(glib,gio,Mock()))
        # Real PyGObject raises when the desktop entry is not installed.
        gio.DesktopAppInfo.new.side_effect=TypeError('constructor returned NULL')
        self.assertIsNone(start_gio(glib,gio,Mock()))

    def test_all_t3_work_items_and_unknown_active_items_suppress_stuck(self):
        self.assertEqual(TOOLS,{'command_execution','dynamic_tool','subagent','file_change','file_search','web_search','compaction'})
        self.poll();self.now+=timedelta(minutes=16)
        for kind in TOOLS|{'future_work_type'}:
            for state in ('running','waiting'):
                with self.subTest(kind=kind,state=state):
                    self.reader.details['a']=detail([{'runId':'r','type':kind,'status':state,'completedAt':None}])
                    self.poll();agent=self.service.agents['data']['projects'][0]['agents'][0]
                    self.assertIsNone(agent['stuck']);self.assertEqual(agent['liveness'],'unknown');self.assertEqual(self.service.notifications(),[])

    def test_display_text_normalization_and_bad_row_isolation_preserve_transitions(self):
        self.reader.rows=[row('good'),row('long'),row('empty'),{**row('orphan'),'projectId':'missing'},None]
        self.reader.rows[1]['title']='x'*300+'\u202e\u2028\u2029';self.reader.rows[1]['modelSelection']['model']='m'*500
        self.reader.rows[2]['title']='\u202e\u2028\u2029'
        self.poll();self.assertEqual(self.service.agents['status'],'ok')
        agents={a['id']:a for a in self.service.agents['data']['projects'][0]['agents']}
        self.assertEqual(len(agents),3);self.assertEqual(agents['empty']['title'],'Untitled thread')
        self.assertEqual(len(agents['long']['title']),180);self.assertTrue(agents['long']['title'].endswith('…'))
        self.assertEqual(len(agents['long']['model']),120)
        self.reader.rows[0].update(status='failed',latestRunCompletedAt=NOW.isoformat());self.poll()
        self.assertEqual(len(self.service.notifications()),1)

    def test_shell_uses_server_older_settled_omission(self):
        client=object.__new__(T3Reader);client.get=Mock(side_effect=[{'orchestrationProtocolVersion':2},{}])
        client.shell();self.assertIn('omitOlderSettled=1',client.get.call_args.args[0])

    def test_deep_json_and_decoder_recursion_are_unavailable(self):
        client=object.__new__(T3Reader);client._token='synthetic-only'
        connection=Mock();connection.getresponse.return_value.status=200
        connection.getresponse.return_value.read.return_value=b'['*100000+b']'*100000
        client.connection=lambda:connection
        with self.assertRaises(Unavailable):client.get('/fixture')
        with patch('t3_reader.strict_json_loads',side_effect=RecursionError()):
            with self.assertRaises(Unavailable):client.get('/fixture')
        self.reader.shell=Mock(side_effect=RecursionError());self.poll()
        self.assertEqual(self.service.agents['status'],'unavailable')

    def test_refresh_survives_arbitrary_exceptions(self):
        service=Mock();service.poll.side_effect=[RecursionError(),RuntimeError(),None]
        stop=Mock();stop.is_set.side_effect=[False,False,False,True]
        server.refresh_loop(service,stop);self.assertEqual(service.poll.call_count,3)

    def test_total_websocket_read_deadline_bounds_trickled_frame(self):
        clock=[0.0]
        class Trickle(io.BytesIO):
            def read1(self,n=-1):clock[0]+=.2;return super().read(1)
        with patch('t3_reader.time.monotonic',side_effect=lambda:clock[0]):
            with self.assertRaises(Unavailable):read_frame(Trickle(b'\x81\x10'+b'x'*16),deadline=.5,sock=Mock())
        self.assertLess(clock[0],1)

    def test_delayed_failure_completion_and_small_clock_skew_are_not_lost(self):
        for delay in (None,1,5):
            with self.subTest(delay=delay):
                with TemporaryDirectory() as temporary:
                    self.directory=Path(temporary);self.service=self.new();self.reader=Reader();self.poll()
                    self.reader.rows[0]['status']='failed'
                    if delay is not None:self.reader.rows[0]['latestRunCompletedAt']=(self.now+timedelta(seconds=delay)).isoformat()
                    self.poll()
                    if delay is None:
                        self.assertEqual(len(self.service.notifications()),1)
                        self.reader.rows[0]['latestRunCompletedAt']=self.now.isoformat()
                    self.now+=timedelta(seconds=30);self.poll();self.assertEqual(len(self.service.notifications()),1)
                    self.poll();self.assertEqual(len(self.service.notifications()),1)

    def test_threshold_changes_never_repeat_the_same_silence_across_restart(self):
        self.poll();self.now+=timedelta(minutes=16);self.poll();self.assertEqual(len(self.service.notifications()),1)
        self.service.save_settings({'endedExpiryHours':24,'stuckMinutes':30});self.poll()
        self.service=self.new();self.now+=timedelta(minutes=15);self.poll()
        self.assertEqual(len(self.service.notifications()),1)
        self.reader.rows[0]['updatedAt']=self.now.isoformat();self.poll()
        self.now+=timedelta(minutes=31);self.poll();self.assertEqual(len(self.service.notifications()),2)

    def test_bad_settings_and_journal_fall_back_and_valid_save_repairs(self):
        settings=self.directory/'nagi-settings.json';settings.write_text(json.dumps({'endedExpiryHours':48,'stuckMinutes':5}));settings.chmod(0o644)
        journal=self.directory/JOURNAL;journal.write_text('broken json');journal.chmod(0o600)
        resource=self.service.settings_resource();self.assertEqual(resource['settings'],DEFAULTS)
        self.assertEqual(resource['warnings'],['settings_invalid','journal_reset'])
        self.poll();self.assertEqual(self.service.agents['status'],'ok')
        self.service.save_settings({'endedExpiryHours':36,'stuckMinutes':20})
        self.assertEqual(self.service.settings_resource()['warnings'],[])
        self.assertEqual(settings.stat().st_mode&0o777,0o600);self.assertIsInstance(json.loads(journal.read_text()),dict)
        settings.write_text('[]');settings.chmod(0o600)
        self.service.save_settings(DEFAULTS);self.assertEqual(self.service.settings(),DEFAULTS)

    def test_conditions_for_threads_gone_seven_days_are_pruned(self):
        self.poll();self.reader.rows=[row('b')];self.now+=timedelta(days=6);self.poll()
        self.assertEqual(len(self.service.journal()['conditions']),2)
        self.now+=timedelta(days=2);self.reader.rows[0]['updatedAt']=self.now.isoformat();self.poll()
        keys=self.service.journal()['conditions'];self.assertEqual(list(keys),['local:1:b'])

    def test_network_read_does_not_block_settings_and_stale_poll_is_discarded(self):
        started=threading.Event();release=threading.Event();original=self.reader.shell
        def blocked():started.set();release.wait(3);return original()
        self.reader.shell=blocked
        worker=threading.Thread(target=self.service.poll);worker.start()
        try:
            self.assertTrue(started.wait(1));at=time.monotonic()
            self.service.save_settings({'endedExpiryHours':48,'stuckMinutes':5})
            self.assertLess(time.monotonic()-at,.5)
        finally:release.set();worker.join(3)
        self.assertIsNone(self.service.last_poll)
        self.reader.shell=original;self.service.poll();self.assertEqual(self.service.agents['status'],'ok')

    def test_twenty_second_polls_use_cached_config_without_rediscovery(self):
        self.reader.config=Mock(return_value={'providers':[]})
        for seconds in (0,20,40,60):self.now=NOW+timedelta(seconds=seconds);self.service.poll()
        self.assertEqual(self.reader.config.call_count,1)
        self.now=NOW+timedelta(seconds=300);self.service.poll();self.assertEqual(self.reader.config.call_count,2)

    def test_dot_dotdot_and_empty_thread_link_segments_are_rejected(self):
        for base in ('t3code://threads/','https://app.t3.codes/threads/'):
            for path in ('./a','e/..','%2e/a','e/%2E%2e','e/','/a'):
                with self.subTest(path=path):self.assertIsNone(thread_links(base+path))

    def test_websocket_deadline_interrupts_a_trickled_upgrade_header(self):
        import socket
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1)
        def peer():
            connection,_=listener.accept()
            try:
                raw=b''
                while b'\r\n\r\n' not in raw:raw+=connection.recv(4096)
                for byte in b'HTTP/1.1 101 Switching Protocols\r\n':
                    connection.sendall(bytes([byte]));time.sleep(.02)
            except OSError:pass
            finally:connection.close()
        worker=threading.Thread(target=peer);worker.start()
        client=object.__new__(T3Reader);client.port=listener.getsockname()[1];client._token='synthetic-placeholder'
        at=time.monotonic()
        try:
            with patch('t3_reader.WS_SECONDS',.15):
                with self.assertRaises(Unavailable):client.config()
            self.assertLess(time.monotonic()-at,.7)
        finally:listener.close();worker.join(2)

    def test_new_silence_after_unobserved_activity_can_notify(self):
        self.poll();self.now+=timedelta(minutes=16);self.poll()
        self.reader.rows[0]['updatedAt']=(self.now+timedelta(minutes=1)).isoformat()
        self.now+=timedelta(minutes=17);self.poll()
        self.assertEqual(len(self.service.notifications()),2)

    def test_failed_config_reads_are_not_retried_every_twenty_seconds(self):
        self.reader.config=Mock(side_effect=Unavailable())
        for seconds in (0,20,40,60):self.now=NOW+timedelta(seconds=seconds);self.service.poll()
        self.assertEqual(self.reader.config.call_count,1)
        self.assertEqual(self.service.providers['claude']['status'],'unavailable')

    def test_structurally_corrupt_quota_cache_cannot_lock_a_failed_poll(self):
        self.poll()
        journal=self.service.journal()
        journal['cache']['claude']={'status':'ok','checkedAt':NOW.isoformat(),'data':{'accounts':[{'windows':'bad'}]}}
        (self.directory/JOURNAL).write_text(json.dumps(journal));(self.directory/JOURNAL).chmod(0o600)
        self.reader.failure=Unavailable;self.poll()
        self.assertEqual(self.service.agents['status'],'unavailable')
        self.assertIn('journal_reset',self.service.settings_resource()['warnings'])
        self.service.save_settings(DEFAULTS);self.assertEqual(self.service.settings_resource()['warnings'],[])
