"""Codex rollout observations and opted-in, reader-only sign-in usage."""
import math
import os
import re
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agents_projection import display, stamp, text
from agents_service import outcome
from local_sources import (LOCAL_COVERAGE, LOCAL_FLAGS, binding, json_lines, native_row,
                           opaque, owned_root, project_rows)

MAX_FILES=64
HEAD_BYTES=128*1024
TAIL_BYTES=256*1024
STANDALONE_ORIGINS={'codex_cli_rs','codex_vscode','Codex Desktop','Codex'}


def rollout_files(home,now):
    from codex_usage import codex_home
    root=owned_root(codex_home(home)/'sessions');found=[];truncated=False
    # Fixed dated roots bound directory work; old sessions are explicitly outside
    # this partial observation, never inferred completed from file age.
    for offset in range(8):
        date=now-timedelta(days=offset);day=root/date.strftime('%Y/%m/%d')
        try:
            owned_root(day)
            with os.scandir(day) as entries:
                names=[]
                for count,entry in enumerate(entries):
                    if count>=4096:truncated=True;break
                    if re.fullmatch(r'rollout-[A-Za-z0-9_.-]+\.jsonl',entry.name) and entry.is_file(follow_symlinks=False):names.append(entry.name)
            for name in sorted(names,reverse=True):
                if len(found)>=MAX_FILES:truncated=True;break
                found.append(day/name)
        except FileNotFoundError:continue
    return found,truncated


def read_rollout(path):
    # Header and tail come from one no-follow fd: a rename cannot splice two
    # sessions. Each poll reopens, so rotations/truncations cannot reuse offsets.
    with os.fdopen(os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK),'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid():raise ValueError('Unsafe rollout')
        header=stream.read(HEAD_BYTES)
        offset=max(0,info.st_size-TAIL_BYTES)
        stream.seek(offset);tail=stream.read(TAIL_BYTES)
        if offset:tail=tail.partition(b'\n')[2]
        after=os.fstat(stream.fileno())
        if after.st_size<info.st_size:raise ValueError('Rollout truncated during read')
    metadata=next((v['payload'] for v in json_lines(header) if v.get('type')=='session_meta' and isinstance(v.get('payload'),dict)),None)
    records=list(json_lines(tail))
    return metadata,records


def session_parent(metadata):
    source=metadata.get('source')
    if isinstance(source,dict) and isinstance(source.get('subagent'),dict):
        spawn=source['subagent'].get('thread_spawn')
        if isinstance(spawn,dict):return text(spawn['parent_thread_id'],128)
    return None


def standalone(metadata):
    if metadata.get('originator') not in STANDALONE_ORIGINS:return False
    source=metadata.get('source')
    if isinstance(source,str):return source in ('cli','vscode','exec')
    return session_parent(metadata) is not None


def rate_windows(rate,at,now):
    if not -5<=(now-stamp(at)).total_seconds()<=900:return []
    bucket=rate.get('limit_id') or 'default';text(bucket,80)
    windows=[]
    for key in ('primary','secondary'):
        value=rate.get(key)
        if value is None:continue
        if not isinstance(value,dict):raise ValueError('Invalid window')
        used=value.get('used_percent');reset=value.get('resets_at');minutes=value.get('window_minutes')
        if (type(used) not in (int,float) or not math.isfinite(used) or not 0<=used<=100
                or type(reset) not in (int,float) or not math.isfinite(reset)
                or type(minutes) not in (int,float) or not math.isfinite(minutes) or minutes<=0):raise ValueError('Invalid window')
        reset=datetime.fromtimestamp(reset,timezone.utc).isoformat()
        if stamp(reset)<=now:continue
        kind='five_hour' if minutes==300 else 'weekly' if minutes==10080 else 'monthly' if minutes>=43200 else 'other'
        label='Session' if key=='primary' else 'Weekly' if minutes==10080 else 'Secondary'
        windows.append({'id':bucket+'/'+key,'label':label,'kind':kind,'remainingPercent':round(100-used,2),
                        'resetsAt':reset,'checkedAt':at})
    return windows


def project_rollouts(files,source_id,now,settings,*,signed_in=None,workspaces=None):
    rows={};observations={};unverified=False;omitted=0
    for path in files:
        try:
            meta,records=read_rollout(path)
            if meta is None:omitted+=1;continue
            if not standalone(meta):continue
            identity=text(meta['id'],128);parent=session_parent(meta)
            model=None;row=None;cwd=meta.get('cwd')
            for record in records:
                kind=record.get('type');payload=record.get('payload')
                if not isinstance(payload,dict):continue
                at=record.get('timestamp')
                try:
                    if not -5<=(now-stamp(at)).total_seconds()<=7*86400:continue
                    if kind=='turn_context':
                        if isinstance(payload.get('cwd'),str):cwd=payload['cwd']
                        if isinstance(payload.get('model'),str):model=display(payload['model'],120)
                        continue
                    if kind!='event_msg':continue
                    event=payload.get('type')
                    if event=='token_count' and isinstance(payload.get('rate_limits'),dict):
                        rate=payload['rate_limits'];windows=rate_windows(rate,at,now)
                        if not windows:continue
                        # Creator identity never updates on resume. Fallback instead requires
                        # the whole session to start after the sign-in last changed: a session
                        # already running keeps its old token in memory after a switch.
                        account=rate.get('account_id')
                        if signed_in is not None:
                            signed_key,changed_at,current_account=signed_in
                            started=meta.get('timestamp')
                            try:started_after=isinstance(started,str) and stamp(started).timestamp()>changed_at
                            except (ValueError,TypeError):started_after=False
                            if (not started_after or stamp(at).timestamp()<=changed_at or rate.get('limit_id','codex') not in ('codex','default')
                                    or account not in (None,current_account)):
                                unverified=True;continue
                            key=signed_key
                            for window in windows:window['id']=window['id'].rsplit('/',1)[-1]
                        else:
                            if not isinstance(account,str) or not 0<len(account)<=256:
                                unverified=True;continue
                            key=opaque(source_id,account)
                        for window in windows:
                            index=(key,window['id']);old=observations.get(index)
                            if old is None or stamp(old['checkedAt'])<stamp(at):observations[index]=window
                    elif event in ('task_started','turn_started'):
                        row=native_row(identity,Path(meta.get('cwd') or '').name,meta.get('title') or 'Codex session','codex',at,parent=parent,model=model)
                        run=payload.get('turn_id')
                        if isinstance(run,str):row['runId']=text(run,128)
                    elif event in ('task_complete','turn_complete','turn_aborted'):
                        # An explicit terminal event proves completion even if
                        # its start lies outside the bounded tail. Start stays null.
                        if row is None:
                            row=native_row(identity,Path(meta.get('cwd') or '').name,meta.get('title') or 'Codex session','codex',at,parent=parent,model=model)
                            row['startedAt']=None;row['runId']=payload.get('turn_id') if isinstance(payload.get('turn_id'),str) else None
                        row.update(state='interrupted' if event=='turn_aborted' else 'completed',endedAt=at,
                                   endedAtSource='latestRunCompletedAt',lastActivityAt=at)
                    elif row and event in ('token_count','item_started','item_completed'):
                        row['lastActivityAt']=at
                except (ValueError,TypeError,OverflowError,OSError):omitted+=1;continue
            if row:
                if row['model'] is None:row['model']=model
                # Reverted/rotated duplicate rollout IDs never duplicate counts.
                old=rows.get(identity)
                if old is None or stamp(old['lastActivityAt'])<stamp(row['lastActivityAt']):
                    rows[identity]=row
                    if workspaces is not None:workspaces[identity]=(cwd,None,None)
        except (OSError,ValueError,TypeError,KeyError,RecursionError):omitted+=1
    data,rows,modes=project_rows(rows,source_id,now,settings)
    data['omittedRows']=omitted
    if omitted:data['warnings'].append('rows_omitted')
    # An unmatched stale start is omitted; never restamp a historical row as live.
    if any(r['state']=='running' and (now-stamp(r['lastActivityAt'])).total_seconds()>900 for r in rows.values()):
        data['warnings'].append('stale_source')
    accounts=[]
    for index,identity in enumerate(sorted({key[0] for key in observations}),1):
        windows=[value for key,value in observations.items() if key[0]==identity]
        accounts.append({'id':identity,'label':'Codex '+str(index),'windows':windows,'status':'ok',
                         'checkedAt':min(w['checkedAt'] for w in windows),'reason':None})
    at=now.isoformat()
    if accounts:
        limits=outcome('ok',at,min(a['checkedAt'] for a in accounts),data={'accounts':accounts})
    else:limits=outcome('unavailable',at,reason='account_unverified' if unverified else 'windows_missing')
    limits['warnings']=['account_unverified'] if unverified else []
    return data,rows,modes,limits


class CodexAdapter:
    identity=None
    potential_capabilities=dict(LOCAL_FLAGS)
    coverage=dict(LOCAL_COVERAGE)

    def configure(self,value):
        if isinstance(value,dict) and value.get('version')==2:
            if (set(value)!={'version','home','usageOptIn'} or type(value['version']) is not int
                    or value['usageOptIn'] is not True):
                raise ValueError('Invalid Codex binding')
            binding({'version':1,'home':value['home']})
            return dict(value)
        return binding(value)

    def configuration_schema(self):
        return {'version':1,'harness':'codex','available':True,'modes':['rollouts'],
                'capabilities':dict(self.potential_capabilities),'requirements':['passive_rollouts','codex_usage_opt_in']}

    def read(self,service,now,settings,caches,force=False):
        at=now.isoformat();rows=modes=None;files=[];workspaces={}
        try:
            files,truncated=rollout_files(service.policy['home'],now)
            data,rows,modes,limits=project_rollouts(files,service.source_id,now,settings,workspaces=workspaces)
            if truncated:data['warnings'].append('coverage_incomplete')
            agents=outcome('ok',at,at,data=data)
        except Exception:
            agents=outcome('unavailable',at,reason='local_data_missing')
            limits={**outcome('unavailable',at,reason='local_data_missing'),'warnings':[]}
        from codex_usage import read_limits
        def fallback(identity,changed_at,account):
            return project_rollouts(files,service.source_id,now,settings,
                                    signed_in=(identity,changed_at,account))[3]
        limits=read_limits(service,now,fallback)
        limits.setdefault('warnings',[])
        return {'agents':agents,'limits':{'codex':limits,'claude':{**outcome('unsupported',at,reason='account_unsupported'),'warnings':[]}},
                'rows':rows,'modes':modes,'icon_sources':{},'success':True,'workspaces':workspaces}
