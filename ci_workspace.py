"""Resolve local Git workspaces without exporting filesystem or remote metadata."""
import os
import re
import selectors
import shutil
import subprocess
import time

PREFERENCE = 'nagi-github-ci.json'
REPO = re.compile(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}', re.ASCII)
BRANCH = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_./-]{0,254}', re.ASCII)
REMOTE_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}', re.ASCII)
GITHUB_PREFIX = r'^(https://github[.]com/|ssh://git@github[.]com/|git@github[.]com:)'
# The value filter runs in git; URLs containing credentials never reach stdout.
REMOTE_FILTER = GITHUB_PREFIX + r'[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,104}/?$'


def repo_name(value):
    return (isinstance(value, str) and REPO.fullmatch(value) is not None
            and value.split('/')[1] not in ('.', '..'))


def branch_name(value):
    return (isinstance(value, str) and BRANCH.fullmatch(value) is not None
            and '..' not in value and not value.endswith('.')
            and all(part and not part.startswith('.') and not part.endswith('.lock')
                    for part in value.split('/')))


def env_path():
    paths = os.environ.get('PATH', os.defpath).split(os.pathsep)
    return os.pathsep.join(path for path in paths if os.path.isabs(path))


def run_bounded(argv, *, env, cwd, timeout, output_limit, stderr_limit=0):
    """Read only bounded pipes and reap the subprocess on every exit path."""
    deadline = time.monotonic() + timeout
    with subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE if stderr_limit else subprocess.DEVNULL) as proc:
        buffers = [bytearray(), bytearray()]
        try:
            with selectors.DefaultSelector() as poll:
                for index, (stream, limit) in enumerate(((proc.stdout, output_limit), (proc.stderr, stderr_limit))):
                    if stream is not None:
                        poll.register(stream, selectors.EVENT_READ, (index, limit))
                while poll.get_map():
                    ready = poll.select(max(0, deadline - time.monotonic()))
                    if not ready or time.monotonic() >= deadline:
                        raise TimeoutError()
                    for key, _ in ready:
                        index, limit = key.data
                        block = os.read(key.fd, min(32768, limit + 1 - len(buffers[index])))
                        if not block:
                            poll.unregister(key.fileobj)
                            continue
                        buffers[index].extend(block)
                        if len(buffers[index]) > limit:
                            raise ValueError('Subprocess output limit')
            code = proc.wait(timeout=max(0, deadline - time.monotonic()))
            return code, bytes(buffers[0]), bytes(buffers[1])
        finally:
            if proc.poll() is None:
                proc.kill()


def workspace_path(value):
    return (isinstance(value, str) and 1 < len(value) <= 4096
            and value.startswith('/') and value.isprintable())


class WorkspaceUnavailable(ValueError):
    pass


class _NotARepository(Exception):
    pass


def resolve_workspace(cwd, branch=None, *, timeout=.5):
    """Return a watch pair, None without a workspace, or False for an unsupported remote."""
    if cwd is None:
        return None
    if not workspace_path(cwd):
        raise WorkspaceUnavailable()
    path = env_path()
    git = shutil.which('git', path=path)
    if not git:
        raise WorkspaceUnavailable()
    env = {'PATH': path, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
           'GIT_TERMINAL_PROMPT': '0', 'LC_ALL': 'C'}
    deadline = time.monotonic() + timeout

    def read(*args):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError()
        code, output, detail = run_bounded([git, *args], env=env, cwd=cwd,
                                           timeout=remaining, output_limit=4096, stderr_limit=4096)
        if code == 0:
            return output.decode('ascii').strip()
        if code == 1:
            return None
        if code == 128 and (b'not a git repository' in detail
                            or b'--local can only be used inside a git repository' in detail):
            raise _NotARepository()
        raise WorkspaceUnavailable()

    try:
        if branch is None:
            branch = read('symbolic-ref', '--quiet', '--short', 'HEAD')
            if branch is None:
                return None
        if not branch_name(branch):
            raise WorkspaceUnavailable()
        tracked = read('config', '--local', '--get', f'branch.{branch}.remote',
                       r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,100}$')
        remote = tracked or 'origin'
        url = read('config', '--local', '--get', f'remote.{remote}.url', REMOTE_FILTER)
        if not url and tracked is None:
            names = (read('remote') or '').splitlines()
            if len(names) == 1 and names[0] != remote and REMOTE_NAME.fullmatch(names[0]):
                url = read('config', '--local', '--get', f'remote.{names[0]}.url', REMOTE_FILTER)
        if not url or not re.fullmatch(REMOTE_FILTER, url):
            return False
        repo = re.sub(GITHUB_PREFIX, '', url).rstrip('/').removesuffix('.git')
        return (repo.lower(), branch) if repo_name(repo) else None
    except _NotARepository:
        return None
    except (OSError, ValueError, subprocess.SubprocessError):
        raise WorkspaceUnavailable() from None
