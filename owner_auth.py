"""Owner credentials and one-use browser launch tickets. No credential logging."""
import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
import threading
import time
from urllib.parse import urlsplit
import urllib.request
import webbrowser

from jsonio import private_json

from runtime_paths import data_directory

TOKEN = re.compile(r'[A-Za-z0-9_-]{43}')
HEX = re.compile(r'[0-9a-f]{64}')
DESTINATION = re.compile(r'/(?:overview|glance|company/tasks/[1-9][0-9]*)')
LEGACY_DESTINATION = re.compile(r'/(?:\?widget=1&(?:compact|panel)=1)?(?:#(?:content|work|study|activity|next=[a-z0-9][a-z0-9_-]{0,63}))?')
TICKET_SECONDS = 10
SESSION_SECONDS = 900


def owner_secret(directory=None, *, create=False):
    directory = data_directory(directory)
    if create:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
        raise ValueError('Expected an owner-controlled runtime directory')
    path = directory / 'nagi-owner.json'
    if create:
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, 'w') as stream:
                json.dump({'version': 1, 'secret': secrets.token_urlsafe(32)}, stream)
                stream.flush()
                os.fsync(stream.fileno())
    data = private_json(path)
    if (not isinstance(data, dict) or set(data) != {'version', 'secret'}
            or type(data['version']) is not int or data['version'] != 1
            or not isinstance(data['secret'], str) or not TOKEN.fullmatch(data['secret'])
            or stat.S_IMODE(path.lstat().st_mode) != 0o600):
        raise ValueError('Invalid owner credential file')
    return data['secret']


def digest(body=b''):
    return hashlib.sha256(body).hexdigest()


def proof(secret, domain, origin, instance, client, nonce, method, path, body_hash):
    message = '\n'.join((domain, origin, instance, client, nonce, method, path, body_hash))
    return hmac.new(secret.encode('ascii'), message.encode('utf-8'), hashlib.sha256).hexdigest()


def valid_target(path):
    return isinstance(path, str) and 0 < len(path) <= 2048 and path.startswith('/') and not path.startswith('//') and all(32 < ord(c) < 127 for c in path) and '#' not in path


def origin_url(origin):
    parsed = urlsplit(origin)
    if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or not parsed.port
            or parsed.netloc != f'127.0.0.1:{parsed.port}' or parsed.path or parsed.query or parsed.fragment):
        raise ValueError('Expected a loopback origin')
    return origin


class OwnerAuth:
    def __init__(self, directory, origin=None):
        self.secret = owner_secret(directory, create=True)
        self.instance = secrets.token_urlsafe(32)
        self.origin = origin_url(origin) if origin is not None else None
        self.lock = threading.Lock()
        self.challenges, self.tickets, self.sessions = {}, {}, {}

    def bind(self, port):
        origin = f'http://127.0.0.1:{port}'
        with self.lock:
            if self.origin not in (None, origin):
                raise ValueError('Reader origin changed')
            self.origin = origin

    def challenge(self, value):
        if (not isinstance(value, dict) or set(value) != {'nonce', 'method', 'path', 'bodyHash'}
                or not isinstance(value['nonce'], str) or not TOKEN.fullmatch(value['nonce'])
                or value['method'] not in ('GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS')
                or not valid_target(value['path']) or not isinstance(value['bodyHash'], str)
                or not HEX.fullmatch(value['bodyHash']) or not self.origin):
            raise ValueError('Invalid challenge')
        with self.lock:
            now = time.monotonic()
            self.challenges = {key: item for key, item in self.challenges.items() if item[0] > now}
            if len(self.challenges) >= 128:
                self.challenges.pop(next(iter(self.challenges)))
            nonce = secrets.token_urlsafe(32)
            self.challenges[nonce] = (now + 10, dict(value))
        mac = proof(self.secret, 'nagi-server-v2', self.origin, self.instance, value['nonce'], nonce,
                    value['method'], value['path'], value['bodyHash'])
        return {'instance': self.instance, 'serverNonce': nonce, 'proof': mac}

    def authenticated(self, headers, method='GET', path='/', body=b''):
        authorization = headers.get_all('Authorization', [])
        sessions = headers.get_all('X-Nagi-Session', [])
        if authorization:
            if len(authorization) != 1 or sessions or not authorization[0].startswith('NagiProof '):
                return False
            parts = authorization[0][10:].split('.')
            if len(parts) != 4 or not all(TOKEN.fullmatch(p) for p in parts[:3]) or not HEX.fullmatch(parts[3]):
                return False
            instance, client, nonce, mac = parts
            with self.lock:
                item = self.challenges.pop(nonce, None)
            expected = {'nonce': client, 'method': method, 'path': path, 'bodyHash': digest(body)}
            if not item or item[0] <= time.monotonic() or item[1] != expected or instance != self.instance:
                return False
            correct = proof(self.secret, 'nagi-client-v2', self.origin, instance, client, nonce, method, path, digest(body))
            return hmac.compare_digest(mac, correct)
        if len(sessions) != 1 or not TOKEN.fullmatch(sessions[0]):
            return False
        with self.lock:
            self.sessions = {key: value for key, value in self.sessions.items() if value[0] > time.monotonic()}
            item = self.sessions.get(sessions[0])
            return bool(item and self.origin and item[1] == self.origin)

    def issue(self, path):
        if not isinstance(path, str) or not (DESTINATION.fullmatch(path) or LEGACY_DESTINATION.fullmatch(path)):
            raise ValueError('Invalid launch destination')
        with self.lock:
            now = time.monotonic()
            self.tickets = {key: value for key, value in self.tickets.items() if value[0] > now}
            if len(self.tickets) >= 64:
                raise RuntimeError('Launch capacity reached')
            token = secrets.token_urlsafe(32)
            self.tickets[token] = (now + TICKET_SECONDS, path)
        return token

    def redeem(self, token, path):
        if not isinstance(token, str) or not TOKEN.fullmatch(token):
            return None
        with self.lock:
            now = time.monotonic()
            item = self.tickets.pop(token, None)
            if not item or item[0] <= now or item[1].split('#')[0] != path:
                return None
            self.sessions = {key: value for key, value in self.sessions.items() if value[0] > now}
            if len(self.sessions) >= 128:
                raise RuntimeError('Session capacity reached')
            session = secrets.token_urlsafe(32)
            self.sessions[session] = (now + SESSION_SECONDS, self.origin)
        return {'token': session, 'expiresAt': int(time.time()) + SESSION_SECONDS,
                'fragment': urlsplit(item[1]).fragment}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def auth_headers(origin, method='GET', path='/api/health', body=b'', directory=None, *, timeout=5):
    origin_url(origin)
    secret = owner_secret(directory)
    client = secrets.token_urlsafe(32)
    value = {'nonce': client, 'method': method, 'path': path, 'bodyHash': digest(body)}
    request = urllib.request.Request(origin + '/auth/challenge', data=json.dumps(value).encode(),
        headers={'Content-Type': 'application/json', 'X-Progress-Desk': '1'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=timeout) as response:
        raw = response.read(4097)
    if len(raw) > 4096:
        raise ValueError('Invalid reader proof')
    result = json.loads(raw)
    if (not isinstance(result, dict) or set(result) != {'instance', 'serverNonce', 'proof'}
            or not all(isinstance(result[k], str) and TOKEN.fullmatch(result[k]) for k in ('instance', 'serverNonce'))
            or not isinstance(result['proof'], str) or not HEX.fullmatch(result['proof'])):
        raise ValueError('Invalid reader proof')
    expected = proof(secret, 'nagi-server-v2', origin, result['instance'], client, result['serverNonce'], method, path, digest(body))
    if not hmac.compare_digest(expected, result['proof']):
        raise ValueError('Reader identity could not be verified')
    mac = proof(secret, 'nagi-client-v2', origin, result['instance'], client, result['serverNonce'], method, path, digest(body))
    return {'Authorization': 'NagiProof ' + '.'.join((result['instance'], client, result['serverNonce'], mac))}


def authenticated_open(request, directory=None, *, timeout=5):
    parsed = urlsplit(request.full_url)
    origin = f'{parsed.scheme}://{parsed.netloc}'
    path = parsed.path + ('?' + parsed.query if parsed.query else '')
    for key, value in auth_headers(origin, request.get_method(), path, request.data or b'', directory, timeout=timeout).items():
        request.add_header(key, value)
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(request, timeout=timeout)


def launch_url(origin, path='/overview', directory=None):
    origin_url(origin)
    request = urllib.request.Request(origin + '/auth/launch', data=json.dumps({'path': path}).encode(),
        headers={'Content-Type': 'application/json', 'X-Progress-Desk': '1'})
    with authenticated_open(request, directory, timeout=5) as response:
        result = json.loads(response.read(4097))
    url = result['url']
    if not isinstance(url, str) or not url.startswith(origin + '/') or not re.fullmatch(r'nagi-launch=[A-Za-z0-9_-]{43}', urlsplit(url).fragment):
        raise ValueError('Invalid launch response')
    return url


def open_browser(origin, path='/overview', directory=None):
    webbrowser.open(launch_url(origin, path, directory))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Open this computer’s private Nagi view')
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--port', type=int, default=47831)
    parser.add_argument('--path', default='/overview')
    args = parser.parse_args()
    try:
        open_browser(f'http://127.0.0.1:{args.port}', args.path, args.data_dir)
    except (OSError, ValueError, KeyError, TypeError):
        parser.exit(1, 'Cannot open Nagi. Check the local reader and owner setup.\n')
