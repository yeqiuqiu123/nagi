"""Compact, owner-local snapshot for terminal clients."""
from agents_projection import stamp
from ci_service import failed_repos

STATUS_PATH = '/api/sources/v1/status'


def agent_counts(sources):
    totals = None
    partial = False
    environments = set()
    local_t3 = any(s['source']['harness']=='t3' and s['source']['placement']=='local'
                   and s['agents']['status'] in ('ok', 'quiet') for s in sources)
    for source in sources:
        value = source['agents']
        if value['status'] not in ('ok', 'quiet') or not value['data']:
            partial = True
            continue
        data = value['data']
        environment = data['environmentId']
        # Cursor's passive hooks cannot reliably distinguish T3-hosted runs.
        if environment in environments or (local_t3 and source['source']['harness']=='cursor'):
            partial = True
            continue
        environments.add(environment)
        partial |= bool(data.get('omittedRows') or set(data.get('warnings', ())) & {'coverage_incomplete', 'stale_source'})
        counts = data['counts']
        if totals is None:
            totals = dict.fromkeys(('running', 'waitingOnYou', 'stuck'), 0)
        for key in totals:
            totals[key] += counts[key]
    return totals, partial


def claude_percent(sources, now):
    readings = []
    direct = False
    for source in sources:
        limits = source['limits'].get('claude')
        if not limits or limits['status'] != 'ok' or not limits.get('checkedAt'):
            continue
        if not -5 <= (now - stamp(limits['checkedAt'])).total_seconds() <= 900:
            continue
        local = source['source']['placement'] in ('local', 'this_computer')
        harness = source['source']['harness']
        accounts = limits['data']['accounts']
        direct |= local and harness=='claude' and bool(accounts)
        for account in accounts:
            valid = [window['remainingPercent'] for window in account['windows']
                     if stamp(window['resetsAt']) > now
                     and -5 <= (now - stamp(window['checkedAt'])).total_seconds() <= 900]
            # Keep an unreadable account in the count. It prevents an apparently
            # singular percentage when several accounts are actually present.
            value = min(valid) if valid and account.get('status', 'ok')=='ok' else None
            readings.append((harness, local, value))
    values = [value for harness, local, value in readings if not (direct and local and harness=='t3')]
    return values[0] if len(values)==1 else None


def ci_summary(ci):
    failed = failed_repos(ci)
    data = ci['data']
    if failed:
        state = 'failed'
    elif ci['reason']=='disabled':
        state = 'disabled'
    elif ci['status']=='quiet' or (ci['status']=='ok' and data and not data['omitted']
                                  and all(row['ci']['status']=='ok' for row in data['rows'])):
        state = 'ok'
    else:
        state = 'unknown'
    return {'state':state, 'failedRepos':failed}


def reader_status(service):
    sources = service.read_sources()['sources']
    counts, partial = agent_counts(sources)
    percent = claude_percent(sources, service.clock())
    ci = ci_summary(service.ci.read())
    threshold = service.legacy.settings()['limitAlertPercent']
    alerts = []
    if counts and counts['waitingOnYou']:
        alerts.append('asks-you')
    if counts and counts['stuck']:
        alerts.append('stuck')
    if ci['state']=='failed':
        alerts.append('ci-failed')
    if percent is not None and threshold!='off' and percent <= threshold:
        alerts.append('low-limit')
    return {'version':1, 'agents':counts, 'partial':partial, 'ci':ci,
            'claudeRemainingPercent':percent, 'alerts':alerts, 'machine':service.machine.read()}
