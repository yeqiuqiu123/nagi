"""Acknowledged desktop delivery with a durable, expiring reservation."""
import json
import re
import sys
import threading
from pathlib import Path
from urllib.request import Request

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agents_projection import stamp, text
from agents_service import validate_limit_event
from nagi_links import open_thread, thread_links
from owner_auth import authenticated_open
from jsonio import strict_json_loads

APP_ID='local.nagi.notifications'
ACTION='open-thread'
PANEL_ACTION='open-panel'
PANEL_APP_ID='local.nagi.panel'
NOTIFICATIONS_API='/api/sources/v1/notifications'
SOURCE_ID=re.compile(r'(?:legacy-t3|[0-9a-f]{32})')
EVENT_ID=re.compile(r'[0-9a-f]{64}')
RESERVATION=re.compile(r'[A-Za-z0-9_-]{43}')


def valid_event(event):
    if isinstance(event,dict) and event.get('kind')=='low_limit':
        try:validate_limit_event(event);return True
        except (ValueError,TypeError,KeyError):return False
    if not isinstance(event,dict) or set(event)!={'id','kind','threadId','projectId','threadTitle','projectTitle','occurredAt','links'}:
        return False
    try:
        if not isinstance(event['id'],str) or not EVENT_ID.fullmatch(event['id']) or event['kind'] not in ('failed','stuck'):
            return False
        for key in ('threadId','projectId','threadTitle','projectTitle'):
            text(event[key])
        stamp(event['occurredAt'])
        links=event['links']
        return isinstance(links,dict) and set(links)=={'desktop','web'} and thread_links(links['desktop'])==links
    except (ValueError,TypeError,UnicodeError):
        return False


def banner(event):
    if event['kind']=='low_limit':
        return (event['accountLabel']+' · '+format(event['remainingPercent'],'g')+'% left',
                'resets '+stamp(event['resetsAt']).astimezone().strftime('%a %H:%M'))
    return event['projectTitle']+' · '+event['threadTitle'],'Thread failed.' if event['kind']=='failed' else 'Thread has been inactive.'


def open_panel(Gio,GLib,origin):
    """Explicit click only: raise the tray panel, or launch Nagi if absent."""
    try:
        bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
        bus.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','GetNameOwner',
                      GLib.Variant('(s)',(PANEL_APP_ID,)),None,Gio.DBusCallFlags.NONE,1000,None)
        # DBusActionGroup loads its action list asynchronously. A fixed direct
        # activation also works on the first click immediately after startup.
        bus.call_sync(PANEL_APP_ID,'/local/nagi/panel','org.gtk.Actions','Activate',
                      GLib.Variant('(sava{sv})',('open',[],{})),None,Gio.DBusCallFlags.NONE,1000,None)
        return True
    except Exception:
        import subprocess
        import os
        from urllib.parse import urlsplit
        from sources_transport import cli_environment
        target=urlsplit(origin)
        if target.scheme!='http' or target.hostname!='127.0.0.1' or not target.port or target.path or target.query or target.fragment:return False
        try:
            env=cli_environment()|{key:os.environ[key] for key in ('DISPLAY','WAYLAND_DISPLAY','DBUS_SESSION_BUS_ADDRESS','XDG_RUNTIME_DIR','XAUTHORITY') if key in os.environ}
            subprocess.Popen([sys.executable,'-B',str(Path(__file__).with_name('tray.py')),'--port',str(target.port)],
                             stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=env,start_new_session=True)
            return True
        except OSError:return False

class NotificationConsumer:
    def __init__(self,origin,send,opener,has_handler=None,transport=authenticated_open,on_panel=None):
        self.origin,self.send,self.opener,self.has_handler,self.transport=origin,send,opener,has_handler,transport
        self.lock=threading.Lock()
        self.on_panel=on_panel or (lambda:False)

    def request(self,path,body=None):
        headers={'Content-Type':'application/json','X-Progress-Desk':'1'} if body is not None else {}
        request=Request(self.origin+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        with self.transport(request,timeout=5) as response:
            return strict_json_loads(response.read(1024*1024+1),1024*1024)

    def poll(self):
        if not self.lock.acquire(blocking=False):return
        try:
            result=self.request(NOTIFICATIONS_API)
            if (not isinstance(result,dict) or set(result)!={'version','events'} or type(result['version']) is not int
                    or result['version']!=1 or not isinstance(result['events'],list) or len(result['events'])>256):return
            candidates=result['events']
            for candidate in candidates:
                if (not isinstance(candidate,dict) or set(candidate)!={'sourceId','event'}
                        or not isinstance(candidate['sourceId'],str) or not SOURCE_ID.fullmatch(candidate['sourceId'])
                        or not valid_event(candidate['event'])):continue
                body={'sourceId':candidate['sourceId'],'id':candidate['event']['id']}
                reserved=self.request(NOTIFICATIONS_API+'/reserve',body)
                if (not isinstance(reserved,dict) or set(reserved)!={'version','reserved','lease'}
                        or type(reserved['version']) is not int or reserved['version']!=1 or reserved['reserved'] is not True):continue
                lease=reserved.get('lease')
                if (not isinstance(lease,dict) or set(lease)!={'reservation','expiresAt','event'}
                        or not isinstance(lease['reservation'],str) or not RESERVATION.fullmatch(lease['reservation'])):continue
                stamp(lease['expiresAt'])
                if not valid_event(lease['event']) or lease['event']!=candidate['event']:
                    self.request(NOTIFICATIONS_API+'/release',{**body,'reservation':lease['reservation']})
                    continue
                event=lease['event']
                sent=False
                try:sent=self.send(event,self.on_panel if event['kind']=='low_limit' else lambda value=event['links']['desktop']:open_thread(value,self.opener,self.has_handler)) is True
                except Exception:pass
                self.request(NOTIFICATIONS_API+('/claim' if sent else '/release'),
                             {**body,'reservation':lease['reservation']})
        except Exception:pass
        finally:self.lock.release()


def register_thread_action(application,GLib,Gio,opener):
    # Serialized targets survive tray/notifier restarts; no per-event action table.
    action=Gio.SimpleAction.new(ACTION,GLib.VariantType.new('s'))
    def activated(_action,target):
        try:
            value=target.get_string()
            open_thread(value,opener,lambda scheme:Gio.AppInfo.get_default_for_uri_scheme(scheme) is not None)
        except (AttributeError,TypeError,ValueError):pass
    action.connect('activate',activated);application.add_action(action)
    return action


def stop_notifier(GLib,notifier):
    if notifier is not None:GLib.source_remove(notifier[2])


def start_gio(GLib,Gio,opener,origin='http://127.0.0.1:47831',on_panel=None):
    # GNOME resolves this ID through its matching installed desktop entry.
    # PyGObject raises TypeError, not None, when the entry is not installed.
    try:entry=Gio.DesktopAppInfo.new(APP_ID+'.desktop')
    except TypeError:entry=None
    if entry is None:return None
    application=Gio.Application(application_id=APP_ID,flags=Gio.ApplicationFlags.FLAGS_NONE)
    register_thread_action(application,GLib,Gio,opener)
    panel_callback=on_panel or (lambda:open_panel(Gio,GLib,origin))
    action=Gio.SimpleAction.new(PANEL_ACTION,None)
    action.connect('activate',lambda *_:panel_callback());application.add_action(action)
    try:
        application.register(None)
        if application.get_is_remote():return None
        bus=application.get_dbus_connection()
        # Use the same protocol as Gio's GTK backend, but retain its reply/error.
        # Application.send_notification discards that reply and cannot confirm a send.
        bus.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','GetNameOwner',
                      GLib.Variant('(s)',('org.gtk.Notifications',)),None,Gio.DBusCallFlags.NONE,5000,None)
        gtk=True
    except Exception:
        try:bus=Gio.bus_get_sync(Gio.BusType.SESSION,None);gtk=False
        except Exception:return None
    fdo_clicks={}
    def invoked(_bus,_sender,_path,_interface,_signal,parameters):
        identity,action=parameters.unpack()
        if action=='default' and identity in fdo_clicks:fdo_clicks[identity]()
    if not gtk:
        bus.signal_subscribe('org.freedesktop.Notifications','org.freedesktop.Notifications','ActionInvoked',
                             '/org/freedesktop/Notifications',None,Gio.DBusSignalFlags.NONE,invoked)
    def send(event,clicked):
        finished=threading.Event();started=threading.Event();guard=threading.Lock();cancelled=[];accepted=[]
        def deliver():
            with guard:
                if cancelled:return False
                started.set()
            try:
                title,body=banner(event)
                if gtk:
                    payload={'title':GLib.Variant('s',title),'body':GLib.Variant('s',body),
                             'default-action':GLib.Variant('s','app.'+(PANEL_ACTION if event['kind']=='low_limit' else ACTION))}
                    if event['kind']!='low_limit':payload['default-action-target']=GLib.Variant('s',event['links']['desktop'])
                    reply=bus.call_sync('org.gtk.Notifications','/org/gtk/Notifications','org.gtk.Notifications','AddNotification',
                                  GLib.Variant('(ssa{sv})',(APP_ID,event['id'],payload)),None,Gio.DBusCallFlags.NONE,5000,None)
                    if reply is None:return False
                else:
                    import html
                    reply=bus.call_sync('org.freedesktop.Notifications','/org/freedesktop/Notifications',
                        'org.freedesktop.Notifications','Notify',GLib.Variant('(susssasa{sv}i)',
                        ('Nagi',0,'view-list-symbolic',html.escape(title),body,['default','Open Nagi' if event['kind']=='low_limit' else 'Open thread'],
                         {'desktop-entry':GLib.Variant('s',APP_ID)},-1)),None,Gio.DBusCallFlags.NONE,5000,None)
                    fdo_clicks[reply.unpack()[0]]=clicked
                    if len(fdo_clicks)>256:fdo_clicks.pop(next(iter(fdo_clicks)))
                accepted.append(True)
            except Exception:pass
            finally:finished.set()
            return False
        GLib.idle_add(deliver)
        # Longer than the bounded DBus call. A late callback is cancelled, not sent
        # after its reservation has already been released.
        if not started.wait(2):
            with guard:
                if not started.is_set():cancelled.append(True);return False
        if not finished.wait(6):return False
        return bool(accepted)
    consumer=NotificationConsumer(origin,send,opener,lambda scheme:Gio.AppInfo.get_default_for_uri_scheme(scheme) is not None,on_panel=panel_callback)
    def tick():threading.Thread(target=consumer.poll,daemon=True).start();return True
    tick();timer=GLib.timeout_add_seconds(20,tick)
    return application,consumer,timer


def activation_main(argv=None):
    """User D-Bus activation: export the stable action without a tray window."""
    import argparse
    import signal
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--activate',action='store_true');parser.add_argument('--port',type=int,default=47831)
    args=parser.parse_args(argv)
    if not 1024<=args.port<=65535:return 2
    import gi
    gi.require_version('Gio','2.0')
    from gi.repository import Gio, GLib
    native=lambda url:Gio.AppInfo.launch_default_for_uri(url,None)
    notifier=start_gio(GLib,Gio,native,'http://127.0.0.1:'+str(args.port))
    if notifier is None:return 0
    loop=GLib.MainLoop()
    for sig in (signal.SIGTERM,signal.SIGINT):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT,sig,lambda:(loop.quit(),False)[1])
    try:loop.run()
    finally:stop_notifier(GLib,notifier)
    return 0

if __name__=='__main__':
    import sys
    sys.exit(activation_main())
