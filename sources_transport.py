"""Bounded setup I/O. No upstream diagnostics or secret-bearing repr escapes."""
import http.client
import ipaddress
import os
import plistlib
import re
import selectors
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

from agents_projection import display
from t3_reader import TAILNET, IODeadline, T3Reader, Unavailable, source_origin
from jsonio import strict_json_loads

SCOPE = 'orchestration:read'
ACCESS_TYPE = 'urn:ietf:params:oauth:token-type:access_token'


ERROR_CODES = {
    'invalid_request', 'owner_required', 'origin_denied', 'not_found', 'method_not_allowed',
    'test_expired', 'configuration_changed', 'source_exists', 'peer_expired', 'request_too_large',
    'pairing_invalid', 'scope_mismatch', 'connection_failed', 'local_pairing_unavailable',
    'storage_unavailable', 'capacity_reached', 'tailscale_unavailable',
    'hook_install_failed', 'hook_remove_failed',
}


class SourceError(Exception):
    def __init__(self, code, status=400):
        # Even a future adapter cannot accidentally promote arbitrary provider
        # text to an HTTP error or a logged exception message.
        if not isinstance(code,str) or code not in ERROR_CODES:
            code, status = 'connection_failed', 422
        super().__init__(code)
        self.code, self.status = code, status


def private_directory(path):
    path = Path(path)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise SourceError('storage_unavailable', 503)
    return path


def valid_token(value):
    return (isinstance(value, str) and 16 <= len(value) <= 8192
            and all(33 <= ord(c) <= 126 for c in value))


def write_credential(path, token):
    if not valid_token(token):
        raise SourceError('pairing_invalid', 422)
    import json
    path = Path(path)
    parent = private_directory(path.parent)
    fd, temporary = tempfile.mkstemp(prefix='.credential-', dir=parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(json.dumps({'token': token, 'scopes': [SCOPE]}).encode())
            stream.flush()
            os.fsync(stream.fileno())
        # Publish complete bytes atomically, with no replacement/following of an
        # existing destination. Registry publication happens only afterward.
        os.link(temporary, path, follow_symlinks=False)
        directory_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        os.unlink(temporary)


def bounded_command(args, *, limit=1024 * 1024, seconds=3, env=None):
    """Drain bounded stdout, discard stderr, kill/reap this PID on every failure."""
    with subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, env=env) as process:
        try:
            deadline = time.monotonic() + seconds
            data = bytearray()
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        raise SourceError('connection_failed', 422)
                    block = os.read(process.stdout.fileno(), min(4096, limit + 1 - len(data)))
                    if not block:
                        break
                    data.extend(block)
                    if len(data) > limit:
                        raise SourceError('connection_failed', 422)
            if process.wait(timeout=max(.001, deadline - time.monotonic())) != 0:
                raise SourceError('connection_failed', 422)
            return bytes(data)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()


CLI_ENV_KEYS=('HOME','PATH','LANG','USER','TMPDIR')


def cli_environment(extra=None):
    # The reader may carry provider keys, Node injection flags and profile/home
    # overrides; none belongs in a source observer provisioning subprocess.
    env={key:os.environ[key] for key in CLI_ENV_KEYS if key in os.environ}
    if extra is not None:
        env.update({key:extra[key] for key in CLI_ENV_KEYS if key in extra})
        if extra.get('ELECTRON_RUN_AS_NODE')=='1':env['ELECTRON_RUN_AS_NODE']='1'
    return env


def local_cli():
    args = ['auth', 'session', 'issue', '--scope', SCOPE, '--label',
            'Nagi (read-only, this computer)', '--ttl', '365d', '--token-only', '--log-level', 'none']
    cli = shutil.which('t3')
    if cli:
        return [cli, *args], cli_environment()
    if sys.platform == 'darwin':
        for base in (Path('/Applications'), Path.home() / 'Applications'):
            for app in sorted(base.glob('T3 Code*.app')):
                try:
                    metadata = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
                    name = metadata['CFBundleExecutable']
                    if not isinstance(name, str) or Path(name).name != name:
                        continue
                    executable = app / 'Contents/MacOS' / name
                    for packaged in ('app.asar.unpacked', 'app.asar'):
                        entry = app / f'Contents/Resources/{packaged}/apps/server/dist/bin.mjs'
                        if executable.is_file() and os.access(executable, os.X_OK) and (entry.exists() or (packaged == 'app.asar' and (app / 'Contents/Resources/app.asar').is_file())):
                            return [str(executable), str(entry), *args], cli_environment({'ELECTRON_RUN_AS_NODE':'1'})
                except (OSError, ValueError, KeyError, TypeError):
                    continue
    raise SourceError('local_pairing_unavailable', 422)


def issue_local(path):
    args, env = local_cli()
    env=cli_environment(env)
    path=Path(path)
    private_directory(path.parent)
    if os.path.lexists(path):
        raise SourceError('storage_unavailable',503)
    writer=None
    completed=False
    # As in mac/setup-mac.sh, connect token-only CLI stdout directly to a
    # credential-from-stdin writer. The HTTP server never captures CLI tokens.
    with subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL,env=env) as issuer:
        try:
            deadline=time.monotonic()+15
            writer=subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),
                                     '--credential-from-stdin',str(path)],
                                    stdin=issuer.stdout,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=cli_environment())
            issuer.stdout.close()
            writer_status=writer.wait(timeout=max(.001,deadline-time.monotonic()))
            issuer_status=issuer.wait(timeout=max(.001,deadline-time.monotonic()))
            if writer_status!=0 or issuer_status!=0:
                raise SourceError('connection_failed',422)
            completed=True
        except subprocess.TimeoutExpired:
            raise SourceError('connection_failed',422) from None
        finally:
            for process in (writer,issuer):
                if process is not None:
                    if process.poll() is None:
                        process.kill()
                    process.wait()
            if not completed:
                path.unlink(missing_ok=True)


def tailnet_inventory():
    cli = shutil.which('tailscale')
    if not cli:
        raise SourceError('tailscale_unavailable')
    value = strict_json_loads(bounded_command([cli, 'status', '--json']), 1024 * 1024, max_depth=32)
    if not isinstance(value, dict) or not isinstance(value.get('Peer'), dict) or len(value['Peer']) > 512:
        raise SourceError('tailscale_unavailable')
    peers = []
    for peer in value['Peer'].values():
        if not isinstance(peer, dict):
            continue
        addresses = []
        for address in peer.get('TailscaleIPs', []) if isinstance(peer.get('TailscaleIPs'), list) else []:
            try:
                parsed = ipaddress.IPv4Address(address)
                if parsed in TAILNET:
                    addresses.append(str(parsed))
            except (ValueError, TypeError, ipaddress.AddressValueError):
                continue
        if not addresses:
            continue
        dns = peer.get('DNSName', '')
        dns = dns.rstrip('.') if isinstance(dns, str) else ''
        try:
            if source_origin('https://' + dns)[0] != 'tls':
                dns = ''
        except ValueError:
            dns = ''
        peers.append({'addresses': addresses, 'dns': dns,
                      'label': display(peer.get('HostName'), 80, 'Computer'),
                      'online': peer.get('Online') is True})
    return peers


def pairing_parts(value):
    """Parse a pairing input without fetching it or exposing it in diagnostics."""
    if (not isinstance(value,str) or not 0<len(value)<=3500 or value!=value.strip()
            or any(ord(c)<33 or ord(c)>126 for c in value)):
        raise SourceError('pairing_invalid',422)
    if value.startswith('t3code://'):
        app=urlsplit(value)
        query=parse_qs(app.query,strict_parsing=True,keep_blank_values=True)
        if (app.scheme!='t3code' or app.netloc!='pair' or app.path or app.fragment
                or '#' in value or set(query)!={'pairingUrl'} or len(query['pairingUrl'])!=1):
            raise SourceError('pairing_invalid',422)
        value=query['pairingUrl'][0]
        if any(ord(c)<33 or ord(c)>126 for c in value):
            raise SourceError('pairing_invalid',422)
    origin,token=None,value
    if '://' in value:
        link=urlsplit(value)
        origin=f'{link.scheme}://{link.netloc}'
        source_origin(origin)
        if (link.path!='/pair' or '?' in value.split('#',1)[0] or not link.fragment.startswith('token=')
                or '&' in link.fragment or '#' in link.fragment):
            raise SourceError('pairing_invalid',422)
        token=link.fragment[len('token='):]
    if not (re.fullmatch(r'[23456789ABCDEFGHJKLMNPQRSTUVWXYZ]{12}',token) or valid_token(token)):
        raise SourceError('pairing_invalid',422)
    return origin,token


def pairing_target(value, peer, port):
    """A discovered peer pins the origin, even when a link is pasted."""
    origin,token=pairing_parts(value)
    if origin is None:
        origin=f"http://{peer['addresses'][0]}:{port}"
    kind,host,_=source_origin(origin)
    if kind=='loopback' or host not in peer['addresses']+([peer['dns']] if peer['dns'] else []):
        raise SourceError('pairing_invalid',422)
    return origin,token


def manual_pairing_target(value, origin=None):
    """Explicit owner selection without discovery; use the same transport rules."""
    linked,token=pairing_parts(value)
    if origin is not None:
        explicit=source_origin(origin)
        if linked is not None and source_origin(linked)!=explicit:
            raise SourceError('pairing_invalid',422)
    target=linked if linked is not None else origin
    kind,host,port=source_origin(target)
    # Canonicalize the optional HTTPS default port for stable conflict checking.
    target=(f'https://{host}'+('' if port==443 else f':{port}') if kind=='tls' else f'http://{host}:{port}')
    return target,token


def exchange_pairing(origin, token):
    reader = T3Reader.public(origin)
    body = urlencode({'grant_type': 'urn:ietf:params:oauth:grant-type:token-exchange',
                      'subject_token': token,
                      'subject_token_type': 'urn:t3:params:oauth:token-type:environment-bootstrap',
                      'requested_token_type': ACCESS_TYPE, 'scope': SCOPE,
                      'client_label': 'Nagi (read-only)', 'client_device_type': 'desktop'}).encode()
    connection = reader.connection()
    try:
        with IODeadline(connection, 8) as budget:
            connection.connect()
            budget.connected()
            connection.request('POST', '/oauth/token', body=body,
                               headers={'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json'})
            response = connection.getresponse()
            raw = response.read(16385)
            budget.check()
            if response.status != 200:
                raise SourceError('pairing_invalid', 422)
            result = strict_json_loads(raw, 16384, max_depth=8)
        if (not isinstance(result, dict) or result.get('scope') != SCOPE
                or result.get('token_type') != 'Bearer' or result.get('issued_token_type') != ACCESS_TYPE):
            raise SourceError('scope_mismatch', 422)
        if (not valid_token(result.get('access_token')) or type(result.get('expires_in')) not in (int, float)
                or not 0 < result['expires_in'] <= 366 * 86400):
            raise SourceError('pairing_invalid', 422)
        return result['access_token']
    except SourceError:
        raise
    except (Unavailable, OSError, ValueError, TypeError, http.client.HTTPException, RecursionError):
        raise SourceError('connection_failed', 422) from None
    finally:
        connection.close()


if __name__=='__main__':
    # Private, bounded pipe sink for local auto-pair. No stdout/stderr diagnostics.
    try:
        if len(sys.argv)!=3 or sys.argv[1]!='--credential-from-stdin':
            raise ValueError()
        raw=sys.stdin.buffer.read(8193)
        write_credential(Path(sys.argv[2]),raw.decode('ascii').strip())
    except (SourceError,OSError,ValueError):
        sys.exit(1)
