"""T3 project icons: the closed RPC allowlist, image limits, override validation, the
favicon fallback paths and the owner-authenticated, path-free icon route."""
import copy
import json
from datetime import datetime, timezone
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Thread
from unittest import TestCase
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import owner_auth
import project_icons
import server
import t3_reader
from agents_service import AgentsService
from t3_reader import T3Reader, Unavailable, checked_image, rpc_allowed

NOW = datetime(2026, 11, 13, 3, tzinfo=timezone.utc)
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 32
SVG = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


class Allowlist(TestCase):
    def test_only_get_config_and_project_favicon_create_url_are_allowed(self):
        self.assertTrue(rpc_allowed('server.getConfig', {}))
        self.assertTrue(rpc_allowed('assets.createUrl', {'resource': {'_tag': 'project-favicon', 'cwd': '/w'}}))
        self.assertTrue(rpc_allowed('assets.createUrl', {'resource': {'_tag': 'project-favicon', 'cwd': '/w', 'path': 'public/favicon.ico'}}))
        for tag in ('workspace-file', 'media-file', 'draft-workspace-file', 'tool-output-image', 'native-app-icon', 'attachment'):
            self.assertFalse(rpc_allowed('assets.createUrl', {'resource': {'_tag': tag, 'cwd': '/w', 'path': 'a.png'}}), tag)
        for bad in ({'resource': {'_tag': 'project-favicon'}}, {'resource': {'_tag': 'project-favicon', 'cwd': ' /w'}},
                    {'resource': {'_tag': 'project-favicon', 'cwd': '/w', 'path': 'secrets.env'}},
                    {'resource': {'_tag': 'project-favicon', 'cwd': '/w', 'extra': 1}},
                    {'resource': {'_tag': 'project-favicon', 'cwd': '/w'}, 'other': 1}):
            self.assertFalse(rpc_allowed('assets.createUrl', bad), bad)
        for tag in ('server.updateSettings', 'orchestration.dispatchCommand', 'projects.mutate', 'git.pull'):
            self.assertFalse(rpc_allowed(tag, {}), tag)
        self.assertFalse(rpc_allowed('server.getConfig', {'deferNetworkDiscovery': True}))

    def test_a_refused_rpc_never_opens_a_connection(self):
        reader = object.__new__(T3Reader)
        with patch.object(T3Reader, 'connection', side_effect=AssertionError('connected')):
            with self.assertRaises(ValueError):
                reader._rpc('assets.createUrl', {'resource': {'_tag': 'workspace-file', 'cwd': '/w', 'path': 'a.png'}})

    def test_favicon_url_returns_the_signed_path_or_none_for_the_fallback_marker(self):
        reader = object.__new__(T3Reader)
        with patch.object(T3Reader, '_rpc', return_value={'relativeUrl': '/api/assets/tok/v1abc-favicon.png'}) as rpc:
            self.assertEqual(reader.favicon_url('/w'), '/api/assets/tok/v1abc-favicon.png')
            self.assertEqual(rpc.call_args.args, ('assets.createUrl', {'resource': {'_tag': 'project-favicon', 'cwd': '/w'}}))
        with patch.object(T3Reader, '_rpc', return_value={'relativeUrl': '/api/assets/tok/project-favicon-missing'}):
            self.assertIsNone(reader.favicon_url('/w'))
        for hostile in ('https://evil.example/x.png', '/api/assets/../api/orchestration/shell', '/api/other/x', '/api/assets/t/x?y=1'):
            with patch.object(T3Reader, '_rpc', return_value={'relativeUrl': hostile}):
                with self.assertRaises(Unavailable):
                    reader.favicon_url('/w')

    def test_images_are_bounded_typed_and_sniffed(self):
        self.assertEqual(checked_image(PNG, 'image/png'), (PNG, 'image/png'))
        self.assertIsNone(checked_image(PNG + b'\x00' * (256 * 1024), 'image/png'))  # over 256 KB
        self.assertIsNone(checked_image(PNG, 'text/html'))  # type not allowlisted
        self.assertIsNone(checked_image(PNG, 'image/jpeg'))  # declared type disagrees with the bytes
        self.assertIsNone(checked_image(b'<html><script>', 'image/png'))
        self.assertIsNone(checked_image(b'', 'image/png'))
        self.assertEqual(checked_image(b'\x00\x00\x01\x00' + b'\x00' * 20, 'image/vnd.microsoft.icon')[1], 'image/x-icon')
        self.assertEqual(checked_image(SVG, 'image/svg+xml')[1], 'image/svg+xml')
        self.assertIsNone(checked_image(b'GIF89a', 'image/avif'))


class Overrides(TestCase):
    def test_overrides_follow_t3s_schema_and_unknown_kinds_fall_back(self):
        self.assertEqual(project_icons.override({'kind': 'monogram', 'text': 'NG', 'color': 'red'}), {'kind': 'monogram', 'text': 'NG', 'color': 'red'})
        self.assertEqual(project_icons.override({'kind': 'lucide', 'name': 'message-square-dashed', 'color': 'gray'}),
                         {'kind': 'lucide', 'name': 'message-square-dashed', 'color': 'gray'})
        # A legacy lucide override carrying monogram text is a monogram, as in T3.
        self.assertEqual(project_icons.override({'kind': 'lucide', 'name': 'code', 'color': 'blue', 'monogramText': 'AB'}),
                         {'kind': 'monogram', 'text': 'AB', 'color': 'blue'})
        self.assertEqual(project_icons.override({'kind': 'emoji', 'emoji': '🚀'}), {'kind': 'emoji', 'emoji': '🚀'})
        for bad in ({'kind': 'image', 'url': 'https://example.com/a.png'}, {'kind': 'monogram', 'text': 'NG', 'color': 'magenta'},
                    {'kind': 'monogram', 'text': '-NG', 'color': 'red'}, {'kind': 'lucide', 'name': 'Bad Name', 'color': 'red'},
                    {'kind': 'emoji', 'emoji': ''}, None, 'monogram'):
            self.assertIsNone(project_icons.override(bad), bad)
        self.assertRegex(project_icons.key('env', 'p1'), r'^[0-9a-f]{32}$')
        self.assertNotEqual(project_icons.key('env', 'p1'), project_icons.key('env', 'p2'))


class Source:
    def __init__(self):
        self.projects = [
            {'id': 'p-fav', 'title': 'Harbor Website', 'workspaceRoot': '/home/owner/secret-path/harbor', 'faviconPath': None, 'projectIcon': None},
            {'id': 'p-mono', 'title': 'Nagi', 'workspaceRoot': '/home/owner/secret-path/nagi', 'projectIcon': None},
            {'id': 'p-luc', 'title': 'No project', 'workspaceRoot': '/home/owner/secret-path/x', 'projectIcon': {'kind': 'lucide', 'name': 'message-square-dashed', 'color': 'gray'}},
        ]
        self.favicons = {'/home/owner/secret-path/harbor': '/api/assets/t/v1-favicon.png'}
        self.calls = []
        self.fail = False

    def shell(self):
        rows = [dict(id=p['id'] + '-t', projectId=p['id'], title='Agent', status='running', updatedAt=NOW.isoformat(),
                     latestRunId='r', latestRunStartedAt=NOW.isoformat(), modelSelection={'model': 'sol'}) for p in self.projects]
        return {'environmentId': 'local:1'}, {'projects': copy.deepcopy(self.projects), 'threads': rows}

    def config(self):
        return {'providers': []}

    def detail(self, identity):
        return {'hasMoreHistory': False, 'projection': {'turnItems': []}}

    def favicon_url(self, cwd, path=None):
        self.calls.append(cwd)
        if self.fail:
            raise Unavailable()
        return self.favicons.get(cwd)

    def asset(self, url):
        return (PNG, 'image/png')


class ServiceAndRoute(TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(TemporaryDirectory()))
        self.source = Source()
        self.enterContext(patch('agents_service.AgentsService.read_machine', lambda s, a: None))
        self.service = AgentsService(self.directory, lambda _: self.source, lambda: NOW)
        self.service.poll(force=True)
        self.icons = {g['id']: g['icon'] for g in self.service.agents['data']['projects']}

    def test_projection_carries_closed_icons_and_no_paths(self):
        self.assertEqual(self.icons['p-luc'], {'kind': 'lucide', 'name': 'message-square-dashed', 'color': 'gray'})
        self.assertEqual(self.icons['p-fav']['kind'], 'favicon')
        self.assertNotIn('secret-path', json.dumps(self.service.agents))
        # The journal accepts the icon field, so the dated cache survives a restart.
        self.assertIn('agents', self.service.journal().get('cache', {}))

    def test_favicon_is_fetched_through_t3_and_misses_fall_back_to_auto(self):
        key = self.icons['p-fav']['key']
        self.assertEqual(self.service.project_icon(key), (PNG, 'image/png'))
        self.assertEqual(self.service.project_icon(key), (PNG, 'image/png'))
        self.assertEqual(self.source.calls.count('/home/owner/secret-path/harbor'), 1)  # cached for the 30-minute bucket
        missing = self.icons['p-mono']['key']
        self.assertIsNone(self.service.project_icon(missing))  # T3's fallback marker
        self.service.last_poll = None
        self.service.poll(force=True)
        icons = {g['id']: g['icon'] for g in self.service.agents['data']['projects']}
        self.assertEqual(icons['p-mono'], {'kind': 'auto'})  # a known miss renders the derived monogram
        self.assertIsNone(self.service.project_icon('0' * 32))  # unknown key
        self.assertIsNone(self.service.project_icon('../../etc'))

    def test_an_unreachable_t3_is_not_cached_as_a_missing_favicon(self):
        key = self.icons['p-fav']['key']
        self.source.fail = True
        self.assertIsNone(self.service.project_icon(key))
        self.assertFalse(self.service.icon_known_missing(key))

    def test_the_icon_route_is_owner_only_typed_and_sandboxed(self):
        auth = owner_auth.OwnerAuth(self.directory)
        http = self.enterContext(ThreadingHTTPServer(('127.0.0.1', 0), server.Handler))
        http.owner_auth, http.service = auth, self.service
        Thread(target=http.serve_forever, daemon=True).start()
        self.addCleanup(http.shutdown)
        origin = f'http://127.0.0.1:{http.server_port}'
        auth.bind(http.server_port)

        def get(path, owner=True):
            connection = HTTPConnection('127.0.0.1', http.server_port, timeout=4)
            headers = {'Host': f'127.0.0.1:{http.server_port}'}
            if owner:
                headers.update(owner_auth.auth_headers(origin, 'GET', path, b'', self.directory))
            connection.request('GET', path, headers=headers)
            response = connection.getresponse()
            result = response.status, {k.lower(): v for k, v in response.getheaders()}, response.read()
            connection.close()
            return result

        key = self.icons['p-fav']['key']
        self.assertEqual(get('/api/project-icon/' + key, owner=False)[0], 401)
        status, headers, body = get('/api/project-icon/' + key)
        self.assertEqual((status, headers['content-type'], body), (200, 'image/png', PNG))
        self.assertEqual(headers['x-content-type-options'], 'nosniff')
        self.assertIn('sandbox', headers['content-security-policy'])
        self.assertEqual(get('/api/project-icon/' + '0' * 32)[0], 404)
        self.assertEqual(get('/api/project-icon/NOTHEX')[0], 404)
        with patch.object(self.source, 'asset', return_value=(SVG, 'image/svg+xml')):
            svg_key = project_icons.key('local:1', 'p-svg')
            self.service.icon_sources[svg_key] = ('/svg', None)
            self.source.favicons['/svg'] = '/api/assets/t/v1-icon.svg'
            status, headers, _ = get('/api/project-icon/' + svg_key)
            self.assertEqual((status, headers['content-type']), (200, 'image/svg+xml'))
            self.assertIn("sandbox", headers['content-security-policy'])
            self.assertIn("default-src 'none'", headers['content-security-policy'])
        glance = get('/glance', owner=False)[1]['content-security-policy']
        self.assertIn("img-src 'self' blob:", glance)
