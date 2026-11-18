#!/usr/bin/env python3
"""Prepare (never activate) a per-user reader service. No writes outside HOME."""
import json
import shlex
from runtime_paths import data_directory, locator_path
import argparse
import os
from pathlib import Path
import plistlib
import sys

ROOT = Path(__file__).resolve().parent


def owned_path(path, home):
    path = Path(os.path.abspath(path))
    if home not in path.parents:
        raise ValueError('Installation paths must be inside your home directory')
    current = home
    for part in path.relative_to(home).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('Installation paths must not contain symlinks')
        if current.exists():
            info = current.stat()
            if info.st_uid != os.getuid() or info.st_mode & 0o022:
                raise ValueError('Installation paths must be owner-controlled')
    return path


def ensure_directory(path, home):
    path = owned_path(path, home)
    current = home
    for part in path.relative_to(home).parts:
        current = current / part
        current.mkdir(mode=0o700, exist_ok=True)
    owned_path(path, home)


def write_private(path, body, home):
    path = owned_path(path, home)
    ensure_directory(path.parent, home)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(body)


def install(platform, directory, port, executable, home):
    if platform not in ('linux', 'darwin') or not 1024 <= port <= 65535:
        raise ValueError('Expected Linux or macOS and a nonprivileged port')
    directory = owned_path(directory, home)
    # A selected Python is an explicit executable, never a shell expression.
    executable = str(Path(executable).resolve(strict=True))
    import subprocess
    subprocess.run([executable, '-c', 'import sys; sys.exit(sys.version_info < (3, 11))'], check=True, timeout=5)
    from owner_auth import owner_secret
    ensure_directory(directory, home)
    owner_secret(directory, create=True)
    search = [str(Path(executable).parent), *os.environ.get('PATH', '').split(os.pathsep),
              str(home / '.local/bin'), str(home / '.bun/bin'), str(home / '.local/share/pnpm'),
              '/opt/homebrew/bin', '/usr/local/bin', '/usr/bin', '/bin', '/usr/sbin', '/sbin']
    cli_path = os.pathsep.join(dict.fromkeys(item for item in search if Path(item).is_absolute()))
    command = [executable, '-B', str(ROOT / 'server.py'), '--port', str(port), '--data-dir', str(directory)]
    if platform == 'darwin':
        target = home / 'Library/LaunchAgents/local.nagi.reader.plist'
        value = {'Label': 'local.nagi.reader', 'ProgramArguments': command,
                 'WorkingDirectory': str(ROOT), 'RunAtLoad': True,
                 'KeepAlive': {'SuccessfulExit': False}, 'ThrottleInterval': 5,
                 'Umask': 0o077,
                 'EnvironmentVariables': {'NAGI_DATA_DIR': str(directory),
                     'PATH': cli_path}}
        body = plistlib.dumps(value)
    else:
        target = home / '.config/systemd/user/nagi-reader.service'
        def quote(value):
            return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%').replace('\n', '\\n') + '"'
        template = (ROOT / 'linux/nagi-reader.service.in').read_text()
        body = template.replace('@COMMAND@', ' '.join(map(quote, command))).replace('@DATA_ENV@', quote('NAGI_DATA_DIR=' + str(directory))).replace('@PATH_ENV@', quote('PATH=' + cli_path)).encode()
    write_private(target, body, home)
    if platform == 'linux':
        # The tray, kept running for the desktop session: started at login, restarted after a crash.
        tray_command = [executable, '-B', str(ROOT / 'linux/tray.py'), '--port', str(port)]
        tray = (ROOT / 'linux/nagi-tray.service.in').read_text().replace('@COMMAND@', ' '.join(map(quote, tray_command)))
        write_private(home / '.config/systemd/user/nagi-tray.service', tray.encode(), home)
    if platform=='linux':
        # Stable notification identity: GNOME rejects unknown per-process app IDs.
        def desktop_quote(value):
            return '"'+value.replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$').replace('%','%%')+'"'
        desktop_command=[executable,'-B',str(ROOT/'linux/tray.py'),'--port',str(port)]
        desktop=(ROOT/'linux/local.nagi.notifications.desktop.in').read_text().replace('@COMMAND@',' '.join(map(desktop_quote,desktop_command)))
        write_private(home/'.local/share/applications/local.nagi.notifications.desktop',desktop.encode(),home)
        activation_command=[executable,'-B',str(ROOT/'linux/agent_notifications.py'),'--activate','--port',str(port)]
        activation=(ROOT/'linux/local.nagi.notifications.service.in').read_text().replace('@COMMAND@',shlex.join(activation_command))
        write_private(home/'.local/share/dbus-1/services/local.nagi.notifications.service',activation.encode(),home)
    write_private(locator_path(home=home), json.dumps({'version': 1, 'dataDir': str(directory)}).encode(), home)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--port', type=int, default=47831)
    parser.add_argument('--python', default=sys.executable)
    args = parser.parse_args()
    home = Path.home().resolve()
    try:
        directory = data_directory(args.data_dir, home=home)
        target = install(sys.platform, directory, args.port, args.python, home)
    except (OSError, ValueError, RuntimeError, __import__('subprocess').SubprocessError):
        parser.exit(1, 'Reader installation rejected. Check Python 3.11+, owner paths and file permissions.\n')
    print(f'Prepared {target}. Service activation requires owner approval.')


if __name__ == '__main__':
    main()
