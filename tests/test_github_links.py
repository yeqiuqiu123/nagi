"""GitHub links from the panel's CI marks: the one shape that may open in the browser,
and the shells' gates around it. Pure checks; no GTK, no browser, no network."""
from pathlib import Path
import sys
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'linux'))
from nagi_links import github_link, open_link, open_thread, thread_links
import notifications

ACCEPTED = (
    'https://github.com/o/r',
    'https://github.com/o/r/pull/12',
    'https://github.com/o/r/pull/12/checks',
    'https://github.com/o/r/actions/runs/123',
    'https://github.com/o/r/commit/0123456789abcdef0123456789abcdef01234567/checks',
    'https://github.com/o/r/deployments',
    'https://github.com/tidepool-labs/tidepool.web/pull/128',
    'https://github.com/o/r/a/b/c/d/e/f',  # owner, repo and six more segments
)
REFUSED = (
    'http://github.com/o/r',
    'https://github.com.evil.example/o/r',
    'https://evil.example/github.com/o/r',
    'https://user@github.com/o/r',
    'https://user:secret@github.com/o/r',
    'https://github.com:443/o/r',
    'https://github.com/o/r/pull/12?tab=checks',
    'https://github.com/o/r?',
    'https://github.com/o/r#top',
    'https://github.com/o/r/pull/12#',
    'https://github.com/o/../r',
    'https://github.com/o/r/..',
    'https://github.com/o/r/./pull',
    'https://github.com/o/..',
    'https://github.com/o/r%2Fpull/1',
    'https://github.com/o/r/pull%2F1',
    'https://github.com/o/r/a/b/c/d/e/f/g',  # seven more segments
    'https://github.com/o/r\n',
    'https://github.com/o/r/pull/1\r',
    'https://github.com/o/r/ pull',
    'https://github.com/o//r',
    'https://github.com/o/r/',
    'https://github.com//o/r',
    'https://gist.github.com/o/r',
    'https://GITHUB.com/o/r',
    'HTTPS://github.com/o/r',
    'https://github.com/o',
    'https://github.com/',
    'https://github.com',
    'https://github.com/o/r\\x',
    'https://github.com/o_x/r',
    'https://github.com/' + 'o' * 40 + '/r',
    'https://github.com/o/' + 'r' * 101,
    'https://github.com/o/r/' + 'x' * 201,
    'https://github.com/o/r/' + 'a/' * 1100 + 'a',
    'https://github.com/o/r/é',
    'javascript:alert(1)',
    'file:///tmp/x',
    '',
    None,
    42,
)


class GitHubLink(TestCase):
    def test_accepted_shapes_are_returned_unchanged(self):
        for value in ACCEPTED:
            with self.subTest(value=value):
                self.assertEqual(github_link(value), value)

    def test_everything_else_is_refused(self):
        for value in REFUSED:
            with self.subTest(value=value):
                self.assertIsNone(github_link(value))

    def test_the_web_model_uses_the_same_table(self):
        # tests/glance-ci.test.cjs checks safeGithub; keep both tables in step.
        script = (ROOT / 'tests' / 'glance-ci.test.cjs').read_text()
        for value in ('https://github.com/o/r/pull/12/checks', 'https://github.com.evil.example/o/r', 'https://github.com/o/r%2Fpull'):
            self.assertIn(value, script)


class OpenLink(TestCase):
    def test_thread_links_open_exactly_as_before(self):
        for has in (None, lambda _: True, lambda _: False):
            first, second = [], []
            self.assertEqual(open_link('t3code://threads/e/a%3Ab', first.append, has),
                             open_thread('t3code://threads/e/a%3Ab', second.append, has))
            self.assertEqual(first, second)
        self.assertEqual(thread_links('https://github.com/o/r'), None)
        self.assertIsNone(github_link('t3code://threads/e/a'))

    def test_a_github_link_opens_once_in_the_browser(self):
        opened = []
        self.assertTrue(open_link('https://github.com/o/r/pull/12', opened.append, lambda _: True))
        self.assertEqual(opened, ['https://github.com/o/r/pull/12'])

    def test_refused_links_never_reach_the_opener(self):
        opened = []
        for value in REFUSED:
            with self.subTest(value=value):
                self.assertFalse(open_link(value, opened.append, lambda _: True))
        self.assertEqual(opened, [])

    def test_an_opener_that_fails_or_raises_is_not_opened(self):
        self.assertFalse(open_link('https://github.com/o/r', lambda _: False))

        def boom(_):
            raise OSError('no browser')
        self.assertFalse(open_link('https://github.com/o/r', boom))


class ShellGates(TestCase):
    def test_tray_panel_lets_a_github_link_leave_and_nothing_wider(self):
        self.assertTrue(notifications.glance_destination('https://github.com/o/r/pull/12'))
        self.assertTrue(notifications.glance_destination('t3code://threads/e/a'))
        for value in REFUSED:
            with self.subTest(value=value):
                self.assertFalse(notifications.glance_destination(value))

    def test_widget_opens_github_links_only_from_a_click_on_the_trusted_panel(self):
        import widget
        page = widget.PANEL_URI
        opened = []
        self.assertTrue(widget.open_panel_external('https://github.com/o/r/pull/12', True, page, opened.append))
        self.assertEqual(opened, ['https://github.com/o/r/pull/12'])
        self.assertFalse(widget.open_panel_external('https://github.com/o/r/pull/12', False, page, opened.append))
        self.assertFalse(widget.open_panel_external('https://github.com/o/r/pull/12', True, 'https://github.com/o/r', opened.append))
        self.assertFalse(widget.open_panel_external('https://github.com.evil.example/o/r', True, page, opened.append))
        self.assertEqual(len(opened), 1)
