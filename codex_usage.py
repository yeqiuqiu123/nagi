"""Opt-in Codex sign-in/usage reader. Credential material never leaves this module."""
import base64
import copy
import hashlib
import hmac
import http.client
import math
import os
import secrets
import stat
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agents_projection import stamp
from agents_service import outcome
from claude_source import expire_windows
from local_sources import opaque
from sources_transport import valid_token
from t3_reader import IODeadline
from jsonio import strict_json_loads


class CodexReadError(Exception):
    def __init__(self, reason):
        allowed={'codex_login_missing','codex_login_expired','codex_login_invalid',
                 'codex_account_changed','provider_rate_limited','provider_unavailable','invalid_usage'}
        self.reason=reason if reason in allowed else 'provider_unavailable'
        super().__init__(self.reason)


def codex_home(home):
    value=os.environ.get('CODEX_HOME')
    root=Path(value) if value else Path(home)/'.codex'
    if not root.is_absolute() or '..' in root.parts:raise ValueError('Invalid Codex home')
    return root


def open_root(root):
    # Walk every component through a no-follow directory fd, closing the
    # lstat/open ancestor race as well as refusing a final symlink.
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in Path(root).parts[1:]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=child
        if os.fstat(fd).st_uid!=os.getuid():raise ValueError('Unsafe Codex home')
        return fd
    except BaseException:
        os.close(fd)
        raise


def fingerprint(root_info, info):
    if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:
        raise ValueError('Unsafe Codex login')
    return (root_info.st_dev,root_info.st_ino,info.st_dev,info.st_ino,
            info.st_size,info.st_mtime_ns,info.st_ctime_ns)


@dataclass(repr=False)
class Login:
    root: Path
    token: str = field(repr=False)
    account: str = field(repr=False)
    changed_at: float
    generation: tuple


def credential(home, now):
    try:
        root=codex_home(home);fd=open_root(root)
        try:
            root_info=os.fstat(fd)
            with os.fdopen(os.open('auth.json',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd),'rb') as stream:
                info=os.fstat(stream.fileno());generation=fingerprint(root_info,info)
                raw=stream.read(64*1024+1)
                if fingerprint(root_info,os.fstat(stream.fileno()))!=generation:
                    raise CodexReadError('codex_account_changed')
        finally:os.close(fd)
        value=strict_json_loads(raw,64*1024,max_depth=8)
        tokens=value['tokens'];token=tokens['access_token'];account=tokens['account_id']
        refreshed=stamp(value['last_refresh']).timestamp() if value.get('last_refresh') is not None else 0
        if (not valid_token(token) or not isinstance(account,str) or not 0<len(account)<=256
                or not all(33<=ord(c)<=126 for c in account) or refreshed>now.timestamp()+5):raise ValueError()
        # Decode only exp. These local claims are not identity attestation, and
        # are never used to find emails, titles, account ids or refresh authority.
        parts=token.split('.')
        if len(parts)!=3:raise ValueError()
        payload=base64.b64decode(parts[1]+'='*(-len(parts[1])%4),altchars=b'-_',validate=True)
        claims=strict_json_loads(payload,32*1024,max_depth=8);expires=claims['exp']
        if type(expires) not in (int,float) or not math.isfinite(expires):raise ValueError()
        if expires<=now.timestamp():raise CodexReadError('codex_login_expired')
        return Login(root,token,account,max(info.st_mtime,info.st_ctime,refreshed),generation)
    except FileNotFoundError:raise CodexReadError('codex_login_missing') from None
    except CodexReadError:raise
    except Exception:raise CodexReadError('codex_login_invalid') from None


def unchanged(login):
    try:
        fd=open_root(login.root)
        try:
            info=os.stat('auth.json',dir_fd=fd,follow_symlinks=False)
            return fingerprint(os.fstat(fd),info)==login.generation
        finally:os.close(fd)
    except Exception:return False


def account_key(store, account):
    name='nagi-codex-identity.json'
    def validate(value):
        if (not isinstance(value,dict) or set(value)!={'salt'} or not isinstance(value['salt'],str)
                or len(value['salt'])!=64 or any(c not in '0123456789abcdef' for c in value['salt'])):raise ValueError()
        return value
    value=store.read(name,None)
    if value is None:
        def create(current):
            validate(current)
            return current
        value=store.mutate(name,{'salt':secrets.token_hex(32)},create)
    validate(value)
    return hmac.new(bytes.fromhex(value['salt']),account.encode(),hashlib.sha256).hexdigest()


def usage_windows(value, now):
    """Project only the two included-usage windows; never return provider text."""
    try:
        if not isinstance(value,dict) or 'rate_limit' not in value:raise ValueError()
        rate=value['rate_limit']
        if rate is None:return []
        if not isinstance(rate,dict):raise ValueError()
        windows=[]
        for key in ('primary','secondary'):
            window=rate.get(key+'_window')
            if window is None:continue
            if not isinstance(window,dict):raise ValueError()
            used=window['used_percent'];seconds=window['limit_window_seconds'];reset=window['reset_at']
            if any(type(n) not in (int,float) or not math.isfinite(n) for n in (used,seconds,reset)):
                raise ValueError()
            if not 0<=used<=100 or seconds<=0:raise ValueError()
            resets=datetime.fromtimestamp(reset,timezone.utc)
            if resets<=now:continue
            minutes=seconds/60
            kind='five_hour' if minutes==300 else 'weekly' if minutes==10080 else 'monthly' if minutes>=43200 else 'other'
            windows.append({'id':key,'label':'Session' if key=='primary' else 'Weekly' if kind=='weekly' else 'Secondary',
                            'kind':kind,'remainingPercent':round(100-used,2),'resetsAt':resets.isoformat(),
                            'checkedAt':now.isoformat()})
        return windows
    except Exception:raise CodexReadError('invalid_usage') from None


def fetch_usage(login, now):
    connection=None
    try:
        connection=http.client.HTTPSConnection('chatgpt.com',timeout=8)
        # http.client ignores proxy env; a fixed host/path and no redirect
        # handler ensure credentials only go to the intended OpenAI endpoint.
        with IODeadline(connection,8) as budget:
            connection.connect();budget.connected()
            connection.request('GET','/backend-api/wham/usage',headers={
                'Authorization':'Bearer '+login.token,'ChatGPT-Account-Id':login.account,
                'Accept':'application/json','User-Agent':'codex-cli'})
            response=connection.getresponse()
            if response.status==401:raise CodexReadError('codex_login_expired')
            if response.status==429:raise CodexReadError('provider_rate_limited')
            if response.status!=200:raise CodexReadError('provider_unavailable')
            raw=response.read(128*1024+1);budget.check()
            try:value=strict_json_loads(raw,128*1024,max_depth=16)
            except Exception:raise CodexReadError('invalid_usage') from None
            if isinstance(value,dict) and value.get('account_id') not in (None,login.account):
                raise CodexReadError('codex_account_changed')
            return usage_windows(value,now)
    except CodexReadError:raise
    except Exception:raise CodexReadError('provider_unavailable') from None
    finally:
        if connection is not None:
            try:connection.close()
            except Exception:pass


def limits_outcome(windows, identity, now):
    at=now.isoformat()
    if not windows:return outcome('unavailable',at,reason='windows_missing')
    checked=min(w['checkedAt'] for w in windows)
    return outcome('ok',at,checked,data={'accounts':[{'id':identity,'label':'Codex 1','windows':windows,
                                                    'status':'ok','checkedAt':checked,'reason':None}]})


def retire_account(service, identity):
    # Retire old pending account alerts too; they must not survive a sign-in
    # change merely because their reset time is still in the future.
    def retire(state):
        state['events']=[e for e in state.get('events',[]) if e['kind']!='low_limit' or e['provider']!='codex'
                         or e['accountId']==identity]
        cache=state.get('cache',{}).get('codex')
        if cache and any(a['id']!=identity for a in (cache.get('data') or {}).get('accounts',[])):
            state['cache'].pop('codex',None)
    service.mutate_journal(retire)


def same_account(service, login, identity, now):
    """True when auth.json is untouched or was rewritten for the same account (a token
    refresh); False for another account; None when it can't be read right now."""
    if unchanged(login):return True
    try:again=credential(service.policy['home'],now)
    except Exception:return None
    return account_key(service.store,again.account)==identity


def read_limits(service, now, fallback):
    """Return sanitized limits. fallback(opaque_id, changed_at, account) reads rollouts only."""
    at=now.isoformat()
    if service.policy.get('usageOptIn') is not True:
        return outcome('unavailable',at,reason='codex_usage_opt_in')
    try:
        login=credential(service.policy['home'],now)
        identity=account_key(service.store,login.account)
        generation=opaque(login.generation)
        service.codex_account_key=identity
        retire_account(service,identity)
        poll=service.journal().get('codexPoll',{})
        try:due=now>=stamp(poll['nextAt'])
        except (ValueError,TypeError,KeyError):due=True
        monotonic=getattr(service,'monotonic',time.monotonic)
        due=due and monotonic()>=getattr(service,'codex_next_poll',0)
        # A refresh rewrites auth.json for the same account: that is still the same account.
        same=poll.get('accountKey')==identity
        if due:
            failures=poll.get('failures',0)
            failures=min(max(failures,0),6) if type(failures) is int else 0
            # Attempt first: force, restart or changing sign-ins cannot bypass
            # the provider's poll floor or exponential outage backoff.
            marker={'nextAt':(now+timedelta(seconds=300)).isoformat(),'failures':failures,'reason':'checking',
                    'accountKey':identity,'generation':generation}
            service.codex_next_poll=monotonic()+300
            service.mutate_journal(lambda state:state.update(codexPoll=marker))
            try:
                windows=getattr(service,'codex_usage_fetcher',fetch_usage)(login,now)
                result=limits_outcome(windows,identity,now)
                marker.update(failures=0,reason=None)
            except CodexReadError as error:
                result=outcome('unavailable',at,reason=error.reason)
                failures=min(failures+1,6)
                delay=min(3600,300*2**failures) if error.reason in ('provider_rate_limited','provider_unavailable') else 300
                marker.update(nextAt=(now+timedelta(seconds=delay)).isoformat(),failures=failures,reason=error.reason)
                service.codex_next_poll=monotonic()+delay
            except Exception:
                result=outcome('unavailable',at,reason='invalid_usage');marker.update(reason='invalid_usage')
            if same_account(service,login,identity,now) is False:
                result=outcome('unavailable',at,reason='codex_account_changed')
                marker.update(reason='codex_account_changed')
            service.mutate_journal(lambda state:state.update(codexPoll=marker))
            # Memory cache contains only DTOs. Durable successful cache is
            # written by the normal AgentsService record path.
            service.codex_result=copy.deepcopy(result)
            poll=marker;same=True
        elif same:
            result=copy.deepcopy(getattr(service,'codex_result',None) or service.journal().get('cache',{}).get('codex'))
            if poll.get('reason') or result is None:
                result=outcome('unavailable',at,reason=poll.get('reason') or 'checking')
            elif result.get('checkedAt') and (now-stamp(result['checkedAt'])).total_seconds()>900:
                result=outcome('unavailable',at,reason='stale_source')
            elif result.get('data'):result=expire_windows(result,now,at)
        else:result=outcome('unavailable',at,reason='codex_account_changed')
        if result['reason'] in ('provider_unavailable','provider_rate_limited') and same:
            replacement=fallback(identity,login.changed_at,login.account)
            if replacement['status']=='ok':
                replacement.setdefault('warnings',[]).append(result['reason'])
            result=replacement
        check=same_account(service,login,identity,now)
        if check is None:
            # Mid-rewrite: say so, keep this account's pending alerts.
            return outcome('unavailable',at,reason='checking')
        if check is False or result['reason']=='codex_account_changed':
            service.codex_account_key=None
            retire_account(service,None)
            return outcome('unavailable',at,reason='codex_account_changed')
        return result
    except CodexReadError as error:
        # A missing or expired sign-in says nothing about which account comes next: hold the
        # pending alerts (undelivered while the key is unknown) instead of deleting them.
        service.codex_account_key=None
        return outcome('unavailable',at,reason=error.reason)
    except Exception:
        service.codex_account_key=None
        return outcome('unavailable',at,reason='codex_login_invalid')
