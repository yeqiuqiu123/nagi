"""Linux glance shell: tray label and tooltip, panel messages and placement, and
the public panel assets. Pure checks; no GTK, DBus or T3 access."""
from datetime import datetime
import json
from pathlib import Path
import sys
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'linux'))
import tray
import notifications
import server

AT = '2026-11-12T23:05:00+00:00'
NOW = datetime.fromisoformat(AT)


def glance(status, counts=None, reason=None):
    data = {'projects': [], 'ended': [], 'counts': {'running': 0, 'waitingOnYou': 0, 'stuck': 0, 'ended': 0, **(counts or {})}} if status in ('ok', 'quiet', 'last_known') else None
    return {'version': 2, 'agents': {'status': status, 'attemptedAt': AT, 'checkedAt': AT if data else None, 'reason': reason, 'data': data}}


def limits(empty, variant=None):
    reset = '2026-11-12T22:00:00Z' if variant == 'expired' else '2026-11-16T14:58:29Z'
    window = {'id': 'primary', 'label': 'Weekly', 'kind': 'weekly', 'remainingPercent': 0 if empty else 12, 'resetsAt': reset, 'checkedAt': AT}
    account = {'id': 'c', 'label': 'Codex 1', 'windows': [window]}
    if variant == 'account_last_known':
        account.update(status='last_known', checkedAt='2026-11-12T22:40:00+00:00', reason='probe_failed')
    ok = {'status': 'last_known' if variant == 'last_known' else 'ok', 'attemptedAt': AT, 'checkedAt': AT, 'reason': None, 'warnings': [], 'data': {'accounts': [account]}}
    return {'version': 2, 'providers': {'codex': ok, 'claude': {'status': 'not_set_up', 'attemptedAt': AT, 'checkedAt': None, 'reason': 'not_installed', 'warnings': [], 'data': None}}}


class TrayLabel(TestCase):
    def test_label_priority_matches_the_shared_case_table(self):
        cases = json.loads((ROOT / 'tests' / 'tray-label-cases.json').read_text())
        for case in cases:
            with self.subTest(case['name']):
                agents = case['agents']
                self.assertEqual(tray.tray_label(glance(agents['status'], agents.get('counts'), agents.get('reason')), limits(case['empty'], case.get('limits')), NOW), case['expect'])

    def test_tooltip_follows_the_copy_deck(self):
        self.assertEqual(tray.tray_tooltip(glance('ok', {'running': 3}), limits(False)), 'Nagi · 3 running')
        self.assertEqual(tray.tray_tooltip(glance('ok', {'running': 3, 'stuck': 1, 'waitingOnYou': 1}), limits(False)), 'Nagi · 3 running · 1 asks you · 1 stuck')
        self.assertRegex(tray.tray_tooltip(glance('ok', {'running': 3}), limits(True), NOW), r'^Nagi · 3 running · Codex 1 is empty until \w{3} \d{1,2} \w{3} \d\d:\d\d$')
        self.assertRegex(tray.tray_tooltip(glance('last_known', {'running': 3}), limits(False)), r"^Nagi · can't reach T3 Code since \d\d:\d\d$")
        self.assertEqual(tray.tray_tooltip(glance('not_set_up', reason='not_configured'), limits(False)), "Nagi · T3 Code isn't connected on this computer")
        self.assertEqual(tray.tray_tooltip(glance('unavailable', reason='checking'), limits(False)), 'Nagi · checking T3 Code…')
        # Retained quota is dated in the tooltip, and a dated 0 is not called empty.
        stale = tray.tray_tooltip(glance('ok', {'running': 1}), limits(True, 'account_last_known'), NOW)
        self.assertNotIn('empty', stale)
        self.assertRegex(stale, r'^Nagi · 1 running · limits as of \d\d:\d\d$')
        self.assertNotIn('empty', tray.tray_tooltip(glance('ok', {'running': 1}), limits(True, 'expired'), NOW))

    def test_tray_reads_the_source_envelope_with_native_proofs_only(self):
        calls = []
        class Response:
            def __init__(self, body): self.body = body
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self, _n): return self.body
        envelope = {'version': 1, 'sources': [{'source': {'id': 'legacy-t3', 'harness': 't3', 'label': 'This computer', 'placement': 'local'},
                                               'agents': glance('ok', {'running': 3})['agents'], 'limits': limits(False)['providers']}],
                    'settings': {}, 'warnings': []}
        def transport(request, timeout):
            calls.append((request.full_url, request.get_method()))
            return Response(json.dumps(envelope).encode())
        env = tray.read_state('http://127.0.0.1:47861', transport)
        self.assertEqual(calls, [('http://127.0.0.1:47861/api/sources/v1/glance', 'GET')])
        self.assertEqual(tray.sources_tooltip(env), 'Nagi · 3 running')  # one source reads exactly as before

    def test_tray_tooltip_sums_fresh_sources_and_names_unread_ones(self):
        tag = lambda i: {'id': i, 'harness': 't3', 'label': i, 'placement': 'local'}
        live = {'source': tag('a'), 'agents': glance('ok', {'running': 2, 'stuck': 1})['agents'], 'limits': {}}
        other = {'source': tag('b'), 'agents': glance('ok', {'running': 1, 'waitingOnYou': 1})['agents'], 'limits': {}}
        down = {'source': tag('c'), 'agents': glance('last_known', {'running': 9})['agents'], 'limits': {}}
        self.assertEqual(tray.sources_tooltip({'sources': []}), 'Nagi · nothing connected yet')
        self.assertEqual(tray.sources_tooltip({'sources': [live, other, down]}), "Nagi · 3 running · 1 asks you · 1 stuck · 1 of 3 sources can't be read")
        self.assertEqual(tray.sources_tooltip({'sources': [down, down]}), "Nagi · can't read your sources")


class PanelShell(TestCase):
    def test_page_messages_are_closed_and_heights_clamped(self):
        self.assertEqual(notifications.panel_message('ready'), ('ready', None))
        self.assertEqual(notifications.panel_message('close'), ('close', None))
        self.assertEqual(notifications.panel_message('height:538'), ('height', 538))
        self.assertEqual(notifications.panel_message('height:2000'), ('height', 690))
        self.assertEqual(notifications.panel_message('height:120'), ('height', 320))
        for bad in ('height:0', 'height:-5', 'height:5e2', 'open', 'height:538;x', None, 42, 'reauthenticate'):
            self.assertIsNone(notifications.panel_message(bad), bad)

    def test_window_pixels_follow_the_desktop_text_scale(self):
        self.assertEqual(notifications.page_scale(96), 1.0)
        self.assertAlmostEqual(notifications.page_scale(125), 125 / 96)
        for unknown in (-1, 0, None, 'x', 50):
            self.assertEqual(notifications.page_scale(unknown), 1.0)
        self.assertEqual(notifications.page_scale(960), 3.0)

    def test_rounded_shell_wraps_the_panel_in_its_shadow_margin(self):
        # 1.3x text scale: 400 CSS px wide plus 16 px either side; 4 px top, 28 px bottom.
        self.assertEqual(notifications.window_frame(3980, 50, 536, 1.3, (4, 16, 28), 46), (3959, 46, 562, 739))
        self.assertEqual(notifications.window_frame(100, 36, 690, 1.0, (0, 0, 0), 32), (100, 36, 400, 690))
        self.assertIn('border-radius: 12px', notifications.SHELL_CSS)
        self.assertIn('background: transparent', notifications.SHELL_CSS)

    def test_shadow_margin_passes_clicks_through(self):
        import widget
        from unittest.mock import MagicMock, patch
        # 562 x 739 window at 1.3x with (4, 16, 28) CSS margins: the panel is the clickable part.
        self.assertEqual(widget.panel_input_rect(562, 739, 1.3, (4, 16, 28)), (21, 5, 520, 698))
        window = MagicMock()
        self.assertTrue(widget.apply_input_shape(window, (21, 5, 520, 698)))
        region = window.input_shape_combine_region.call_args.args[0]
        self.assertTrue(region.contains_point(30, 30))
        self.assertFalse(region.contains_point(5, 30))    # side shadow
        self.assertFalse(region.contains_point(30, 720))  # bottom shadow
        # Without cairo's GI bridge the window simply keeps taking clicks.
        with patch.dict(sys.modules, {'cairo': None}):
            self.assertFalse(widget.apply_input_shape(MagicMock(), (0, 0, 1, 1)))

    def test_panel_sits_under_the_bar_aligned_to_the_click(self):
        work, screen = (0, 32, 1920, 1048), (0, 0, 1920, 1080)
        self.assertEqual(notifications.panel_origin(work, screen, (1700, 14)), (1314, 36))
        self.assertEqual(notifications.panel_origin(work, screen, (1910, 14)), (1512, 36))  # 8 px from the edge
        self.assertEqual(notifications.panel_origin(work, screen, (40, 14)), (8, 36))
        self.assertEqual(notifications.panel_origin(work, screen, (900, 700)), (1512, 36))  # not a bar click
        self.assertEqual(notifications.panel_origin(work, screen, None), (1512, 36))
        second = ((1920, 0, 1280, 1024), (1920, 0, 1280, 1024))
        self.assertEqual(notifications.panel_origin(*second, (3100, 10)), (2714, 4))


class PanelAssets(TestCase):
    def test_panel_assets_are_routed_and_fonts_bundled_with_licences(self):
        for route in ('/nagi-glance.js', '/nagi-model.js', '/nagi-motion.js', '/nagi-icons.js', '/nagi-glance.css', '/nagi-sheet.css', '/fonts/inter-opsz.woff2', '/fonts/nagi-glyph-serif.woff2'):
            self.assertIn(route, server.FILES)
            self.assertTrue((ROOT / 'web' / server.FILES[route]).is_file(), route)
        self.assertEqual(server.TYPES['.woff2'], 'font/woff2')
        fonts = ROOT / 'web' / 'fonts'
        self.assertIn('SIL Open Font License', (fonts / 'inter-opsz-LICENSE.txt').read_text())
        self.assertIn('SIL Open Font License', (fonts / 'nagi-glyph-OFL.txt').read_text())
        self.assertTrue((ROOT / 'linux' / 'icons' / 'nagi-symbolic.svg').is_file())
        for name in ('glance-v2.html', 'glance-v2.js', 'glance-model.js', 'glance-motion.js', 'glance-v2.css', 'glance-sheet.css'):
            text = (ROOT / 'web' / name).read_text()
            self.assertNotIn('<script>', text)
            self.assertNotIn('style=', text)
            self.assertNotIn('fixture', text)


class TrayIconChoice(TestCase):
    """One click opens the panel where the desktop allows it (an X11 tray icon)."""

    def test_x11_uses_the_click_through_tray_icon(self):
        import notifications
        X11Display = type('X11Display', (), {})
        WaylandDisplay = type('WaylandDisplay', (), {})
        self.assertTrue(notifications.wants_tray_icon(X11Display()))
        self.assertFalse(notifications.wants_tray_icon(WaylandDisplay()))
        self.assertFalse(notifications.wants_tray_icon(None))

    def test_tray_glyph_is_recoloured_and_checked(self):
        import notifications
        svg = notifications.tray_glyph_svg('#ffffff')
        self.assertIn('fill="#ffffff"', svg)
        self.assertNotIn('#bebebe', svg)
        with self.assertRaises(ValueError):
            notifications.tray_glyph_svg('red"/><script')
