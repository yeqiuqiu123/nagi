"""Owner-opted background CI reads and durable notifications."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
from os.path import isdir
import shutil
import threading
import time

from agents_projection import stamp
from agents_service import AgentsService, outcome
from ci_workspace import PREFERENCE, branch_name, env_path, repo_name, resolve_workspace
from github_ci import GitHub, GitHubError, SETUP_REASONS

CI_SOURCE_ID = 'github-ci'
MAX_PAIRS = 20
MAX_WORKSPACES = 80
MAX_ALERTS = 100_000
FAST, SLOW = 30, 120
RUNNING_DEPLOYS = {'queued', 'pending', 'in_progress', 'waiting'}
RETRY_REASONS = SETUP_REASONS | {'rate_limited', 'cannot_reach_github', 'invalid_response'}


def disabled(at):
    return outcome('not_set_up', at, reason='disabled')


def failure(reason, at, previous=None):
    status = 'not_set_up' if reason in SETUP_REASONS else 'unavailable'
    return outcome(status, at, (previous or {}).get('checkedAt'), reason)


def observe(at, data):
    return outcome('ok' if data is not None else 'quiet', at, at, data=data)


def failed_repos(value):
    return sorted({row['repo'] for row in ((value or {}).get('data') or {}).get('rows', [])
                   if row['ci']['status'] == 'ok' and row['ci']['data']['state'] == 'failed'})


def discover(candidates):
    grouped = {}
    resolved = {}
    omitted = False
    seen = 0
    for identity, mode, location in candidates:
        if isinstance(location, list) and len(location) == 2:
            repo, branch = location
            pair = (repo.lower(), branch) if repo_name(repo) and branch_name(branch) else None
        elif isinstance(location, tuple) and len(location) == 3:
            cwd, branch, root = location
            if any(v is not None and not isinstance(v, str) for v in location):
                omitted = True
                continue
            if cwd and cwd != root and branch and mode == 'ended':
                if not isdir(cwd):
                    cwd = root
            key = cwd, branch
            if key not in resolved:
                if len(resolved) >= MAX_WORKSPACES:
                    omitted = True
                    continue
                resolved[key] = resolve_workspace(cwd, branch)
            pair = resolved[key]
        else:
            omitted = True
            continue
        if pair is None:
            seen += 1
            continue
        if pair not in grouped and len(grouped) >= MAX_PAIRS:
            omitted = True
            continue
        agents = grouped.setdefault(pair, {})
        agents.setdefault(identity, mode)
    return grouped, omitted, seen


class CIService:
    def __init__(self, store, home, clock, candidates):
        self.store, self.home, self.clock, self.candidates = store, home, clock, candidates
        self.delivery = AgentsService(store.directory, clock=clock, source_id=CI_SOURCE_ID)
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='nagi-ci')
        self.future = None
        self.closed = False
        self.generation = 0
        self.due = 0
        self.failures = 0
        self.previous = {}
        try:
            self.enabled = self.preference(self.store.read(PREFERENCE, {'enabled':False}))
        except (OSError, ValueError, TypeError, AttributeError):
            self.enabled = False
        at = self.clock().isoformat()
        self.reset_snapshots(at)

    @staticmethod
    def preference(value):
        if not isinstance(value, dict) or set(value)!={'enabled'} or type(value['enabled']) is not bool:
            raise ValueError('Invalid GitHub CI preference')
        return value['enabled']

    def settings(self):
        with self.lock:
            return {'version': 1, 'enabled': self.enabled}

    def configure(self, enabled):
        with self.lock:
            if self.enabled != enabled:
                self.store.mutate(PREFERENCE, {'enabled':False}, lambda value: value.update(enabled=enabled),
                                  repair=True, validate=self.preference)
                self.enabled = enabled
                self.generation += 1
                self.due = 0
                self.failures = 0
                self.previous = {}
                at = self.clock().isoformat()
                self.reset_snapshots(at)
            return self.settings()

    def active(self, generation):
        with self.lock:
            return self.enabled and not self.closed and self.generation == generation

    def schedule(self):
        with self.lock:
            if (self.active(self.generation) and time.monotonic() >= self.due
                    and (self.future is None or self.future.done())):
                self.future = self.executor.submit(self.poll, self.generation, self.previous)

    def close(self, wait):
        with self.lock:
            self.closed = True
        self.executor.shutdown(wait=wait, cancel_futures=True)

    def reset_snapshots(self, at):
        self.snapshots = dict.fromkeys(('ci', 'pulls', 'ended'),
                                       failure('checking', at) if self.enabled else disabled(at))

    def read(self, kind='ci'):
        with self.lock:
            return self.snapshots[kind]

    def poll(self, generation, previous):
        started = time.monotonic()
        at = self.clock().isoformat()
        failures = []
        rows, ended_rows, alerts = [], [], []
        running = False
        try:
            if not shutil.which('gh', path=env_path()):
                raise GitHubError('gh_missing')
            candidates, incomplete = self.candidates()
            pairs, omitted, non_github = discover(candidates)
            partial = omitted or incomplete
            if pairs:
                github = GitHub(self.home, lambda: self.active(generation))
                ended_partial = partial
                with ThreadPoolExecutor(max_workers=4) as pool:
                    observed = pool.map(lambda item: self.read_pair(github, item, at, previous), pairs.items())
                    for row, sha, finished, finished_partial in observed:
                        rows.append(row)
                        ended_rows.extend(finished)
                        ended_partial |= finished_partial
                        for key in ('ci', 'deploy'):
                            if row[key]['reason'] in RETRY_REASONS:
                                failures.append(row[key]['reason'])
                        ci, deploy = row['ci']['data'] or {}, row['deploy']['data'] or {}
                        running |= (ci.get('state') == 'running' or ci.get('running', 0) > 0
                                    or deploy.get('state') in RUNNING_DEPLOYS)
                        if ci.get('state') == 'failed':
                            alerts.append((row['repo'], sha))
                    pulls, pull_failures = self.read_pulls(github, pool, pairs, partial, at)
                    failures.extend(pull_failures)
                result = {
                    'ci': observe(at, {'rows': rows, 'omitted': partial}),
                    'pulls': pulls,
                    'ended': self.ended_result(at, ended_rows, ended_partial, rows, pairs),
                }
            elif partial:
                result = {kind: failure('coverage_incomplete', at, prior)
                          for kind, prior in self.snapshots.items()}
            elif non_github:
                result = dict.fromkeys(self.snapshots, outcome('unsupported', at, reason='not_github'))
            else:
                result = {kind: self.list_outcome(kind, at, [], False) for kind in self.snapshots}
        except GitHubError as exc:
            failures.append(exc.args[0])
            result = {kind: failure(exc.args[0], at, prior)
                      for kind, prior in self.snapshots.items()}
        except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
            failures.append('invalid_response')
            result = {kind: failure('invalid_response', at, prior)
                      for kind, prior in self.snapshots.items()}
        with self.lock:
            if not self.active(generation):
                return
            if alerts:
                try:
                    self.record_alerts(alerts, at)
                except (OSError, ValueError, KeyError, TypeError, RecursionError):
                    # Keep reading CI while a damaged journal remains fail-closed.
                    pass
            if rows:
                self.previous = {(row['repo'], row['branch']): row for row in rows}
            elif not failures:
                self.previous = {}
            self.snapshots = result
            self.failures = min(self.failures + 1, 6) if failures else 0
            delay = (min(1800, (120 if 'rate_limited' in failures else FAST) * 2**self.failures)
                     if failures else FAST if running or result['ci']['status'] == 'unavailable' else SLOW)
            self.due = max(started + delay, time.monotonic() + (FAST if failures else 0))

    @staticmethod
    def list_outcome(kind, at, rows, omitted):
        data = {'rows': rows, 'omitted': omitted}
        if kind == 'pulls':
            data['count'] = len(rows)
        return outcome('ok' if rows or omitted else 'quiet', at, at, data=data)

    def read_pulls(self, github, pool, pairs, partial, at):
        def read(repo):
            try:
                return github.waiting_pulls(repo, pairs), None
            except GitHubError as exc:
                return None, exc.args[0]

        repos = dict.fromkeys(repo for repo, _ in pairs)
        rows, failures = [], []
        for result, reason in pool.map(read, repos):
            if reason:
                failures.append(reason)
                continue
            found, omitted = result
            rows.extend(found)
            partial |= omitted
        if len(failures) == len(repos):
            return failure(failures[0], at, self.read('pulls')), failures
        rows.sort(key=lambda pr: (stamp(pr['updatedAt']), pr['repo'], pr['number']), reverse=True)
        return self.list_outcome('pulls', at, rows[:100], partial or bool(failures) or len(rows) > 100), failures

    def ended_result(self, at, ended_rows, partial, rows, pairs):
        relevant = [row for row in rows if 'ended' in pairs[row['repo'], row['branch']].values()]
        reasons = [row['ci']['reason'] for row in relevant if row['ci']['reason'] in RETRY_REASONS]
        if not ended_rows and reasons and len(reasons) == len(relevant):
            return failure(reasons[0], at, self.read('ended'))
        return self.list_outcome('ended', at, ended_rows[:1024], partial or len(ended_rows) > 1024)

    @staticmethod
    def read_pair(github, item, at, previous):
        (repo, branch), agents = item
        prior = previous.get((repo, branch), {})
        sha = pr = historical = None
        ended = [identity for identity, mode in agents.items() if mode == 'ended']
        try:
            sha, pr, check, historical, partial = github.checks(repo, branch, bool(ended))
            ci = failure(check, at, prior.get('ci')) if isinstance(check, str) else observe(at, check)
        except GitHubError as exc:
            ci = failure(exc.args[0], at, prior.get('ci'))
            partial = bool(ended)
        try:
            # An authentication/rate failure already precludes the deployment call.
            if ci['reason'] in SETUP_REASONS | {'rate_limited', 'disabled'}:
                raise GitHubError(ci['reason'])
            deploy = observe(at, github.deployment(repo, branch))
        except GitHubError as exc:
            deploy = failure(exc.args[0], at, prior.get('deploy'))
        finished = [dict(historical, agentId=identity) for identity in ended] if historical else []
        return {'repo': repo, 'branch': branch, 'agentIds': list(agents),
                'pr': pr, 'ci': ci, 'deploy': deploy}, sha, finished, partial

    def record_alerts(self, alerts, at):
        now = self.clock()

        def build(journal):
            seen = set(journal.get('ciAlerts', []))
            events = [event for event in journal.get('events', [])
                      if self.delivery.pending(event)]
            for repo, sha in alerts:
                identity = hashlib.sha256(f'{CI_SOURCE_ID}:{repo}:{sha}'.encode()).hexdigest()
                if identity in seen or len(seen) >= MAX_ALERTS or len(events) >= 256:
                    continue
                seen.add(identity)
                events.append({'id': identity, 'kind': 'ci_failed', 'repo': repo, 'occurredAt': at,
                               'links': {'desktop': None, 'web': None}, 'claimed': False})
            journal.update(ciAlerts=sorted(seen), events=events)

        if 0 <= (now - stamp(at)).total_seconds() < 86400:
            self.delivery.mutate_journal(build, repair=False)
