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


def write_private(path, body, home, *, mode=0o600):
    path = owned_path(path, home)
    ensure_directory(path.parent, home)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        os.fchmod(stream.fileno(), mode)
        stream.write(body)


LOGIN_ENTRY = '.config/autostart/local.nagi.tray.desktop'


def desktop_quote(value):
    """One Exec argument, in both layers of the Desktop Entry spec: the Exec quoting
    (backslash before backslash, double quote, backtick and dollar, inside double quotes;
    %% for %), then the key-file string escape (each backslash doubled)."""
    exec_arg = '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$') + '"'
    return exec_arg.replace('\\', '\\\\').replace('%', '%%')


def login_entry_disabled(text):
    """The owner switched Nagi's login entry off in [Desktop Entry]: keep that choice."""
    group = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('[') and line.endswith(']'):
            group = line
        elif group == '[Desktop Entry]' and '=' in line:
            key, value = (part.strip() for part in line.split('=', 1))
            if (key == 'Hidden' and value == 'true') or (key == 'X-GNOME-Autostart-enabled' and value == 'false'):
                return True
    return False


def open_home_directory(home, relative):
    """A descriptor for home/relative, walking one component at a time and never through a
    symlink, so a symlinked ~/.config or ~/.config/autostart can't send a write elsewhere.
    Desktops often make these folders group-writable, so only ownership is checked."""
    fd = os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in Path(relative).parts:
            try:
                os.mkdir(part, 0o700, dir_fd=fd)
            except FileExistsError:
                pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            if os.fstat(fd).st_uid != os.getuid():
                raise ValueError('Installation paths must be yours')
        return fd
    except BaseException:
        os.close(fd)
        raise


def write_login_entry(home, executable, port):
    """Nagi's login entry runs `tray.py --login`: a small supervisor, living as long as the
    desktop session, that restarts the tray after a crash. An entry that isn't Nagi's, or
    that was switched off in [Desktop Entry], is left as it is."""
    folder, name = os.path.split(LOGIN_ENTRY)
    command = [executable, '-B', str(ROOT / 'linux/tray.py'), '--port', str(port), '--login']
    body = ('[Desktop Entry]\nType=Application\nName=Nagi\nComment=What your agents are doing, at a glance\n'
            'Exec=' + ' '.join(map(desktop_quote, command)) + '\nTerminal=false\nNoDisplay=true\nX-GNOME-Autostart-enabled=true\n')
    parent = open_home_directory(home, folder)
    try:
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        except FileNotFoundError:
            pass
        else:
            with os.fdopen(fd, 'rb') as stream:
                text = stream.read(65536).decode(errors='replace')
            if 'linux/tray.py' not in text or login_entry_disabled(text):
                return None
        # Replace atomically beside it, never following a link.
        temp = '.' + name + '.tmp'
        try:
            os.unlink(temp, dir_fd=parent)
        except FileNotFoundError:
            pass
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(body.encode())
        os.replace(temp, name, src_dir_fd=parent, dst_dir_fd=parent)
        return home / LOGIN_ENTRY
    finally:
        os.close(parent)


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
        def arg_quote(value):
            # systemd expands ${VAR} in arguments even inside quotes ($$ is a literal $); the
            # executable is looked up literally, so it keeps its $.
            return quote(value).replace('$', '$$')
        template = (ROOT / 'linux/nagi-reader.service.in').read_text()
        body = template.replace('@COMMAND@', ' '.join([quote(command[0]), *map(arg_quote, command[1:])])).replace('@DATA_ENV@', quote('NAGI_DATA_DIR=' + str(directory))).replace('@PATH_ENV@', quote('PATH=' + cli_path)).encode()
    write_private(target, body, home)
    if platform == 'linux':
        write_login_entry(home, executable, port)
    if platform=='linux':
        # Stable notification identity: GNOME rejects unknown per-process app IDs.
        desktop_command=[executable,'-B',str(ROOT/'linux/tray.py'),'--port',str(port)]
        desktop=(ROOT/'linux/local.nagi.notifications.desktop.in').read_text().replace('@COMMAND@',' '.join(map(desktop_quote,desktop_command)))
        write_private(home/'.local/share/applications/local.nagi.notifications.desktop',desktop.encode(),home)
        activation_command=[executable,'-B',str(ROOT/'linux/agent_notifications.py'),'--activate','--port',str(port)]
        activation=(ROOT/'linux/local.nagi.notifications.service.in').read_text().replace('@COMMAND@',shlex.join(activation_command))
        write_private(home/'.local/share/dbus-1/services/local.nagi.notifications.service',activation.encode(),home)
    write_status_launcher(home, executable, port)
    write_private(locator_path(home=home), json.dumps({'version': 1, 'dataDir': str(directory)}).encode(), home)
    return target


STATUS_MARKER = b'#!/bin/sh\n# Installed by Nagi\n'


def write_status_launcher(home, executable, port):
    path = owned_path(home/'.local/bin/nagi', home)
    try:
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as existing:
            from stat import S_ISREG
            if not S_ISREG(os.fstat(existing.fileno()).st_mode) or existing.read(len(STATUS_MARKER)) != STATUS_MARKER:
                raise ValueError('The nagi command is already in use')
    except FileNotFoundError:
        pass
    command = shlex.join([executable, '-E', '-B', str(ROOT/'nagi_cli.py')])
    template = (f'NAGI_PORT=${{NAGI_PORT:-{port}}}\nexport NAGI_PORT\n'
                f'exec {command} "$@"\n')
    write_private(path, STATUS_MARKER + template.encode(), home, mode=0o700)


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
