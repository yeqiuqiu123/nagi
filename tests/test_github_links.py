"""GitHub links from the panel's CI marks: the one shape that may open in the browser,
and the shells' gates around it. Pure checks; no GTK, no browser, no network."""
from pathlib import Path
import json
import re
import sys
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'linux'))
from nagi_links import GITHUB_RESERVED, github_link, open_link, open_thread, thread_links
import notifications

CASES = json.loads((ROOT / 'tests' / 'github-link-cases.json').read_text())
ACCEPTED = tuple(CASES['accepted'])
REFUSED = tuple(CASES['refused']) + (None, 42, b'https://github.com/o/r/pull/1')
# Refused as a GitHub link and not a T3 thread link either: nothing the shells may open.
NOT_LINKS = tuple(value for value in REFUSED if value != 't3code://threads/e/a')


class GitHubLink(TestCase):
    def test_accepted_shapes_are_returned_unchanged(self):
        self.assertGreaterEqual(len(ACCEPTED), 8)
        for value in ACCEPTED:
            with self.subTest(value=value):
                self.assertEqual(github_link(value), value)

    def test_everything_else_is_refused(self):
        self.assertGreaterEqual(len(REFUSED), 70)
        for value in REFUSED:
            with self.subTest(value=value):
                self.assertIsNone(github_link(value))

    def test_githubs_own_first_segments_are_never_an_owner(self):
        # /new/import and /features/actions have the shape of a repository; so does every
        # other page under a reserved name, whatever route follows and however it is cased.
        self.assertGreaterEqual(len(CASES['reserved']), 300)
        for name in CASES['reserved']:
            for owner in (name, name.upper(), name.capitalize()):
                for rest in ('x', 'x/pull/1', 'actions', 'actions/actions', 'x/deployments'):
                    with self.subTest(owner=owner, rest=rest):
                        self.assertIsNone(github_link('https://github.com/' + owner + '/' + rest))
        for name in ('new', 'features', 'orgs', 'login', 'settings', 'sessions', 'enterprises', 'marketplace', 'topics', 'copilot', 'sso'):
            self.assertIn(name, CASES['reserved'])

    def test_a_repository_name_is_a_name(self):
        for repo in ('.', '..', 'r.', 'r..', '...', '.github.'):
            with self.subTest(repo=repo):
                self.assertIsNone(github_link('https://github.com/o/' + repo + '/pull/1'))
        self.assertEqual(github_link('https://github.com/o/.github/pull/1'), 'https://github.com/o/.github/pull/1')

    def test_the_three_validators_hold_the_same_reserved_names(self):
        # The list is written out in each language. All three must equal the shared table,
        # so a name added to one can't be forgotten in another, even where Swift isn't run.
        want = set(CASES['reserved'])
        self.assertEqual(set(GITHUB_RESERVED), want)
        web = (ROOT / 'web' / 'glance-ci.js').read_text()
        js = re.search(r"const RESERVED = new Set\(\(\s*'([a-z0-9 -]+)'\s*\)\.split\(' '\)\);", web)
        self.assertIsNotNone(js)
        self.assertEqual(set(js.group(1).split(' ')), want)
        swift = (ROOT / 'mac' / 'Sources' / 'NagiCore' / 'SourceLinks.swift').read_text()
        mac = re.search(r'githubReserved: Set<String> = Set\(\(\s*"([a-z0-9 -]+)"\s*\)\.split\(separator: " "\)', swift)
        self.assertIsNotNone(mac)
        self.assertEqual(set(mac.group(1).split(' ')), want)
        # And all three test suites read the one table.
        for path in ('tests/glance-ci.test.cjs', 'mac/Tests/NagiCoreTests/GitHubLinkTests.swift'):
            self.assertIn('github-link-cases.json', (ROOT / path).read_text())


class OpenLink(TestCase):
    def test_thread_links_open_exactly_as_before(self):
        for has in (None, lambda _: True, lambda _: False):
            first, second = [], []
            self.assertEqual(open_link('t3code://threads/e/a%3Ab', first.append, has),
                             open_thread('t3code://threads/e/a%3Ab', second.append, has))
            self.assertEqual(first, second)
        self.assertEqual(thread_links('https://github.com/o/r/pull/1'), None)
        self.assertIsNone(github_link('t3code://threads/e/a'))

    def test_a_github_link_opens_once_in_the_browser(self):
        opened = []
        self.assertTrue(open_link('https://github.com/o/r/pull/12', opened.append, lambda _: True))
        self.assertEqual(opened, ['https://github.com/o/r/pull/12'])

    def test_refused_links_never_reach_the_opener(self):
        opened = []
        for value in NOT_LINKS:
            with self.subTest(value=value):
                self.assertFalse(open_link(value, opened.append, lambda _: True))
        self.assertEqual(opened, [])

    def test_an_opener_that_fails_or_raises_is_not_opened(self):
        self.assertFalse(open_link('https://github.com/o/r/pull/1', lambda _: False))

        def boom(_):
            raise OSError('no browser')
        self.assertFalse(open_link('https://github.com/o/r/pull/1', boom))


class ShellGates(TestCase):
    def test_tray_panel_lets_a_github_link_leave_and_nothing_wider(self):
        self.assertTrue(notifications.glance_destination('https://github.com/o/r/pull/12'))
        self.assertTrue(notifications.glance_destination('t3code://threads/e/a'))
        for value in NOT_LINKS:
            with self.subTest(value=value):
                self.assertFalse(notifications.glance_destination(value))

    def test_widget_opens_github_links_only_from_a_click_on_the_trusted_panel(self):
        import widget
        page = widget.PANEL_URI
        opened = []
        self.assertTrue(widget.open_panel_external('https://github.com/o/r/pull/12', True, page, opened.append))
        self.assertEqual(opened, ['https://github.com/o/r/pull/12'])
        self.assertFalse(widget.open_panel_external('https://github.com/o/r/pull/12', False, page, opened.append))
        self.assertFalse(widget.open_panel_external('https://github.com/o/r/pull/12', True, 'https://github.com/o/r/pull/1', opened.append))
        self.assertFalse(widget.open_panel_external('https://github.com.evil.example/o/r/pull/1', True, page, opened.append))
        self.assertFalse(widget.open_panel_external('https://github.com/new/import', True, page, opened.append))
        self.assertFalse(widget.open_panel_external('https://github.com/features/actions', True, page, opened.append))
        self.assertEqual(len(opened), 1)
