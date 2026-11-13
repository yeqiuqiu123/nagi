import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'linux'))
from native_auth import SessionRecovery, REFRESH_SECONDS, UNAVAILABLE, bind_auth_signal
from tray import launch_local


class Clock:
    def __init__(self): self.now=0;self.tasks={};self.next=0
    def schedule(self,delay,callback):
        self.next+=1;self.tasks[self.next]=(self.now+delay,callback);return self.next
    def cancel(self,task): self.tasks.pop(task,None)
    def advance(self,delay):
        end=self.now+delay
        while self.tasks and min(value[0] for value in self.tasks.values())<=end:
            key=min(self.tasks,key=lambda key:self.tasks[key][0]);at,callback=self.tasks.pop(key)
            self.now=at;callback()
        self.now=end


class NativeRecoveryTests(TestCase):
    def controller(self,launch):
        clock=Clock();loaded=[];errors=[]
        def dispatch(work,complete):
            try: value,failed=work(),False
            except OSError: value,failed=None,True
            complete(value,failed)
        recovery=SessionRecovery(launch,loaded.append,errors.append,clock.schedule,clock.cancel,dispatch,lambda:clock.now)
        return recovery,clock,loaded,errors

    def test_every_show_and_twelve_visible_minutes_get_a_new_ticket(self):
        launch=Mock(side_effect=['first','second','third','fourth'])
        recovery,clock,loaded,errors=self.controller(launch)
        recovery.shown();self.assertEqual(loaded,['first'])
        recovery.shown();self.assertEqual(loaded,['first','second'])
        clock.advance(REFRESH_SECONDS-1);self.assertEqual(len(loaded),2)
        clock.advance(1);self.assertEqual(loaded[-1],'third')
        recovery.hidden();clock.advance(2*REFRESH_SECONDS);self.assertEqual(len(loaded),3)
        recovery.shown();self.assertEqual(loaded[-1],'fourth');self.assertEqual(errors,[])

    def test_401_request_refreshes_and_coalesces_in_flight_work(self):
        clock=Clock();pending=[];loaded=[]
        recovery=SessionRecovery(lambda:'ticket',loaded.append,Mock(),clock.schedule,clock.cancel,
                                 lambda work,done:pending.append(done),lambda:clock.now)
        recovery.shown();recovery.request();self.assertEqual(len(pending),1)
        pending.pop()( 'first',False)
        recovery.request();self.assertEqual(len(pending),1)
        recovery.hidden();pending.pop()('late',False);self.assertEqual(loaded,['first'])
        recovery.shown();pending.pop()('fresh',False);self.assertEqual(loaded[-1],'fresh')

    def test_missing_startup_reader_retries_thirty_seconds_then_shows_plain_error(self):
        launch=Mock(side_effect=OSError('private diagnostic'))
        recovery,clock,loaded,errors=self.controller(launch)
        recovery.shown();clock.advance(29);self.assertEqual(errors,[])
        clock.advance(1);self.assertEqual(errors,[UNAVAILABLE]);self.assertEqual(loaded,[])
        self.assertGreater(launch.call_count,3);self.assertLess(launch.call_count,10)
        self.assertNotIn('private diagnostic',errors[0]);self.assertEqual(clock.tasks,{})
        launch.side_effect=None;launch.return_value='recovered';recovery.request()
        self.assertEqual(loaded,['recovered'])

    def test_late_login_reader_recovers_within_backoff_without_exiting(self):
        launch=Mock(side_effect=[OSError(),OSError(),'ready'])
        recovery,clock,loaded,errors=self.controller(launch)
        recovery.shown();clock.advance(3)
        self.assertEqual(loaded,['ready']);self.assertEqual(errors,[])
        self.assertEqual(min(at for at,_ in clock.tasks.values()),3+REFRESH_SECONDS)

    def test_gtk_signal_validates_value_and_current_native_origin(self):
        web=Mock();manager=web.get_user_content_manager.return_value
        refresh=Mock();trusted=Mock(return_value=True)
        bind_auth_signal(web,trusted,refresh)
        manager.connect.assert_called_once();self.assertEqual(manager.connect.call_args.args[0],'script-message-received::nagiAuth')
        callback=manager.connect.call_args.args[1];result=Mock()
        result.get_js_value.return_value.is_string.return_value=True
        result.get_js_value.return_value.to_string.return_value='reauthenticate'
        callback(manager,result);refresh.assert_called_once()
        trusted.return_value=False;callback(manager,result);refresh.assert_called_once()
        trusted.return_value=True;result.get_js_value.return_value.to_string.return_value='arbitrary';callback(manager,result);refresh.assert_called_once()

    def test_tray_launch_errors_are_caught_and_reported_without_diagnostics(self):
        opened=Mock();messages=[]
        with patch('owner_auth.launch_url',side_effect=OSError('private diagnostic')):
            self.assertFalse(launch_local('http://127.0.0.1:47831/overview','http://127.0.0.1:47831',opened,messages.append))
        opened.assert_not_called();self.assertEqual(len(messages),1);self.assertIn('local reader',messages[0]);self.assertNotIn('private diagnostic',messages[0])
        with patch('owner_auth.launch_url',return_value='launch-ticket'),patch.object(opened,'side_effect',OSError()):
            self.assertFalse(launch_local('http://127.0.0.1:47831/overview','http://127.0.0.1:47831',opened,messages.append))

    def test_real_glance_entrypoint_stays_open_at_login_and_wires_show_timer_and_401(self):
        # Operate the actual entrypoint with a deterministic GLib loop, no GUI/files/services.
        from types import ModuleType, SimpleNamespace
        from unittest.mock import MagicMock
        import notifications
        clock=Clock();gtk=MagicMock();web=MagicMock();context=MagicMock();manager=web.get_user_content_manager.return_value
        window=gtk.Window.return_value;window.get_screen.return_value=None
        monitor=window.get_display.return_value.get_primary_monitor.return_value
        monitor.get_workarea.return_value=SimpleNamespace(x=0,y=0,width=1000,height=800)
        monitor.get_geometry.return_value=SimpleNamespace(x=0,y=0,width=1000,height=800)
        visible={'now':False}
        window.show_all.side_effect=lambda:visible.update(now=True)
        window.hide.side_effect=lambda:visible.update(now=False)
        window.get_visible.side_effect=lambda:visible['now']
        menus={}
        def menu_item(*,label):
            item=MagicMock()
            item.connect.side_effect=lambda signal,callback:menus.update({label:callback})
            return item
        gtk.MenuItem.side_effect=menu_item
        glib=MagicMock()
        glib.timeout_add.side_effect=lambda ms,fn:clock.schedule(ms/1000,fn)
        glib.source_remove.side_effect=clock.cancel
        glib.idle_add.side_effect=lambda fn,*args:clock.schedule(0,lambda:fn(*args))
        glib.get_monotonic_time.side_effect=lambda:int(clock.now*1_000_000)
        gi=ModuleType('gi');gi.require_version=lambda *_:None
        repo=ModuleType('gi.repository')
        for name,value in {'Gtk':gtk,'Gdk':MagicMock(),'Gio':MagicMock(),'GLib':glib,'WebKit2':MagicMock(),'AyatanaAppIndicator3':MagicMock()}.items():
            setattr(repo,name,value)
        repo.WebKit2.WebView.return_value=web
        class ImmediateThread:
            def __init__(self,*,target,daemon):self.target=target
            def start(self):self.target()
        ready=False;attempts=[]
        def launch(*_):
            attempts.append(clock.now)
            if not ready:raise OSError('private diagnostic')
            return notifications.GLANCE_URI+'#nagi-launch='+str(len(attempts)).zfill(43)
        web.load_uri.side_effect=lambda uri:setattr(web.get_uri,'return_value',uri)
        def operate():
            nonlocal ready
            clock.advance(30)
            self.assertEqual(gtk.Label.return_value.set_text.call_args.args[0],UNAVAILABLE)
            self.assertEqual(web.load_uri.call_count,0)
            # Open Nagi toggles: the login panel hides, then a later click shows and launches.
            ready=True;menus['Open Nagi'](None);self.assertFalse(visible['now']);clock.advance(1)
            menus['Open Nagi'](None);clock.advance(0);self.assertTrue(visible['now'])
            self.assertEqual(web.load_uri.call_count,1)
            clock.advance(720);self.assertEqual(web.load_uri.call_count,2)
            callback=manager.connect.call_args.args[1];result=MagicMock()
            result.get_js_value.return_value.is_string.return_value=True
            result.get_js_value.return_value.to_string.return_value='reauthenticate'
            callback(manager,result);clock.advance(0);self.assertEqual(web.load_uri.call_count,3)
            menus['Open Nagi'](None);clock.advance(720);self.assertEqual(web.load_uri.call_count,3)
            menus['Open Nagi'](None);clock.advance(0);self.assertEqual(web.load_uri.call_count,4)
            self.assertEqual(list(menus),['Open Nagi','Settings…','Quit Nagi'])
        gtk.main.side_effect=operate
        with patch.dict(sys.modules,{'gi':gi,'gi.repository':repo}), patch.object(notifications,'InstanceLock'), \
             patch.object(notifications,'scoped_web_context',return_value=context), patch('native_auth.threading.Thread',ImmediateThread), \
             patch('owner_auth.launch_url',side_effect=launch), patch('agent_notifications.start_gio',return_value=(None,None,999)), \
             patch('native_auth.SessionRecovery',side_effect=lambda *args:SessionRecovery(*args,clock=lambda:clock.now)), \
             patch('tray.read_state',side_effect=OSError('no reader in tests')), patch.object(notifications.threading,'Thread',ImmediateThread):
            self.assertEqual(notifications.run(),0)
        gtk.main.assert_called_once()
        indicator=repo.AyatanaAppIndicator3.Indicator.new_with_path.return_value
        indicator.set_label.assert_any_call('','')  # glyph only: the bar never shows a count, stale or not
        indicator.set_title.assert_any_call("Nagi · can't reach its local reader")
        self.assertEqual(indicator.set_secondary_activate_target.call_count,1)
