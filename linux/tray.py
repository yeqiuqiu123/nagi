#!/usr/bin/env python3
"""Linux Nagi tray: one Quick glance and native failed/stuck banners.

Importing this module is pure. The label and tooltip below mirror
web/glance-model.js and are checked against tests/tray-label-cases.json.
"""
import argparse
from datetime import datetime, timezone
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

PROVIDERS=('codex','claude','cursor')
POLL_SECONDS=20


def launch_local(uri, origin, opener, report):
    from owner_auth import launch_url
    try:
        opener(launch_url(origin, uri[len(origin):]))
        return True
    except Exception:
        report('Nagi could not open. Check that its local reader is running, then try again.')
        return False


def agents_mode(agents):
    status=agents.get('status') if isinstance(agents,dict) else None
    if status in ('ok','quiet'):return 'live'
    if status=='last_known' and agents.get('data'):return 'dated'
    if status in ('not_set_up','unsupported'):return status
    if status=='unavailable' and agents.get('reason')=='checking':return 'checking'
    return 'never'


def _when(iso):
    try:return datetime.fromisoformat(iso.replace('Z','+00:00'))
    except (AttributeError,TypeError,ValueError):return None


def fresh_empty(limits, now=None):
    """The account with a window at 0, only from a fresh ok account and an unexpired window."""
    now=now or datetime.now(timezone.utc)
    providers=(limits or {}).get('providers') or {}
    for key in PROVIDERS:
        source=providers.get(key)
        if not isinstance(source,dict) or source.get('status')!='ok' or not source.get('data'):continue
        for account in source['data'].get('accounts') or []:
            if account.get('status','ok')!='ok':continue
            for window in (account.get('windows') or [])+(account.get('secondaryWindows') or []):
                reset=_when(window.get('resetsAt'))
                if isinstance(window.get('remainingPercent'),(int,float)) and window['remainingPercent']<=0 and reset and reset>now:
                    return account,window
    return None


def dated_limits(limits):
    """The oldest check time behind any retained (last-known) quota, or None."""
    providers=(limits or {}).get('providers') or {}
    oldest=None
    for key in PROVIDERS:
        source=providers.get(key)
        if not isinstance(source,dict) or not source.get('data'):continue
        stamps=[source.get('checkedAt')] if source.get('status')=='last_known' else []
        stamps+=[a.get('checkedAt') for a in source['data'].get('accounts') or [] if a.get('status')=='last_known']
        for at in filter(None,map(_when,stamps)):
            oldest=at if oldest is None or at<oldest else oldest
    return oldest


def tray_label(glance, limits, now=None):
    """`3`, `3 · ●`, `3 · ?`, `3 · empty`, `–` (can't reach), `·` (T3 Code not set up) or nothing.
    Unreachable replaces the count; then `?` outranks `●`, which outranks `empty`. One mark
    at a time; `empty` needs fresh, unexpired evidence."""
    agents=(glance or {}).get('agents')
    mode=agents_mode(agents)
    if mode=='checking':return ''
    if mode=='not_set_up':return '·'  # not a failure: no count, no dash
    if mode!='live':return '–'
    counts=(agents.get('data') or {}).get('counts') or {}
    mark='?' if counts.get('waitingOnYou',0)>0 else '●' if counts.get('stuck',0)>0 else 'empty' if fresh_empty(limits,now) else ''
    running=counts.get('running',0)
    return ' · '.join(part for part in (str(running) if running>0 else '',mark) if part)


def _local(iso):
    return datetime.fromisoformat(iso.replace('Z','+00:00')).astimezone()


def tray_tooltip(glance, limits, now=None):
    agents=(glance or {}).get('agents') or {}
    mode=agents_mode(agents)
    if mode=='checking':return 'Nagi · checking T3 Code…'
    if mode=='not_set_up':return "Nagi · T3 Code isn't connected on this computer"
    if mode!='live':
        since=agents.get('checkedAt') or agents.get('attemptedAt')
        try:return "Nagi · can't reach T3 Code since "+_local(since).strftime('%H:%M')
        except (AttributeError,TypeError,ValueError):return "Nagi · can't reach T3 Code"
    counts=(agents.get('data') or {}).get('counts') or {}
    text=f"Nagi · {counts.get('running',0)} running"
    if counts.get('waitingOnYou',0):text+=f" · {counts['waitingOnYou']} asks you"
    if counts.get('stuck',0):text+=f" · {counts['stuck']} stuck"
    found=fresh_empty(limits,now)
    if found:
        account,window=found
        try:text+=f" · {account.get('label')} is empty until "+_local(window['resetsAt']).strftime('%a %-d %b %H:%M')
        except (KeyError,TypeError,ValueError):text+=f" · {account.get('label')} is empty"
    dated=dated_limits(limits)
    if dated:text+=' · limits as of '+dated.astimezone().strftime('%H:%M')  # retained quota is dated, never live
    return text


def _source_view(env, source):
    glance={'version':2,'agents':source.get('agents'),'settings':env.get('settings'),'warnings':env.get('warnings',[])}
    return glance,{'providers':source.get('limits') or {}}


def sources_tooltip(env, now=None):
    """The tray's summary from the source envelope (API v1): one source reads exactly as before;
    several sum fresh, source-local counts only and say when some could not be read."""
    sources=(env or {}).get('sources') or []
    if not sources:return 'Nagi · nothing connected yet'
    if len(sources)==1:return tray_tooltip(*_source_view(env,sources[0]),now)
    live=[s for s in sources if agents_mode(s.get('agents'))=='live']
    if not live:return "Nagi · can't read your sources"
    total=lambda key:sum(((s['agents'].get('data') or {}).get('counts') or {}).get(key,0) for s in live)
    text=f"Nagi · {total('running')} running"
    if total('waitingOnYou'):text+=f" · {total('waitingOnYou')} asks you"
    if total('stuck'):text+=f" · {total('stuck')} stuck"
    if len(live)<len(sources):text+=f" · {len(sources)-len(live)} of {len(sources)} sources can't be read"
    return text


def read_state(origin, transport=None):
    """A native, owner-proved read of the source envelope (every source's agents and limits)."""
    from urllib.request import Request
    from jsonio import strict_json_loads
    if transport is None:
        from owner_auth import authenticated_open as transport
    with transport(Request(origin+'/api/sources/v1/glance'),timeout=5) as response:
        return strict_json_loads(response.read(8*1024*1024+1),8*1024*1024,max_depth=160)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=47831)
    args=parser.parse_args()
    from notifications import run
    return run(args.port)

if __name__=='__main__':sys.exit(main())
