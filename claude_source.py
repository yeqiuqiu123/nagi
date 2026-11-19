"""Opt-in Claude reader. OAuth material exists only in this reader's memory."""
import copy
import http.client
import math
import sys
import time
from datetime import timedelta
from pathlib import Path

from agents_projection import stamp
from agents_service import outcome
from local_sources import (LOCAL_COVERAGE, LOCAL_FLAGS, binding, json_file, json_lines,
                           native_row, owned_root, project_rows, read_owned)
from sources_transport import bounded_command, cli_environment, valid_token
from t3_reader import IODeadline
from jsonio import strict_json_loads


class ClaudeReadError(Exception):
    def __init__(self,reason):
        allowed={'claude_login_missing','claude_login_expired','claude_login_invalid',
                 'provider_rate_limited','provider_unavailable','invalid_usage'}
        self.reason=reason if reason in allowed else 'provider_unavailable'
        super().__init__(self.reason)


def credential(home,now,*,platform=None,command=None):
    raw=None
    if (platform or sys.platform)=='darwin':
        try:
            raw=(command or bounded_command)(['/usr/bin/security','find-generic-password','-s','Claude Code-credentials','-w'],
                                            limit=64*1024,seconds=2,env=cli_environment())
        except Exception:pass  # Locked/missing Keychain falls back; never reveal stderr.
    try:
        if raw is None:
            owned_root(Path(home)/'.claude')
            value=json_file(Path(home)/'.claude/.credentials.json',64*1024,private=True)
        else:value=strict_json_loads(raw,64*1024,max_depth=8)
        oauth=value['claudeAiOauth'];token=oauth['accessToken'];expires=oauth['expiresAt']
        if not valid_token(token) or type(expires) not in (int,float) or not math.isfinite(expires):raise ValueError()
        if expires/1000<=now.timestamp():raise ClaudeReadError('claude_login_expired')
        # subscriptionType/rateLimitTier may be present; neither identifies an
        # account or changes the generic display label, so neither is exported.
        return token
    except FileNotFoundError:raise ClaudeReadError('claude_login_missing') from None
    except ClaudeReadError:raise
    except Exception:raise ClaudeReadError('claude_login_invalid') from None


def fetch_usage(home,now):
    token=credential(home,now)
    connection=http.client.HTTPSConnection('api.anthropic.com',timeout=8)
    try:
        # http.client ignores proxy variables; host and path are fixed and no
        # redirect handler exists. The token is never an argv or env value.
        with IODeadline(connection,8) as budget:
            connection.connect();budget.connected()
            connection.request('GET','/api/oauth/usage',headers={'Authorization':'Bearer '+token,
                               'anthropic-beta':'oauth-2025-04-20','Accept':'application/json'})
            response=connection.getresponse()
            if response.status==401:raise ClaudeReadError('claude_login_expired')
            if response.status==429:raise ClaudeReadError('provider_rate_limited')
            if response.status!=200:raise ClaudeReadError('provider_unavailable')
            raw=response.read(128*1024+1);budget.check()
            value=strict_json_loads(raw,128*1024,max_depth=16)
            if not isinstance(value,dict):raise ClaudeReadError('invalid_usage')
            return value
    except ClaudeReadError:raise
    except Exception:raise ClaudeReadError('provider_unavailable') from None
    finally:
        token=None
        connection.close()


def usage_provider(value,checked,account='claude-local'):
    if not isinstance(value,dict):raise ClaudeReadError('invalid_usage')
    windows=[]
    for key,bucket in value.items():
        if key not in ('five_hour','seven_day') and not (isinstance(key,str) and key.startswith('seven_day_')):continue
        if bucket is None:continue
        if not isinstance(bucket,dict):raise ClaudeReadError('invalid_usage')
        used=bucket.get('utilization');reset=bucket.get('resets_at')
        if type(used) not in (int,float) or not math.isfinite(used) or not 0<=used<=100:raise ClaudeReadError('invalid_usage')
        try:stamp(reset)
        except (ValueError,TypeError):raise ClaudeReadError('invalid_usage') from None
        label='Session' if key=='five_hour' else 'Weekly' if key=='seven_day' else 'Weekly · '+key[10:].replace('_',' ').title()
        windows.append({'id':key,'label':label,'usedPercent':used,'resetsAt':reset,
                        'windowDurationMins':300 if key=='five_hour' else 10080})
    return {'driver':'claudeAgent','instanceId':account,'installed':True,'enabled':True,
            'usageLimits':{'checkedAt':checked,'windows':windows}}


class ClaudeAdapter:
    identity=None  # Set by the static registry without circular imports.
    potential_capabilities=dict(LOCAL_FLAGS,asksYou=True)
    coverage=dict(LOCAL_COVERAGE,asksYou='partial')

    def configure(self,value):return binding(value)

    def configuration_schema(self):
        return {'version':1,'harness':'claude','available':True,'modes':['direct'],
                'capabilities':dict(self.potential_capabilities),
                'requirements':['claude_hooks_opt_in','claude_usage_opt_in']}

    def read(self,service,now,settings,caches,force=False):
        at=now.isoformat();home=service.policy['home'];journal=service.journal()
        agents=outcome('unavailable',at,reason='local_data_missing');rows=modes=None
        workspaces={}
        try:
            events=[]
            for suffix in ('.1',''):
                # Tail-read with headroom, so a file written before the rotation fix can never take the source down.
                try:events.extend(json_lines(read_owned(service.store.directory/('claude-'+service.source_id+'.jsonl'+suffix),1280*1024,private=True,tail=True)))
                except FileNotFoundError:pass
            rows={};metadata={}
            for event in events:
                try:
                    when=event['timestamp'];age=(now-stamp(when)).total_seconds()
                    if not 0<=age<=7*86400:continue
                    session=event['sessionId'];agent=event.get('agentId');kind=event['event']
                    if not isinstance(session,str) or not isinstance(agent,(str,type(None))):continue
                    identity=session if not agent else session+'/'+agent
                    if 'github' in event:workspaces[identity]=event['github']
                    # Only explicit starts produce a row. A subagent stop by itself
                    # may be an internal feature, not a user-visible agent.
                    if kind in ('UserPromptSubmit','SubagentStart'):
                        rows[identity]=native_row(identity,event.get('project'),event.get('title') or 'Claude session',
                                                   'claudeAgent',when,parent=session if agent else None,model=event.get('model') or metadata.get(session))
                    elif kind=='SessionStart':
                        # Session start proves presence, not an executing turn.
                        metadata[session]=event.get('model')
                        continue
                    row=rows.get(identity)
                    if row is None:continue
                    if kind!='SessionStart':row['lastActivityAt']=when
                    if kind in ('Stop','SessionEnd','SubagentStop'):
                        row.update(state='completed',endedAt=when,endedAtSource='latestRunCompletedAt')
                    if kind=='SessionEnd' and not agent:
                        for child_id,child in rows.items():
                            if child_id.startswith(session+'/'):
                                child.update(state='completed',endedAt=when,endedAtSource='latestRunCompletedAt',lastActivityAt=when)
                                child['waitingOnYou']={'question':False,'approval':False,'blocking':False}
                    if kind in ('PreToolUse','PostToolUse','UserPromptSubmit','Stop','SessionEnd','SubagentStop'):
                        row['waitingOnYou']={'question':False,'approval':False,'blocking':False}
                    if kind=='Notification' and event.get('asksYou') is True:
                        question=event.get('askKind')=='question'
                        row['waitingOnYou']={'question':question,'approval':not question,'blocking':True}
                        row['lastActivityAt']=when
                    elif kind=='Notification' and event.get('askKind')=='clear':
                        row['waitingOnYou']={'question':False,'approval':False,'blocking':False}
                except (ValueError,TypeError,KeyError):continue
            data,rows,modes=project_rows(rows,service.source_id,now,settings)
            # A session that went quiet without Stop (Esc, a closed terminal, a lost event) drops out on
            # its own; it never blanks the others. The warning says coverage has a gap.
            if any(row['state']=='running' and modes[key] is None for key,row in rows.items()):
                data['warnings']=[*data['warnings'],'stale_source']
            agents=outcome('ok' if data['projects'] or data['ended'] else 'quiet',at,at,data=data)
        except Exception:agents=outcome('unavailable',at,reason='invalid_source');rows=modes=None
        poll=journal.get('claudePoll',{})
        try:due=now>=stamp(poll['nextAt'])
        except (ValueError,TypeError,KeyError):due=True
        monotonic=getattr(service,'monotonic',time.monotonic)
        due=due and monotonic()>=getattr(service,'claude_next_poll',0)
        if not due:
            limits=copy.deepcopy(getattr(service,'claude_result',None) or caches.get('claude'))
            if poll.get('reason'):
                limits=outcome('unavailable',at,reason=poll['reason'])
            if limits is None:limits=outcome('unavailable',at,reason=poll.get('reason','checking'))
            if limits.get('checkedAt') and (now-stamp(limits['checkedAt'])).total_seconds()>900:
                limits=outcome('unavailable',at,reason='stale_source')
            elif limits.get('data'):
                limits=expire_windows(limits,now,at)
        else:
            failures=min(poll.get('failures',0),6) if type(poll.get('failures',0)) is int else 0
            # Save the attempt BEFORE I/O: restart/crash cannot evade the floor.
            marker={'nextAt':(now+timedelta(seconds=300)).isoformat(),'failures':failures,'reason':'checking'}
            service.claude_next_poll=monotonic()+300
            service.mutate_journal(lambda state:state.update(claudePoll=marker))
            try:
                value=getattr(service,'usage_fetcher',fetch_usage)(home,now)
                checked=service.clock().isoformat()
                provider=usage_provider(value,checked)
                warnings=[]
                limits=service.provider_limits('claude',[provider],at,now,{},True,warnings)
                limits['warnings']=warnings
                marker.update(failures=0,reason=None)
            except ClaudeReadError as error:
                limits=outcome('unavailable',at,reason=error.reason)
                failures=min(failures+1,6)
                delay=min(3600,300*2**failures) if error.reason in ('provider_rate_limited','provider_unavailable') else 300
                marker.update(nextAt=(now+timedelta(seconds=delay)).isoformat(),failures=failures,reason=error.reason)
                service.claude_next_poll=monotonic()+delay
            except Exception:
                limits=outcome('unavailable',at,reason='invalid_usage');marker.update(reason='invalid_usage')
            service.mutate_journal(lambda state:state.update(claudePoll=marker))
            service.claude_result=copy.deepcopy(limits)
        limits.setdefault('warnings',[])
        return {'agents':agents,'limits':{'claude':limits,'codex':{**outcome('unsupported',at,reason='account_unsupported'),'warnings':[]}},
                'rows':rows,'modes':modes,'icon_sources':{},'success':True,
                'workspaces':{key:workspaces.get(key) or workspaces.get(key.split('/',1)[0])
                              for key,mode in (modes or {}).items() if mode}}


def expire_windows(value,now,at):
    for account in value['data']['accounts']:
        for key in ('windows','secondaryWindows'):
            if key in account:account[key]=[w for w in account[key] if stamp(w['resetsAt'])>now]
    value['data']['accounts']=[a for a in value['data']['accounts'] if a['windows'] or a.get('secondaryWindows')]
    return value if value['data']['accounts'] else outcome('unavailable',at,reason='windows_missing')
