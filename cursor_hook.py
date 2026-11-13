"""Passive Cursor hook sink. Standalone stdlib; no stdout, decisions or prompts."""
import fcntl
import json
import os
import re
import select
import signal
import stat
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

EVENTS=('sessionStart','sessionEnd','beforeSubmitPrompt','postToolUse','postToolUseFailure',
        'afterShellExecution','afterMCPExecution','afterFileEdit','afterAgentResponse',
        'afterAgentThought','stop','subagentStop')
MAX_BYTES=1024*1024
MAX_INPUT=1024*1024  # a long prompt rides in UserPromptSubmit's input; only metadata is kept


def clean(value,limit=120):
    if not isinstance(value,str):return None
    return ''.join(c for c in value if c.isprintable() and c not in '\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069')[:limit] or None


def capture(value,env):
    # No verified T3 discriminator exists. Do not infer one from paths or IDs.
    event=value.get('hook_event_name')
    if event not in EVENTS and event!='subagentStart':return None
    def identity(key,required=False):
        v=value.get(key)
        if v is None and not required:return None
        if not isinstance(v,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',v):raise ValueError()
        return v
    roots=value.get('workspace_roots')
    root=roots[0] if isinstance(roots,list) and roots and isinstance(roots[0],str) else None
    return {'conversation_id':identity('conversation_id',True),
            'generation_id':identity('generation_id'),
            'subagent_id':identity('subagent_id'),
            'parent_conversation_id':identity('parent_conversation_id') if event=='subagentStart' else None,
            'event':event,'timestamp':datetime.now(timezone.utc).isoformat(),
            'project':clean(Path(root).name) if root else None,
            'cursor_version':clean(value.get('cursor_version'),40)}


def append(directory,source,event):
    directory=Path(directory);info=directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:return
    lock=os.open(directory/('.cursor-'+source+'.lock'),os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK,0o600)
    try:
        info=os.fstat(lock)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:return
        # Parallel tool and subagent hooks arrive together: wait briefly (bounded), drop on contention.
        for attempt in range(20):
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);break
            except BlockingIOError:
                if attempt==19:return
                time.sleep(.005)
        path=directory/('cursor-'+source+'.jsonl')
        line=(json.dumps(event,separators=(',',':'))+'\n').encode()
        try:
            info=path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:return
            # Rotate before the file would pass the cap, so neither file ever exceeds what the reader reads.
            if info.st_size+len(line)>MAX_BYTES:
                try:
                    previous=Path(str(path)+'.1').lstat()
                    if not stat.S_ISREG(previous.st_mode) or previous.st_uid!=os.getuid() or previous.st_mode&0o077:return
                except FileNotFoundError:pass
                os.replace(path,str(path)+'.1')
        except FileNotFoundError:pass
        fd=os.open(path,os.O_WRONLY|os.O_APPEND|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK,0o600)
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:return
            os.write(fd,line)
        finally:os.close(fd)
    finally:os.close(lock)


def main():
    signal.signal(signal.SIGALRM,lambda *_:sys.exit(0));signal.setitimer(signal.ITIMER_REAL,1)
    if len(sys.argv)!=3 or not re.fullmatch(r'[0-9a-f]{32}',sys.argv[2]):return
    raw=bytearray()
    # Read to EOF; a slow writer gets until the one-second alarm, never longer.
    while len(raw)<=MAX_INPUT and select.select([sys.stdin.buffer],[],[],.5)[0]:
        block=os.read(sys.stdin.fileno(),65536)
        if not block:break
        raw.extend(block)
    if len(raw)>MAX_INPUT:return
    value=json.loads(raw)
    if not isinstance(value,dict):return
    event=capture(value,os.environ)
    if event:append(sys.argv[1],sys.argv[2],event)


if __name__=='__main__':
    try:main()
    except BaseException:pass  # Hook failure must never affect Cursor, even on timeout.
    os._exit(0)
