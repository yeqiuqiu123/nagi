"""Opt-in, fixture-qualified Cursor beta. Secrets stay in the runtime reader."""
import base64
import copy
import http.client
import math
import os
import re
import sqlite3
import stat
import sys
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote

from agents_projection import stamp
from agents_service import outcome
from claude_source import expire_windows
from local_sources import (LOCAL_COVERAGE, LOCAL_FLAGS, binding, json_file, json_lines,
                           native_row, owned_root, project_rows, read_owned)
from t3_reader import IODeadline
from jsonio import strict_json_loads


class CursorReadError(Exception):
    def __init__(self,reason):
        allowed={'cursor_login_missing','cursor_login_expired','cursor_login_invalid',
                 'provider_rate_limited','provider_unavailable','invalid_usage'}
        self.reason=reason if reason in allowed else 'provider_unavailable'
        super().__init__(self.reason)


def keychain_token():
    # Run native Keychain access in a bounded reader-owned child, never a shell.
    from sources_transport import bounded_command, cli_environment
    raw=bounded_command([sys.executable,'-I','-B',str(Path(__file__).with_name('cursor_keychain.py'))],
                        limit=64*1024,seconds=2,env=cli_environment())
    if not raw:raise FileNotFoundError()
    return raw.decode('utf-8')


def jwt_identity(token,now):
    try:
        if (not isinstance(token,str) or len(token)>64*1024 or
                not re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',token)):raise ValueError()
        payload=token.split('.')[1]
        value=strict_json_loads(base64.urlsafe_b64decode(payload+'='*(-len(payload)%4)),64*1024,max_depth=8)
        sub=value['sub'];expires=value['exp']
        if not isinstance(sub,str) or not re.fullmatch(r'[A-Za-z0-9_|-]{1,256}',sub):raise ValueError()
        if type(expires) not in (int,float) or not math.isfinite(expires):raise ValueError()
        if expires<=now.timestamp():raise CursorReadError('cursor_login_expired')
        return sub
    except CursorReadError:raise
    except Exception:raise CursorReadError('cursor_login_invalid') from None


def credential(home,now,*,platform=None,environ=None,keychain=None):
    home=Path(home);platform=platform or sys.platform;env=os.environ if environ is None else environ
    config=Path(env.get('XDG_CONFIG_HOME') or home/'.config')
    if not config.is_absolute():config=home/'.config'
    raw=None;invalid=False
    if platform=='darwin':
        try:raw=(keychain or keychain_token)()
        except FileNotFoundError:pass
        except Exception:invalid=True
    else:
        try:
            owned_root(config/'cursor')
            raw=json_file(config/'cursor/auth.json',64*1024,private=True)['accessToken']
        except FileNotFoundError:pass
        except Exception:invalid=True
    expired=False
    if raw is not None:
        try:
            jwt_identity(raw,now)
            return raw
        except CursorReadError as error:
            # An old CLI sign-in must not hide a current IDE one: try the IDE next.
            if error.reason!='cursor_login_expired':raise
            raw=None;expired=True
    path=(home/'Library/Application Support/Cursor' if platform=='darwin' else config/'Cursor')/'User/globalStorage/state.vscdb'
    connection=None
    try:
        owned_root(path.parent)
        info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o022:raise ValueError()
        # Immutable prevents sidecars/checkpoints/writes; WAL lag is a documented gap.
        connection=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True,timeout=.2)
        deadline=time.monotonic()+.2
        connection.set_progress_handler(lambda: int(time.monotonic()>deadline),100)
        connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH,64*1024)
        result=connection.execute('SELECT value FROM ItemTable WHERE key = ? LIMIT 1',('cursorAuth/accessToken',)).fetchone()
        if result is None:raise FileNotFoundError()
        raw=result[0]
        # JSON-encoded strings occur in VS Code's storage; no other keys are read.
        if isinstance(raw,str) and raw.startswith('"'):raw=strict_json_loads(raw,64*1024,max_depth=2)
        if isinstance(raw,str) and raw.startswith('cursor-safe-storage:v1:'):raise ValueError()
        jwt_identity(raw,now)
        return raw
    except FileNotFoundError:
        raise CursorReadError('cursor_login_expired' if expired else 'cursor_login_invalid' if invalid else 'cursor_login_missing') from None
    except CursorReadError:raise
    except Exception:raise CursorReadError('cursor_login_invalid') from None
    finally:
        raw=None
        if connection is not None:connection.close()


def fetch_usage(home,now):
    token=credential(home,now)
    connection=http.client.HTTPSConnection('cursor.com',timeout=8)
    try:
        # `sub` is `<provider>|<user id>`; the dashboard cookie wants the user id alone.
        user=jwt_identity(token,now).split('|')[-1]
        if not user:raise CursorReadError('cursor_login_invalid')
        with IODeadline(connection,8) as budget:
            connection.connect();budget.connected()
            connection.request('GET','/api/usage-summary',headers={'Cookie':'WorkosCursorSessionToken='+quote(user,safe='')+'%3A%3A'+token,
                               'Accept':'application/json'})
            response=connection.getresponse()
            if response.status==401:raise CursorReadError('cursor_login_expired')
            if response.status==429:raise CursorReadError('provider_rate_limited')
            if response.status!=200:raise CursorReadError('provider_unavailable')
            raw=response.read(128*1024+1);budget.check()
            return strict_json_loads(raw,128*1024,max_depth=16)
    except CursorReadError:raise
    except Exception:raise CursorReadError('provider_unavailable') from None
    finally:
        token=None
        try:connection.close()
        except Exception:pass


def usage_provider(value,checked):
    try:
        plan=value['individualUsage']['plan'];reset=value['billingCycleEnd'];stamp(reset)
        def number(v):
            if type(v) not in (int,float) or not math.isfinite(v) or v<0:raise ValueError()
            return v
        if not isinstance(plan,dict) or plan.get('enabled') is False:raise ValueError()
        if plan.get('totalPercentUsed') is not None:used=number(plan['totalPercentUsed'])
        else:
            limit=number(plan['limit'])
            if limit<=0:raise ValueError()
            amount=plan.get('used');remaining=plan.get('remaining')
            if amount is None:amount=limit-number(remaining)
            amount=number(amount)
            # Past the plan, `remaining` stays at 0 while `used` keeps growing: consistent, not invalid.
            if (remaining is not None and not math.isclose(amount+number(remaining),limit,rel_tol=1e-6,abs_tol=.01)
                    and not (amount>=limit and number(remaining)==0)):raise ValueError()
            used=100*amount/limit
        used=min(100.0,used)  # over the plan reads as 0% left
        return {'driver':'cursor','instanceId':'cursor-local','installed':True,'enabled':True,
                'usageLimits':{'checkedAt':checked,'windows':[{'id':'month','label':'Month','usedPercent':used,
                    'resetsAt':reset,'windowDurationMins':43200}]}}
    except Exception:raise CursorReadError('invalid_usage') from None


ACTIVITY={'postToolUse','postToolUseFailure','afterShellExecution','afterMCPExecution',
          'afterFileEdit','afterAgentResponse','afterAgentThought'}


def project_events(events,source,now,settings):
    rows={};generations={};parents={};unknown=False
    for event in events:
        try:
            when=event['timestamp']
            if not 0<=(now-stamp(when)).total_seconds()<=7*86400:continue
            session=event['conversation_id'];generation=event.get('generation_id');kind=event['event']
            if not isinstance(session,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',session):continue
            child=event.get('subagent_id')
            if child is not None and (not isinstance(child,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',child)):continue
            identity=session if not child else session+'/'+child
            if kind=='subagentStart':
                # Only explicit parent_conversation_id; never recency/path inference.
                parents[identity]=event.get('parent_conversation_id')
                continue  # permission boundary does not prove execution
            if kind=='beforeSubmitPrompt':
                rows.pop(identity,None);generations[identity]=generation
            elif kind in ACTIVITY:
                if generation is None:unknown=True;continue
                row=rows.get(identity)
                if row is None or generations.get(identity)!=generation:
                    row=native_row(identity,event.get('project'),'Cursor session','cursor',when,parent=parents.get(identity))
                    row['runId']=generation;rows[identity]=row;generations[identity]=generation
                row['lastActivityAt']=when
            elif kind in ('stop','subagentStop','sessionEnd'):
                if kind=='subagentStop' and not child:unknown=True;continue
                if kind=='sessionEnd' or generation is None or generations.get(identity)==generation:
                    rows.pop(identity,None)
                if kind=='sessionEnd':
                    # A session's sub-agents end with it, whether or not lineage was proven.
                    for key in list(rows):
                        if rows[key]['parentId']==session or key.startswith(session+'/'):rows.pop(key)
        except (ValueError,TypeError,KeyError):continue
    data,rows,modes=project_rows(rows,source,now,settings)
    if unknown or any(mode is None for mode in modes.values()):data['warnings'].append('stale_source')
    return data,rows,modes


class CursorAdapter:
    identity=None
    potential_capabilities=dict(LOCAL_FLAGS,lineage=False)
    coverage=dict(LOCAL_COVERAGE,lineage='unsupported')

    def configure(self,value):return binding(value)

    def configuration_schema(self):
        return {'version':1,'harness':'cursor','available':True,'modes':['hooks'],
                'capabilities':dict(self.potential_capabilities),
                'requirements':['cursor_hooks_opt_in','cursor_usage_opt_in']}

    def read(self,service,now,settings,caches,force=False):
        at=now.isoformat();home=service.policy['home'];journal=service.journal()
        rows=modes=None
        try:
            events=[];found=False
            for suffix in ('.1',''):
                try:events.extend(json_lines(read_owned(service.store.directory/('cursor-'+service.source_id+'.jsonl'+suffix),1280*1024,private=True,tail=True)));found=True
                except FileNotFoundError:pass
            data,rows,modes=project_events(events,service.source_id,now,settings)
            if found:agents=outcome('ok' if data['projects'] or data['ended'] else 'quiet',at,at,data=data)
            else:
                agents=outcome('unavailable',at,reason='local_data_missing')
                rows=modes=None
        except Exception:agents=outcome('unavailable',at,reason='invalid_source')
        poll=journal.get('cursorPoll',{})
        try:due=now>=stamp(poll['nextAt'])
        except (ValueError,TypeError,KeyError):due=True
        monotonic=getattr(service,'monotonic',time.monotonic)
        due=due and monotonic()>=getattr(service,'cursor_next_poll',0)
        if not due:
            limits=copy.deepcopy(getattr(service,'cursor_result',None) or caches.get('cursor'))
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
            service.cursor_next_poll=monotonic()+300
            service.mutate_journal(lambda state:state.update(cursorPoll=marker))
            try:
                value=getattr(service,'usage_fetcher',fetch_usage)(home,now)
                checked=service.clock().isoformat()
                provider=usage_provider(value,checked)
                warnings=[]
                limits=service.provider_limits('cursor',[provider],at,now,{},True,warnings)
                limits['warnings']=warnings
                marker.update(failures=0,reason=None)
            except CursorReadError as error:
                limits=outcome('unavailable',at,reason=error.reason)
                failures=min(failures+1,6)
                delay=min(3600,300*2**failures) if error.reason in ('provider_rate_limited','provider_unavailable','cursor_login_expired') else 300
                marker.update(nextAt=(now+timedelta(seconds=delay)).isoformat(),failures=failures,reason=error.reason)
                service.cursor_next_poll=monotonic()+delay
            except Exception:
                limits=outcome('unavailable',at,reason='invalid_usage');marker.update(reason='invalid_usage')
            service.mutate_journal(lambda state:state.update(cursorPoll=marker))
            service.cursor_result=copy.deepcopy(limits)
        limits.setdefault('warnings',[])
        return {'agents':agents,'limits':{'cursor':limits},'rows':rows,'modes':modes,
                'icon_sources':{},'success':True}
