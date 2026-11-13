"""Independent local reader auth, platform and optional-source regressions."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.message import Message
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import machine
import owner_auth
import server

ROOT = Path(__file__).resolve().parents[1]


class LocalOwnerTests(TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(TemporaryDirectory()))
        self.auth = owner_auth.OwnerAuth(self.directory)
        self.http = self.enterContext(ThreadingHTTPServer(('127.0.0.1', 0), server.Handler))
        self.http.owner_auth, self.http.data_dir = self.auth, self.directory
        self.http.service = server.AgentsService(self.directory)
        thread = Thread(target=self.http.serve_forever)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(self.http.shutdown)
        self.origin = f'http://127.0.0.1:{self.http.server_port}'
        self.auth.bind(self.http.server_port)

    def request(self, path, *, method='GET', body=None, headers=None, owner=True, duplicates=()):
        connection = HTTPConnection('127.0.0.1', self.http.server_port, timeout=4)
        values = {'Host': f'127.0.0.1:{self.http.server_port}'}
        data = json.dumps(body).encode() if body is not None else b''
        if owner:
            values.update(owner_auth.auth_headers(self.origin, method, path, data, self.directory))
        if method == 'POST':
            values.update({'Content-Type': 'application/json', 'X-Progress-Desk': '1', 'Content-Length': str(len(data))})
        values.update(headers or {})
        connection.putrequest(method, path, skip_host=True)
        for key, value in list(values.items()) + list(duplicates):
            connection.putheader(key, value)
        connection.endheaders(data)
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def session(self, path='/overview'):
        code, _, raw = self.request('/auth/launch', method='POST', body={'path':path})
        self.assertEqual(code, 200)
        from urllib.parse import urlsplit
        url = json.loads(raw)['url']
        ticket = urlsplit(url).fragment.removeprefix('nagi-launch=')
        code, headers, raw = self.request('/auth/redeem', method='POST', owner=False,
                                         body={'ticket':ticket,'path':path})
        self.assertEqual(code, 200)
        self.assertNotIn('Set-Cookie', headers)
        return json.loads(raw), ticket

    def test_every_private_feed_and_legacy_route_denies_without_owner(self):
        for path in ('/api/glance','/api/limits','/api/settings','/api/notifications','/api/health'):
            with self.subTest(path=path):
                self.assertEqual(self.request(path,owner=False)[0],401)
                self.assertEqual(self.request(path,method='HEAD',owner=False)[0],401)
        for path in ('/api/company','/api/state','/api/export','/api/nagi/harnesses','/company/tasks/22'):
            self.assertEqual(self.request(path,owner=False)[0],404)
        for path in ('/overview','/glance','/nagi-glance.js'):
            code,headers,raw=self.request(path,owner=False)
            self.assertEqual(code,200);self.assertNotIn(b'fixture',raw);self.assertNotIn('Set-Cookie',headers)

    def test_native_mutual_proofs_bind_method_path_body_and_are_one_use(self):
        self.assertEqual(self.request('/api/health')[0], 200)
        headers = owner_auth.auth_headers(self.origin, 'GET', '/api/health', directory=self.directory)
        self.assertEqual(self.request('/api/health', owner=False, headers=headers)[0], 200)
        self.assertEqual(self.request('/api/health', owner=False, headers=headers)[0], 401)
        for method, path, body in [('HEAD','/api/health',None), ('GET','/api/settings',None), ('POST','/auth/launch',{'path':'/glance'})]:
            headers = owner_auth.auth_headers(self.origin, 'GET', '/api/health', directory=self.directory)
            self.assertEqual(self.request(path, method=method, body=body, owner=False, headers=headers)[0], 401)
        headers = owner_auth.auth_headers(self.origin, 'POST', '/auth/launch', b'{}', self.directory)
        self.assertEqual(self.request('/auth/launch', method='POST', body={'path':'/overview'}, owner=False, headers=headers)[0], 401)
        headers = owner_auth.auth_headers(self.origin, 'GET', '/api/health', directory=self.directory)
        self.assertEqual(self.request('/api/health', owner=False, headers=headers, duplicates=list(headers.items()))[0], 401)

    def test_impostor_listener_gets_only_public_challenge_never_secret_or_credential(self):
        requests = []
        class Fake(server.BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_POST(fake):
                raw = fake.rfile.read(int(fake.headers['Content-Length']))
                requests.append((fake.path, dict(fake.headers), raw))
                payload = json.dumps({'instance':'a'*43,'serverNonce':'b'*43,'proof':'0'*64}).encode()
                fake.send_response(200); fake.send_header('Content-Length',str(len(payload))); fake.end_headers(); fake.wfile.write(payload)
        with ThreadingHTTPServer(('127.0.0.1',0), Fake) as impostor:
            thread = Thread(target=impostor.serve_forever); thread.start()
            try:
                origin = f'http://127.0.0.1:{impostor.server_port}'
                for operation in (lambda: owner_auth.launch_url(origin, directory=self.directory),
                                  lambda: owner_auth.authenticated_open(__import__('urllib.request',fromlist=['Request']).Request(origin+'/api/ingest',data=b'private-input'), self.directory)):
                    with self.assertRaisesRegex(ValueError, 'Reader identity'):
                        operation()
            finally:
                impostor.shutdown(); thread.join(5)
        self.assertEqual(len(requests), 2)
        for path, headers, body in requests:
            self.assertEqual(path, '/auth/challenge')
            self.assertNotIn('Authorization', headers)
            self.assertNotIn('Cookie', headers)
            self.assertNotIn('X-Nagi-Session', headers)
            self.assertNotIn(self.auth.secret, json.dumps(headers)+body.decode())
            self.assertNotIn(b'private-input', body)

    def test_proof_expiry_and_challenge_capacity_are_bounded(self):
        headers = owner_auth.auth_headers(self.origin, 'GET', '/api/health', directory=self.directory)
        with patch('owner_auth.time.monotonic',return_value=10**15):
            self.assertEqual(self.request('/api/health',owner=False,headers=headers)[0],401)
        value={'nonce':'x'*43,'method':'GET','path':'/api/health','bodyHash':owner_auth.digest()}
        self.auth.challenges.clear()
        oldest = self.auth.challenge(value)['serverNonce']
        for _ in range(127): self.auth.challenge(value)
        self.assertEqual(self.request('/auth/challenge',method='POST',body=value,owner=False)[0],200)
        self.assertEqual(len(self.auth.challenges),128)
        self.assertNotIn(oldest,self.auth.challenges)

    def test_server_proof_cannot_be_relayed_from_another_port(self):
        client = 'c'*43
        value = {'nonce':client,'method':'GET','path':'/api/health','bodyHash':owner_auth.digest()}
        response = self.auth.challenge(value)
        bad = owner_auth.proof(self.auth.secret,'nagi-server-v2','http://127.0.0.1:1',response['instance'],client,response['serverNonce'],'GET','/api/health',owner_auth.digest())
        self.assertNotEqual(response['proof'], bad)

    def test_sessions_expire_restart_revoke_and_other_ports_cannot_use_them(self):
        value, _ = self.session()
        headers = {'X-Nagi-Session':value['token']}
        self.assertEqual(self.request('/api/health',owner=False,headers=headers)[0],200)
        self.assertEqual(self.request('/auth/launch',method='POST',body={'path':'/overview'},owner=False,headers=headers)[0],401)
        self.assertEqual(self.request('/api/health',owner=False,headers={**headers,'Origin':'http://127.0.0.1:1'})[0],403)
        other = owner_auth.OwnerAuth(self.directory, 'http://127.0.0.1:1')
        message = Message(); message['X-Nagi-Session'] = value['token']
        self.assertFalse(other.authenticated(message,'GET','/api/health'))
        restarted = owner_auth.OwnerAuth(self.directory, self.origin)
        self.assertFalse(restarted.authenticated(message,'GET','/api/health'))
        with patch('owner_auth.time.monotonic', return_value=10**15):
            self.assertEqual(self.request('/api/health',owner=False,headers=headers)[0],401)
        self.assertNotEqual(value['token'], self.session()[0]['token'])

    def test_tickets_have_ten_second_expiry_and_get_head_never_consume(self):
        with patch('owner_auth.time.monotonic',return_value=10):
            ticket = self.auth.issue('/glance')
        self.assertEqual(self.request('/glance#nagi-launch='+ticket, method='HEAD',owner=False)[0],200)
        with patch('owner_auth.time.monotonic',return_value=20):
            self.assertIsNone(self.auth.redeem(ticket,'/glance'))
        value,ticket = self.session()
        self.assertEqual(self.request('/auth/redeem',method='POST',owner=False,body={'ticket':ticket,'path':'/overview'})[0],401)
        self.assertIsNotNone(value['token'])

    def test_redemption_is_atomic_and_ticket_capacity_is_bounded(self):
        ticket = self.auth.issue('/glance')
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _:self.auth.redeem(ticket,'/glance'),range(4)))
        self.assertEqual(sum(result is not None for result in results),1)
        for _ in range(64): self.auth.issue('/overview')
        self.assertEqual(self.request('/auth/launch',method='POST',body={'path':'/glance'})[0],503)

    def test_cookie_planting_has_no_effect_and_never_authenticates(self):
        session,_ = self.session()
        cookies = 'nagi_owner=x; nagi_owner=y'
        self.assertEqual(self.request('/api/health',owner=False,headers={'Cookie':cookies})[0],401)
        self.assertEqual(self.request('/api/health',owner=False,headers={'Cookie':cookies,'X-Nagi-Session':session['token']})[0],200)
        self.assertEqual(self.request('/api/health',owner=False,headers={'Authorization':'Bearer '+self.auth.secret})[0],401)

    def test_dns_rebinding_and_cross_site_guards(self):
        for headers in ({'Host':'localhost:'+str(self.http.server_port)}, {'Host':'evil.example'},
                        {'Origin':'https://evil.example'}, {'Sec-Fetch-Site':'cross-site'}):
            self.assertEqual(self.request('/api/health',headers=headers)[0],403)
        self.assertEqual(self.request('/api/health',duplicates=[('Host','127.0.0.1')])[0],403)
        self.assertEqual(self.request('/api/health',headers={'Origin':self.origin},duplicates=[('Origin',self.origin)])[0],403)

    def test_secret_private_idempotent_and_unsafe_files_rejected(self):
        path = self.directory/'nagi-owner.json'
        self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
        self.assertEqual(owner_auth.OwnerAuth(self.directory).secret,self.auth.secret)
        path.chmod(0o644)
        with self.assertRaises(ValueError): owner_auth.OwnerAuth(self.directory)
        path.chmod(0o600); saved=self.directory/'saved'; path.rename(saved); path.symlink_to(saved)
        with self.assertRaises(OSError): owner_auth.OwnerAuth(self.directory)

    def test_retired_gateway_and_unsupported_methods(self):
        self.assertFalse((ROOT/'readonly_gateway.py').exists())
        self.assertEqual(self.request('/api/health',owner=False,headers={'Tailscale-User-Login':'owner'})[0],401)
        for method in ('PUT','DELETE','PATCH','OPTIONS'):
            self.assertEqual(self.request('/api/company',method=method)[0],405)
        self.assertEqual(self.request('/data/nagi-owner.json')[0],404)

    def test_v2_routes_settings_and_claim_require_owner_and_closed_shapes(self):
        for path,key in (('/api/glance','agents'),('/api/limits','providers'),('/api/notifications','events')):
            code,_,raw=self.request(path);self.assertEqual(code,200)
            value=json.loads(raw);self.assertEqual(value['version'],2);self.assertIn(key,value)
        settings={'stuckMinutes':5,'endedExpiryHours':48}
        self.assertEqual(self.request('/api/settings',method='POST',body=settings,owner=False)[0],401)
        self.assertEqual(self.request('/api/settings',method='POST',body=settings)[0],200)
        self.assertEqual(json.loads(self.request('/api/settings')[2])['settings'],dict(settings,limitAlertPercent=10))
        self.assertEqual(self.request('/api/settings',method='POST',body={**settings,'stop':True})[0],400)
        self.assertEqual(self.request('/api/notifications/claim',method='POST',body={'id':'a'*64},owner=False)[0],401)
        value=json.loads(self.request('/api/notifications/claim',method='POST',body={'id':'a'*64,'reservation':'x'*43})[2])
        self.assertFalse(value['claimed']);self.assertIsNone(value['event'])

    def test_settings_resource_defaults_clamping_and_authenticated_json_boundary(self):
        expected={'endedExpiryHours':24,'stuckMinutes':15,'limitAlertPercent':10}
        self.assertEqual(json.loads(self.request('/api/settings')[2]),{'version':2,'settings':expected,'defaults':expected,'warnings':[]})
        submitted={'endedExpiryHours':999,'stuckMinutes':-1}
        for headers in ({'Origin':'http://127.0.0.1:1'},{'Content-Type':'text/plain'},{'X-Progress-Desk':'0'}):
            self.assertEqual(self.request('/api/settings',method='POST',body=submitted,headers=headers)[0],403)
        self.assertEqual(self.request('/api/settings',method='POST',body=submitted,owner=False)[0],401)
        code,_,raw=self.request('/api/settings',method='POST',body=submitted)
        self.assertEqual(code,200);value=json.loads(raw)
        self.assertEqual(value['settings'],{'endedExpiryHours':168,'stuckMinutes':5,'limitAlertPercent':10});self.assertEqual(value['defaults'],expected)
        from agents_service import AgentsService
        self.http.service=AgentsService(self.directory)
        self.assertEqual(json.loads(self.request('/api/settings')[2]),value)
        for invalid in ({'stuckMinutes':5},dict(expected,stop=True),dict(expected,stuckMinutes=True),
                        dict(expected,stuckMinutes=5.5),dict(expected,endedExpiryHours='24'),dict(expected,stuckMinutes=float('nan'))):
            self.assertEqual(self.request('/api/settings',method='POST',body=invalid)[0],400)
        self.assertEqual(json.loads(self.request('/api/settings')[2]),value)
        self.assertEqual((self.directory/'nagi-settings.json').stat().st_mode&0o777,0o600)

    def test_new_reservation_routes_require_owner_and_confirm_the_lease(self):
        from test_agents_v2 import Reader,NOW
        reader=Reader();service=server.AgentsService(self.directory,lambda _:reader,lambda:NOW)
        self.http.service=service
        with patch('agents_service.AgentsService.read_machine',lambda s,a:None):
            service.poll(force=True);reader.rows[0].update(status='failed',latestRunCompletedAt=NOW.isoformat());service.poll(force=True)
        identity=service.notifications()[0]['id']
        for route in ('reserve','release','claim'):
            self.assertEqual(self.request('/api/notifications/'+route,method='POST',body={'id':identity},owner=False)[0],401)
        path='/api/notifications/reserve'
        self.assertEqual(self.request(path,method='POST',body={'id':identity},headers={'Origin':'http://127.0.0.1:1'})[0],403)
        code,_,raw=self.request(path,method='POST',body={'id':identity});self.assertEqual(code,200)
        lease=json.loads(raw)['lease'];self.assertEqual(lease['event']['id'],identity)
        self.assertNotIn('reservation',lease['event'])
        self.assertFalse(json.loads(self.request(path,method='POST',body={'id':identity})[2])['reserved'])
        self.assertEqual(self.request('/api/notifications/claim',method='POST',body={'id':identity})[0],400)
        body={'id':identity,'reservation':lease['reservation']}
        self.assertTrue(json.loads(self.request('/api/notifications/claim',method='POST',body=body)[2])['claimed'])
        self.assertFalse(json.loads(self.request('/api/notifications/claim',method='POST',body=body)[2])['claimed'])

    def test_corrupt_state_is_reported_and_repairable_over_http(self):
        (self.directory/'nagi-settings.json').write_text('bad');(self.directory/'nagi-settings.json').chmod(0o644)
        (self.directory/'nagi-agent-state.json').write_text('[]');(self.directory/'nagi-agent-state.json').chmod(0o600)
        code,_,raw=self.request('/api/settings');self.assertEqual(code,200)
        self.assertEqual(json.loads(raw)['warnings'],['settings_invalid','journal_reset'])
        for route in ('/api/glance','/api/limits','/api/notifications'):
            self.assertEqual(self.request(route)[0],200)
        code,_,raw=self.request('/api/settings',method='POST',body={'endedExpiryHours':24,'stuckMinutes':15})
        self.assertEqual(code,200);self.assertEqual(json.loads(raw)['warnings'],[])

    def test_retired_task_routes_are_not_served(self):
        for path in ('/company/tasks/22','/api/company/tasks/22'):
            for owner in (True,False):
                self.assertEqual(self.request(path,owner=owner)[0],404)


class MachineTests(TestCase):
    def test_mac_host_metrics_sample_counters_without_proc(self):
        result = lambda args, **_: SimpleNamespace(stdout={
            'hw.memsize': '16384\n', 'kern.boottime': '{ sec = 1000, usec = 0 } Thu Jan 1\n',
            '/usr/bin/vm_stat': 'Mach Virtual Memory Statistics: (page size of 4096 bytes)\nPages free: 1.\nPages inactive: 1.\nPages speculative: 0.\n',
        }[args[-1] if args[0].endswith('sysctl') else args[0]])
        with patch('sys.platform', 'darwin'), patch('machine.subprocess.run', side_effect=result), \
             patch('machine.mac_cpu_ticks', side_effect=[(100, 80), (200, 130)]), \
             patch('machine.time.time', return_value=1120), patch('machine.time.sleep'), \
             patch('pathlib.Path.open', side_effect=AssertionError('/proc must not be read')):
            value = machine.host_metrics(Path("/"))
        self.assertEqual(value['memoryTotalBytes'], 16384)
        self.assertEqual(value['memoryUsedBytes'], 8192)
        self.assertEqual(value['cpuPercent'], 50)
        self.assertEqual(value['uptimeSeconds'], 120)

    def test_linux_host_metrics_use_proc_and_do_not_call_mac(self):
        original_open = Path.open
        def fake_open(path, *args, **kwargs):
            if str(path) == '/proc/meminfo':
                return io.StringIO('MemTotal: 100 kB\nMemAvailable: 40 kB\n')
            if str(path) == '/proc/uptime':
                return io.StringIO('123.0 100.0')
            return original_open(path, *args, **kwargs)
        with patch('sys.platform', 'linux'), patch('pathlib.Path.open', fake_open), \
             patch('machine.cpu_ticks', side_effect=[(100, 60), (200, 100)]), \
             patch('machine.time.sleep'), patch('machine.mac_memory_uptime') as mac:
            value = machine.host_metrics(Path("/"))
            self.assertEqual(value['cpuPercent'], 60)
            self.assertEqual(value['memoryUsedBytes'], 60 * 1024)
            self.assertEqual(value['uptimeSeconds'], 123)
            mac.assert_not_called()

    def test_unsupported_platform_reports_unsupported_before_any_read(self):
        with patch('sys.platform', 'other'), patch('pathlib.Path.open', side_effect=AssertionError('nothing is read')):
            self.assertEqual(machine.host_metrics(Path('/')), {'status': 'unsupported'})


class ReaderCommandTests(TestCase):
    def test_reader_entrypoint_uses_selected_runtime_and_browser_launch_cookie(self):
        import http.cookiejar
        import socket
        import time
        import urllib.error
        import urllib.request
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            auth = owner_auth.OwnerAuth(directory)
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', 0))
                port = probe.getsockname()[1]
            process = subprocess.Popen([sys.executable, '-B', str(ROOT / 'server.py'), '--port', str(port),
                                        '--data-dir', str(directory)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                origin = f'http://127.0.0.1:{port}'
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
                request = urllib.request.Request(origin + '/api/health')
                for _ in range(100):
                    try:
                        with owner_auth.authenticated_open(request, directory=directory, timeout=.2) as response:
                            self.assertEqual(json.load(response)['app'], 'nagi')
                        break
                    except OSError:
                        self.assertIsNone(process.poll(), 'Disposable reader exited before readiness')
                        time.sleep(.02)
                else:
                    self.fail('Disposable reader readiness timeout')
                from urllib.parse import urlsplit
                launch = owner_auth.launch_url(origin, directory=directory)
                with opener.open(origin + '/overview',timeout=3) as response:
                    self.assertIn(b'Agents and limits',response.read())
                ticket=urlsplit(launch).fragment.removeprefix('nagi-launch=')
                redeem=urllib.request.Request(origin+'/auth/redeem',data=json.dumps({'ticket':ticket,'path':'/overview'}).encode(),
                    headers={'Content-Type':'application/json','X-Progress-Desk':'1'})
                with opener.open(redeem,timeout=3) as response:
                    token=json.load(response)['token']
                for _ in range(100):
                    with opener.open(urllib.request.Request(origin+'/api/glance',headers={'X-Nagi-Session':token}),timeout=3) as response:
                        if json.load(response)['agents']['status']=='not_set_up':break
                    time.sleep(.02)
                else:self.fail('Source readiness timeout')
                self.assertFalse((directory / 'state.json').exists())
            finally:
                process.terminate()
                process.wait(timeout=5)
