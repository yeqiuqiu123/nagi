"""Bounded native preferences and private, app-only WebKit storage paths.

No state is touched on import. Production paths are fixed, never CLI/feed input.
"""
import json
import os
from pathlib import Path
import stat
import tempfile
from dataclasses import dataclass

PRESETS = ('compact', 'medium', 'large')
MIN_WIDTH = 480
MAX_WIDTH = 16384
MAX_SETTINGS_BYTES = 1024


@dataclass(frozen=True)
class PanelPreference:
    preset: str = 'medium'
    width: int = 960

    def __post_init__(self):
        if self.preset not in (*PRESETS, 'custom') or type(self.width) is not int or not MIN_WIDTH <= self.width <= MAX_WIDTH:
            raise ValueError('Invalid panel size preference')


def app_data_path():
    return Path.home() / '.local' / 'share' / 'progress-desk'


def _directory(path, private=False):
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or info.st_mode & (0o077 if private else 0o022)):
        raise OSError('Unsafe app storage directory; permissions were not changed')
    return path


def private_app_directory():
    root = app_data_path()
    # Check each fixed component, refusing symlinks and writable shared parents.
    _directory(root.parent.parent)
    _directory(root.parent)
    return _directory(root, private=True)


def load_preference():
    try:
        root = private_app_directory()
        fd = os.open(root / 'panel-settings.json', os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_nlink != 1 or info.st_mode & 0o077 or info.st_size > MAX_SETTINGS_BYTES):
                return PanelPreference()
            raw = stream.read(MAX_SETTINGS_BYTES + 1)
        if len(raw) > MAX_SETTINGS_BYTES:
            return PanelPreference()
        data = json.loads(raw)
        if type(data) is not dict or set(data) != {'version', 'preset', 'width'} or type(data['version']) is not int or data['version'] != 1:
            return PanelPreference()
        return PanelPreference(data['preset'], data['width'])
    except (OSError, ValueError, TypeError, KeyError):
        return PanelPreference()


def save_preference(preference):
    """Atomic same-directory replacement; a failed write never truncates settings."""
    temporary = None
    try:
        preference = PanelPreference(preference.preset, preference.width)
        root = private_app_directory()
        payload = json.dumps({'version': 1, 'preset': preference.preset, 'width': preference.width}) + '\n'
        fd, temporary = tempfile.mkstemp(prefix='.panel-settings-', dir=root)
        with os.fdopen(fd, 'w', encoding='utf8') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, root / 'panel-settings.json')
        temporary = None
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return True
    except (OSError, ValueError, TypeError):
        return False
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass  # Do not turn a failed save into a GUI exception.


def scoped_web_context(WebKit2):
    """Never fall back to a shared/default profile or persistent credentials.

    The fixed origin may persist local UI drafts/history. Cookies, credentials,
    navigation, downloads and permissions remain separately denied by the shell.
    """
    manager_type = getattr(WebKit2, 'WebsiteDataManager', None)
    if (manager_type is None or not hasattr(manager_type, 'set_persistent_credential_storage_enabled')
            or not hasattr(WebKit2.WebContext, 'new_with_website_data_manager')):
        raise RuntimeError('Private UI persistence unavailable')
    root = private_app_directory()
    storage = _directory(root / 'native-ui', private=True)
    data = _directory(storage / 'data', private=True)
    cache = _directory(storage / 'cache', private=True)
    # WebKit's child processes also inherit private creation permissions.
    os.umask(0o077)
    manager = manager_type(base_data_directory=str(data), base_cache_directory=str(cache))
    manager.set_persistent_credential_storage_enabled(False)
    if manager.get_persistent_credential_storage_enabled():
        raise RuntimeError('Credential persistence could not be disabled')
    context = WebKit2.WebContext.new_with_website_data_manager(manager)
    if context is None:
        raise RuntimeError('Private UI persistence unavailable')
    context.get_cookie_manager().set_accept_policy(WebKit2.CookieAcceptPolicy.NEVER)
    return context
