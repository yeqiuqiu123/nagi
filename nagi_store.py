"""Owner-only atomic local preferences, sanitized cache and notification journal."""
import fcntl
import copy
import json
import os
from pathlib import Path
import stat
from tempfile import NamedTemporaryFile
from threading import RLock
from jsonio import strict_json_loads


class LocalStore:
    def __init__(self, directory):
        self.directory=Path(directory); self.lock=RLock()
        self.directory.mkdir(mode=0o700,parents=True,exist_ok=True)

    def read(self,name,default):
        try:
            with os.fdopen(os.open(self.directory/name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK),'rb') as stream:
                info=os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:raise ValueError('Invalid local state')
                return strict_json_loads(stream.read(16*1024*1024+1),16*1024*1024,max_depth=160)
        except FileNotFoundError:return default

    def unlink_owned(self,name,*,expected=None):
        """Atomic no-follow removal inside this private directory, never a target."""
        if not isinstance(name,str) or Path(name).name!=name:raise ValueError('Invalid state name')
        fd=os.open(self.directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            parent=os.fstat(fd)
            if parent.st_uid!=os.getuid() or parent.st_mode&0o077:raise ValueError('Unsafe state directory')
            try:info=os.stat(name,dir_fd=fd,follow_symlinks=False)
            except FileNotFoundError:return False
            if info.st_uid!=os.getuid() or not (stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)):
                raise ValueError('Unsafe state file')
            if expected is not None and (info.st_dev,info.st_ino)!=(expected.st_dev,expected.st_ino):return False
            os.unlink(name,dir_fd=fd)
            os.fsync(fd)
            return True
        finally:os.close(fd)

    def remove(self,name):
        with self.lock:
            fd=os.open(self.directory/'.nagi-v2.lock',os.O_RDONLY|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK,0o600)
            try:
                info=os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:
                    raise ValueError('Invalid state lock')
                fcntl.flock(fd,fcntl.LOCK_EX)
                return self.unlink_owned(name)
            finally:os.close(fd)

    def mutate(self,name,default,build,*,repair=False,validate=None):
        with self.lock:
            with os.fdopen(os.open(self.directory/'.nagi-v2.lock',os.O_RDONLY|os.O_CREAT|os.O_NOFOLLOW,0o600),'rb') as lock:
                info=os.fstat(lock.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:raise ValueError('Invalid state lock')
                fcntl.flock(lock,fcntl.LOCK_EX)
                try:
                    data=self.read(name,copy.deepcopy(default))
                    if validate is not None:validate(data)
                except (OSError,ValueError,TypeError,RecursionError):
                    if not repair:raise
                    # Repair only this owner's regular file, never a link or foreign inode.
                    try:
                        info=(self.directory/name).lstat()
                        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid():raise OSError('Unsafe state file')
                    except FileNotFoundError:pass
                    data=copy.deepcopy(default)
                result=build(data)
                raw=json.dumps(data,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()
                if len(raw)>16*1024*1024:raise ValueError('Local state too large')
                with NamedTemporaryFile(dir=self.directory,prefix='.nagi-v2-',delete=False) as stream:
                    temporary=Path(stream.name)
                    try:
                        os.fchmod(stream.fileno(),0o600);stream.write(raw);stream.flush();os.fsync(stream.fileno())
                        os.replace(temporary,self.directory/name)
                        directory_fd=os.open(self.directory,os.O_RDONLY|os.O_DIRECTORY)
                        try:os.fsync(directory_fd)
                        finally:os.close(directory_fd)
                    finally:temporary.unlink(missing_ok=True)
                return result
