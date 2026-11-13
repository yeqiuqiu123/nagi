"""Closed, read-only protocol-2 client. Credentials stay inside this transport."""
import base64
import hashlib
import http.client
import ipaddress
import json
import os
import re
import secrets
import socket
import ssl
import struct
import sys
import time
import threading
from urllib.parse import quote, urlsplit

from loopback_peer import peer_uid
from jsonio import private_json
from jsonio import strict_json_loads

MAX_RESPONSE = 8 * 1024 * 1024
WS_SECONDS=8
HTTP_SECONDS=8
LIVENESS_SECONDS=8
MAX_HISTORY_PAGES=3
MAX_HISTORY_ITEMS=2000
MAX_HISTORY_BYTES=4*1024*1024


class NotConfigured(Exception): pass
class Unsupported(Exception): pass
class Unavailable(Exception): pass


class OwnerConnection(http.client.HTTPConnection):
    def connect(self):
        super().connect()
        if sys.platform == 'linux' and peer_uid(self.sock.getpeername(), self.sock.getsockname()) != os.getuid():
            self.close()
            raise Unavailable('Local source identity unavailable')


class TailnetConnection(http.client.HTTPConnection):
    """Plain HTTP to one Tailscale CGNAT address, carried inside WireGuard.

    No peer-UID check: the listener is on another machine, so there is no local
    socket owner to match. The tailnet's node identity stands in for it."""


TAILNET = ipaddress.IPv4Network('100.64.0.0/10')
LABEL = r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?'
TS_NET = re.compile(r'(?:' + LABEL + r'\.)+ts\.net')


def source_origin(value):
    """(kind, host, port) for the T3 origin in nagi-t3.json, or ValueError.

    loopback: http://127.0.0.1:<port> (Linux peer-UID checked before any credential).
    tailnet:  http://<IPv4 in 100.64.0.0/10>:<port>.
    tls:      https://<name>.ts.net[:port], with normal certificate verification.
    No other host, scheme, path, query, fragment, userinfo, IPv6 or http hostname."""
    if not isinstance(value, str) or not value.isascii() or any(ord(c) < 33 or ord(c) > 126 for c in value):
        raise ValueError('Invalid source origin')
    origin = urlsplit(value)
    if (origin.path or '?' in value or '#' in value or '@' in origin.netloc
            or origin.username is not None or origin.password is not None):
        raise ValueError('Invalid source origin')
    host, port = origin.hostname, origin.port  # port raises ValueError when malformed
    if origin.scheme == 'http' and host and port and origin.netloc == f'{host}:{port}':
        try:
            address = ipaddress.IPv4Address(host)
        except ValueError:
            raise ValueError('Invalid source origin') from None
        if str(address) == host and host == '127.0.0.1':
            return 'loopback', host, port
        if str(address) == host and address in TAILNET:
            return 'tailnet', host, port
    if (origin.scheme == 'https' and host and TS_NET.fullmatch(host) and len(host) <= 253
            and (port is None or port > 0) and origin.netloc in (host, f'{host}:{port}')):
        return 'tls', host, port or 443
    raise ValueError('Invalid source origin')


class IODeadline:
    """One budget for connect, headers and body, including trickle reads."""
    def __init__(self,connection,seconds):
        self.connection=connection;self.seconds=seconds;self.sock=None
    def __enter__(self):
        self.deadline=time.monotonic()+self.seconds
        self.connection.timeout=min(4,self.seconds)
        def expire():
            sock=self.sock or getattr(self.connection,'sock',None)
            if sock is not None:
                try:sock.shutdown(socket.SHUT_RDWR)
                except OSError:pass
        self.timer=threading.Timer(self.seconds,expire);self.timer.daemon=True;self.timer.start()
        return self
    def connected(self):
        self.sock=self.connection.sock;self.check()
        self.sock.settimeout(min(4,self.deadline-time.monotonic()))
    def check(self):
        if time.monotonic()>=self.deadline:raise Unavailable()
    def __exit__(self,*_):self.timer.cancel()


class T3Reader:
    def __init__(self, directory):
        from pathlib import Path
        try:
            policy = private_json(Path(directory) / 'nagi-t3.json')
        except FileNotFoundError:
            raise NotConfigured() from None
        self._load_policy(policy)

    @classmethod
    def public(cls, origin):
        """Credential-free transport, using exactly the same origin/UID/TLS rules."""
        reader=object.__new__(cls)
        reader.kind,reader.host,reader.port=source_origin(origin)
        return reader

    @classmethod
    def from_policy(cls, policy):
        reader=object.__new__(cls)
        reader._load_policy(policy)
        return reader

    def _load_policy(self, policy):
        from pathlib import Path
        if not isinstance(policy, dict) or set(policy) != {'version','origin','credentialFile'} or type(policy['version']) is not int or policy['version'] != 1:
            raise Unavailable()
        try: self.kind, self.host, port = source_origin(policy['origin'])
        except ValueError: raise Unavailable() from None
        path = Path(policy['credentialFile'])
        if not path.is_absolute(): raise Unavailable()
        try: credential = private_json(path)
        except FileNotFoundError: raise NotConfigured() from None
        if (not isinstance(credential, dict) or set(credential) != {'token','scopes'}
                or credential['scopes'] != ['orchestration:read'] or not isinstance(credential['token'], str)
                or not 16 <= len(credential['token']) <= 8192
                or any(ord(c) < 33 or ord(c) > 126 for c in credential['token'])):
            raise Unavailable()
        self.port, self._token = port, credential['token']

    def connection(self):
        # http.client never follows redirects, so the token only reaches this origin.
        kind, host = getattr(self, 'kind', 'loopback'), getattr(self, 'host', '127.0.0.1')
        if kind == 'tls':
            return http.client.HTTPSConnection(host, self.port, timeout=4, context=ssl.create_default_context())
        if kind == 'tailnet':
            return TailnetConnection(host, self.port, timeout=4)
        return OwnerConnection('127.0.0.1', self.port, timeout=4)

    def read_budget(self, seconds):
        deadline=getattr(self,'_source_deadline',None)
        if deadline is not None:
            seconds=min(seconds,deadline-time.monotonic())
        if seconds<=0:raise Unavailable()
        return seconds

    def get(self, path, *, authenticated=True, timeout=None):
        connection = self.connection()
        try:
            with IODeadline(connection,self.read_budget(min(HTTP_SECONDS,timeout) if timeout is not None else HTTP_SECONDS)) as budget:
                connection.connect()  # Verify the listener (local UID or TLS) before any credential.
                budget.connected()
                headers = {'x-t3-orchestration-protocol':'2','Accept':'application/json'}
                if authenticated: headers['Authorization'] = 'Bearer ' + self._token
                connection.request('GET', path, headers=headers)
                response = connection.getresponse()
                raw = response.read(MAX_RESPONSE + 1)
                budget.check()
                if response.status in (404,426): raise Unsupported()
                if response.status != 200 or len(raw) > MAX_RESPONSE: raise Unavailable()
                return strict_json_loads(raw,MAX_RESPONSE,max_depth=160)
        except (OSError, ValueError, RecursionError, http.client.HTTPException):
            raise Unavailable() from None
        finally: connection.close()

    def shell(self):
        descriptor = self.get('/.well-known/t3/environment', authenticated=False)
        if descriptor.get('orchestrationProtocolVersion') != 2: raise Unsupported()
        snapshot = self.get('/api/orchestration/shell?omitIdleSubagents=0&omitOlderSettled=1')
        return descriptor, snapshot

    def detail(self, identity):
        return self.get('/api/orchestration/threads/' + quote(identity,safe='') + '/bounded')

    def liveness(self,identity,run,started_at=None):
        """Page only far enough to cover this run; never fetch a full transcript."""
        from agents_projection import current_run_covered
        deadline=time.monotonic()+self.read_budget(LIVENESS_SECONDS)
        def fetch(path):
            remaining=deadline-time.monotonic()
            if remaining<=0:raise Unavailable()
            return self.get(path,timeout=remaining)
        path='/api/orchestration/threads/'+quote(identity,safe='')
        detail=fetch(path+'/bounded')
        if not isinstance(detail,dict):return None
        projection=detail.get('projection')
        if not isinstance(projection,dict) or not isinstance(projection.get('turnItems'),list):return None
        seen=set();pages=0;size=len(json.dumps(detail).encode())
        if size>MAX_HISTORY_BYTES or len(projection['turnItems'])>MAX_HISTORY_ITEMS:return None
        while not current_run_covered(detail,run,started_at):
            cursor=detail.get('historyCursor')
            if (not isinstance(cursor,str) or not 0<len(cursor)<=4096 or cursor in seen or pages>=MAX_HISTORY_PAGES
                    or len(projection['turnItems'])>=MAX_HISTORY_ITEMS or size>=MAX_HISTORY_BYTES):break
            if detail.get('idTable') or detail.get('turnItemsOmitLocalVisible'):break
            # Already observed work safely suppresses stuck without more history.
            if any(isinstance(i,dict) and i.get('runId')==run and i.get('status') in ('running','waiting','pending')
                   and not i.get('completedAt') for i in projection['turnItems']):break
            seen.add(cursor);pages+=1
            page=fetch(path+'/history?cursor='+quote(cursor,safe=''))
            if (not isinstance(page,dict) or page.get('idTable') or page.get('snapshotSequence')!=detail.get('snapshotSequence')
                    or not isinstance(page.get('items'),list)):return None
            size+=len(json.dumps(page).encode())
            if size>MAX_HISTORY_BYTES:return None
            older=[]
            for projected in page['items']:
                if not isinstance(projected,dict) or not isinstance(projected.get('item'),dict):return None
                if projected.get('sourceThreadId')==identity:older.append(projected['item'])
            if len(older)+len(projection['turnItems'])>MAX_HISTORY_ITEMS:return None
            # Update overlapping items from the newest snapshot, not older pages.
            existing={item.get('id') for item in projection['turnItems'] if isinstance(item,dict) and item.get('id')}
            projection['turnItems']=[item for item in older if not item.get('id') or item['id'] not in existing]+projection['turnItems']
            projection['visibleTurnItems']=page['items']+projection.get('visibleTurnItems',[])
            detail['hasMoreHistory']=page.get('hasMoreHistory');detail['historyCursor']=page.get('nextCursor')
        return detail

    def config(self):
        """Only server.getConfig and project-favicon assets.createUrl are ever emitted."""
        return self._rpc('server.getConfig', {})

    def favicon_url(self, cwd, path=None):
        """T3's own project-favicon lookup (orchestration:read). Returns a same-origin
        relative URL, or None for T3's fallback marker."""
        resource = {'_tag': 'project-favicon', 'cwd': cwd}
        if path is not None: resource['path'] = path
        value = self._rpc('assets.createUrl', {'resource': resource})
        url = value.get('relativeUrl') if isinstance(value, dict) else None
        if not valid_asset_url(url): raise Unavailable()
        return None if url.rsplit('/', 1)[-1] == FAVICON_FALLBACK_MARKER else url

    def asset(self, url):
        """Fetch a signed /api/assets/ URL from this same T3 origin: bounded, typed, sniffed.
        The signed path is the credential; no bearer token is sent. None means no image."""
        if not valid_asset_url(url): raise ValueError('Not a T3 asset URL')
        connection = self.connection()
        try:
            with IODeadline(connection, self.read_budget(HTTP_SECONDS)) as budget:
                connection.connect(); budget.connected()
                connection.request('GET', url, headers={'Accept': 'image/*'})
                response = connection.getresponse()
                raw = response.read(MAX_ICON_BYTES + 1)
                budget.check()
                if response.status != 200: return None
                kind = (response.getheader('Content-Type') or '').split(';')[0].strip().lower()
                return checked_image(raw, kind)
        except (OSError, ValueError, http.client.HTTPException):
            raise Unavailable() from None
        finally: connection.close()

    def _rpc(self, tag, payload):
        """One request over T3's RPC WebSocket. Closed allowlist; not a generic proxy."""
        if not rpc_allowed(tag, payload): raise ValueError('RPC not allowed')
        connection = self.connection()
        try:
            with IODeadline(connection,self.read_budget(WS_SECONDS)) as budget:
                connection.connect();budget.connected();deadline=budget.deadline
                key = base64.b64encode(secrets.token_bytes(16)).decode()
                connection.putrequest('GET','/ws?orchestrationProtocol=2')
                for name,value in {'Upgrade':'websocket','Connection':'Upgrade','Sec-WebSocket-Key':key,
                                   'Sec-WebSocket-Version':'13','Authorization':'Bearer '+self._token}.items():
                    connection.putheader(name,value)
                connection.endheaders()
                response = connection.getresponse()
                expected = base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
                if response.status != 101 or response.getheader('Sec-WebSocket-Accept') != expected:
                    raise Unavailable()
                budget.check()
                # HTTPResponse buffers bytes after the upgrade; continue through its reader.
                stream = response.fp
                send_frame(connection.sock, 1, json.dumps({'_tag':'Request','id':'1','tag':tag,'payload':payload,'headers':[]}).encode())
                accumulated = bytearray()
                for _ in range(256):
                    remaining=deadline-time.monotonic()
                    if remaining<=0:raise Unavailable()
                    connection.sock.settimeout(min(4,remaining))
                    opcode, final, data = read_frame(stream,deadline,connection.sock)
                    if opcode == 8: raise Unavailable()
                    if opcode == 9:
                        send_frame(connection.sock,10,data);continue
                    if opcode == 10: continue
                    if opcode not in (0,1): raise Unavailable()
                    accumulated.extend(data)
                    if len(accumulated) > MAX_RESPONSE: raise Unavailable()
                    if not final: continue
                    messages = strict_json_loads(accumulated,MAX_RESPONSE,max_depth=160);accumulated.clear()
                    for message in messages if isinstance(messages,list) else [messages]:
                        if not isinstance(message,dict):raise Unavailable()
                        if message.get('_tag') == 'Ping':
                            send_frame(connection.sock,1,b'{"_tag":"Pong"}');continue
                        if message.get('_tag') == 'Exit' and str(message.get('requestId',message.get('id'))) == '1':
                            exit = message.get('exit',{})
                            if exit.get('_tag') != 'Success': raise Unavailable()
                            value=exit['value']
                            if not isinstance(value,dict):raise Unavailable()
                            return value
                raise Unavailable()
        except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError, http.client.HTTPException):
            raise Unavailable() from None
        finally:connection.close()


FAVICON_FALLBACK_MARKER = 'project-favicon-missing'
MAX_ICON_BYTES = 256 * 1024
ICON_TYPES = {'image/png', 'image/jpeg', 'image/webp', 'image/gif', 'image/x-icon', 'image/vnd.microsoft.icon', 'image/svg+xml'}


def rpc_allowed(tag, payload):
    """server.getConfig with an empty payload, or assets.createUrl for a project favicon only:
    never workspace-file, media-file, draft-workspace-file or any other resource."""
    if tag == 'server.getConfig': return payload == {}
    if tag != 'assets.createUrl' or not isinstance(payload, dict) or set(payload) != {'resource'}: return False
    resource = payload['resource']
    if not isinstance(resource, dict) or resource.get('_tag') != 'project-favicon': return False
    if not {'_tag', 'cwd'} <= set(resource) <= {'_tag', 'cwd', 'path'}: return False
    cwd = resource['cwd']
    if not isinstance(cwd, str) or not cwd.strip() or cwd != cwd.strip() or len(cwd) > 1024: return False
    path = resource.get('path')
    if path is not None and (not isinstance(path, str) or path != path.strip() or not 0 < len(path) <= 1024
                             or not path.lower().endswith(('.avif', '.gif', '.icns', '.ico', '.jpg', '.jpeg', '.png', '.svg', '.webp'))):
        return False
    return True


def valid_asset_url(url):
    return (isinstance(url, str) and url.startswith('/api/assets/') and len(url) <= 4096
            and all(32 < ord(c) < 127 for c in url) and '..' not in url and '?' not in url and '#' not in url and '\\' not in url)


def checked_image(raw, kind):
    """Bytes within 256 KB whose declared type is allowlisted and matches their magic bytes."""
    if len(raw) > MAX_ICON_BYTES or not raw or kind not in ICON_TYPES: return None
    head = raw[:16]
    sniffed = ('image/png' if head.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg' if head.startswith(b'\xff\xd8\xff')
               else 'image/gif' if head[:6] in (b'GIF87a', b'GIF89a') else 'image/webp' if head[:4] == b'RIFF' and raw[8:12] == b'WEBP'
               else 'image/x-icon' if head[:4] == b'\x00\x00\x01\x00'
               else 'image/svg+xml' if b'<svg' in raw[:2048].lower() and raw.lstrip(b'\xef\xbb\xbf \t\r\n')[:1] == b'<' else None)
    if kind == 'image/vnd.microsoft.icon': kind = 'image/x-icon'
    return (raw, kind) if sniffed == kind else None


def send_frame(sock, opcode, data):
    mask = secrets.token_bytes(4)
    length = len(data)
    size = bytes([0x80|length]) if length < 126 else b'\xfe'+struct.pack('!H',length) if length <= 65535 else b'\xff'+struct.pack('!Q',length)
    sock.sendall(bytes([0x80|opcode])+size+mask+bytes(byte ^ mask[i%4] for i,byte in enumerate(data)))


def read_frame(stream,deadline=None,sock=None):
    def read(n):
        result=bytearray()
        while len(result)<n:
            if deadline is not None:
                remaining=deadline-time.monotonic()
                if remaining<=0:raise Unavailable()
                if sock is not None:sock.settimeout(min(4,remaining))
            value=getattr(stream,'read1',stream.read)(n-len(result))
            if not value:raise Unavailable()
            result.extend(value)
        return bytes(result)
    first,second=read(2)
    if first & 0x70 or second & 0x80: raise Unavailable()
    length=second&127
    if length == 126: length=struct.unpack('!H',read(2))[0]
    if length == 127: length=struct.unpack('!Q',read(8))[0]
    if length > MAX_RESPONSE: raise Unavailable()
    return first&15,bool(first&0x80),read(length)
