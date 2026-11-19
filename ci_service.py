"""Owner-opted background CI reads and durable notifications."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import hashlib
from os.path import isdir
import shutil
import threading
import time

from agents_projection import stamp
from agents_service import AgentsService, outcome
from ci_workspace import (PREFERENCE, WorkspaceUnavailable, branch_name, env_path,
                          repo_name, resolve_workspace)
from github_ci import GitHub, GitHubError, SETUP_REASONS

CI_SOURCE_ID = 'github-ci'
MAX_PAIRS = 20
MAX_WORKSPACES = 80
MAX_ALERTS = 100_000
FAST, SETTLED, ENDED = 30, 120, 600
FAST_WINDOW = 600
RUNNING_DEPLOYS = {'queued', 'pending', 'in_progress', 'waiting'}


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
    non_github = False
    for identity, mode, location in candidates:
        if location is None or location == []:
            continue
        if isinstance(location, list):
            if len(location) != 2 or not repo_name(location[0]) or not branch_name(location[1]):
                omitted = True
                continue
            repo, branch = location
            pair = repo.lower(), branch
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
                try:
                    resolved[key] = resolve_workspace(cwd, branch), False
                except WorkspaceUnavailable:
                    resolved[key] = None, True
            pair, check_failed = resolved[key]
            if check_failed:
                omitted = True
                continue
        else:
            omitted = True
            continue
        if pair is False:
            non_github = True
            continue
        if pair is None:
            continue
        if pair not in grouped and len(grouped) >= MAX_PAIRS:
            omitted = True
            continue
        agents = grouped.setdefault(pair, {})
        agents.setdefault(identity, mode)
    return grouped, omitted, non_github


@dataclass(frozen=True)
class BranchRead:
    active: bool
    history_requested: bool
    due: float
    failures: int
    sha: str | None
    running_since: float | None
    row: dict | None
    history: dict | None
    history_partial: bool
    history_reason: str | None

    @property
    def reason(self):
        if self.row is None:
            return None
        return self.row['ci']['reason'] or self.row['deploy']['reason']

    @property
    def readable(self):
        return (self.row is None or self.row['ci']['status']=='ok'
                or self.row['deploy']['status']=='ok')


@dataclass(frozen=True)
class PullRead:
    watched: frozenset
    active: bool
    due: float
    failures: int
    rows: list
    partial: bool
    reason: str | None


def retry_delay(reason, failures):
    if reason in SETUP_REASONS:
        return min(180, FAST * 2**failures)
    if reason == 'rate_limited':
        return min(1800, SETTLED * 2**failures)
    return min(ENDED, FAST * 2**failures)


def watch_delay(active, reason, failures):
    delay = retry_delay(reason, failures)
    return delay if active or reason in SETUP_REASONS or reason=='rate_limited' else max(ENDED, delay)


def branch_mode(agents):
    return 'active' in agents.values(), 'ended' in agents.values()


def branch_due(sample, agents, now):
    active, historical = branch_mode(agents)
    return (sample is None or now >= sample.due or active != sample.active
            or (historical and not sample.history_requested))


class CIService:
    def __init__(self, store, home, clock, candidates, *, monotonic=time.monotonic):
        self.store, self.home, self.clock, self.candidates = store, home, clock, candidates
        self.monotonic = monotonic
        self.delivery = AgentsService(store.directory, clock=clock, source_id=CI_SOURCE_ID)
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='nagi-ci')
        self.future = None
        self.closed = False
        self.generation = 0
        self.due = 0
        self.failures = 0
        self.branches, self.pulls = {}, {}
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
                self.branches, self.pulls = {}, {}
                at = self.clock().isoformat()
                self.reset_snapshots(at)
            return self.settings()

    def active(self, generation):
        with self.lock:
            return self.enabled and not self.closed and self.generation == generation

    def schedule(self):
        with self.lock:
            if (self.active(self.generation) and self.monotonic() >= self.due
                    and (self.future is None or self.future.done())):
                self.future = self.executor.submit(self.poll, self.generation, self.branches, self.pulls)

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

    def poll(self, generation, prior_branches, prior_pulls):
        started = self.monotonic()
        at = self.clock().isoformat()
        alerts = []
        global_reason = None
        branches, pulls = {}, {}
        try:
            candidates, incomplete = self.candidates()
            pairs, omitted, non_github = discover(candidates)
            partial = omitted or incomplete
            if pairs:
                watched = {}
                for key, agents in pairs.items():
                    watched.setdefault(key[0], {})[key] = agents
                branches = {pair: prior_branches[pair] for pair in pairs if pair in prior_branches}
                pulls = {repo: prior_pulls[repo] for repo in watched if repo in prior_pulls}
                branch_tasks = {key: agents for key, agents in pairs.items()
                                if branch_due(branches.get(key), agents, started)}
                pull_tasks = {}
                for repo, pairs_in_repo in watched.items():
                    keys = frozenset(pairs_in_repo)
                    active = any(branch_mode(agents)[0] for agents in pairs_in_repo.values())
                    sample = pulls.get(repo)
                    if sample is None or started >= sample.due or keys != sample.watched or active != sample.active:
                        pull_tasks[repo] = keys, active

                if branch_tasks or pull_tasks:
                    github = GitHub(self.home, lambda: self.active(generation))
                    with ThreadPoolExecutor(max_workers=4) as pool:
                        def read_branch(key):
                            return self.read_pair(github, key, branch_tasks[key], at, started, branches.get(key))

                        for key, sample in zip(branch_tasks, pool.map(read_branch, branch_tasks)):
                            branches[key] = sample
                            ci = sample.row['ci']['data'] if sample.row else None
                            if ci and ci['state']=='failed':
                                alerts.append((key[0], sample.sha))

                        def read_pulls(repo):
                            return self.read_pulls(github, repo, *pull_tasks[repo], started, pulls.get(repo))

                        for repo, sample in zip(pull_tasks, pool.map(read_pulls, pull_tasks)):
                            pulls[repo] = sample

                    global_reason = github.stop_reason
                    if (not global_reason and branch_tasks
                            and not any(sample.readable for sample in branches.values())):
                        global_reason = next((sample.reason for sample in branches.values() if sample.reason), None)

                result = self.project(pairs, branches, pulls, partial, at)
            elif partial:
                result = {kind: failure('coverage_incomplete', at, prior)
                          for kind, prior in self.snapshots.items()}
            elif non_github:
                result = dict.fromkeys(self.snapshots, outcome('unsupported', at, reason='not_github'))
            else:
                result = {kind: self.list_outcome(kind, at, [], False) for kind in self.snapshots}
        except GitHubError as exc:
            global_reason = exc.args[0]
            result = {kind: failure(global_reason, at, prior)
                      for kind, prior in self.snapshots.items()}
        except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
            global_reason = 'invalid_response'
            result = {kind: failure(global_reason, at, prior)
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
            self.branches, self.pulls = branches, pulls
            self.snapshots = result
            self.failures = min(self.failures + 1, 6) if global_reason else 0
            delay = retry_delay(global_reason, self.failures) if global_reason else FAST
            self.due = started + delay

    @staticmethod
    def list_outcome(kind, at, rows, omitted):
        data = {'rows': rows, 'omitted': omitted}
        if kind == 'pulls':
            data['count'] = len(rows)
        return outcome('ok' if rows or omitted else 'quiet', at, at, data=data)

    def project(self, pairs, branches, pulls, partial, at):
        rows, ended = [], []
        history_errors = []
        ended_partial = partial
        histories = 0
        for key, agents in pairs.items():
            sample = branches[key]
            if sample.row is not None:
                rows.append(dict(sample.row, agentIds=list(agents)))
            finished = [identity for identity, mode in agents.items() if mode=='ended']
            if not finished:
                continue
            histories += 1
            ended_partial |= sample.history_partial
            if sample.history_reason:
                history_errors.append(sample.history_reason)
            if sample.history:
                ended.extend(dict(sample.history, agentId=identity) for identity in finished)

        pull_rows = [pr for sample in pulls.values() for pr in sample.rows]
        pull_rows.sort(key=lambda pr: (stamp(pr['updatedAt']), pr['repo'], pr['number']), reverse=True)
        pull_errors = [sample.reason for sample in pulls.values() if sample.reason]
        pull_partial = partial or any(sample.partial for sample in pulls.values()) or len(pull_rows)>100
        return {
            'ci': self.list_outcome('ci', at, rows, partial),
            'pulls': (failure(pull_errors[0], at, self.read('pulls')) if pull_errors and len(pull_errors)==len(pulls)
                      else self.list_outcome('pulls', at, pull_rows[:100], pull_partial)),
            'ended': (failure(history_errors[0], at, self.read('ended')) if history_errors and len(history_errors)==histories
                      else self.list_outcome('ended', at, ended[:1024], ended_partial or len(ended)>1024)),
        }

    @staticmethod
    def read_pulls(github, repo, watched, active, started, prior):
        try:
            rows, partial = github.waiting_pulls(repo, watched)
            return PullRead(watched, active, started + (SETTLED if active else ENDED), 0, rows, partial, None)
        except GitHubError as exc:
            reason = exc.args[0]
            failures = min((prior.failures if prior else 0) + 1, 6)
            return PullRead(watched, active, started + watch_delay(active, reason, failures),
                            failures, [], True, reason)

    @staticmethod
    def read_pair(github, key, agents, at, started, prior):
        repo, branch = key
        active, wants_history = branch_mode(agents)
        history_reason = None
        try:
            sha, pr, check, deploy, historical, partial = github.checks(repo, branch, wants_history)
        except GitHubError as exc:
            sha = pr = historical = None
            check = deploy = exc.args[0]
            partial = wants_history
            history_reason = check if wants_history else None

        row = None
        reason = None
        busy = False
        if check is not None:
            previous = (prior.row or {}) if prior else {}
            ci = failure(check, at, previous.get('ci')) if isinstance(check, str) else observe(at, check)
            deployment = failure(deploy, at, previous.get('deploy')) if isinstance(deploy, str) else observe(at, deploy)
            row = {'repo': repo, 'branch': branch, 'pr': pr, 'ci': ci, 'deploy': deployment}
            reason = ci['reason'] or deployment['reason']
            checks = ci['data'] or {}
            busy = (checks.get('state') == 'running' or checks.get('running', 0) > 0
                    or (deployment['data'] or {}).get('state') in RUNNING_DEPLOYS)
        # An intermittent failure cannot restart the fast-poll budget for
        # the same pending tip.
        clock_sha = sha or (prior.sha if reason and prior else None)
        pending_since = prior.running_since if prior and prior.sha==clock_sha else None
        if busy and pending_since is None:
            pending_since = started
        if not busy and not reason:
            pending_since = None

        failures = min((prior.failures if prior else 0) + 1, 6) if reason else 0
        delay = (watch_delay(active, reason, failures) if reason
                 else ENDED if not active
                 else FAST if busy and started-pending_since < FAST_WINDOW else SETTLED)
        return BranchRead(active, wants_history, started+delay, failures, clock_sha, pending_since,
                          row, historical, partial, history_reason)

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
