#!/usr/bin/env python3
"""Nagi's Linux tray item and its Quick glance panel.

Reuses the existing app lock, private WebKit storage, navigation policy and
native session recovery. No desktop reservation, board writer, backend or
additional service. The tray label and tooltip come from tray.py.
"""
import math
import re
import signal
import sys
import threading
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from widget import ORIGIN, InstanceLock, AlreadyRunning, private_web_settings, scoped_web_context, panel_input_rect, apply_input_shape

GLANCE_URI = ORIGIN + '/glance'
DASHBOARD_URI = ORIGIN + '/overview'
SECTIONS = ('agents','limits','ended')
ICON_DIR = str(Path(__file__).resolve().parent / 'icons')
PANEL_WIDTH = 400
MIN_HEIGHT, MAX_HEIGHT = 320, 690
BAR_GAP, SCREEN_EDGE = 4, 8
TOGGLE_GRACE_US = 350_000  # a click that just closed the panel by focus loss does not reopen it
TRAY_GLYPH = '#ffffff'  # GNOME's top bar is dark in both appearances
EMBED_WAIT_MS = 2500  # how long a tray icon may take to be embedded before the indicator takes over


def tray_glyph_svg(color=TRAY_GLYPH):
    """The 凪 glyph for a tray that draws the app's own pixels (no symbolic recolouring)."""
    svg = (Path(ICON_DIR) / 'nagi-symbolic.svg').read_text()
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
        raise ValueError('colour must be #rrggbb')
    return svg.replace('fill="#bebebe"', f'fill="{color}"')


def wants_tray_icon(display):
    """One click should open the panel. GNOME's AppIndicator extension always opens an
    indicator's menu on a left click, but hands clicks on a legacy (XEmbed) tray icon straight
    to the app. That needs X11; elsewhere the indicator, with its menu, is the only choice."""
    return display is not None and 'X11' in type(display).__name__

def glance_page(uri):
    return uri == GLANCE_URI or uri in {GLANCE_URI+'#'+section for section in SECTIONS}

def glance_destination(uri):
    from nagi_links import thread_links
    try:return bool(glance_page(uri) or uri in {DASHBOARD_URI,*{DASHBOARD_URI+'#'+section for section in SECTIONS}} or thread_links(uri))
    except (ValueError,UnicodeError):return False


def panel_message(value):
    """The page's only native messages: `ready`, `close` and `height:<px>`."""
    if value in ('ready','close'):return (value,None)
    match = re.fullmatch(r'height:([1-9][0-9]{1,3})', value) if isinstance(value,str) else None
    return ('height',max(MIN_HEIGHT,min(MAX_HEIGHT,int(match.group(1))))) if match else None


def panel_origin(work, screen, pointer, width=PANEL_WIDTH):
    """Top-left for a panel 4 px under the bar, right edge on the indicator.

    work and screen are (x, y, width, height) of the monitor's work area and full
    geometry; pointer is where the click happened. A click near the bar anchors the
    panel's right edge just past it; otherwise it sits at the work area's right edge.
    The panel stays at least 8 px from the screen edges."""
    wx, wy, ww, _wh = work
    sx, _sy, sw, _sh = screen
    if pointer is not None and sx <= pointer[0] < sx + sw and pointer[1] < wy + 160:
        right = pointer[0] + 14
    else:
        right = wx + ww - SCREEN_EDGE
    right = max(sx + SCREEN_EDGE + width, min(sx + sw - SCREEN_EDGE, right))
    return right - width, wy + BAR_GAP


# The rounded shell: a transparent margin (top, sides, bottom, CSS px) holds the shadow.
SHELL_MARGINS = (4, 16, 28)
SHELL_CSS = (
    'html, body { background: transparent !important; }\n'
    '.panel { margin: 4px 16px 0 !important; height: calc(100vh - 32px) !important;'
    ' border-radius: 12px !important; overflow: hidden !important; background: var(--bg) !important;'
    ' box-shadow: 0 0 0 .5px rgb(0 0 0 / .30), 0 10px 24px rgb(0 0 0 / .34) !important; }\n')


def window_frame(x, y, css_height, scale, margins, top_limit):
    """Window rect for a panel whose visible top-left is (x, y): the margins wrap it."""
    top, side, bottom = margins
    wx = x - round(side * scale)
    wy = max(top_limit, y - round(top * scale))
    return wx, wy, math.ceil((PANEL_WIDTH + 2 * side) * scale), math.ceil((css_height + top + bottom) * scale)


def page_scale(resolution):
    """Window pixels per CSS px: the font resolution over 96, never below 1."""
    try:
        value = float(resolution)
    except (TypeError, ValueError):
        return 1.0
    return max(1.0, min(3.0, value / 96)) if value > 0 else 1.0


def follow_system_theme(Gio, Gtk):
    """WebKitGTK reads GTK's dark preference; GNOME keeps it in color-scheme."""
    source = Gio.SettingsSchemaSource.get_default()
    schema = source.lookup('org.gnome.desktop.interface', True) if source else None
    if schema is None or not schema.has_key('color-scheme'):
        return None
    interface = Gio.Settings.new('org.gnome.desktop.interface')
    gtk = Gtk.Settings.get_default()
    def apply(*_):
        gtk.set_property('gtk-application-prefer-dark-theme', interface.get_string('color-scheme') == 'prefer-dark')
    apply()
    interface.connect('changed::color-scheme', apply)
    return interface


def run(port=47831, *, preview=False):
    """preview=True is a review copy beside an installed tray: no app lock, no
    banners and its own indicator id. Everything else is the same code path."""
    global ORIGIN,GLANCE_URI,DASHBOARD_URI
    if type(port) is not int or not 1024<=port<=65535:return 2
    ORIGIN=f'http://127.0.0.1:{port}';GLANCE_URI=ORIGIN+'/glance';DASHBOARD_URI=ORIGIN+'/overview'
    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('WebKit2', '4.1')
    gi.require_version('AyatanaAppIndicator3', '0.1')
    from gi.repository import Gtk, Gdk, GdkPixbuf, Gio, GLib, WebKit2, AyatanaAppIndicator3
    from tray import sources_tooltip, read_state, POLL_SECONDS

    guard = InstanceLock()
    if not preview:
        try:
            guard.acquire()
        except AlreadyRunning:
            print('Nagi is already running. Use its existing panel.', file=sys.stderr)
            return 2
    try:
        theme = follow_system_theme(Gio, Gtk)
        window = Gtk.Window(title='Nagi')
        screen = window.get_screen()
        # WebKitGTK renders CSS px at the desktop's text scale (Xft.dpi / 96), so the
        # panel's 400 × 690 CSS px take that many more window pixels.
        scale = page_scale(screen.get_resolution() if screen else -1)
        width = math.ceil(PANEL_WIDTH * scale)
        # With a compositor the panel is a rounded sheet with a soft shadow in a transparent
        # margin; without one it stays a plain rectangle (no alpha to round against).
        rounded = bool(screen and screen.is_composited() and screen.get_rgba_visual())
        margins = SHELL_MARGINS if rounded else (0, 0, 0)
        _x, _y, frame_w, frame_min = window_frame(0, 0, MIN_HEIGHT, scale, margins, 0)
        window.set_default_size(frame_w, window_frame(0, 0, MAX_HEIGHT, scale, margins, 0)[3])
        window.set_size_request(frame_w, frame_min)
        window.set_decorated(False)
        window.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        window.set_skip_taskbar_hint(True)
        window.set_skip_pager_hint(True)
        window.set_keep_above(True)
        if rounded:
            window.set_visual(screen.get_rgba_visual())
            window.set_app_paintable(True)
        provider = Gtk.CssProvider()
        provider.load_from_data(b'window {background: transparent;}')
        window.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        context = scoped_web_context(WebKit2)
        context.get_cookie_manager().set_accept_policy(WebKit2.CookieAcceptPolicy.NEVER)
        context.connect('download-started', lambda _context, download: download.cancel())
        web = WebKit2.WebView(web_context=context)
        private_web_settings(web.get_settings(), WebKit2)
        colour = Gdk.RGBA()
        colour.parse('rgba(0,0,0,0)')
        web.set_background_color(colour)
        stack = Gtk.Stack()
        stack.add_named(web, 'web')
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_border_width(24)
        message = Gtk.Label(label='Connecting to Nagi…')
        message.set_line_wrap(True)
        box.pack_start(message, True, True, 0)
        retry = Gtk.Button(label='Try again')
        box.pack_start(retry, False, False, 0)
        stack.add_named(box, 'message')
        window.add(stack)
        bootstrap_uri = None
        state = {'height': MAX_HEIGHT, 'size_pending': False, 'ready': False, 'settings': False, 'hidden_at': 0, 'anchor': None}

        def anchor():
            display = window.get_display()
            pointer = None
            try:
                _screen, px, py = display.get_default_seat().get_pointer().get_position()
                pointer = (px, py)
            except (AttributeError, TypeError, ValueError):
                pass
            monitor = (display.get_monitor_at_point(*pointer) if pointer else None) or display.get_primary_monitor() or display.get_monitor(0)
            if not monitor:
                return None
            work, geo = monitor.get_workarea(), monitor.get_geometry()
            # A middle click lands on the indicator itself; a menu item sits below it, so a
            # menu open reuses the last x seen on the bar.
            if pointer and pointer[1] < work.y:
                state['bar_x'] = pointer[0]
            elif pointer and pointer[1] < work.y + 160 and state.get('bar_x') is not None:
                pointer = (state['bar_x'], geo.y)
            x, y = panel_origin((work.x, work.y, work.width, work.height), (geo.x, geo.y, geo.width, geo.height), pointer, width)
            return x, y, work.y, max(MIN_HEIGHT, int((work.y + work.height - y - SCREEN_EDGE) / scale) - margins[0] - margins[2])

        def place():
            if state['anchor'] is None:
                return
            x, y, top_limit, room = state['anchor']
            wx, wy, ww, wh = window_frame(x, y, min(state['height'], room), scale, margins, top_limit)
            window.resize(ww, wh)
            window.move(wx, wy)

        def show(*_):
            state['anchor'] = anchor()
            place()
            state['size_pending'] = True
            window.show_all()
            window.present()
            web.grab_focus()
            recovery.shown()

        def hide(*_):
            if window.get_visible():
                state['hidden_at'] = GLib.get_monotonic_time()
            recovery.hidden()
            window.hide()
            return True

        def toggle(*_):
            if window.get_visible():
                hide()
                # The grace is for a click that arrives after focus loss already closed the
                # panel; a click that closes it itself leaves the next click free to reopen.
                state['hidden_at'] = 0
            elif GLib.get_monotonic_time() - state['hidden_at'] > TOGGLE_GRACE_US:
                show()

        def run_page(script):
            try:
                web.evaluate_javascript(script, -1, None, None, None, None, None)
            except (AttributeError, TypeError):
                web.run_javascript(script, None, None, None)

        def open_settings(*_):
            if window.get_visible() and state['ready']:
                run_page('window.NagiGlance && window.NagiGlance.openSettings()')
            else:
                state['settings'] = True
                show()

        def key(_window, event):
            # The page owns Esc (sheet first, then the panel); this covers the native message view.
            if event.keyval == Gdk.KEY_Escape and stack.get_visible_child_name() == 'message':
                return hide()
            return False

        def policy(_web, decision, kind):
            if kind not in (WebKit2.PolicyDecisionType.NAVIGATION_ACTION, WebKit2.PolicyDecisionType.NEW_WINDOW_ACTION):
                return False
            action = decision.get_navigation_action()
            uri = action.get_request().get_uri()
            if kind == WebKit2.PolicyDecisionType.NAVIGATION_ACTION and (glance_page(uri) or (bootstrap_uri is not None and uri == bootstrap_uri)):
                decision.use()
            else:
                decision.ignore()
                gesture = bool(action.is_user_gesture())
                try:
                    def opener(url):
                        from owner_auth import launch_url
                        if url.startswith(ORIGIN + '/'):
                            url = launch_url(ORIGIN, url[len(ORIGIN):].split('#')[0])
                        from nagi_links import open_thread
                        native=lambda target:Gio.AppInfo.launch_default_for_uri(target,None)
                        if not url.startswith(ORIGIN+'/'):
                            return open_thread(url,native,lambda scheme:Gio.AppInfo.get_default_for_uri_scheme(scheme) is not None)
                        native(url)
                        return True
                    opened = (gesture and glance_page(web.get_uri())
                              and glance_destination(uri) and opener(uri))
                except Exception:
                    opened = False
                if opened:
                    hide()
            return True

        def panel_signal(_manager, result):
            try:
                value = result.get_js_value()
                if not (glance_page(web.get_uri()) and value.is_string()):
                    return
                parsed = panel_message(value.to_string())
            except (AttributeError, TypeError, ValueError):
                return
            if parsed is None:
                return
            kind, height = parsed
            if kind == 'close':
                hide()
            elif kind == 'ready':
                state['ready'] = True
                if state['settings']:
                    state['settings'] = False
                    run_page('window.NagiGlance && window.NagiGlance.openSettings()')
            elif kind == 'height':
                state['height'] = height
                if state['size_pending'] and window.get_visible():
                    state['size_pending'] = False  # the panel resizes only on open
                    place()

        web.connect('decide-policy', policy)
        web.connect('create', lambda *_: None)
        web.connect('permission-request', lambda _web, request: (request.deny(), True)[1])
        web.connect('authenticate', lambda _web, request: (request.cancel(), True)[1])
        manager = web.get_user_content_manager()
        if rounded:
            # A native user stylesheet applies before the page's first paint and outside its CSP.
            manager.add_style_sheet(WebKit2.UserStyleSheet.new(SHELL_CSS, WebKit2.UserContentInjectedFrames.TOP_FRAME,
                WebKit2.UserStyleLevel.USER, None, None))
        manager.connect('script-message-received::nagiPanel', panel_signal)
        if not manager.register_script_message_handler('nagiPanel'):
            raise ValueError('Native panel channel unavailable')
        if rounded:
            # Only the visible panel takes clicks; the shadow margin passes them to the desktop.
            shaped = {'size': None}
            def reshape(widget, allocation):
                size = (allocation.width, allocation.height)
                if size != shaped['size']:
                    shaped['size'] = size
                    apply_input_shape(widget, panel_input_rect(size[0], size[1], scale, margins))
            window.connect('size-allocate', reshape)
        window.connect('delete-event', hide)
        window.connect('key-press-event', key)
        window.connect('focus-out-event', hide)

        menu = Gtk.Menu()
        items = []
        for title, callback in [('Open Nagi', toggle), ('Settings…', open_settings), (None, None), ('Quit Nagi', lambda *_: Gtk.main_quit())]:
            item = Gtk.SeparatorMenuItem() if title is None else Gtk.MenuItem(label=title)
            if callback:
                item.connect('activate', callback)
            menu.append(item)
            items.append(item)
        menu.show_all()
        tray = {'icon': None, 'indicator': None, 'title': 'Nagi'}

        def indicator_shown(on):
            # Created once, then only shown or hidden, so there is never a second item.
            if tray['indicator'] is None:
                if not on:
                    return
                # Middle click toggles the panel. GNOME's AppIndicator extension opens this menu
                # on a left click (it ignores ItemIsMenu), so `Open Nagi` is its first item.
                indicator = AyatanaAppIndicator3.Indicator.new_with_path('nagi-preview' if preview else 'company-desk', 'nagi-symbolic',
                    AyatanaAppIndicator3.IndicatorCategory.APPLICATION_STATUS, ICON_DIR)
                indicator.set_title(tray['title'])
                indicator.set_menu(menu)
                indicator.set_secondary_activate_target(items[0])
                tray['indicator'] = indicator
            tray['indicator'].set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE if on else AyatanaAppIndicator3.IndicatorStatus.PASSIVE)

        def glyph(size):
            loader = GdkPixbuf.PixbufLoader.new_with_type('svg')
            loader.set_size(size, size)
            loader.write(tray_glyph_svg().encode())
            loader.close()
            return loader.get_pixbuf()

        def use_tray_icon():
            # A left click opens or closes the panel at once; a right click shows the menu.
            # Gtk.StatusIcon is deprecated in GTK 3 but is the only click-through tray item here.
            try:
                first = glyph(22)
            except (GLib.Error, OSError, ValueError):
                return False
            warnings.filterwarnings('ignore', message=r'Gtk\.StatusIcon', category=DeprecationWarning)
            icon = Gtk.StatusIcon()
            icon.set_name('nagi-preview' if preview else 'nagi')
            icon.set_title('Nagi')
            icon.set_tooltip_text(tray['title'])
            icon.set_from_pixbuf(first)

            def resized(i, size):
                try:
                    i.set_from_pixbuf(glyph(max(16, size)))
                except (GLib.Error, OSError, ValueError):
                    pass  # keep the glyph it has
                return True
            icon.connect('activate', toggle)
            icon.connect('popup-menu', lambda i, button, when: menu.popup(None, None, Gtk.StatusIcon.position_menu, i, button, when))
            icon.connect('size-changed', resized)
            tray['icon'] = icon

            # The indicator stands in whenever no tray host holds the icon: at start after a short
            # wait, and later if the host goes away; it steps back when a host takes the icon.
            def settle():
                tray['wait'] = None
                indicator_shown(not icon.is_embedded())
                return False
            icon.connect('notify::embedded', lambda *_: tray['wait'] is None and indicator_shown(not icon.is_embedded()))
            icon.set_visible(True)
            tray['wait'] = GLib.timeout_add(EMBED_WAIT_MS, settle)
            return True

        tray['wait'] = None
        if not (wants_tray_icon(Gdk.Display.get_default()) and use_tray_icon()):
            indicator_shown(True)

        def set_tray_title(text):
            # The owner wants the glyph alone in the bar; the summary lives in the tooltip.
            tray['title'] = text
            if tray['icon'] is not None:
                tray['icon'].set_tooltip_text(text)
            if tray['indicator'] is not None:
                tray['indicator'].set_label('', '')
                tray['indicator'].set_title(text)

        def update_tray(envelope):
            set_tray_title(sources_tooltip(envelope))
            return False

        def reader_down():
            set_tray_title("Nagi · can't reach its local reader")
            return False

        def poll_tray():
            def work():
                try:
                    envelope = read_state(ORIGIN)
                except Exception:
                    GLib.idle_add(reader_down)
                else:
                    GLib.idle_add(update_tray, envelope)
            threading.Thread(target=work, daemon=True).start()
            return True

        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, lambda: (Gtk.main_quit(), False)[1])
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, lambda: (Gtk.main_quit(), False)[1])
        from owner_auth import launch_url
        from native_auth import gtk_recovery, bind_auth_signal
        def load(url):
            nonlocal bootstrap_uri
            bootstrap_uri = url
            state['ready'] = False
            stack.set_visible_child_name('web')
            web.load_uri(url)
        def error(text):
            message.set_text(text)
            stack.set_visible_child_name('message')
        recovery = gtk_recovery(GLib, lambda: launch_url(ORIGIN, '/glance'), load, error)
        bind_auth_signal(web, lambda uri: glance_page(uri) or (bootstrap_uri is not None and uri == bootstrap_uri), recovery.request)
        retry.connect('clicked', lambda *_: (message.set_text('Connecting to Nagi…'), recovery.request()))
        window.connect('unmap', lambda *_: recovery.hidden())
        window.connect('destroy', lambda *_: recovery.hidden())
        stack.set_visible_child_name('message')
        notifier = None
        panel_application = None
        if not preview:
            from agent_notifications import PANEL_APP_ID, start_gio
            panel_application=Gio.Application(application_id=PANEL_APP_ID,flags=Gio.ApplicationFlags.FLAGS_NONE)
            panel_action=Gio.SimpleAction.new('open',None)
            panel_action.connect('activate',lambda *_:show())
            panel_application.add_action(panel_action);panel_application.register(None)
            notifier = start_gio(GLib,Gio,lambda url:Gio.AppInfo.launch_default_for_uri(url,None),ORIGIN,on_panel=show)
        poll_tray()
        tray_timer = GLib.timeout_add_seconds(POLL_SECONDS, poll_tray)
        show()
        Gtk.main()
        GLib.source_remove(tray_timer)
        if notifier is not None:
            from agent_notifications import stop_notifier
            stop_notifier(GLib,notifier)
        if tray['wait'] is not None:
            GLib.source_remove(tray['wait'])
        if tray['indicator'] is not None:
            tray['indicator'].set_status(AyatanaAppIndicator3.IndicatorStatus.PASSIVE)
        if tray['icon'] is not None:
            tray['icon'].set_visible(False)
        window.destroy()
        del theme
        return 0
    finally:
        guard.release()


if __name__ == '__main__':
    sys.exit(run())
