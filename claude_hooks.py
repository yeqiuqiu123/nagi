"""Connect-only reversible hook edits. Never called by detection or polling."""
import fcntl
import json
import os
import shlex
import stat
import sys
import tempfile
from pathlib import Path

from claude_hook import EVENTS
from local_sources import owned_root, read_owned


def hook_command(directory,source):
    script=Path(__file__).resolve().with_name('claude_hook.py')
    return shlex.join([sys.executable,'-I','-B',str(script),str(directory),source])


def ours(hook,source):
    """A Nagi hook for this source, even if Python or Nagi moved since connect."""
    if not isinstance(hook,dict) or hook.get('type')!='command' or not isinstance(hook.get('command'),str):return False
    try:parts=shlex.split(hook['command'])
    except ValueError:return False
    return len(parts)>=3 and Path(parts[-3]).name=='claude_hook.py' and parts[-1]==source


def settings(home):
    root=owned_root(Path(home)/'.claude');path=root/'settings.json'
    try:
        raw=read_owned(path)
        value=json.loads(raw)
    except FileNotFoundError:raw=None;value={}
    if not isinstance(value,dict) or not isinstance(value.get('hooks',{}),dict):raise ValueError('Invalid hook settings')
    for groups in value.get('hooks',{}).values():
        if not isinstance(groups,list):raise ValueError('Invalid hook settings')
        for group in groups:
            if not isinstance(group,dict) or not isinstance(group.get('hooks'),list):raise ValueError('Invalid hook settings')
    return path,raw,value


def edit(home,directory,source,*,remove=False):
    path,_,_=settings(home)
    fd=os.open(path.parent/'.nagi-hooks.lock',os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK,0o600)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:raise ValueError('Unsafe hook lock')
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        path,original,value=settings(home)
        command=hook_command(directory,source)
        hooks=value.setdefault('hooks',{})
        for event in EVENTS:
            groups=hooks.get(event,[]);kept=[]
            for group in groups:
                remaining=[h for h in group['hooks'] if not ours(h,source)]
                if remaining:kept.append(dict(group,hooks=remaining))
                elif not group['hooks']:kept.append(group)
            if not remove:kept.append({'hooks':[{'type':'command','command':command,'timeout':1,'async':True}]})
            if kept:hooks[event]=kept
            else:hooks.pop(event,None)
        if not hooks:value.pop('hooks',None)
        raw=(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()
        if original is not None and json.loads(original)==value:return
        # Backups are immutable, private and unique; never overwrite an owner's backup.
        if original is not None:
            backup,backup_name=tempfile.mkstemp(prefix='settings.nagi-backup-',suffix='.json',dir=path.parent)
            with os.fdopen(backup,'wb') as stream:stream.write(original);stream.flush();os.fsync(stream.fileno())
            prune_backups(path.parent,keep=backup_name)
        temporary,name=tempfile.mkstemp(prefix='.nagi-settings-',dir=path.parent)
        try:
            # Keep the owner's file mode (usually 0644); mkstemp would leave 0600.
            mode=stat.S_IMODE(path.lstat().st_mode) if original is not None else 0o644
            os.fchmod(temporary,mode)
            with os.fdopen(temporary,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
            try:current=read_owned(path)
            except FileNotFoundError:current=None
            if current!=original:raise ValueError('Concurrent settings change')
            os.replace(name,path)
            parent=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:os.fsync(parent)
            finally:os.close(parent)
        finally:
            if os.path.exists(name):os.unlink(name)
    finally:os.close(fd)


def prune_backups(directory,*,keep,limit=3):
    """Nagi's own backups only: the newest few stay, older ones go. Never another file."""
    found=[]
    for entry in os.scandir(directory):
        if not (entry.name.startswith('settings.nagi-backup-') and entry.name.endswith('.json')):continue
        try:
            info=entry.stat(follow_symlinks=False)
            if stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid():found.append((info.st_mtime_ns,entry.path))
        except OSError:continue
    found.sort(reverse=True)
    for _,victim in found[limit:]:
        if victim!=keep:
            try:os.unlink(victim)
            except OSError:pass
