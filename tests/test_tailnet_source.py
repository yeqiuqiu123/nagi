"""The T3 source origin: this computer's loopback, one Tailscale CGNAT address, or a
ts.net HTTPS name. Everything else is refused before any credential is read or sent."""
import http.client
import json
import os
import ssl
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from unittest import TestCase
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import t3_reader
from t3_reader import T3Reader, OwnerConnection, TailnetConnection, Unavailable, source_origin

ACCEPTED = {
    'http://127.0.0.1:3773': ('loopback', '127.0.0.1', 3773),
    'http://100.101.102.103:3773': ('tailnet', '100.101.102.103', 3773),
    'http://100.64.0.1:3773': ('tailnet', '100.64.0.1', 3773),
    'http://100.127.255.254:1024': ('tailnet', '100.127.255.254', 1024),
    'https://linux-box.tail1234.ts.net': ('tls', 'linux-box.tail1234.ts.net', 443),
    'https://linux-box.tail1234.ts.net:8443': ('tls', 'linux-box.tail1234.ts.net', 8443),
}
REJECTED = [
    'http://100.63.255.255:3773', 'http://100.128.0.1:3773', 'http://10.0.0.1:3773', 'http://192.168.1.2:3773',
    'http://127.0.0.2:3773', 'http://localhost:3773', 'http://100.101.102.103', 'http://100.0101.102.103:3773',
    'http://0x64.88.232.122:3773', 'http://[fd7a:115c:a1e0::1]:3773', 'http://[::1]:3773',
    'http://x.ts.net:3773', 'http://x.ts.net', 'https://100.101.102.103:3773', 'https://evil.ts.net.example.com',
    'https://ts.net', 'https://.ts.net', 'https://a..ts.net', 'https://-a.ts.net', 'https://A.ts.net',
    'https://a.ts.net:0', 'https://a.ts.net/', 'https://a.ts.net/path', 'https://a.ts.net?x=1', 'https://a.ts.net#x',
    'https://user@a.ts.net', 'https://user:pw@a.ts.net', 'http://user@100.101.102.103:3773',
    'http://100.101.102.103:3773@evil.example', 'ws://100.101.102.103:3773', 'wss://a.ts.net', 'ftp://a.ts.net',
    'http://100.101.102.103:3773/', 'http://100.101.102.103:99999', 'https://a.ts.net:99999', 'http://100.101.102.103:3773 ',
    'https://a.ts.net\n', 'https://bücher.ts.net', None, 3773,
]


class SourceOrigin(TestCase):
    def test_accepts_loopback_one_tailnet_address_or_a_ts_net_name(self):
        for value, expected in ACCEPTED.items():
            with self.subTest(value=value):self.assertEqual(source_origin(value), expected)

    def test_refuses_look_alikes_and_everything_else(self):
        for value in REJECTED:
            with self.subTest(value=value), self.assertRaises(ValueError):source_origin(value)


class Policy(TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(TemporaryDirectory()))
        self.credential = self.directory / 'credential'
        self.credential.write_text(json.dumps({'token': 'synthetic-placeholder', 'scopes': ['orchestration:read']}))
        self.credential.chmod(0o600)

    def policy(self, origin):
        path = self.directory / 'nagi-t3.json'
        path.write_text(json.dumps({'version': 1, 'origin': origin, 'credentialFile': str(self.credential)}))
        path.chmod(0o600)

    def test_each_origin_class_gets_its_own_transport(self):
        self.policy('http://127.0.0.1:3773')
        self.assertIsInstance(T3Reader(self.directory).connection(), OwnerConnection)
        self.policy('http://100.101.102.103:3773')
        reader = T3Reader(self.directory)
        connection = reader.connection()
        self.assertIsInstance(connection, TailnetConnection)
        self.assertNotIsInstance(connection, OwnerConnection)
        self.assertEqual((connection.host, connection.port), ('100.101.102.103', 3773))
        self.policy('https://linux-box.tail1234.ts.net')
        connection = T3Reader(self.directory).connection()
        self.assertIsInstance(connection, http.client.HTTPSConnection)
        self.assertEqual((connection.host, connection.port), ('linux-box.tail1234.ts.net', 443))
        self.assertEqual(connection._context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(connection._context.check_hostname)

    def test_policy_keys_and_scope_stay_strict(self):
        path = self.directory / 'nagi-t3.json'
        path.write_text(json.dumps({'version': 1, 'origin': 'http://100.101.102.103:3773', 'credentialFile': str(self.credential), 'remote': True}))
        path.chmod(0o600)
        with self.assertRaises(Unavailable):T3Reader(self.directory)
        self.credential.write_text(json.dumps({'token': 'synthetic-placeholder', 'scopes': ['orchestration:read', 'orchestration:write']}))
        self.policy('http://100.101.102.103:3773')
        with self.assertRaises(Unavailable):T3Reader(self.directory)

    def test_a_rejected_origin_never_reads_or_sends_the_token(self):
        for origin in ('http://100.128.0.1:3773', 'https://evil.ts.net.example.com', 'http://user@100.101.102.103:3773', 'http://x.ts.net:3773'):
            with self.subTest(origin=origin):
                self.policy(origin)
                with patch('socket.create_connection') as connect, patch('t3_reader.private_json', wraps=t3_reader.private_json) as read:
                    with self.assertRaises(Unavailable):T3Reader(self.directory)
                connect.assert_not_called()
                self.assertEqual(read.call_count, 1, 'Only the policy is read; the credential file is not')


class Transport(TestCase):
    def serve(self, status, location=None):
        seen = []
        class Fake(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            def log_message(self, *_):pass
            def do_GET(h):
                seen.append((h.path, h.headers.get('Authorization')))
                body = b'{"ok":true}' if status == 200 else b''
                h.send_response(status)
                if location:h.send_header('Location', location)
                h.send_header('Content-Length', str(len(body)));h.end_headers();h.wfile.write(body)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Fake)
        worker = Thread(target=server.serve_forever);worker.start()
        self.addCleanup(lambda:(server.shutdown(), server.server_close(), worker.join(5)))
        return server.server_port, seen

    def client(self, kind, port):
        client = object.__new__(T3Reader)
        client.kind, client.host, client.port, client._token = kind, '127.0.0.1', port, 'synthetic-only'
        return client

    def test_tailnet_transport_skips_only_the_local_peer_check(self):
        port, seen = self.serve(200)
        foreign = os.getuid() + 1
        with patch('t3_reader.peer_uid', return_value=foreign), patch('sys.platform', 'linux'):
            self.assertEqual(self.client('tailnet', port).get('/x'), {'ok': True})
            with self.assertRaises(Unavailable):self.client('loopback', port).get('/x')
        self.assertEqual(seen, [('/x', 'Bearer synthetic-only')], 'The loopback check refused before sending anything')

    def test_redirects_are_never_followed(self):
        target_port, target_seen = self.serve(200)
        port, seen = self.serve(302, f'http://127.0.0.1:{target_port}/x')
        with self.assertRaises(Unavailable):self.client('tailnet', port).get('/x')
        self.assertEqual(len(seen), 1)
        self.assertEqual(target_seen, [])

    def test_websocket_config_uses_the_same_transport(self):
        attempts = []
        def refuse(connection):
            attempts.append(type(connection))
            raise OSError('synthetic: no network in tests')
        for kind, expected in (('tls', http.client.HTTPSConnection), ('tailnet', TailnetConnection), ('loopback', OwnerConnection)):
            with self.subTest(kind=kind), patch.object(expected, 'connect', refuse):
                with self.assertRaises(Unavailable):self.client(kind, 9).config()
        self.assertEqual(attempts, [http.client.HTTPSConnection, TailnetConnection, OwnerConnection])
