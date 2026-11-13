#!/usr/bin/env python3
"""Optional, fixed-origin Gtk3 / WebKit2 4.1 client. No backend is started.

Importing this module is pure: GI and the fixed health endpoint are used only
by explicit runtime entry points. Alpha support is not a wallpaper/blur claim.
"""
import json
import fcntl
import os
import re
import stat
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from panel_geometry import Rect, sized_panel, pointer_sized_panel, right_strut, reserved_workarea, workarea_needs_refit
from panel_preferences import (PanelPreference, PRESETS, MIN_WIDTH, MAX_WIDTH,
                               load_preference, save_preference, scoped_web_context)
from x11_panel import XConnection, PanelReservation
from planning_view import open_external
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener, Request

ORIGIN = 'http://127.0.0.1:47831'
WIDGET_URI = ORIGIN + '/glance'
PANEL_URI = ORIGIN + '/glance'
RESIZE_POLL_MS = 30
RESIZE_TIMEOUT_US = 60_000_000
RESERVATION_SETTLE_US = 3_000_000
ALLOCATION_SETTLE_US = 3_000_000
PANEL_CONTROL_HEIGHT = 48


def read_root_workarea(connection):
    """Coherent, bounded EWMH read only; XConnection rejects truncated properties."""
    root_width, root_height = connection.root_size
    if any(type(v) is not int or not 0 < v <= 0xffffffff for v in (root_width, root_height)):
        raise ValueError('Invalid root bounds')
    desktop = connection.read(connection.root, '_NET_CURRENT_DESKTOP', 'CARDINAL')
    areas = connection.read(connection.root, '_NET_WORKAREA', 'CARDINAL')
    again = connection.read(connection.root, '_NET_CURRENT_DESKTOP', 'CARDINAL')
    if (len(desktop) != 1 or len(again) != 1 or type(desktop[0]) is not int
            or type(again[0]) is not int or desktop != again
            or not areas or len(areas) > 4096 or len(areas) % 4
            or not 0 <= desktop[0] < len(areas) // 4
            or any(type(v) is not int or not 0 <= v <= 0xffffffff for v in areas)):
        raise ValueError('Incoherent root work area')
    for i in range(0, len(areas), 4):
        x, y, width, height = areas[i:i + 4]
        if not (width > 0 and height > 0 and x + width <= root_width and y + height <= root_height):
            raise ValueError('Root work area outside root bounds')
    offset = desktop[0] * 4
    return desktop[0], Rect(*areas[offset:offset + 4])


def private_web_settings(settings, WebKit2):
    settings.set_enable_developer_extras(False)
    if hasattr(settings, 'set_hardware_acceleration_policy'):
        settings.set_hardware_acceleration_policy(WebKit2.HardwareAccelerationPolicy.NEVER)
    settings.set_enable_html5_local_storage(True)
    for name in ('set_enable_html5_database', 'set_enable_offline_web_application_cache', 'set_enable_page_cache'):
        if hasattr(settings, name):
            getattr(settings, name)(False)


def panel_input_rect(width, height, scale, margins):
    """The visible panel inside a window that carries a transparent shadow margin.

    margins are (top, sides, bottom) in CSS px; the result is (x, y, w, h) in window px."""
    top, side, bottom = (round(m * scale) for m in margins)
    return side, top, max(1, width - 2 * side), max(1, height - top - bottom)


def apply_input_shape(window, rect):
    """Let clicks on the transparent shadow margin reach the desktop beneath.

    Needs cairo's GI bridge (python3-gi-cairo); without it the whole window keeps
    taking clicks, exactly as before. Returns True when the shape was applied."""
    try:
        import gi
        gi.require_foreign('cairo')
        import cairo
        window.input_shape_combine_region(cairo.Region(cairo.RectangleInt(*rect)))
        return True
    except (ImportError, ValueError, TypeError, AttributeError):
        return False


def instance_lock_path():
    """Fixed per-user app-owned runtime path, never supplied by a feed or CLI."""
    return f'/run/user/{os.getuid()}/progress-desk-panel.lock'


class AlreadyRunning(RuntimeError):
    pass


class InstanceLock:
    """Keep one inode/descriptor locked for the entire GUI lifetime.

    Do not unlink on release: unlink/recreate races could admit two owners.
    No PID files, process inspection, signalling, activation or focus requests.
    """
    def __init__(self):
        self.fd = None

    def acquire(self):
        if self.fd is not None:
            raise RuntimeError('Instance lock already acquired')
        fd = os.open(instance_lock_path(), os.O_CREAT | os.O_RDWR | os.O_CLOEXEC
                     | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_nlink != 1 or info.st_mode & 0o077):
                raise OSError('Unsafe app instance lock; no permissions were changed')
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise AlreadyRunning('Nagi is already running') from error
        except BaseException:
            os.close(fd)
            raise
        self.fd = fd

    def release(self):
        if self.fd is not None:
            os.close(self.fd)  # Kernel releases flock on close/exit, even after a crash.
            self.fd = None


def launch_gui(unavailable=False, mode='panel', diagnostics=False, size=None):
    guard = InstanceLock()
    try:
        guard.acquire()
    except AlreadyRunning:
        print('Nagi is already running; no second window was opened. Use the existing panel controls to float, compact or close it.', file=sys.stderr)
        return 2
    except OSError:
        print('Nagi could not acquire its private runtime lock. No window was opened and no files or permissions were repaired. A normal Linux user runtime directory is required.', file=sys.stderr)
        return 1
    try:
        return run(unavailable, mode, diagnostics, size)
    finally:
        guard.release()


def allowed_navigation(uri):
    return isinstance(uri,str) and (uri == PANEL_URI or uri in {PANEL_URI+'#agents',PANEL_URI+'#limits',PANEL_URI+'#ended'})


def open_panel_external(uri, user_gesture, source_uri, opener):
    """Exact local and public destinations require a click from the trusted panel.

    Keep lesson URL validation in its existing helper; never attach draft text,
    queries or native commands to the homepage fallback.
    """
    if not user_gesture or not allowed_navigation(source_uri):
        return False
    from nagi_links import open_thread
    if open_thread(uri, opener): return True
    if uri == ORIGIN + '/overview':
        from owner_auth import launch_url
        opener(launch_url(ORIGIN))
        return True
    return False


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def check_health():
    """Explicit launcher-only check; never redirects or consults proxy settings."""
    try:
        opener = build_opener(ProxyHandler({}), NoRedirect())
        with __import__('owner_auth').authenticated_open(Request(ORIGIN + '/api/health'), timeout=3) as response:
            data = json.loads(response.read(2049))
            return response.status == 200 and data.get('app') == 'nagi' and data.get('schemaVersion') == 2
    except (OSError, ValueError, TypeError):
        return False


def run(unavailable=False, mode='panel', diagnostics=False, size=None):
    try:
        import gi
        gi.require_version('Gtk', '3.0')
        gi.require_version('Gdk', '3.0')
        gi.require_version('WebKit2', '4.1')
        from gi.repository import Gdk, Gio, GLib, Gtk, Pango, WebKit2
    except (ImportError, ValueError) as error:
        print('Native client unavailable: installed Gtk3 and WebKit2 API 4.1 bindings are required. No dependencies were installed.', file=sys.stderr)
        return 1

    class PanelWebView(WebKit2.WebView):
        # Web content/natural width must not hold a previously wide viewport
        # open inside a smaller native panel. Gtk parents supply the real width.
        def do_get_preferred_width(self):
            return 1, 1

        def do_get_preferred_width_for_height(self, _height):
            return 1, 1

    class Widget(Gtk.Window):
        def __init__(self):
            super().__init__(title='Nagi')
            self.mode = mode
            self.preference = PanelPreference(size) if size else load_preference()
            self.preference_saved = save_preference(self.preference) if size else True
            self.drag_timer = 0
            self.dragging = False
            self.reservation = self.x11 = None
            self.refit_timer = self.diagnostic_timer = 0
            self.map_timer = 0
            self.pending_strut = None
            self.mapping_phase = 'idle'
            self.mapping_verified = False
            self.mapping_frame = None
            self.refitting = False
            self.baseline = self.target = self.expected_area = None
            self.monitor_handlers = []
            self.set_focus_on_map(False)
            self.set_default_size(480, 760)
            self.set_size_request(1, 1)
            self.set_resizable(True)
            self.get_style_context().add_class('progress-desk-widget')
            screen = self.get_screen()
            alpha = bool(screen and screen.is_composited() and screen.get_rgba_visual())
            if alpha:
                self.set_visual(screen.get_rgba_visual())
                self.set_app_paintable(True)
            provider = Gtk.CssProvider()
            css = '.progress-desk-widget {background-color: '+('transparent' if alpha else '#171d21')+';} .progress-desk-widget .unavailable-surface {background: #171d21;} .progress-desk-widget .panel-toolbar {background: #171d21; border-top: 1px solid rgba(255,255,255,0.10);} .progress-desk-widget .panel-toolbar label {color: #a8cbbf; font-size: 11px; font-weight: 600;} .progress-desk-widget .panel-toolbar button {background: transparent; color: #d4dedb; border: 0; box-shadow: none; min-height: 44px; min-width: 32px; padding: 0 7px;} .progress-desk-widget .panel-toolbar button:hover {background: rgba(255,255,255,0.08);} .progress-desk-widget button {background: #343b3c; color: #f2eee6; border-color: #69726d;} .progress-desk-widget label {color: #f2eee6;}'
            css += ' .progress-desk-widget .panel-resize-handle {background: rgba(168,203,191,0.10); border-right: 1px solid rgba(168,203,191,0.24);} .progress-desk-widget .panel-resize-handle:hover, .progress-desk-widget .panel-resize-handle:focus {background: rgba(168,203,191,0.28);}'
            provider.load_from_data(css.encode())
            Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            shell = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            self.add(shell)
            self.resize_handle = Gtk.EventBox()
            self.resize_handle.set_size_request(12, -1)
            self.resize_handle.set_can_focus(True)
            self.resize_handle.set_tooltip_text('Drag to resize. Alt+1 Compact, Alt+2 Medium, Alt+3 Large. Escape cancels resizing.')
            self.resize_handle.get_accessible().set_name('Resize panel — drag left edge; Alt+1, Alt+2, Alt+3 for sizes')
            self.resize_handle.get_style_context().add_class('panel-resize-handle')
            self.resize_handle.add(Gtk.Label(label='⋮'))
            self.resize_handle.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
            self.resize_handle.connect('button-press-event', self.begin_panel_resize)
            self.resize_handle.connect('realize', lambda handle: handle.get_window().set_cursor(Gdk.Cursor.new_from_name(self.get_display(), 'ew-resize')))
            shell.pack_start(self.resize_handle, False, False, 0)
            shell.pack_start(layout, True, True, 0)
            header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            header.get_style_context().add_class('panel-toolbar')
            header.set_border_width(0)
            header.set_size_request(-1, PANEL_CONTROL_HEIGHT)
            self.panel_status = Gtk.Label(label='●  PINNED TO DESKTOP')
            self.panel_status.set_xalign(0)
            self.panel_status.set_ellipsize(Pango.EllipsizeMode.END)
            header.pack_start(self.panel_status, True, True, 14)
            controls = Gtk.MenuButton(label='⋯')
            controls.get_accessible().set_name('Panel options')
            controls.set_tooltip_text('Panel size, pin, float, mini window or close')
            menu = Gtk.Menu()
            for title, action in [('Pin right', lambda *_: self.pin()),
                                  ('Float / move', lambda *_: self.float_window()),
                                  ('Mini window', lambda *_: self.float_window(compact=True)),
                                  ('Close', lambda *_: self.close())]:
                item = Gtk.MenuItem(label=title)
                item.connect('activate', action)
                menu.append(item)
            menu.prepend(Gtk.SeparatorMenuItem())
            for preset, shortcut in reversed(list(zip(PRESETS, ('Alt+1', 'Alt+2', 'Alt+3')))):
                item = Gtk.MenuItem(label='Panel size: ' + preset.title() + ' (' + shortcut + ')')
                item.connect('activate', lambda _item, value=preset: self.choose_size(value))
                menu.prepend(item)
            menu.show_all()
            controls.set_popup(menu)
            header.pack_start(controls, False, False, 0)
            close = Gtk.Button(label='×')
            close.set_tooltip_text('Close panel (Ctrl+W)')
            close.get_accessible().set_name('Close panel')
            close.connect('clicked', lambda *_: self.close())
            header.pack_start(close, False, False, 0)
            layout.pack_end(header, False, False, 0)  # App controls stay at the unobstructed footer.
            self.stack = Gtk.Stack()
            self.stack.set_transition_type(Gtk.StackTransitionType.NONE)
            self.stack.set_hhomogeneous(False)
            self.stack.set_vhomogeneous(False)
            self.stack.set_hexpand(True)
            layout.pack_start(self.stack, True, True, 0)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
            box.get_style_context().add_class('unavailable-surface')
            box.set_border_width(28)
            self.message = Gtk.Label(label='Updates unavailable.\nTry again when Nagi is available.')
            self.message.set_line_wrap(True)
            box.pack_start(self.message, True, True, 0)
            retry = Gtk.Button(label='Try again')
            retry.connect('clicked', lambda *_: self.load())
            box.pack_start(retry, False, False, 0)
            self.stack.add_named(box, 'unavailable')
            # Only app-owned UI storage, never a personal/default browser profile.
            try:
                context = scoped_web_context(WebKit2)
            except Exception:
                context = None
            if context is None:
                self.message.set_text('Private UI storage unavailable on this device. Updates and saved drafts are unavailable; no shared browser profile was used.')
                retry.set_sensitive(False)
                self.web = None
            else:
                context.connect('download-started', lambda _context, download: download.cancel())
                context.get_cookie_manager().set_accept_policy(WebKit2.CookieAcceptPolicy.NEVER)
                self.web = PanelWebView(web_context=context)
                self.web.set_hexpand(True)
                self.web.set_vexpand(True)
                self.web.set_halign(Gtk.Align.FILL)
                self.web.set_valign(Gtk.Align.FILL)
                settings = self.web.get_settings()
                private_web_settings(settings, WebKit2)
                if hasattr(self.web, 'set_background_color'):
                    color = Gdk.RGBA()
                    color.parse('rgba(0,0,0,0)' if alpha else '#232729')
                    self.web.set_background_color(color)
                self.web.connect('decide-policy', self.policy)
                self.web.connect('create', lambda *_: None)
                self.web.connect('permission-request', self.deny_permission)
                self.web.connect('load-failed', self.failed)
                self.web.connect('load-changed', self.loaded)
                if hasattr(self.web, 'connect'):
                    self.web.connect('authenticate', self.deny_authentication)
                self.stack.add_named(self.web, 'web')
                from native_auth import gtk_recovery, bind_auth_signal
                from owner_auth import launch_url
                self.auth_recovery = gtk_recovery(GLib,
                    lambda: launch_url(ORIGIN, (WIDGET_URI if self.mode == 'compact' else PANEL_URI)[len(ORIGIN):]),
                    self.authenticated_load, self.auth_failed)
                bind_auth_signal(self.web, lambda uri: allowed_navigation(uri) or (uri is not None and uri == getattr(self, 'bootstrap_uri', None)), self.auth_recovery.request)
                from agent_notifications import start_gio,stop_notifier
                self.notifier = start_gio(GLib, Gio, lambda url: Gio.AppInfo.launch_default_for_uri(url,None))
                self.connect('map', lambda *_: self.auth_recovery.shown())
                self.connect('unmap', lambda *_: self.auth_recovery.hidden())
                self.connect('destroy', lambda *_: self.auth_recovery.hidden())
                self.connect('destroy', lambda *_: stop_notifier(GLib,self.notifier))
            self.connect('delete-event', self.before_close)
            self.connect('destroy', self.destroyed)
            self.connect('key-press-event', self.key)
            self.connect('map-event', self.mapped)
            self.connect('configure-event', self.configured)
            self.realize()
            # Never attempt an X connection on Wayland or a headless import.
            try:
                gi.require_version('GdkX11', '3.0')
                from gi.repository import GdkX11
                if isinstance(self.get_display(), GdkX11.X11Display):
                    self.x11 = XConnection()
                    self.reservation = PanelReservation(self.x11, int(self.get_window().get_xid()))
            except (ImportError, ValueError, OSError):
                pass
            screen.connect('monitors-changed', self.display_changed)
            screen.connect('size-changed', self.display_changed)
            self.watch_monitors()
            if mode == 'panel':
                self.fit_panel()
            else:
                self.float_window(compact=mode == 'compact', reload=False)
            self.show_all()
            if unavailable or not self.web:
                self.stack.set_visible_child_name('unavailable')
            else:
                self.load()
            if diagnostics:
                self.diagnostic_timer = GLib.timeout_add(5000, self.report)

        @staticmethod
        def rectangle(value):
            return Rect(value.x, value.y, value.width, value.height)

        def watch_monitors(self):
            for monitor, handler in self.monitor_handlers:
                monitor.disconnect(handler)
            self.monitor_handlers = []
            display = self.get_display()
            for i in range(display.get_n_monitors()):
                monitor = display.get_monitor(i)
                for prop in ('geometry', 'scale-factor', 'workarea'):
                    handler = monitor.connect('notify::' + prop, self.display_changed)
                    self.monitor_handlers.append((monitor, handler))

        def display_changed(self, *_args):
            if self.mode == 'panel' and self.mapping_phase == 'reserved':
                try:
                    monitor = self.get_display().get_primary_monitor() or self.get_display().get_monitor(0)
                    if (not monitor or self.topology() != self.last_topology
                            or self.rectangle(monitor.get_workarea()) not in (self.baseline, self.expected_area)):
                        self.mapping_failed('Display/work area changed during reservation verification')
                except Exception:
                    self.mapping_failed('Display unavailable during reservation verification')
                return
            if self.dragging:
                current = self.rectangle(self.drag_monitor.get_workarea())
                if self.topology() == self.drag_topology and current in (self.baseline, self.expected_area):
                    return  # Our released strut, not a monitor/dock change.
                self.cancel_resize()
                self.pin()
                return
            if self.mode != 'panel' or self.refitting:
                return
            monitor = self.get_display().get_primary_monitor() or self.get_display().get_monitor(0)
            if not monitor:
                self.float_window()
                return
            current = self.rectangle(monitor.get_workarea())
            topology = self.topology()
            # Ignore the work-area notification caused by OUR strut. Never take
            # the newly reduced width as the next sizing baseline.
            if not workarea_needs_refit(current, self.baseline, self.expected_area,
                                       topology, getattr(self, 'last_topology', None)):
                return
            self.pin()

        def topology(self):
            display = self.get_display()
            return [(self.rectangle(display.get_monitor(i).get_geometry()),
                     display.get_monitor(i).get_scale_factor()) for i in range(display.get_n_monitors())]

        def clear_reservation(self):
            self.root_area_proof = None
            if self.reservation:
                self.reservation.clear()

        def cancel_refit(self):
            self.allocation_deadline = 0
            self.map_previous_target = None
            self.root_area_proof = None
            self.cancel_resize()
            if self.refit_timer:
                GLib.source_remove(self.refit_timer)
                self.refit_timer = 0
            if self.map_timer:
                GLib.source_remove(self.map_timer)
                self.map_timer = 0
            self.pending_strut = None
            self.mapping_verified = False
            self.mapping_phase = 'idle'

        def pin(self):
            self.cancel_refit()
            self.refitting = True
            self.clear_reservation()
            self.hide()  # Remap with the new type; some WMs inspect it only at map.
            self.mode = 'panel'
            # Let the WM restore the work area before sampling it. This also
            # respects changed third-party docks rather than guessing their size.
            self.refit_attempts = 0
            self.refit_timer = GLib.timeout_add(300, self.settled_fit)

        def settled_fit(self):
            monitor = self.get_display().get_primary_monitor() or self.get_display().get_monitor(0)
            current = self.rectangle(monitor.get_workarea()) if monitor else None
            if current is not None and current == self.expected_area:
                self.refit_attempts += 1
                if self.refit_attempts < 5:
                    return True
                self.refit_timer = 0
                self.float_window(reason='Reservation unavailable · floating')
                self.show_all()
                return False
            self.refit_timer = 0
            self.watch_monitors()
            self.fit_panel()
            self.show_all()  # focus_on_map remains False across every transition.
            self.load_for_mode()
            return False

        def fit_panel(self):
            self.root_area_proof = None
            display = self.get_display()
            monitor = display.get_primary_monitor() or display.get_monitor(0)
            if not monitor:
                self.float_window(reason='Display unavailable · floating', reload=False)
                return
            geometry = self.rectangle(monitor.get_geometry())
            self.baseline = self.rectangle(monitor.get_workarea())
            self.last_topology = self.topology()
            try:
                self.target = sized_panel(geometry, self.baseline, self.preference)
            except ValueError:
                self.float_window(reason='Work area unavailable · floating', reload=False)
                return
            scale = monitor.get_scale_factor()
            # Reopen after a topology change: Xlib's cached screen size must not
            # outlive the display geometry from which the CARDINALs are derived.
            if self.x11 and self.reservation:
                xid = self.reservation.xid
                self.x11.close()
                try:
                    self.x11 = XConnection()
                    self.reservation = PanelReservation(self.x11, xid)
                except OSError:
                    self.x11 = self.reservation = None
            strut = right_strut(self.target, geometry, self.last_topology, scale,
                                self.x11.root_size) if self.x11 else None
            self.refitting = True
            if not strut or not self.reservation or not self.reservation.supported():
                self.float_window(reason='Reservation unavailable · floating', reload=False)
                return
            self.set_decorated(False)
            self.set_type_hint(Gdk.WindowTypeHint.DOCK)
            self.set_skip_taskbar_hint(True)
            # Nonresizable GTK windows negotiate their natural/minimum size;
            # resize() alone before map was discarded on the real GNOME trial.
            # Keep negotiation enabled and pin its minimum/default explicitly.
            self.set_resizable(True)
            self.set_geometry_hints(None, Gdk.Geometry(), 0)
            self.set_size_request(self.target.width, self.target.height)
            self.set_default_size(self.target.width, self.target.height)
            self.move(self.target.x, self.target.y)
            self.resize(self.target.width, self.target.height)
            self.expected_area = reserved_workarea(self.baseline, self.target)
            # Do not reserve a single pixel until the mapped frame, client and
            # GTK allocation actually agree with this target.
            self.pending_strut = strut
            self.mapping_phase = 'awaiting-map'
            self.mapping_verified = False
            self.panel_status.set_text('Sizing panel…')

        def mapped(self, *_args):
            if self.mode != 'panel' or self.mapping_phase != 'awaiting-map':
                return False
            if not self.target:
                self.mapping_failed('Panel target unavailable')
                return False
            self.mapping_phase = 'sizing'
            try:
                # One supported after-map request on THIS GdkWindow, in logical
                # coordinates. No focus activation or configure/resize loop.
                t = self.target
                self.map_previous_target = getattr(self, 'last_native_target', None)
                self.get_window().move_resize(t.x, t.y, t.width, t.height)
                self.last_native_target = t
                self.queue_resize()  # Re-negotiate descendants, not just the X/GdkWindow size.
                self.allocation_checks = 0
                self.allocation_deadline = GLib.get_monotonic_time() + ALLOCATION_SETTLE_US
                self.map_timer = GLib.timeout_add(300, self.verify_panel_mapping)
            except Exception:
                self.mapping_failed('After-map sizing unavailable')
            return False

        def web_allocation_matches(self, width, height):
            if self.web is None or self.stack.get_visible_child_name() != 'web':
                return True
            stack = self.stack.get_allocation()
            web = self.web.get_allocation()
            grip = self.resize_handle.get_allocation()
            return (stack.width == width - grip.width and 0 < stack.height <= height
                    and (web.width, web.height) == (stack.width, stack.height))

        def actual_frame(self):
            if not self.x11 or not self.reservation:
                raise ValueError('Native frame reader unavailable')
            monitor = self.get_display().get_primary_monitor() or self.get_display().get_monitor(0)
            scale = monitor.get_scale_factor() if monitor else None
            frame = self.x11.frame_geometry(self.reservation.xid)
            if (type(scale) is not int or scale < 1 or len(frame) != 4
                    or any(type(v) is not int or v % scale for v in frame)):
                raise ValueError('Native frame scale unavailable')
            return Rect(*(v // scale for v in frame))

        def mapping_matches(self):
            if not self.get_mapped() or not self.target or not self.get_window():
                return False
            native = self.get_window()
            self.mapping_frame = self.actual_frame()
            _, _, width, height = native.get_geometry()
            allocation = self.get_allocation()
            t = self.target
            return (self.mapping_frame == t and (width, height) == (t.width, t.height)
                    and (allocation.width, allocation.height) == (t.width, t.height)
                    and self.web_allocation_matches(t.width, t.height))

        def allocation_may_settle(self):
            # Before reservation only: GTK/WebKit can lag a completed native
            # resize, or the immediately preceding owned request can be in flight.
            # Unknown frame/client geometry is not a layout-settling candidate.
            if not self.get_mapped() or not self.get_window() or (self.reservation and self.reservation.active):
                return False
            known = [t for t in (self.target, self.map_previous_target) if t is not None]
            _, _, width, height = self.get_window().get_geometry()
            return (self.mapping_frame in known
                    and (width, height) in [(t.width, t.height) for t in known])

        def capture_root_area_proof(self):
            """Optional witness only for a single full-baseline root-origin monitor.

            Capture immediately BEFORE applying our strut. Existing docks or an
            unproven/invalid root baseline disable this witness, not the GDK path.
            """
            self.root_area_proof = None
            try:
                if not self.x11 or self.expected_area is None or len(self.last_topology) != 1:
                    return
                geometry, scale = self.last_topology[0]
                if (type(scale) is not int or scale < 1 or geometry != self.baseline
                        or geometry.x != 0 or geometry.y != 0
                        or self.x11.root_size != (geometry.width * scale, geometry.height * scale)):
                    return
                full = Rect(0, 0, *self.x11.root_size)
                desktop, area = read_root_workarea(self.x11)
                if area == full:
                    expected = self.expected_area
                    self.root_area_proof = (desktop, full, Rect(expected.x * scale, expected.y * scale,
                                                              expected.width * scale, expected.height * scale))
            except Exception:
                self.root_area_proof = None

        def verify_panel_mapping(self):
            self.map_timer = 0
            if self.mode != 'panel' or self.mapping_phase not in ('sizing', 'reserved'):
                return False
            try:
                if self.topology() != self.last_topology:
                    self.mapping_failed('Display changed during panel verification')
                    return False
                if not self.mapping_matches():
                    self.allocation_checks += 1
                    if (self.mapping_phase == 'sizing' and self.allocation_may_settle()
                            and self.allocation_checks < 10
                            and GLib.get_monotonic_time() < self.allocation_deadline):
                        self.map_timer = GLib.timeout_add(300, self.verify_panel_mapping)
                        return False  # Observe only; do not resize, requeue layout or reserve.
                    self.mapping_failed('Mapped frame/client/allocation differs from target')
                    return False
                if self.mapping_phase == 'sizing':
                    if GLib.get_monotonic_time() > self.allocation_deadline:
                        self.mapping_failed('Panel allocation verification timed out')
                        return False
                    self.capture_root_area_proof()
                    if not self.pending_strut or not self.reservation or not self.reservation.apply(self.pending_strut):
                        self.mapping_failed('Reservation unavailable after mapping')
                        return False
                    self.stick()  # Supported GTK/X11 hint on this mapped window.
                    # GTK nonresizable windows switch to their natural requisition,
                    # which can replace a previously verified dock size on remap.
                    # Keep negotiation enabled, with exact min/max geometry instead.
                    hints = Gdk.Geometry()
                    hints.min_width = hints.max_width = self.target.width
                    hints.min_height = hints.max_height = self.target.height
                    self.set_geometry_hints(None, hints, Gdk.WindowHints.MIN_SIZE | Gdk.WindowHints.MAX_SIZE)
                    self.set_resizable(True)
                    self.mapping_phase = 'reserved'
                    self.reservation_checks = 0
                    self.reservation_deadline = GLib.get_monotonic_time() + RESERVATION_SETTLE_US
                    self.panel_status.set_text('Pinning…')
                    # A second read verifies that WM reservation/GTK hint changes
                    # did not shrink the window. No further resize is attempted.
                    self.map_timer = GLib.timeout_add(300, self.verify_panel_mapping)
                else:
                    monitor = self.get_display().get_primary_monitor() or self.get_display().get_monitor(0)
                    if (not self.x11 or not self.reservation or not monitor or not self.pending_strut
                            or self.x11.read(self.reservation.xid, '_NET_WM_STRUT_PARTIAL', 'CARDINAL') != self.pending_strut
                            or self.x11.read(self.reservation.xid, '_NET_WM_STRUT', 'CARDINAL') != self.pending_strut[:4]):
                        self.mapping_failed('Reservation verification unavailable')
                        return False
                    current = self.rectangle(monitor.get_workarea())
                    self.reservation_checks += 1
                    now = GLib.get_monotonic_time()
                    root_verified = False
                    if current == self.baseline and self.root_area_proof is not None:
                        desktop, full, expected = self.root_area_proof
                        observed_desktop, area = read_root_workarea(self.x11)
                        if (observed_desktop != desktop or self.x11.root_size != (full.width, full.height)
                                or area not in (full, expected)):
                            self.mapping_failed('Root reservation witness changed or differs from target')
                            return False
                        root_verified = area == expected
                    if current != self.expected_area and not root_verified:
                        # Only an unchanged baseline may be asynchronous WM/GDK
                        # settling. Never retry sizing or reapply the strut.
                        if (current == self.baseline and self.reservation_checks < 10
                                and now < self.reservation_deadline):
                            self.map_timer = GLib.timeout_add(300, self.verify_panel_mapping)
                            return False
                        self.mapping_failed('Reservation work area did not settle')
                        return False
                    if now > self.reservation_deadline:
                        self.mapping_failed('Reservation verification timed out')
                        return False
                    self.mapping_phase = 'verified'
                    self.mapping_verified = True
                    self.pending_strut = None
                    self.refitting = False
                    label = self.preference.preset.title()
                    self.panel_status.set_text('●  PINNED · ' + label + ' · ' + str(self.target.width) + ' px' + ('' if self.preference_saved else ' · size not saved'))
            except Exception:
                self.mapping_failed('Mapped geometry verification unavailable')
            return False

        def configured(self, *_args):
            # No periodic polling: a later unexpected configure revokes the
            # reservation immediately rather than leaving a tiny reserved dock.
            if self.mode == 'panel' and self.reservation and self.reservation.active:
                try:
                    if not self.mapping_matches():
                        self.mapping_failed('Reserved panel geometry changed')
                except Exception:
                    self.mapping_failed('Reserved geometry unavailable')
            return False

        def choose_size(self, preset):
            if preset not in PRESETS:
                return
            self.preference = PanelPreference(preset)
            self.preference_saved = save_preference(self.preference)
            self.pin()

        def cancel_resize(self):
            if self.drag_timer:
                GLib.source_remove(self.drag_timer)
                self.drag_timer = 0
            self.dragging = False

        def begin_panel_resize(self, _handle, event):
            if (event.button != 1 or self.mode != 'panel' or not self.mapping_verified
                    or self.dragging or self.refitting):
                return False
            # DOCK interactive WM resizing was ignored on the native trial.
            # Observe this user-started gesture and resize only our GdkWindow.
            # Never resize against an active stale strut or acquire a mouse grab.
            self.clear_reservation()
            self.mapping_verified = False
            self.mapping_phase = 'dragging'
            self.dragging = True
            self.drag_checks = 0
            try:
                if self.target is None or self.baseline is None:
                    raise ValueError('Resize target unavailable')
                self.drag_device = event.get_device()
                self.drag_monitor = (self.get_display().get_primary_monitor()
                                     or self.get_display().get_monitor(0))
                if self.drag_device is None or self.drag_monitor is None:
                    raise ValueError('Resize device unavailable')
                self.drag_topology = self.topology()
                self.drag_geometry = self.rectangle(self.drag_monitor.get_geometry())
                self.drag_initial = self.drag_target = self.target
                self.drag_press_x = int(event.x_root)
                self.drag_released = False
                self.drag_settle_checks = 0
                self.drag_deadline = GLib.get_monotonic_time() + RESIZE_TIMEOUT_US
                maximum = pointer_sized_panel(self.target, self.drag_geometry, self.baseline,
                                              self.drag_press_x, self.drag_press_x - MAX_WIDTH)
                self.set_resizable(True)
                self.set_size_request(MIN_WIDTH, self.target.height)
                hints = Gdk.Geometry()
                hints.min_width, hints.max_width = MIN_WIDTH, maximum.width
                hints.min_height = hints.max_height = self.target.height
                self.set_geometry_hints(None, hints, Gdk.WindowHints.MIN_SIZE | Gdk.WindowHints.MAX_SIZE)
                self.panel_status.set_text('Resize panel · Escape to cancel')
                self.drag_timer = GLib.timeout_add(RESIZE_POLL_MS, self.finish_panel_resize)
            except Exception:
                self.cancel_resize()
                self.pin()  # Restore the last preference through the mapping gate.
            return True

        def finish_panel_resize(self):
            if not self.dragging or self.mode != 'panel':
                self.drag_timer = 0
                return False
            try:
                if self.target is None or self.baseline is None:
                    raise ValueError('Resize target unavailable')
                if (self.topology() != self.drag_topology
                        or self.rectangle(self.drag_monitor.get_workarea()) not in (self.baseline, self.expected_area)):
                    raise ValueError('Display changed during resize')
                self.drag_checks += 1
                if GLib.get_monotonic_time() >= self.drag_deadline or self.drag_checks >= 2000:
                    raise ValueError('Resize did not finish')
                native = self.get_window()
                if not self.drag_released:
                    _child, x, y, state = native.get_device_position(self.drag_device)
                    # Device coordinates are relative to this moving window.
                    # GDK translates them to logical root coordinates; do not
                    # add the original x or multiply by monitor scale again.
                    root_x, _root_y = native.get_root_coords(x, y)
                    target = pointer_sized_panel(self.drag_initial, self.drag_geometry, self.baseline,
                                                 self.drag_press_x, root_x)
                    if target != self.drag_target:
                        native.move_resize(target.x, target.y, target.width, target.height)
                        self.last_native_target = target
                        self.queue_resize()
                        self.drag_target = target
                    if state & Gdk.ModifierType.BUTTON1_MASK:
                        return True
                    self.drag_released = True  # Freeze width at release, not later pointer motion.
                    self.drag_settle_deadline = GLib.get_monotonic_time() + ALLOCATION_SETTLE_US
                frame = self.actual_frame()
                self.mapping_frame = frame
                _, _, width, height = native.get_geometry()
                allocation = self.get_allocation()
                if (frame != self.drag_target
                        or (width, height) != (frame.width, frame.height)
                        or (allocation.width, allocation.height) != (width, height)
                        or not self.web_allocation_matches(width, height)):
                    self.drag_settle_checks += 1
                    if (self.drag_settle_checks < 100
                            and GLib.get_monotonic_time() < self.drag_settle_deadline):
                        return True  # Bounded allocation settling; never retry resize requests.
                    raise ValueError('Resize geometry unavailable')
                if GLib.get_monotonic_time() > self.drag_settle_deadline:
                    raise ValueError('Resize allocation verification timed out')
                if frame.width != self.target.width:
                    self.preference = PanelPreference('custom', frame.width)
                    self.preference_saved = save_preference(self.preference)
                self.drag_timer = 0
                self.dragging = False
                self.pin()  # Unchanged mapping gate verifies the new strut.
            except Exception:
                self.drag_timer = 0
                self.cancel_resize()
                self.pin()  # Device/time/geometry failures never replace the preference.
            return False

        def mapping_failed(self, reason):
            measured = {}
            try:
                native = self.get_window()
                allocation = self.get_allocation()
                measured = {'phase': self.mapping_phase, 'clientLogical': list(native.get_geometry()),
                            'gtkAllocation': [allocation.width, allocation.height],
                            'toolkitFrameLogical': vars(self.rectangle(native.get_frame_extents())),
                            'stackAllocation': [self.stack.get_allocation().width, self.stack.get_allocation().height],
                            'webAllocation': [self.web.get_allocation().width, self.web.get_allocation().height] if self.web else None}
            except Exception:
                pass
            self.clear_reservation()  # Release first, before any fallback/remap.
            print(json.dumps({'panelMapping': 'failed', 'measurements': measured, 'reason': reason,
                              'configuredLogical': vars(self.target) if self.target else None,
                              'mappedFrameLogical': vars(self.mapping_frame) if self.mapping_frame else None}),
                  file=sys.stderr, flush=True)
            self.float_window(reason='Panel size unavailable · floating')

        def float_window(self, compact=False, reload=True, reason=None):
            self.cancel_refit()
            self.refitting = True
            self.clear_reservation()
            was_visible = self.get_visible()
            if was_visible:
                self.hide()
            self.mode = 'compact' if compact else 'float'
            self.unstick()  # Restore an ordinary, current-workspace app window.
            self.set_type_hint(Gdk.WindowTypeHint.NORMAL)
            self.set_skip_taskbar_hint(False)
            self.set_decorated(True)
            self.set_resizable(True)
            self.set_geometry_hints(None, Gdk.Geometry(), 0)
            self.set_size_request(1, 1)  # Undo the pinned target's minimum size.
            display = self.get_display()
            monitor = display.get_primary_monitor() or display.get_monitor(0)
            if monitor:
                area = self.rectangle(monitor.get_workarea())
                self.set_default_size(min(480 if compact else 960, area.width), min(760, area.height))
                self.resize(min(480 if compact else 960, area.width), min(760, area.height))
                self.move(area.x + max(0, area.width - min(480 if compact else 960, area.width)), area.y)
            self.panel_status.set_text(reason or ('Compact' if compact else 'Floating · drag title bar to move'))
            self.refitting = False
            if was_visible:
                self.show_all()
            if reload:
                self.load_for_mode()

        def before_close(self, *_args):
            self.cancel_refit()
            self.clear_reservation()
            return False

        def destroyed(self, *_args):
            self.cancel_refit()
            if self.diagnostic_timer:
                GLib.source_remove(self.diagnostic_timer)
            # On destruction X11 removes the window's properties automatically.
            # Do not write to a dead XID (which could have been reused).
            if self.x11:
                self.x11.close()
            Gtk.main_quit()

        def report(self):
            self.diagnostic_timer = 0
            self.configured()  # Never report a known undersized reserved panel.
            frame = self.get_window().get_frame_extents()
            data = {'mode': self.mode, 'configuredLogical': vars(self.target) if self.target else None,
                    'mappedFrameLogical': vars(self.actual_frame()),
                    'toolkitFrameLogical': vars(self.rectangle(frame)),
                    'mappingPhase': self.mapping_phase, 'mappingVerified': self.mapping_verified,
                    'reservationRequested': bool(self.reservation and self.reservation.active),
                    'reservationSupported': bool(self.reservation and self.reservation.supported()),
                    'ownStrutPhysical': self.x11.read(self.reservation.xid, '_NET_WM_STRUT_PARTIAL', 'CARDINAL') if self.x11 and self.reservation else [],
                    'rootWorkareaPhysical': self.x11.read(self.x11.root, '_NET_WORKAREA', 'CARDINAL') if self.x11 else []}
            print(json.dumps(data), flush=True)
            # Intentionally no records, URLs, arbitrary JS, paths or window list.
            if self.web and allowed_navigation(self.web.get_uri()):
                script = "JSON.stringify({day:document.querySelector('#date')?.textContent,work:document.querySelectorAll('#task-list .task-card').length,quests:document.querySelectorAll('#quest-segments .quest-slot').length,widgets:document.querySelectorAll('.typed-widget').length})"
                def finished(web, result, *_):
                    try:
                        print(web.run_javascript_finish(result).get_js_value().to_string(), flush=True)
                    except Exception:
                        print('{"dom":"unavailable"}', flush=True)
                self.web.run_javascript(script, None, finished, None)
            return False

        def key(self, _window, event):
            if event.keyval == Gdk.KEY_Escape and self.dragging:
                self.cancel_resize()
                self.pin()
                return True
            if event.state & Gdk.ModifierType.MOD1_MASK:
                for keyval, preset in zip((Gdk.KEY_1, Gdk.KEY_2, Gdk.KEY_3), PRESETS):
                    if event.keyval == keyval:
                        self.choose_size(preset)
                        return True
            if event.keyval == Gdk.KEY_w and event.state & Gdk.ModifierType.CONTROL_MASK:
                self.close()
                return True
            return False

        def load_for_mode(self):
            desired = WIDGET_URI if self.mode == 'compact' else PANEL_URI
            if self.web:
                current = self.web.get_uri()
                if allowed_navigation(current) and urlsplit(current)._replace(fragment='') == urlsplit(desired):
                    return  # A presentation resize must not reload/dismiss the user's draft.
            self.load()

        def authenticated_load(self, url):
            self.bootstrap_uri = url
            self.web.load_uri(url)

        def auth_failed(self, text):
            self.message.set_text(text)
            self.stack.set_visible_child_name('unavailable')

        def load(self):
            if self.web:
                self.message.set_text('Connecting to Nagi…')
                self.stack.set_visible_child_name('unavailable')
                self.auth_recovery.request()

        def loaded(self, web, event):
            if event == WebKit2.LoadEvent.COMMITTED and (allowed_navigation(web.get_uri()) or web.get_uri() == getattr(self, 'bootstrap_uri', None)):
                self.stack.set_visible_child_name('web')

        def failed(self, *_args):
            self.message.set_text('Updates unavailable.\nPlease try again in a moment.')
            self.stack.set_visible_child_name('unavailable')
            return True

        def policy(self, _web, decision, kind):
            if kind in (WebKit2.PolicyDecisionType.NAVIGATION_ACTION, WebKit2.PolicyDecisionType.NEW_WINDOW_ACTION):
                action = decision.get_navigation_action()
                uri = action.get_request().get_uri()
                if kind == WebKit2.PolicyDecisionType.NAVIGATION_ACTION and (allowed_navigation(uri) or uri == getattr(self, 'bootstrap_uri', None)):
                    decision.use()
                else:
                    decision.ignore()
                    gesture = bool(hasattr(action, 'is_user_gesture') and action.is_user_gesture())
                    try:
                        opened = open_panel_external(uri, gesture, _web.get_uri(), lambda url: Gio.AppInfo.launch_default_for_uri(url, None))
                    except Exception:
                        opened = False
                    if not opened:
                        self.message.set_text('This link couldn’t open. Only supported lesson links or the ChatGPT homepage can open in your browser.')
                        self.stack.set_visible_child_name('unavailable')
                return True
            if kind == WebKit2.PolicyDecisionType.RESPONSE:
                response = decision.get_response()
                uri = response.get_uri()
                if not (allowed_navigation(uri) or uri == getattr(self, 'bootstrap_uri', None)) or not decision.is_mime_type_supported():
                    decision.ignore()
                    return True
                return False
            decision.ignore()  # New windows never open external apps.
            return True

        def deny_permission(self, _web, request):
            request.deny()
            return True

        def deny_authentication(self, _web, request):
            request.cancel()
            return True

    Widget()
    Gtk.main()
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv == ['--check-health']:
        return 0 if check_health() else 1  # Deliberately lock-free and GUI-free.
    import argparse
    parser = argparse.ArgumentParser(description='Fixed-origin, read-only desktop companion. No backend is started.')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--panel', action='store_true', help='Right-anchored reserved panel (default)')
    modes.add_argument('--compact', action='store_true', help='Original movable compact window')
    modes.add_argument('--float', action='store_true', help='Movable, unreserved panel layout')
    parser.add_argument('--unavailable', action='store_true')
    parser.add_argument('--size', choices=PRESETS, help='Saved panel size: Compact 640px, Medium 960px (initial default), Large right third')
    parser.add_argument('--diagnostics', action='store_true', help='Print own geometry and bounded DOM counts once after five seconds')
    args = parser.parse_args(argv)
    return launch_gui(args.unavailable, 'compact' if args.compact else 'float' if args.float else 'panel', args.diagnostics, args.size)


if __name__ == '__main__':
    sys.exit(main())
