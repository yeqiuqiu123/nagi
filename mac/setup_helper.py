#!/usr/bin/env python3
"""Small, quiet steps for mac/setup-mac.sh. Never prints a token.

  credential-from-stdin PATH   store a read-only T3 token piped on stdin (0600, only if absent)
  credential-ok PATH           exit 0 when PATH is a valid private read-only credential
  policy DATA_DIR ORIGIN CRED  write <data>/nagi-t3.json (0600) when it differs
  origin-kind ORIGIN           print loopback, tailnet or tls; exit 1 when refused
  t3-ok ORIGIN                 exit 0 when ORIGIN serves T3 orchestration protocol 2 (public probe)
  app-agent PLIST APP          write the launch-at-login LaunchAgent for Nagi.app
"""
import json
import os
from pathlib import Path
import plistlib
import stat
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from t3_reader import source_origin  # noqa: E402  (one origin rule for reader and setup)

SCOPES = ['orchestration:read']


def valid_token(value):
    return isinstance(value, str) and 16 <= len(value) <= 8192 and all(33 <= ord(c) <= 126 for c in value)


def private_file(path):
    info = os.lstat(path)
    return stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o600


def write_private(path, body):
    """Atomic 0600 write in an existing owner-only directory; never follows links."""
    path = Path(path)
    parent = path.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid() or parent.st_mode & 0o077:
        raise ValueError('Expected an owner-only directory')
    temporary = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def credential_ok(path):
    try:
        if not private_file(path):
            return False
        value = json.loads(Path(path).read_bytes()[:16384])
    except (OSError, ValueError):
        return False
    return (isinstance(value, dict) and set(value) == {'token', 'scopes'}
            and value['scopes'] == SCOPES and valid_token(value['token']))


def credential_from_stdin(path):
    if os.path.lexists(path):
        return 0 if credential_ok(path) else 3
    token = sys.stdin.read(8193).strip()
    if not valid_token(token):
        return 2
    write_private(path, json.dumps({'token': token, 'scopes': SCOPES}).encode())
    return 0


def policy(directory, origin, credential):
    source_origin(origin)
    if not os.path.isabs(credential):
        raise ValueError('Credential path must be absolute')
    body = json.dumps({'version': 1, 'origin': origin, 'credentialFile': credential}).encode()
    path = Path(directory) / 'nagi-t3.json'
    try:
        if private_file(path) and path.read_bytes() == body:
            return 0
    except FileNotFoundError:
        pass
    write_private(path, body)
    return 0


def t3_ok(origin):
    source_origin(origin)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(origin + '/.well-known/t3/environment',
                                     headers={'Accept': 'application/json', 'x-t3-orchestration-protocol': '2'})
    try:
        with opener.open(request, timeout=4) as response:
            if response.geturl() != request.full_url:
                return 1
            value = json.loads(response.read(65537)[:65536])
    except (OSError, ValueError):
        return 1
    return 0 if isinstance(value, dict) and value.get('orchestrationProtocolVersion') == 2 else 1


def app_agent(plist, app):
    executable = str(Path(app) / 'Contents/MacOS/Nagi')
    value = {'Label': 'local.nagi.app', 'ProgramArguments': [executable], 'RunAtLoad': True,
             'KeepAlive': {'SuccessfulExit': False}, 'LimitLoadToSessionType': 'Aqua',
             'ProcessType': 'Interactive', 'ThrottleInterval': 10}
    Path(plist).parent.mkdir(parents=True, exist_ok=True)
    body = plistlib.dumps(value)
    fd = os.open(plist, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(body)
    return 0


def main(argv):
    try:
        command, args = argv[0], argv[1:]
        if command == 'credential-from-stdin' and len(args) == 1:
            return credential_from_stdin(args[0])
        if command == 'credential-ok' and len(args) == 1:
            return 0 if credential_ok(args[0]) else 1
        if command == 'policy' and len(args) == 3:
            return policy(*args)
        if command == 'origin-kind' and len(args) == 1:
            print(source_origin(args[0])[0])
            return 0
        if command == 't3-ok' and len(args) == 1:
            return t3_ok(args[0])
        if command == 'app-agent' and len(args) == 2:
            return app_agent(*args)
    except (IndexError, OSError, ValueError):
        return 1
    print(__doc__, file=sys.stderr)
    return 64


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
