"""One owner-local runtime selection for the reader, installers and all clients."""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

ROOT = Path(__file__).resolve().parent


def locator_path(*, home=None, checkout=None):
    home = Path(home) if home is not None else Path.home()
    checkout = Path(checkout) if checkout is not None else ROOT
    key = hashlib.sha256(str(checkout.resolve()).encode()).hexdigest()[:24]
    return home / '.config/nagi/runtime-paths' / key / 'nagi-runtime.json'


def data_directory(explicit=None, *, home=None, platform=None):
    home = Path(home) if home is not None else Path.home()
    if explicit is not None:
        selected = explicit
    elif os.environ.get('NAGI_DATA_DIR'):
        selected = os.environ['NAGI_DATA_DIR']
    else:
        path = locator_path(home=home)
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            selected = home / ('Library/Application Support/Nagi/data' if (platform or sys.platform) == 'darwin' else '.local/share/nagi/data')
        else:
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
                    raise ValueError('Expected an owner-only runtime locator')
                raw = stream.read(4097)
            if len(raw) > 4096:
                raise ValueError('Invalid runtime locator')
            value = json.loads(raw)
            if not isinstance(value, dict) or set(value) != {'version', 'dataDir'} or type(value['version']) is not int or value['version'] != 1:
                raise ValueError('Invalid runtime locator')
            selected = value['dataDir']
    if not isinstance(selected, (str, Path)) or not Path(selected).is_absolute():
        raise ValueError('Expected an absolute runtime directory')
    return Path(selected)


if __name__ == '__main__':
    print(data_directory())
