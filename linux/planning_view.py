"""Pure frontend projection shared by the generic tray and native link policy.
No service, browser, GI import, or filesystem access occurs on import.
"""
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

VN = timezone(timedelta(hours=7))
LABELS = {'active': 'Working', 'verification': 'Verifying', 'blocked': 'Blocked', 'awaiting_user': 'Needs you', 'completed': 'Done', 'complete': 'Complete', 'rest': 'Rest', 'skipped': 'Skipped', 'waiting': 'Waiting'}


def stamp(value):
    try:
        d = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if d.tzinfo is None:
            d = d.replace(tzinfo=VN)
        return d.timestamp()
    except (ValueError, TypeError, AttributeError):
        return float('-inf')


def local_day(now):
    return datetime.fromtimestamp(now, VN).date().isoformat()


def safe_source(url):
    if not isinstance(url, str) or re.search(r'[\s\\]', url):
        return None
    try:
        u = urlsplit(url)
        return url if (u.scheme == 'https' and u.hostname and not u.username and not u.password and not u.fragment and u.hostname not in ('localhost', '127.0.0.1', '::1')) else None
    except ValueError:
        return None


def current_lesson(c):
    if not c:
        return None
    if c.get('source') is not None:
        return conversation_source(c['source'])
    b = next((b for b in c.get('books', []) if b['id'] == c.get('currentBookId') and b['status'] == 'current'), None)
    return conversation_source(b.get('source')) if b and stamp(b.get('verifiedAt')) <= stamp(c.get('updatedAt')) else None


def conversation_source(uri):
    uuid = r'[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}'
    pattern = r'https://chatgpt\.com/(?:g/[A-Za-z0-9][A-Za-z0-9_-]{0,127}/)?c/'+uuid+r'(?:\?messageId='+uuid+r')?'
    return uri if safe_source(uri) and re.fullmatch(pattern, uri) else None


def allowed_external(uri, user_gesture):
    return bool(user_gesture and conversation_source(uri))


def open_external(uri, user_gesture, opener):
    if not allowed_external(uri, user_gesture):
        return False
    opener(uri)
    return True


def loopback_origin(port=47831):
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('Port must be an integer from 1 to 65535')
    return 'http://127.0.0.1:'+str(port)


def record_target(record_id, compact=False, port=47831):
    if not isinstance(record_id, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', record_id):
        return None
    return loopback_origin(port)+'/' + ('?widget=1&compact=1' if compact else '') + '#next=' + record_id


def lesson_action(uri, opener):
    """Bind one exact URI now; launch only when a GTK activation invokes it."""
    def activate(_item=None):
        return open_external(uri, True, opener)
    return activate


def today_quests(snapshot, summary, quests, now):
    return {q['curriculumId']: q['status'] for q in quests or [] if q['day'] == local_day(now) and float('-inf') < stamp(q.get('at')) <= now and local_day(stamp(q.get('at'))) == q['day']}


def age_freshness(at, seconds, now):
    value = stamp(at)
    if value == float('-inf'):
        return 'unknown'
    if value > now:
        return 'clock_skew'
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', at):
        return 'unknown'
    return 'fresh' if now-value < seconds else 'stale'


def planning(snapshot, summary, quests, now, offline=False):
    today = today_quests(snapshot, summary, quests, now)
    dedup = {}
    for r in snapshot.get('upNext', []):
        key = (r['owner'], r['kind'], r.get('relatedId'), ' '.join(r['title'].strip().lower().split()))
        old = dedup.get(key)
        if old is None or stamp(r['updatedAt']) > stamp(old['updatedAt']) or (stamp(r['updatedAt']) == stamp(old['updatedAt']) and r['id'] < old['id']):
            dedup[key] = r

    def expired(x):
        return bool(x) and stamp(x) + (86400 if re.fullmatch(r'\d{4}-\d{2}-\d{2}', x) else 0) <= now

    def project(r):
        p = {**r, 'bucket': 'update', 'reason': 'Availability unknown', 'lesson': None, 'currentAction': r['nextAction'], 'currentCheckpoint': r['checkpoint'], 'currentTitle': r['title']}
        def result(bucket=None, reason=None):
            if bucket:
                p['bucket'] = bucket
            if reason:
                p['reason'] = reason
            return p
        t = next((t for t in snapshot['tasks'] if t['id'] == r.get('relatedId')), None)
        c = next((c for c in snapshot['curricula'] if c['id'] == r.get('relatedId')), None)
        p['lesson'] = current_lesson(c)
        if r['state'] == 'needs_approval':
            if t and t['status'] == 'completed' and stamp(t['updatedAt']) > stamp(r['updatedAt']):
                return result('history', 'Earlier than the reported outcome')
            return result('needs', 'Decision needed · display only')
        if expired(r.get('deadline')) or expired(r.get('scheduledFor')):
            return result(reason='Needs an update · reported date has passed')
        if r.get('relatedId') is None and r['kind'] in ('project', 'study'):
            if r['state'] in ('waiting', 'blocked'):
                return result('waiting', LABELS[r['state']])
            if r['state'] == 'scheduled' and r.get('scheduledFor'):
                return result('scheduled', 'Scheduled')
            return p
        if r['kind'] == 'project':
            if not t or t['status'] == 'unknown':
                return p
            if t['status'] == 'completed' and stamp(r['updatedAt']) <= stamp(t['updatedAt']):
                return result('history', 'Earlier than the reported outcome')
            if t['status'] in ('blocked', 'awaiting_user'):
                return result('waiting', LABELS[t['status']])
        elif r['kind'] == 'study':
            if not c:
                return p
            p['lesson'] = current_lesson(c)
            if stamp(r['updatedAt']) < stamp(c['updatedAt']):
                p.update(currentTitle=c['title']+' · last known lesson', currentAction=c['nextLesson'], currentCheckpoint=c['checkpoint'])
                if not p['lesson'] or not c.get('nextLesson') or c['nextLesson'].lower() == 'unknown':
                    return result(reason='Needs an update · current lesson unavailable')
            if r['state'] == 'ready' and today.get(c['id']) in ('complete', 'rest', 'skipped'):
                return result('optional', 'Optional · today is '+LABELS[today[c['id']]].lower())
            if r['state'] == 'ready' and (stamp(r['updatedAt']) == float('-inf') or local_day(stamp(r['updatedAt'])) != local_day(now)):
                return result(reason='Needs an update · recommendation is from another day')
        else:
            return p
        if r['state'] in ('waiting', 'blocked'):
            return result('waiting', LABELS[r['state']])
        if r['state'] == 'scheduled' and r.get('scheduledFor'):
            return result('scheduled', 'Scheduled')
        if r['state'] == 'ready' and (p['lesson'] if r['kind'] == 'study' else safe_source(r.get('source'))):
            return result('ready', 'Ready')
        return result(reason='Needs an update · source or availability unknown')

    def derive(r):
        related = next((t for t in snapshot['tasks']+snapshot['curricula'] if t['id'] == r.get('relatedId')), None)
        seconds = snapshot['staleAfterMinutes']*60
        row_age = age_freshness(r.get('updatedAt'), seconds, now)
        related_age = age_freshness(related.get('updatedAt'), seconds, now) if related else 'fresh' if r.get('relatedId') is None else 'unknown'
        related_known = not related or related.get('status') != 'unknown' and ('books' not in related or bool(related.get('nextLesson') and related['nextLesson'].lower() != 'unknown' and any(b['id'] == related.get('currentBookId') and b['status'] == 'current' for b in related['books'])))
        current = not offline and age_freshness(snapshot.get('sourceAt'), seconds, now) == 'fresh' and row_age == related_age == 'fresh' and related_known
        p = {**r, 'recommendationFreshness': row_age, 'relatedFreshness': related_age, 'canNavigate': bool(r['lesson'] or safe_source(r.get('source'))), 'recommendable': current and not r['dependencies'] and r['bucket'] in ('ready', 'optional'), 'executable': False, 'actionable': False, 'lastKnown': not current, 'approvalCurrent': r['bucket'] == 'needs' and current}
        if r['bucket'] == 'needs' and not current:
            p.update(bucket='previous', reason='Previously waiting · check current status')
        elif r['bucket'] in ('ready', 'optional', 'scheduled') and (not current or r['dependencies']):
            p.update(bucket='update', reason='Check dependencies' if r['dependencies'] else 'Last known lesson' if r['lesson'] else 'Reported state')
        return p

    order = {k: i for i, k in enumerate(('needs', 'ready', 'scheduled', 'waiting', 'optional', 'previous', 'update', 'history'))}
    return sorted((derive(project(r)) for r in dedup.values()), key=lambda p: (order[p['bucket']], stamp(p['scheduledFor']) if p['bucket'] == 'scheduled' else -stamp(p['updatedAt']), p['id']))
