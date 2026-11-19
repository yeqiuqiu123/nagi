"""GitHub CLI reads and closed CI/deployment projections."""
import os
import re
import shutil
import subprocess
import threading
from urllib.parse import urlencode

from agents_projection import stamp
from ci_workspace import env_path, repo_name, run_bounded
from jsonio import strict_json_loads

QUERY = """
query($owner: String!, $repo: String!, $ref: String!, $branch: String!, $ended: Boolean!) {
  repository(owner: $owner, name: $repo) {
    ref(qualifiedName: $ref) {
      target {
        ... on Commit {
          oid
          statusCheckRollup {
            contexts(first: 100) {
              pageInfo { hasNextPage }
              nodes {
                __typename
                ... on CheckRun { status conclusion completedAt startedAt }
                ... on StatusContext { state createdAt }
              }
            }
          }
        }
      }
      associatedPullRequests(first: 10, states: [OPEN], orderBy: {field: UPDATED_AT, direction: DESC}) {
        nodes { number headRefOid isCrossRepository }
      }
    }
    historical: pullRequests(first: 20, headRefName: $branch,
      orderBy: {field: UPDATED_AT, direction: DESC}) @include(if: $ended) {
      pageInfo { hasNextPage }
      nodes { ...PullSummary }
    }
  }
}
"""

PULL_SUMMARY = """
fragment PullSummary on PullRequest {
  number title updatedAt state isDraft reviewDecision mergeable mergeStateStatus
  headRefName headRepository { nameWithOwner }
  statusCheckRollup { state }
}
"""

WAITING_QUERY = """
query($owner: String!, $repo: String!) {
  viewer { login }
  repository(owner: $owner, name: $repo) {
    pullRequests(first: 50, states: [OPEN], orderBy: {field: UPDATED_AT, direction: DESC}) {
      pageInfo { hasNextPage }
      nodes {
        ...PullSummary
        author { login }
        reviewRequests(first: 30) {
          pageInfo { hasNextPage }
          nodes { requestedReviewer { ... on User { login } } }
        }
      }
    }
  }
}
"""

SETUP_REASONS = {'gh_missing', 'gh_signed_out'}
DEPLOY_STATES = {'queued', 'pending', 'in_progress', 'success', 'failure',
                 'error', 'inactive', 'waiting'}
PENDING = {'QUEUED', 'IN_PROGRESS', 'PENDING', 'REQUESTED', 'WAITING', 'EXPECTED'}
CONCLUSIONS = {
    'SUCCESS': 'passed', 'CANCELLED': 'cancelled', 'NEUTRAL': 'neutral',
    'SKIPPED': 'neutral', 'FAILURE': 'failed', 'ERROR': 'failed',
    'ACTION_REQUIRED': 'failed', 'TIMED_OUT': 'failed', 'STALE': 'failed',
    'STARTUP_FAILURE': 'failed',
}
SHA = re.compile(r'[0-9a-f]{40}')
MAX_OUTPUT = 512 * 1024


class GitHubError(Exception):
    pass


def failure_reason(detail):
    detail = detail.lower()
    if any(mark in detail for mark in (b'rate limit', b'http 429', b'secondary rate')):
        return 'rate_limited'
    if any(mark in detail for mark in (b'gh auth login', b'http 401', b'bad credentials', b'not logged')):
        return 'gh_signed_out'
    return 'cannot_reach_github'


class GitHub:
    def __init__(self, home, active):
        path = env_path()
        self.executable = shutil.which('gh', path=path)
        if not self.executable:
            raise GitHubError('gh_missing')
        self.home, self.active = home, active
        self.lock = threading.Lock()
        self.stop_reason = None
        self.env = {'HOME': str(home), 'PATH': path, 'LC_ALL': 'C',
                    'GH_HOST': 'github.com', 'GH_PROMPT_DISABLED': '1',
                    'GH_NO_UPDATE_NOTIFIER': '1', 'GH_NO_EXTENSION_UPDATE_NOTIFIER': '1',
                    'GH_TELEMETRY': 'false', 'NO_COLOR': '1'}
        for key in ('GH_CONFIG_DIR', 'XDG_CONFIG_HOME', 'DBUS_SESSION_BUS_ADDRESS',
                    'XDG_RUNTIME_DIR'):
            if value := os.environ.get(key):
                self.env[key] = value
        # An owner-configured transport could send these reads elsewhere.
        # Ask gh about routing keys only. Never query its credentials.
        for key in ('api_host', 'http_unix_socket'):
            code, raw, _ = self.command('config', 'get', key, '--host', 'github.com')
            if code not in (0, 1) or raw.strip():
                raise GitHubError('cannot_reach_github')

    def command(self, *args):
        if not self.active():
            raise GitHubError('disabled')
        try:
            return run_bounded([self.executable, *args], env=self.env, cwd=self.home,
                               timeout=4, output_limit=MAX_OUTPUT,
                               stderr_limit=8192)
        except FileNotFoundError:
            raise GitHubError('gh_missing') from None
        except ValueError:
            raise GitHubError('invalid_response') from None
        except (OSError, subprocess.SubprocessError):
            raise GitHubError('cannot_reach_github') from None

    def api(self, endpoint, *args):
        with self.lock:
            if self.stop_reason:
                raise GitHubError(self.stop_reason)
        code, raw, detail = self.command('api', endpoint, '--hostname', 'github.com', *args)
        if code:
            reason = failure_reason(detail)
            if reason in {'rate_limited', 'gh_signed_out'}:
                with self.lock:
                    self.stop_reason = reason
            raise GitHubError(reason)
        try:
            return strict_json_loads(raw, MAX_OUTPUT)
        except (ValueError, TypeError, RecursionError):
            raise GitHubError('invalid_response') from None

    def graphql(self, query, **fields):
        variables = []
        for key, value in fields.items():
            variables.extend(('-F', f'{key}={str(value).lower()}') if type(value) is bool
                             else ('-f', f'{key}={value}'))
        result = self.api('graphql', '-f', 'query=' + query, *variables)
        if not isinstance(result, dict) or result.get('errors'):
            raise GitHubError('invalid_response')
        return result.get('data')

    def checks(self, repo, branch, ended=False):
        owner, name = repo.split('/')
        repository = self.graphql(QUERY + PULL_SUMMARY, owner=owner, repo=name,
                                  ref='refs/heads/' + branch, branch=branch, ended=ended)
        try:
            repository = repository['repository']
            historical, partial = historical_pull(repository['historical'], repo, branch) if ended else (None, False)
            ref = repository['ref']
            if ref is None:
                return None, None, 'branch_unavailable', historical, partial
            commit = ref['target']
            sha = commit['oid']
            if not isinstance(sha, str) or not SHA.fullmatch(sha):
                raise ValueError()
            pr = next((node for node in ref['associatedPullRequests']['nodes']
                       if node['headRefOid'] == sha and node['isCrossRepository'] is False), None)
            url = f'https://github.com/{repo}'
            pr_number = number(pr['number']) if pr else None
            link = {'number': pr_number, 'url': f'{url}/pull/{pr_number}'} if pr_number else None
            checks_url = link['url'] if link else f'{url}/actions?' + urlencode({'query': 'branch:' + branch})
            try:
                checks = check_rollup(commit['statusCheckRollup'], checks_url)
            except GitHubError as exc:
                checks = exc.args[0]
            except (KeyError, TypeError, ValueError):
                checks = 'invalid_response'
            return sha, link, checks, historical, partial
        except (TypeError, ValueError, KeyError, AttributeError):
            raise GitHubError('invalid_response') from None

    def waiting_pulls(self, repo, pairs):
        owner, name = repo.split('/')
        data = self.graphql(WAITING_QUERY + PULL_SUMMARY, owner=owner, repo=name)
        try:
            viewer = data['viewer']['login'].lower()
            nodes, partial = connection(data['repository']['pullRequests'], 50)
            rows = []
            for pr in nodes:
                if pr['isDraft'] is True:
                    continue
                author = (pr.get('author') or {}).get('login')
                if (not isinstance(author, str) or author.lower() != viewer) and (head_repo(pr), pr['headRefName']) not in pairs:
                    continue
                projection, why, omitted = attention_pull(pr, repo, viewer)
                partial |= omitted
                if why:
                    rows.append(dict(projection, why=why))
            return rows, partial
        except (TypeError, ValueError, KeyError, AttributeError):
            raise GitHubError('invalid_response') from None

    def deployment(self, repo, branch):
        try:
            prefix = f'repos/{repo}/deployments'
            deployments = self.api(prefix + '?' + urlencode({'ref': branch, 'per_page': 1}))
            current = first(deployments)
            if current is None:
                return None
            if current['ref'] not in (branch, 'refs/heads/' + branch):
                raise ValueError()
            deployment_id = number(current['id'])
            status = first(self.api(f'{prefix}/{deployment_id}/statuses?per_page=1'))
            state = status['state'] if status is not None else 'unknown'
            if status is not None and state not in DEPLOY_STATES:
                raise ValueError()
            environment = (status or {}).get('environment') or current['environment']
            safe_environment = (isinstance(environment, str)
                                and re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,39}', environment))
            return {'environment': environment if safe_environment else 'Deployment', 'state': state,
                    'url': f'https://github.com/{repo}/deployments',
                    'updatedAt': iso((status or current)['created_at'])}
        except (TypeError, ValueError, KeyError, AttributeError):
            raise GitHubError('invalid_response') from None


def first(values):
    if not isinstance(values, list) or len(values) > 1:
        raise ValueError()
    return values[0] if values else None


def number(value):
    if type(value) is not int or value <= 0:
        raise ValueError()
    return value


def iso(value):
    return stamp(value).isoformat()


def check_rollup(rollup, url):
    nodes = []
    if rollup is not None:
        values = rollup['contexts']
        nodes = values['nodes']
        if values['pageInfo']['hasNextPage'] is not False:
            raise GitHubError('coverage_incomplete')
        if not isinstance(nodes, list) or len(nodes) > 100:
            raise ValueError()
    counts = dict.fromkeys(('passed', 'failed', 'running', 'cancelled', 'neutral'), 0)
    updated = []
    for node in nodes:
        kind = node['__typename']
        if kind == 'CheckRun':
            status = node['status']
            result = CONCLUSIONS[node['conclusion']] if status == 'COMPLETED' else (
                'running' if status in PENDING else None)
            date = node['completedAt'] or node['startedAt']
        elif kind == 'StatusContext':
            status = node['state']
            result = 'running' if status in PENDING else CONCLUSIONS[status]
            date = node['createdAt']
        else:
            raise ValueError()
        counts[result] += 1
        if date is not None:
            updated.append(stamp(date))
    state = next((key for key in ('failed', 'running', 'cancelled', 'passed') if counts[key]), 'none')
    return {'state': state, 'total': len(nodes), 'passed': counts['passed'],
            'failed': counts['failed'], 'running': counts['running'], 'url': url,
            'updatedAt': max(updated).isoformat() if updated else None}


PULL_CI = {'SUCCESS': 'passed', 'PENDING': 'running', 'EXPECTED': 'running',
           'FAILURE': 'failed', 'ERROR': 'failed'}


def connection(value, maximum):
    nodes, partial = value['nodes'], value['pageInfo']['hasNextPage']
    if not isinstance(nodes, list) or len(nodes) > maximum or type(partial) is not bool:
        raise ValueError()
    return nodes, partial


def head_repo(pr):
    name = (pr['headRepository'] or {}).get('nameWithOwner')
    return name.lower() if repo_name(name) else None


def pull_summary(pr, repo):
    pr_number = number(pr['number'])
    title = pr['title']
    # Slash, dot and credential-like strings can carry paths, hosts, URLs or IDs.
    if (not isinstance(title, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ,!?:()'_-]{0,119}", title)
            or re.search(r'[A-Za-z0-9_-]{20,}', title)):
        title = f'Pull request #{pr_number}'
    rollup = pr['statusCheckRollup']
    ci = PULL_CI.get(rollup['state']) if rollup is not None else 'none'
    return {'repo': repo, 'number': pr_number, 'title': title,
            'url': f'https://github.com/{repo}/pull/{pr_number}', 'ci': ci,
            'updatedAt': iso(pr['updatedAt'])}


def ready_to_merge(pr, ci):
    return pr['reviewDecision'] == 'APPROVED' or (
        pr['mergeable'] == 'MERGEABLE' and pr['mergeStateStatus'] in ('CLEAN', 'HAS_HOOKS')
        and ci == 'passed')


def attention_pull(pr, repo, viewer):
    summary = pull_summary(pr, repo)
    requests = pr['reviewRequests']
    if requests is None:
        reviewers, partial = [], True
    else:
        reviewers, partial = connection(requests, 30)
    requested = any(isinstance(login, str) and viewer == login.lower()
                    for request in reviewers
                    if (login := (request['requestedReviewer'] or {}).get('login')) is not None)
    if requested:
        reason = 'review_requested'
    elif pr['reviewDecision'] == 'CHANGES_REQUESTED':
        reason = 'changes_requested'
    elif ready_to_merge(pr, summary['ci']):
        reason = 'ready_to_merge'
    else:
        reason = None
    return summary, reason, partial and not requested


def historical_pull(connection_value, repo, branch):
    nodes, partial = connection(connection_value, 20)
    # Keep the latest updated matching PR. A fork with the same branch
    # name is a different workspace even when its PR targets this repo.
    pr = next((node for node in nodes if head_repo(node) == repo and node['headRefName'] == branch), None)
    if not pr:
        return None, partial
    summary = pull_summary(pr, repo)
    state = pr['state']
    if state in ('MERGED', 'CLOSED'):
        merged = state.lower()
    elif state != 'OPEN':
        merged = 'unknown'
    elif pr['isDraft']:
        merged = 'draft'
    elif pr['reviewDecision'] == 'CHANGES_REQUESTED':
        merged = 'changes_requested'
    elif ready_to_merge(pr, summary['ci']):
        merged = 'ready_to_merge'
    else:
        merged = 'open'
    return dict(summary, mergeState=merged), False
