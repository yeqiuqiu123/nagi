"""Bounded, metadata-only helpers for direct sources. Never starts a harness."""
import hashlib
import json
import os
import stat
from pathlib import Path

from agents_projection import display, stamp
from jsonio import strict_json_loads

NULL_LINKS={'desktop':None,'web':None}
LOCAL_COVERAGE={'agents':'partial','lineage':'partial','limits':'account_dependent',
                'asksYou':'unsupported','stuck':'unsupported','deepLinks':'unsupported'}
LOCAL_FLAGS={'agents':True,'lineage':True,'limits':True,'stuckDetection':False,'asksYou':False,'deepLinks':False}


def opaque(*values):
    return hashlib.sha256(json.dumps(values,separators=(',',':')).encode()).hexdigest()


def owned_root(path):
    path=Path(path)
    # Refuse redirected profiles, including an intermediate symlink.
    for part in (path,*path.parents):
        info=part.lstat()
        if stat.S_ISLNK(info.st_mode):raise ValueError('Unsafe source root')
    info=path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid():raise ValueError('Unsafe source root')
    return path


def read_owned(path,limit=1024*1024,*,private=False,tail=False):
    with os.fdopen(os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK),'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or (private and info.st_mode&0o077):
            raise ValueError('Unsafe source file')
        offset=max(0,info.st_size-limit) if tail else 0
        if offset:stream.seek(offset)
        raw=stream.read(limit+1)
        if len(raw)>limit:raise ValueError('Source too large')
        if offset:raw=raw.partition(b'\n')[2]
        return raw


def json_file(path,limit=1024*1024,*,private=False):
    return strict_json_loads(read_owned(path,limit,private=private),limit,max_depth=32)


def json_lines(raw):
    # Ignore a torn last line; never buffer an unbounded record across polls.
    for line in raw.splitlines(keepends=True):
        if not line.endswith(b'\n') or len(line)>128*1024:continue
        try:
            value=strict_json_loads(line,128*1024,max_depth=32)
            if isinstance(value,dict):yield value
        except (ValueError,RecursionError):continue


def binding(value):
    if (not isinstance(value,dict) or set(value)!={'version','home'} or type(value['version']) is not int
            or value['version']!=1 or not isinstance(value['home'],str) or not Path(value['home']).is_absolute()
            or str(Path(value['home']))!=value['home']):raise ValueError('Invalid local binding')
    return dict(value)


def project_rows(rows,source_id,now,settings):
    """Group normalized native rows; no T3 links, state inference or stuck claims."""
    rows={key:dict(row,children=[]) for key,row in rows.items()}
    for row in rows.values():
        parent=rows.get(row['parentId'])
        if not parent or parent['projectId']!=row['projectId']:row['parentId']=None
        seen={row['id']};ancestor=row['parentId']
        while ancestor:
            if ancestor in seen or len(seen)>32:raise ValueError('Invalid lineage')
            seen.add(ancestor);ancestor=rows[ancestor]['parentId']
    # Silence ends a row after 15 minutes, except one that is asking the owner something:
    # that stays up to a day, because the wait is the owner's, not the agent's.
    def quiet_limit(row):
        return 86400 if row['waitingOnYou'].get('approval') or row['waitingOnYou'].get('question') else 900
    modes={key:('active' if row['state']=='running' and (now-stamp(row['lastActivityAt'])).total_seconds()<=quiet_limit(row)
                else 'ended' if row['endedAt'] and 0<=(now-stamp(row['endedAt'])).total_seconds()<=settings['endedExpiryHours']*3600
                else None) for key,row in rows.items()}
    def groups(mode):
        included={key for key in rows if modes[key]==mode};selected=set(included)
        for key in selected:
            parent=rows[key]['parentId']
            while parent:included.add(parent);parent=rows[parent]['parentId']
        copies={key:dict(rows[key],children=[],contextOnly=key not in selected) for key in included}
        result={}
        for key,row in copies.items():
            if row['parentId'] in copies:copies[row['parentId']]['children'].append(row)
            else:result.setdefault(row['projectId'],[]).append(row)
        def sort(items):
            items.sort(key=lambda r:(r['title'],r['id']))
            for item in items:sort(item['children'])
        for items in result.values():sort(items)
        return [{'id':key,'title':key,'agents':items} for key,items in sorted(result.items())]
    data={'environmentId':opaque(source_id),'projects':groups('active'),'ended':groups('ended'),
          'counts':{'running':sum(v=='active' for v in modes.values()),
                    'waitingOnYou':sum(modes[k]=='active' and any(r['waitingOnYou'][v] for v in ('question','approval')) for k,r in rows.items()),
                    'stuck':0,'ended':sum(v=='ended' for v in modes.values())},
          'omittedRows':0,'warnings':['partial_coverage']}
    return data,rows,modes


def native_row(identity,project,title,provider,at,*,parent=None,model=None):
    return {'id':identity,'projectId':display(project,120,'Sessions'),'parentId':parent,'title':display(title),
            'state':'running','provider':provider,'model':display(model,120) if model else None,
            'runId':at,'startedAt':at,'lastActivityAt':at,'endedAt':None,'endedAtSource':None,
            'waitingOnYou':{'question':False,'approval':False,'blocking':False},'stuck':None,
            'liveness':'unknown','contextOnly':False,'links':dict(NULL_LINKS),'children':[]}
