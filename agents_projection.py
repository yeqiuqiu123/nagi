"""Closed metadata-only T3 projection. No prompts, transcripts or tool bodies."""
from datetime import datetime, timezone
from urllib.parse import quote

ACTIVE={'queued','preparing','starting','running','waiting'}
ENDED={'completed','failed','interrupted'}
# T3 shared/orchestrationV2PendingBackgroundWork.ts EXECUTION_TURN_ITEM_TYPES.
TOOLS={'command_execution','dynamic_tool','subagent','file_change','file_search','web_search','compaction'}
BIDI=set('\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069')


def stamp(value):
    if not isinstance(value,str) or len(value)>40:raise ValueError('Invalid source timestamp')
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.tzinfo is None:raise ValueError('Missing source timezone')
    return result


def text(value,limit=512):
    if not isinstance(value,str) or not value or len(value)>limit or any(ord(c)<32 for c in value):raise ValueError('Invalid source metadata')
    return value


def display(value,limit=180,fallback='Untitled thread'):
    if not isinstance(value,str):return fallback
    cleaned=' '.join(''.join(c for c in value if c not in BIDI and c not in '\u2028\u2029' and (ord(c)>=32 or c.isspace())).split())
    return (cleaned[:limit-1]+'…' if len(cleaned)>limit else cleaned) or fallback


def links(environment,identity):
    if environment in ('.','..') or identity in ('.','..'):raise ValueError('Invalid link segment')
    path=quote(text(environment),safe='')+'/'+quote(text(identity),safe='')
    return {'desktop':'t3code://threads/'+path,'web':'https://app.t3.codes/threads/'+path}


def current_run_covered(detail,run,started_at=None):
    if (not isinstance(detail,dict) or detail.get('turnItemsOmitLocalVisible') or detail.get('idTable')):return False
    projection=detail.get('projection')
    if not isinstance(projection,dict) or not isinstance(projection.get('turnItems'),list):return False
    if not run:return False
    if detail.get('hasMoreHistory') is False:return True
    items=projection['turnItems']
    runs=projection.get('runs',[])
    if not isinstance(runs,list):return False
    metadata=next((r for r in runs if isinstance(r,dict) and r.get('id')==run),{})
    first_message=metadata.get('userMessageId')
    for item in items:
        if not isinstance(item,dict) or item.get('runId')!=run:continue
        if first_message and (item.get('id')==first_message or item.get('messageId')==first_message):return True
        # A current-run input at/before the start is evidence of its first item;
        # merely retaining the run metadata is not evidence of item coverage.
        if item.get('type')=='user_message':
            at=item.get('createdAt') or item.get('startedAt')
            start=metadata.get('requestedAt') or metadata.get('startedAt') or started_at
            try:
                if at and start and stamp(at)<=stamp(start):return True
            except ValueError:pass
    visible=projection.get('visibleTurnItems',[])
    if isinstance(visible,list) and visible and started_at and isinstance(projection.get('thread'),dict):
        local=[r for r in visible if isinstance(r,dict) and isinstance(r.get('item'),dict)
               and type(r.get('position')) is int and not r['item'].get('deferredWork') and r.get('sourceThreadId')==projection.get('thread',{}).get('id')]
        if local:
            first=min(local,key=lambda r:r.get('position',float('inf')))['item']
            at=first.get('createdAt') or first.get('startedAt')
            try:
                if at and stamp(at)<=stamp(started_at):return True
            except ValueError:pass
    return False


class CyclicLineage(ValueError):
    """A snapshot whose parent links loop; the whole observation is rejected."""


def tool_liveness(detail,run,started_at=None):
    if not current_run_covered(detail,run,started_at):return 'unknown'
    runs=detail['projection'].get('runs',[])
    if not isinstance(runs,list):return 'unknown'
    metadata=next((r for r in runs if isinstance(r,dict) and r.get('id')==run),{})
    if metadata.get('status') in ENDED|{'cancelled','rolled_back'}:return 'unknown'
    for item in detail['projection']['turnItems']:
        if not isinstance(item,dict):return 'unknown'
        if item.get('runId')!=run:continue
        if item.get('status') in ('running','waiting','pending','in_progress','started') and not item.get('completedAt'):return 'unknown'
        if item.get('deferredWork') or (item.get('streaming') and not item.get('completedAt')):return 'unknown'
    return 'inactive'


def project_agents(descriptor,snapshot,providers,settings,details,now):
    environment=text(descriptor.get('environmentId',descriptor.get('id')))
    if not isinstance(snapshot,dict) or not isinstance(snapshot.get('projects'),list) or len(snapshot['projects'])>512:raise ValueError('Incomplete project snapshot')
    threads=snapshot.get('threads')
    archived=snapshot.get('archivedThreads',[])
    if not isinstance(threads,list) or not isinstance(archived,list) or len(threads)+len(archived)>4096:raise ValueError('Incomplete thread snapshot')
    projects={};malformed=0
    for project in snapshot['projects']:
        try:key=text(project['id'])
        except (KeyError,ValueError,TypeError):malformed+=1;continue
        if key not in projects:projects[key]=display(project.get('title'),180,'Untitled project')
        else:malformed+=1
    provider_map={p['instanceId']:p.get('driver') for p in providers if isinstance(p,dict) and isinstance(p.get('instanceId'),str)}
    rows={};modes={}
    for source in threads+archived:
        try:
            if not isinstance(source,dict):raise ValueError('Invalid thread')
            identity=text(source['id'])
            if identity in rows:malformed+=1;continue
            project=text(source['projectId'])
            if project not in projects:raise ValueError('Missing project coverage')
            if source.get('deletedAt'):continue
            state=source['status']
            if state in ('cancelled','rolled_back','superseded'):state='interrupted'
            if state not in ACTIVE|ENDED|{'idle'}:raise ValueError('Unknown thread state')
            updated=source.get('updatedAt');at=stamp(updated)
            if (at-now).total_seconds()>5:raise ValueError('Future source evidence')
            def date(key):
                value=source.get(key)
                if value is not None and (stamp(value)-now).total_seconds()>5:raise ValueError('Future event')
                return value
            run=source.get('latestRunId');run=text(run) if run is not None else None
            request=source.get('pendingRuntimeRequest') or {}
            if not isinstance(request,dict):raise ValueError('Invalid pending request')
            kind=request.get('kind')
            waiting={'question':kind=='user_input','approval':kind is not None and kind!='user_input',
                     'blocking':bool(kind is not None and request.get('blocking',True))}
            liveness='recent';stuck=False
            if state=='running' and (now-at).total_seconds()>=settings['stuckMinutes']*60:
                if kind is not None:liveness='waiting_on_you'
                elif source.get('blockedOnThreadWait'):liveness='child_wait'
                else:liveness=tool_liveness(details.get(identity),run,source.get('activityRunStartedAt') or source.get('latestRunStartedAt'))
                stuck=True if liveness=='inactive' else None if liveness=='unknown' else False
            selection=source.get('modelSelection') or {}
            if not isinstance(selection,dict):raise ValueError('Invalid model selection')
            model=selection.get('model');provider=provider_map.get(source.get('providerInstanceId',selection.get('instanceId')))
            parent=(source.get('lineage') or {}).get('parentThreadId')
            ended=date('latestRunCompletedAt')
            ended_source='latestRunCompletedAt' if ended else None
            if ended is None and state=='failed':ended=updated;ended_source='updatedAt'
            row={'id':identity,'projectId':project,'parentId':text(parent) if parent is not None else None,
                 'title':display(source.get('title')),'state':state,
                 'provider':display(provider,120,'Unknown provider') if provider is not None else None,'model':display(model,120,'Unknown model') if model is not None else None,
                 'runId':run,'startedAt':date('activityRunStartedAt') or date('latestRunStartedAt'),
                 'lastActivityAt':updated,'endedAt':ended,'endedAtSource':ended_source,'waitingOnYou':waiting,'stuck':stuck,
                 'liveness':liveness,'contextOnly':False,'links':links(environment,identity),'children':[]}
            rows[identity]=row
            modes[identity]='active' if state in ACTIVE else 'ended' if state in ENDED and row['endedAt'] and -5<=(now-stamp(row['endedAt'])).total_seconds()<=settings['endedExpiryHours']*3600 else None
        except (ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError):
            malformed+=1
            continue
    for row in rows.values():
        parent=rows.get(row['parentId'])
        if not parent or parent['projectId']!=row['projectId']:row['parentId']=None
    def ancestors(identity):
        seen=set();parent=identity
        while parent is not None:
            if parent in seen or len(seen)>=64:raise ValueError('Invalid parent cycle/depth')
            seen.add(parent);parent=rows[parent]['parentId']
        return seen
    # The contract rejects a cyclic (or unboundedly deep) lineage outright; nothing is detached.
    for identity in rows:
        try:ancestors(identity)
        except ValueError as error:raise CyclicLineage('Cyclic thread lineage') from error
    def group(mode):
        selected={identity for identity in rows if modes[identity]==mode}
        included=set().union(*(ancestors(identity) for identity in selected)) if selected else set()
        copies={identity:{**rows[identity],'children':[],'contextOnly':identity not in selected} for identity in included}
        groups={}
        for identity,row in copies.items():
            if row['parentId'] in copies:copies[row['parentId']]['children'].append(row)
            else:groups.setdefault(row['projectId'],[]).append(row)
        def sort(items):
            items.sort(key=lambda row:(row['title'].casefold(),row['id']))
            for row in items:sort(row['children'])
        result=[]
        for project,items in groups.items():
            sort(items);result.append({'id':project,'title':projects[project],'agents':items})
        result.sort(key=lambda p:(p['title'].casefold(),p['id']))
        return result
    actual=[row for key,row in rows.items() if modes[key]=='active']
    data={'environmentId':environment,'omittedRows':malformed,'warnings':['rows_omitted'] if malformed else [],'projects':group('active'),'ended':group('ended'),
          'counts':{'running':sum(row['state']=='running' for row in actual),
                    'waitingOnYou':sum(row['waitingOnYou']['question'] or row['waitingOnYou']['approval'] for row in actual),
                    'stuck':sum(row['stuck'] is True for row in actual),'ended':sum(mode=='ended' for mode in modes.values())}}
    return data,rows,modes
