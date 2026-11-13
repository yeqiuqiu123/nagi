"""Read-only source polling, dated display cache and durable transition delivery."""
from datetime import datetime, timezone
import hashlib
import json
import copy
import secrets
import threading
import time
import project_icons

from agents_projection import stamp,text,display
from nagi_store import LocalStore
from t3_reader import T3Reader

DEFAULTS={'endedExpiryHours':24,'stuckMinutes':15,'limitAlertPercent':10}
BOUNDS={'endedExpiryHours':(1,168),'stuckMinutes':(5,120)}
JOURNAL='nagi-agent-state.json'


def utcnow():return datetime.now(timezone.utc)

def outcome(status,attempted,checked=None,reason=None,data=None):
    return {'status':status,'attemptedAt':attempted,'checkedAt':checked,'reason':reason,'data':data}


# T3 names provider drivers; Claude runs under the claudeAgent driver.
DRIVERS={'codex':'codex','claude':'claudeAgent','cursor':'cursor'}
# T3 refreshes quotas every few minutes and Nagi caches config for five, so a
# healthy reading can be up to about ten minutes old.
STALE_LIMIT_SECONDS=900


def validate_limit_event(event):
    fields={'id','kind','provider','accountId','accountLabel','windowId','windowLabel',
            'remainingPercent','resetsAt','occurredAt','links'}
    if not isinstance(event,dict) or set(event)!=fields or event['kind']!='low_limit':raise ValueError()
    AgentsService.event_id(event['id'])
    if event['provider'] not in ('codex','claude','cursor'):raise ValueError()
    for key in ('accountId','accountLabel','windowId','windowLabel'):text(event[key],512)
    percent=event['remainingPercent']
    if type(percent) not in (int,float) or not 0<=percent<=100:raise ValueError()
    stamp(event['resetsAt']);stamp(event['occurredAt'])
    if event['links']!={'desktop':None,'web':None}:raise ValueError()


class AgentsService:
    def __init__(self,directory,reader_factory=T3Reader,clock=utcnow,*,source_id=None):
        self.store=LocalStore(directory);self.factory=reader_factory;self.clock=clock
        self.source_id=source_id
        self.journal_name=JOURNAL if source_id is None else f'nagi-source-{source_id}-state.json'
        self.lock=threading.RLock();self.last_poll=None
        self.poll_gate=threading.Lock();self.revision=0;self.journal_warning=False
        self.config_cache=None;self.config_at=None;self.config_valid=False
        # Favicon sources stay here, keyed by opaque project keys; paths never reach a DTO.
        self.icon_sources={};self.icon_cache={}
        at=self.clock().isoformat()
        self.agents=outcome('unavailable',at,reason='checking')
        self.providers={key:{**outcome('unavailable',at,reason='checking'),'warnings':[]} for key in ('codex','claude')}
        self.machine=outcome('unavailable',at,reason='checking')

    def settings_info(self):
        try:
            value=self.store.read('nagi-settings.json',dict(DEFAULTS))
            if isinstance(value,dict) and set(value)=={'stuckAfterSeconds','endedWithinHours'}:
                if any(type(item) is not int for item in value.values()):raise ValueError()
                value={'stuckMinutes':(value['stuckAfterSeconds']+59)//60,'endedExpiryHours':value['endedWithinHours']}
            return self.validate_settings(value),False
        except (OSError,ValueError,TypeError,RecursionError):return dict(DEFAULTS),True

    def settings(self):return self.settings_info()[0]

    def warnings(self):
        self.journal()
        return (['settings_invalid'] if self.settings_info()[1] else [])+(['journal_reset'] if self.journal_warning else [])

    def settings_resource(self):
        return {'version':2,'settings':self.settings(),'defaults':dict(DEFAULTS),'warnings':self.warnings()}

    @staticmethod
    def validate_journal(value):
        if not isinstance(value,dict):raise ValueError()
        if not isinstance(value.get('conditions',{}),dict) or not isinstance(value.get('cache',{}),dict) or not isinstance(value.get('events',[]),list):raise ValueError()
        alerts=value.get('limitAlerts',{})
        if not isinstance(alerts,dict) or len(alerts)>2048:raise ValueError()
        for key,reset in alerts.items():
            AgentsService.event_id(key);stamp(reset)
        for condition in value.get('conditions',{}).values():
            if not isinstance(condition,dict):raise ValueError()
            for field in ('failedGeneration','stuckGeneration'):
                if type(condition.get(field,0)) is not int or condition.get(field,0)<0:raise ValueError()
            if 'lastSeenAt' in condition:stamp(condition['lastSeenAt'])
        for event in value.get('events',[]):
            if not isinstance(event,dict) or event.get('kind') not in ('failed','stuck','low_limit') or type(event.get('claimed')) is not bool:raise ValueError()
            if not isinstance(event.get('id'),str) or len(event['id'])!=64:raise ValueError()
            stamp(event['occurredAt'])
            if event['kind']=='low_limit':
                validate_limit_event(AgentsService.public_event(event))
                continue
            for key in ('threadId','projectId','threadTitle','projectTitle'):text(event[key])
            if not isinstance(event.get('links'),dict) or set(event['links'])!={'desktop','web'}:raise ValueError()
        for key,cache in value.get('cache',{}).items():
            if not isinstance(cache,dict) or cache.get('status') not in ('ok','quiet'):raise ValueError()
            stamp(cache['checkedAt'])
            data=cache.get('data')
            if not isinstance(data,dict):raise ValueError()
            fields=('projects','ended') if key=='agents' else ('accounts',)
            if any(not isinstance(data.get(field),list) for field in fields):raise ValueError()
            if key=='agents':
                text(data['environmentId'])
                if not {'environmentId','projects','ended','counts'}<=set(data)<= {'environmentId','projects','ended','counts','omittedRows','warnings'} or not isinstance(data['counts'],dict):raise ValueError()
                if type(data.get('omittedRows',0)) is not int or data.get('omittedRows',0)<0:raise ValueError()
                if set(data['counts'])!={'running','waitingOnYou','stuck','ended'} or any(type(n) is not int or n<0 for n in data['counts'].values()):raise ValueError()
                for group in data['projects']+data['ended']:
                    if not isinstance(group,dict) or not {'id','title','agents'}<=set(group)<={'id','title','agents','icon'} or not isinstance(group['agents'],list):raise ValueError()
                    text(group['id']);text(group['title'])
                    icon=group.get('icon',{'kind':'auto'})
                    if not (icon in ({'kind':'auto'},) or project_icons.override(icon)==icon
                            or (isinstance(icon,dict) and set(icon)=={'kind','key'} and icon['kind']=='favicon' and project_icons.KEY.fullmatch(str(icon['key'])))):raise ValueError()
            else:
                if key not in ('codex','claude','cursor') or set(data)!={'accounts'}:raise ValueError()
                for account in data['accounts']:
                    if not isinstance(account,dict) or not {'id','label','windows'}<=set(account)<={'id','label','windows','secondaryWindows','status','checkedAt','reason'} or not isinstance(account['windows'],list):raise ValueError()
                    text(account['id']);text(account['label'])
                    if account.get('status','ok') not in ('ok','last_known','unavailable','unsupported'):raise ValueError()
                    if account.get('checkedAt') is not None:stamp(account['checkedAt'])
                    if account.get('reason') is not None:text(account['reason'],64)
                    for window in account['windows']+account.get('secondaryWindows',[]):
                        if not isinstance(window,dict) or set(window) not in ({'kind','remainingPercent','resetsAt','checkedAt'},{'id','label','kind','remainingPercent','resetsAt','checkedAt'}):raise ValueError()
                        if window['kind'] not in ('five_hour','weekly','monthly','other') or type(window['remainingPercent']) not in (int,float) or not 0<=window['remainingPercent']<=100:raise ValueError()
                        stamp(window['resetsAt']);stamp(window['checkedAt'])


    def journal(self):
        try:
            value=self.store.read(self.journal_name,{})
            self.validate_journal(value)
            if value.get('recovered'):self.journal_warning=True
            return value
        except (OSError,ValueError,KeyError,TypeError,RecursionError):
            self.journal_warning=True;return {}

    def mutate_journal(self,build):
        self.journal()
        def apply(value):
            if self.journal_warning:value['recovered']=True
            return build(value)
        return self.store.mutate(self.journal_name,{},apply,repair=True,validate=self.validate_journal)

    @staticmethod
    def validate_settings(value):
        if not isinstance(value,dict) or set(value) not in (set(DEFAULTS),set(BOUNDS)):
            raise ValueError('Invalid local settings')
        if any(type(value[key]) is not int for key in BOUNDS):raise ValueError('Invalid local settings')
        alert=value.get('limitAlertPercent',10)
        if alert!='off' and (type(alert) is not int or not 1<=alert<=50):raise ValueError('Invalid local settings')
        return {key:max(low,min(high,value[key])) for key,(low,high) in BOUNDS.items()}|{'limitAlertPercent':alert}

    def save_settings(self,value):
        value=self.validate_settings(value)
        with self.lock:
            def write(current):current.clear();current.update(value)
            self.store.mutate('nagi-settings.json',dict(DEFAULTS),write,repair=True,validate=self.validate_settings)
            def repaired(journal):journal.pop('recovered',None)
            self.mutate_journal(repaired)
            self.journal_warning=False;self.revision+=1
            self.last_poll=None
        return dict(value)

    def poll(self,force=False):
        if not self.poll_gate.acquire(blocking=False):return
        try:
            with self.lock:
                now=self.clock();attempted=now.isoformat()
                if not force and self.last_poll is not None and 0<=(now-self.last_poll).total_seconds()<20:return
                settings=self.settings();journal=self.journal();caches=copy.deepcopy(journal.get('cache',{}));revision=self.revision
            from source_adapters import ADAPTERS
            read=ADAPTERS[getattr(self,'adapter_id','t3')].read(self,now,settings,caches,force)
            agents,limits,rows,modes,icon_sources,success=(read[key] for key in
                ('agents','limits','rows','modes','icon_sources','success'))
            self.read_machine(attempted)
            with self.lock:
                if revision!=self.revision or settings!=self.settings():return
                self.limit_observations=set()
                for provider,value in limits.items():
                    old_accounts={a['id']:a for a in (caches.get(provider,{}).get('data') or {}).get('accounts',[])}
                    if value['status']!='ok':continue
                    for account in (value.get('data') or {}).get('accounts',[]):
                        prior=old_accounts.get(account['id'],{})
                        prior_windows={w.get('id'):w for w in prior.get('windows',[])+prior.get('secondaryWindows',[])}
                        for window in account.get('windows',[])+account.get('secondaryWindows',[]):
                            old=prior_windows.get(window.get('id'))
                            if old is None or stamp(window['checkedAt'])>stamp(old['checkedAt']):
                                self.limit_observations.add((provider,account['id'],window.get('id'),window['checkedAt']))
                if success:self.record(agents,limits,rows,modes,now,settings)
                if success and rows is not None:self.icon_sources=icon_sources
                self.agents=agents;self.providers=limits;self.last_poll=now
        finally:self.poll_gate.release()

    ICON_TTL=30*60      # T3 signs project-favicon URLs in 30-minute buckets
    ICON_RETRY=60       # a failed lookup (T3 unreachable) is retried after a minute

    def icon_known_missing(self,key):
        cached=self.icon_cache.get(key)
        return cached is not None and cached[1] is None and cached[2] and cached[0]>time.monotonic()

    def attach_icons(self,data,snapshot):
        """Give each project T3's icon: a validated override, its favicon key, or auto."""
        sources={};environment=data['environmentId']
        raw={p.get('id'):p for p in snapshot.get('projects',[]) if isinstance(p,dict)}
        for group in data['projects']+data['ended']:
            source=raw.get(group['id'],{})
            chosen=project_icons.override(source.get('projectIcon'))
            if chosen is None:
                favicon=project_icons.favicon_source(source);key=project_icons.key(environment,group['id'],source_id=self.source_id)
                if favicon:sources[key]=favicon
                chosen={'kind':'favicon','key':key} if favicon and not self.icon_known_missing(key) else {'kind':'auto'}
            group['icon']=chosen
        return sources

    def project_icon(self,key):
        """(bytes, content type) of a project's favicon through T3's own lookup, or None."""
        if not isinstance(key,str) or not project_icons.KEY.fullmatch(key):return None
        with self.lock:source=self.icon_sources.get(key);cached=self.icon_cache.get(key)
        if source is None:return None
        now=time.monotonic()
        if cached is not None and cached[0]>now:return cached[1]
        result=None;settled=True
        try:
            reader=self.factory(self.store.directory)
            url=reader.favicon_url(*source) if hasattr(reader,'favicon_url') else None
            result=reader.asset(url) if url else None
        except Exception:
            settled=False  # T3 unreachable or refused: not a verdict on the favicon
        with self.lock:
            self.icon_cache[key]=(now+(self.ICON_TTL if settled else self.ICON_RETRY),result,settled)
            if len(self.icon_cache)>512:self.icon_cache.pop(next(iter(self.icon_cache)))
        return result

    @staticmethod
    def failed(status,attempted,reason,prior,now=None):
        if status=='unavailable' and isinstance(prior,dict) and prior.get('data') is not None:
            if now is not None:
                prior=copy.deepcopy(prior)
                for account in prior['data']['accounts']:
                    if any('id' not in w or 'label' not in w for w in account['windows']+account.get('secondaryWindows',[])):
                        return outcome(status,attempted,reason=reason)
                    # Every retained account is dated, never left marked fresh.
                    if account.get('status','ok')=='ok':account.update(status='last_known',checkedAt=account.get('checkedAt') or prior['checkedAt'])
                    account['windows']=[w for w in account['windows'] if stamp(w['resetsAt'])>now]
                    if 'secondaryWindows' in account:account['secondaryWindows']=[w for w in account['secondaryWindows'] if stamp(w['resetsAt'])>now]
                prior['data']['accounts']=[a for a in prior['data']['accounts'] if a['windows'] or a.get('secondaryWindows')]
                if not prior['data']['accounts']:return outcome(status,attempted,reason=reason)
            if now is None:
                prior=copy.deepcopy(prior);data=prior['data']
                data.setdefault('omittedRows',0);data.setdefault('warnings',[])
                stack=[a for p in data['projects']+data['ended'] for a in p['agents']]
                while stack:
                    row=stack.pop();row.setdefault('endedAtSource','latestRunCompletedAt' if row.get('endedAt') else None)
                    stack.extend(row['children'])
            return outcome('last_known',attempted,prior['checkedAt'],reason,prior['data'])
        return outcome(status,attempted,reason=reason)

    def project_limits(self,providers,attempted,now,caches,config_ok=True):
        result={}
        for kind in ('codex','claude'):
            warnings=[]
            try:result[kind]=self.provider_limits(kind,providers,attempted,now,caches,config_ok,warnings)
            except Exception:
                warnings.append('invalid_account')
                result[kind]=self.failed('unavailable',attempted,'invalid_source',caches.get(kind),now)
            if result[kind]['status']=='last_known':warnings.extend(caches.get(kind,{}).get('warnings',[]))
            result[kind]['warnings']=list(dict.fromkeys(warnings))
        return result

    def provider_limits(self,kind,providers,attempted,now,caches,config_ok,warnings):
        selected=[p for p in providers if p.get('driver')==DRIVERS[kind] and p.get('enabled')]
        if not selected or not any(p.get('installed') for p in selected):
            return self.failed('not_set_up' if config_ok else 'unavailable',attempted,
                'not_installed' if config_ok else 'probe_failed',caches.get(kind),now)
        accounts=[];reason='windows_missing';unsupported=True;checks=[]
        headlines=('month',) if kind=='cursor' else ('five_hour','seven_day') if kind=='claude' else ('primary','secondary')
        installed=[p for p in selected if p.get('installed')]
        prior=caches.get(kind) if isinstance(caches.get(kind),dict) else {}
        cached={a.get('id'):a for a in ((prior.get('data') or {}).get('accounts') or []) if isinstance(a,dict)}
        def unexpired(items):return [w for w in items if isinstance(w,dict) and w.get('resetsAt') and stamp(w['resetsAt'])>now]
        def missing(identity,label,why):
            # A failed account keeps its line: dated last-known windows from its own cache, or unavailable.
            old=cached.get(identity) or {}
            windows,secondary=unexpired(old.get('windows') or []),unexpired(old.get('secondaryWindows') or [])
            if windows or secondary:
                entry={'id':identity,'label':label,'windows':windows,'status':'last_known','checkedAt':old.get('checkedAt') or prior.get('checkedAt'),'reason':why}
                if secondary:entry['secondaryWindows']=secondary
                return entry
            return {'id':identity,'label':label,'windows':[],'status':'unavailable','checkedAt':None,'reason':why}
        for index,provider in enumerate(installed):
            # Labels follow this computer's account order, so Codex 2 stays Codex 2 when Codex 1 fails.
            label=kind.title()+' '+str(index+1)
            try:
                identity=text(provider['instanceId']);limit=provider.get('usageLimits') or {};issue=limit.get('unavailable') or {}
                if issue.get('reason')!='unsupported':unsupported=False
                if issue:
                    if issue.get('reason')=='unsupported':
                        reason='account_unsupported'
                        accounts.append({'id':identity,'label':label,'windows':[],'status':'unsupported','checkedAt':None,'reason':'account_unsupported'})
                    else:
                        reason='probe_failed';accounts.append(missing(identity,label,'probe_failed'))
                    continue
                checked=limit.get('checkedAt')
                if not checked or not -5<=(now-stamp(checked)).total_seconds()<=STALE_LIMIT_SECONDS:
                    reason='stale_source';accounts.append(missing(identity,label,'stale_source'));continue
                if not isinstance(limit.get('windows',[]),list):raise ValueError()
                windows={};secondary={}
                for window in limit.get('windows',[]):
                    try:
                        identity_window=text(window['id'],120)
                        if identity_window not in headlines and not (kind=='claude' and identity_window.startswith('seven_day_')):
                            warnings.append('unexpected_window');continue
                        if identity_window in windows or identity_window in secondary:warnings.append('duplicate_window');continue
                        minutes=window.get('windowDurationMins');used=window.get('usedPercent');reset=window.get('resetsAt')
                        if type(used) not in (int,float) or not 0<=used<=100 or not reset:raise ValueError()
                        if stamp(reset)<=now:continue
                        window_kind='five_hour' if minutes==300 else 'weekly' if minutes==10080 else 'monthly' if type(minutes) in (int,float) and minutes>=43200 else 'other'
                        fallback='5-hour' if window_kind=='five_hour' else window_kind.title()
                        if identity_window not in headlines:fallback='Weekly · '+identity_window[len('seven_day_'):].replace('_',' ')
                        item={'id':identity_window,'label':display(window.get('label'),120,fallback),'kind':window_kind,
                            'remainingPercent':round(100-used,2),'resetsAt':reset,'checkedAt':checked}
                        (windows if identity_window in headlines else secondary)[identity_window]=item
                    except (ValueError,TypeError,KeyError,AttributeError,OverflowError):warnings.append('invalid_window');continue
                if windows or secondary:
                    account={'id':identity,'label':label,'windows':[windows[key] for key in headlines if key in windows],
                             'status':'ok','checkedAt':checked,'reason':None}
                    if secondary:account['secondaryWindows']=list(secondary.values())
                    accounts.append(account);checks.append(checked)
                else:accounts.append(missing(identity,label,'windows_missing'))
            except (ValueError,TypeError,KeyError,AttributeError,OverflowError):
                unsupported=False;warnings.append('invalid_account');reason='invalid_source'
        if checks:
            # Partial coverage is explicit: the provider is ok, and the warning names the gap.
            if any(a['status'] in ('unavailable','last_known') for a in accounts):warnings.append('account_unavailable')
            return outcome('ok',attempted,min(checks,key=stamp),data={'accounts':accounts})
        return self.failed('unsupported' if unsupported else 'unavailable',attempted,'account_unsupported' if unsupported else reason,caches.get(kind),now)

    def record(self,agents,providers,rows,modes,now,settings):
        def build(journal):
            if rows is None:
                # A rejected agents snapshot leaves conditions and the agents cache alone.
                journal['cache']={**journal.get('cache',{}),**{k:v for k,v in providers.items() if v['status']=='ok'}}
                return
            prior=journal.get('conditions',{});first='conditions' not in journal
            events=journal.get('events',[]);journal.pop('rebaseline',None)
            conditions={key:{**value,'lastSeenAt':value.get('lastSeenAt',now.isoformat())} for key,value in prior.items()
                        if (now-stamp(value.get('lastSeenAt',now.isoformat()))).total_seconds()<=7*86400}
            projects={p['id']:p['title'] for p in agents['data']['projects']+agents['data']['ended']}
            for identity,row in rows.items():
                key=(agents['data']['environmentId']+':'+identity if self.source_id is None else
                     hashlib.sha256(json.dumps([self.source_id,agents['data']['environmentId'],identity],separators=(',',':')).encode()).hexdigest())
                old=prior.get(key,{})
                same_run=old.get('runId')==row['runId']
                silence=str(row['runId'])+':'+row['lastActivityAt']
                notified=old.get('stuckSilence') if same_run else None
                # Old journals migrate their already-decided stuck condition conservatively.
                if notified is None and same_run and old.get('stuck') is True:notified=silence
                if old.get('activityAt',row['lastActivityAt'])!=row['lastActivityAt']:notified=None
                failed=row['state']=='failed'
                decided=not failed or row['endedAt'] is not None or first
                condition={'runId':row['runId'],'failed':failed if decided else old.get('failed',False) if same_run else False,
                    'stuck':row['stuck'],'stuckSilence':notified,'activityAt':row['lastActivityAt'],'lastSeenAt':now.isoformat(),
                    'failedGeneration':old.get('failedGeneration',0),'stuckGeneration':old.get('stuckGeneration',0)}
                for kind in ('failed','stuck'):
                    entered=condition[kind] is True and (old.get(kind) is not True or not same_run)
                    eligible=entered and not first
                    if kind=='failed':eligible=eligible and modes[identity]=='ended'
                    else:
                        eligible=(condition[kind] is True and (entered or old.get('activityAt',row['lastActivityAt'])!=row['lastActivityAt'])
                                  and not first and condition['stuckSilence']!=silence)
                        if condition[kind] is True:condition['stuckSilence']=silence
                    if eligible:
                        field=kind+'Generation';condition[field]+=1
                        event_id=hashlib.sha256((f"{key}:{row['runId']}:{kind}:{condition[field]}" if self.source_id is None else
                            json.dumps([self.source_id,key,row['runId'],kind,condition[field]],separators=(',',':'))).encode()).hexdigest()
                        events.append({'id':event_id,'kind':kind,'threadId':identity,'projectId':row['projectId'],'threadTitle':row['title'],
                            'projectTitle':projects[row['projectId']],'occurredAt':now.isoformat(),'links':row['links'],'claimed':False})
                    if kind=='stuck' and condition[kind] is None and same_run:condition[kind]=old.get(kind)
                conditions[key]=condition
            journal['conditions']=conditions
            journal['events']=[e for e in events if (now-stamp(e['occurredAt'])).total_seconds()<86400][-256:]
            journal['cache']={**journal.get('cache',{}),'agents':agents,**{k:v for k,v in providers.items() if v['status']=='ok'}}
        self.mutate_journal(build)

    def read_machine(self,attempted):
        try:
            from machine import host_metrics
            value=host_metrics(self.store.directory)
            if value.get('status')=='unsupported':self.machine=outcome('unsupported',attempted,reason='platform_unsupported');return
            keys=('cpuPercent','memoryUsedBytes','memoryTotalBytes','diskFreeBytes','diskTotalBytes','uptimeSeconds')
            self.machine=outcome('ok',attempted,attempted,data={key:value[key] for key in keys})
        except Exception:self.machine=outcome('unavailable',attempted,reason='cannot_read_machine')

    @staticmethod
    def public_event(event):return {key:value for key,value in event.items() if key not in ('claimed','lease','leaseUntil')}

    def pending(self,event):
        age=(self.clock()-stamp(event['occurredAt'])).total_seconds()
        return (not event['claimed'] and 0<=age<(900 if event['kind']=='low_limit' else 86400)
                and (event['kind']!='low_limit' or stamp(event['resetsAt'])>self.clock()))

    def notifications(self,*,include_limits=False):
        now=self.clock()
        return [self.public_event(event) for event in self.journal().get('events',[])
                if (include_limits or event['kind']!='low_limit') and self.pending(event) and (not event.get('leaseUntil') or stamp(event['leaseUntil'])<=now)]

    def record_limit_alerts(self,settings,*,suppressed=()):
        now=self.clock();threshold=settings['limitAlertPercent']
        if threshold=='off' or self.journal_warning:return
        providers=copy.deepcopy(self.providers);fresh=getattr(self,'limit_observations',set())
        def build(journal):
            seen={key:reset for key,reset in journal.get('limitAlerts',{}).items() if stamp(reset)>now}
            events=journal.get('events',[])
            for provider,value in providers.items():
                if provider in suppressed or value['status']!='ok':continue
                for account in (value.get('data') or {}).get('accounts',[]):
                    if account.get('status','ok')!='ok':continue
                    for window in account.get('windows',[])+account.get('secondaryWindows',[]):
                        if ((provider,account['id'],window.get('id'),window['checkedAt']) not in fresh
                                or not -5<=(now-stamp(window['checkedAt'])).total_seconds()<=STALE_LIMIT_SECONDS
                                or stamp(window['resetsAt'])<=now or window['remainingPercent']>threshold):continue
                        identity=hashlib.sha256(json.dumps([self.source_id or 'legacy-t3',provider,account['id'],
                            window.get('id'),stamp(window['resetsAt']).astimezone(timezone.utc).isoformat()],separators=(',',':')).encode()).hexdigest()
                        if identity in seen or len(seen)>=2048:continue
                        event={'id':identity,'kind':'low_limit','provider':provider,'accountId':account['id'],
                               'accountLabel':account['label'],'windowId':window['id'],'windowLabel':window['label'],
                               'remainingPercent':window['remainingPercent'],'resetsAt':window['resetsAt'],
                               'occurredAt':window['checkedAt'],'links':{'desktop':None,'web':None}}
                        validate_limit_event(event)
                        events.append(dict(event,claimed=False));seen[identity]=window['resetsAt']
            journal['limitAlerts']=seen
            journal['events']=[e for e in events if (now-stamp(e['occurredAt'])).total_seconds()<86400][-256:]
        self.mutate_journal(build)

    @staticmethod
    def event_id(identity):
        if not isinstance(identity,str) or len(identity)!=64 or any(c not in '0123456789abcdef' for c in identity):raise ValueError('Invalid event id')

    def reserve(self,identity,*,include_limits=False):
        from datetime import timedelta
        self.event_id(identity)
        def build(journal):
            for event in journal.get('events',[]):
                if event['kind']=='low_limit' and not include_limits:continue
                if event['id']==identity and self.pending(event) and (not event.get('leaseUntil') or stamp(event['leaseUntil'])<=self.clock()):
                    event['lease']=secrets.token_urlsafe(32);event['leaseUntil']=(self.clock()+timedelta(seconds=30)).isoformat()
                    return {'reservation':event['lease'],'expiresAt':event['leaseUntil'],'event':self.public_event(event)}
            return None
        return self.mutate_journal(build)

    def claim(self,identity,reservation,*,release=False,include_limits=False):
        self.event_id(identity)
        if not isinstance(reservation,str) or len(reservation)!=43:raise ValueError('Invalid reservation')
        def build(journal):
            for event in journal.get('events',[]):
                if event['kind']=='low_limit' and not include_limits:continue
                if (event['id']==identity and self.pending(event) and event.get('lease')==reservation
                        and stamp(event['leaseUntil'])>self.clock()):
                    if not release:event['claimed']=True
                    event.pop('lease',None);event.pop('leaseUntil',None)
                    return self.public_event(event)
            return None
        return self.mutate_journal(build)
