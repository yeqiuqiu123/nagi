import io
import ipaddress
import json
import os
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from unittest import TestCase
from unittest.mock import patch

import loopback_peer as peer
from owner_auth import OwnerAuth
from server import Handler


def address(host, port):
    ip = ipaddress.ip_address(host)
    raw = ip.packed
    raw = raw[::-1] if ip.version == 4 else b''.join(raw[i:i+4][::-1] for i in range(0,16,4))
    return raw.hex().upper() + f':{port:04X}'


def row(client, server, uid, state='01'):
    return f'0: {address(*client)} {address(*server)} {state} 00000000:00000000 00:00000000 00000000 {uid} 0 12345 1\n'


def tables(tcp='', tcp6=''):
    def read(path, *_args, **_kwargs):
        if str(path) == '/proc/net/tcp': return io.StringIO('header\n' + tcp)
        if str(path) == '/proc/net/tcp6': return io.StringIO('header\n' + tcp6)
        raise OSError('Unavailable')
    return read


class PeerUIDTests(TestCase):
    def test_client_uid_not_reverse_reader_entry_or_listener(self):
        client, server = ('127.0.0.1',40000), ('127.0.0.1',47831)
        source = row(server,client,os.getuid()) + row(client,server,os.getuid()+1)
        with patch('loopback_peer.Path.open',tables(source)), patch('sys.platform','linux'):
            self.assertEqual(peer.peer_uid(client,server),os.getuid()+1)
            self.assertFalse(peer.same_user(client,server))
        with patch('loopback_peer.Path.open',tables(row(client,server,os.getuid()))):
            self.assertTrue(peer.same_user(client,server))

    def test_ipv6_and_ipv4_mapped_client_entries(self):
        for host in ('::1','::ffff:127.0.0.1'):
            client, server = (host,40000),(host,47831)
            with patch('loopback_peer.Path.open',tables(tcp6=row(client,server,os.getuid()))):
                self.assertEqual(peer.peer_uid(client,server),os.getuid())
        with patch('loopback_peer.Path.open',tables(tcp6=row(('::ffff:127.0.0.1',40000),('::ffff:127.0.0.1',47831),os.getuid()))):
            self.assertEqual(peer.peer_uid(('127.0.0.1',40000),('127.0.0.1',47831)),os.getuid())

    def test_exact_tuple_established_and_unambiguous_uid_required(self):
        client, server = ('127.0.0.1',40000),('127.0.0.1',47831)
        for source in (row(client,('127.0.0.1',47832),os.getuid()), row(client,server,os.getuid(),'0A'),
                       row(client,server,os.getuid())+row(client,server,os.getuid()+1), 'malformed'):
            with patch('loopback_peer.Path.open',tables(source)):
                self.assertIsNone(peer.peer_uid(client,server))
        with patch('loopback_peer.Path.open',side_effect=PermissionError()), patch('sys.platform','linux'):
            self.assertFalse(peer.same_user(client,server))
        self.assertIsNone(peer.peer_uid(('192.0.2.1',40000),server))

    def test_macos_does_not_use_linux_proc(self):
        with patch('sys.platform','darwin'), patch('loopback_peer.Path.open',side_effect=AssertionError()):
            self.assertTrue(peer.same_user(('127.0.0.1',40000),('127.0.0.1',47831)))

    def test_foreign_or_unresolved_uid_denies_all_routes_before_auth_or_ticket_consumption(self):
        with TemporaryDirectory() as directory, ThreadingHTTPServer(('127.0.0.1',0),Handler) as reader:
            auth=OwnerAuth(Path(directory));auth.bind(reader.server_port);reader.owner_auth=auth
            thread=Thread(target=reader.serve_forever);thread.start()
            try:
                ticket=auth.issue('/glance')
                cases=[('POST','/auth/challenge',{'nonce':'c'*43,'method':'GET','path':'/api/health','bodyHash':'0'*64}),
                       ('POST','/auth/redeem',{'ticket':ticket,'path':'/glance'}), ('POST','/auth/launch',{'path':'/glance'}),
                       ('GET','/overview',None),('GET','/api/company',None),('HEAD','/api/health',None),
                       ('POST','/api/import',{}),('PUT','/api/company',None)]
                for uid in (os.getuid()+1,None):
                    for method,path,body in cases:
                        with self.subTest(uid=uid,method=method,path=path):
                            connection=HTTPConnection('127.0.0.1',reader.server_port,timeout=3);connection.connect()
                            client=connection.sock.getsockname();server=('127.0.0.1',reader.server_port)
                            source=(row(server,client,os.getuid())+row(client,server,uid)) if uid is not None else ''
                            with patch('loopback_peer.Path.open',tables(source)):
                                raw=json.dumps(body).encode() if body is not None else None
                                connection.request(method,path,body=raw,headers={'Content-Type':'application/json','X-Progress-Desk':'1'})
                                response=connection.getresponse();self.assertEqual(response.status,403);response.read()
                            connection.close()
                self.assertIsNotNone(auth.redeem(ticket,'/glance'))
            finally:
                reader.shutdown();thread.join(5)
