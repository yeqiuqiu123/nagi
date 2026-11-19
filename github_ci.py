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
    deployments(first: 30, orderBy: {field: CREATED_AT, direction: DESC}) {
      pageInfo { hasNextPage }
      nodes { ...DeploymentSample }
    }
    ref(qualifiedName: $ref) {
      target {
        ... on Commit {
          oid
          tipDeployments: deployments(first: 1, orderBy: {field: CREATED_AT, direction: DESC}) {
            nodes { ...DeploymentSample }
          }
          statusCheckRollup { ...CheckContexts }
        }
      }
      associatedPullRequests(first: 1, states: [OPEN], orderBy: {field: UPDATED_AT, direction: DESC}) {
        nodes {
          number headRefOid repository { nameWithOwner }
          statusCheckRollup { ...CheckContexts }
        }
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

DEPLOYMENTS = """
fragment DeploymentSample on Deployment {
  createdAt latestEnvironment originalEnvironment
  ref { prefix name }
  latestStatus { state createdAt }
}
"""

CHECK_CONTEXTS = """
fragment CheckContexts on StatusCheckRollup {
  state
  contexts(first: 100) {
    pageInfo { hasNextPage }
    nodes {
      __typename
      ... on CheckRun { status conclusion completedAt startedAt }
      ... on StatusContext { state createdAt }
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
    if any(mark in detail for mark in (b'http 404', b'could not resolve to a repository')):
        return 'repo_not_found'
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

    def graphql(self, query, **fields):
        with self.lock:
            if self.stop_reason:
                raise GitHubError(self.stop_reason)
        variables = []
        for key, value in fields.items():
            variables.extend(('-F', f'{key}={str(value).lower()}') if type(value) is bool
                             else ('-f', f'{key}={value}'))
        code, raw, detail = self.command('api', 'graphql', '--hostname', 'github.com',
                                         '-f', 'query=' + query, *variables)
        try:
            result = strict_json_loads(raw, MAX_OUTPUT)
        except (ValueError, TypeError, RecursionError):
            result = None
        if isinstance(result, dict) and result.get('errors'):
            errors = result['errors']
            types = {error.get('type') for error in errors if isinstance(error, dict)} if isinstance(errors, list) else set()
            if 'RATE_LIMITED' in types:
                reason = 'rate_limited'
            elif 'NOT_FOUND' in types and isinstance(result.get('data'), dict) and result['data'].get('repository') is None:
                reason = 'repo_not_found'
            elif (isinstance(result.get('data'), dict) and result['data'].get('repository') is not None
                  and isinstance(errors, list) and all(is_partial_error(error) for error in errors)):
                # Keep a missing ref or inaccessible deployment local to that measure.
                return result['data']
            else:
                reason = failure_reason(detail) if code else 'invalid_response'
        elif code:
            reason = failure_reason(detail)
        elif isinstance(result, dict) and isinstance(result.get('data'), dict):
            return result['data']
        else:
            reason = 'invalid_response'
        if reason in {'rate_limited', 'gh_signed_out'}:
            with self.lock:
                self.stop_reason = reason
        raise GitHubError(reason)

    def checks(self, repo, branch, ended=False):
        owner, name = repo.split('/')
        repository = self.graphql(QUERY + CHECK_CONTEXTS + DEPLOYMENTS + PULL_SUMMARY, owner=owner, repo=name,
                                  ref='refs/heads/' + branch, branch=branch, ended=ended)
        try:
            repository = repository['repository']
            if repository is None:
                raise GitHubError('repo_not_found')
            historical, partial = historical_pull(repository['historical'], repo, branch) if ended else (None, False)
            ref = repository['ref']
            if ref is None:
                return None, None, None, None, historical, partial
            commit = ref['target']
            sha = commit['oid']
            if not isinstance(sha, str) or not SHA.fullmatch(sha):
                raise ValueError()
            pr = first(ref['associatedPullRequests']['nodes'])
            link = None
            rollup = commit['statusCheckRollup']
            if pr is not None and pr['headRefOid'] == sha:
                pr_repo = pr['repository']['nameWithOwner']
                if not repo_name(pr_repo):
                    raise ValueError()
                pr_number = number(pr['number'])
                link = {'number': pr_number, 'url': f'https://github.com/{pr_repo.lower()}/pull/{pr_number}'}
                rollup = pr['statusCheckRollup'] or rollup
            checks_url = link['url'] if link else f'https://github.com/{repo}/actions?' + urlencode({'query': 'branch:' + branch})
            try:
                checks = check_rollup(rollup, checks_url)
            except GitHubError as exc:
                checks = exc.args[0]
            except (KeyError, TypeError, ValueError):
                checks = 'invalid_response'
            try:
                deploy = deployment(repo, branch, repository['deployments'], commit['tipDeployments'])
            except (TypeError, ValueError, KeyError, AttributeError, GitHubError) as exc:
                deploy = exc.args[0] if isinstance(exc, GitHubError) else 'invalid_response'
            return sha, link, checks, deploy, historical, partial
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


def is_partial_error(error):
    if not isinstance(error, dict):
        return False
    path = error.get('path')
    return isinstance(path, list) and (
        path[:2] == ['repository', 'deployments']
        or path[:4] == ['repository', 'ref', 'target', 'tipDeployments']
        or (path == ['repository', 'ref'] and error.get('type') == 'NOT_FOUND'))


def deployment(repo, branch, repository_deploys, tip_deploys):
    if repository_deploys is None or tip_deploys is None:
        raise GitHubError('invalid_response')
    nodes, partial = connection(repository_deploys, 30)
    matches = [node for node in nodes if (node['ref'] or {}).get('prefix') == 'refs/heads/'
               and node['ref'].get('name') == branch]
    tip = first(tip_deploys['nodes'])
    if tip is not None:
        matches.append(tip)
    if not matches:
        if partial:
            raise GitHubError('coverage_incomplete')
        return None
    latest = max(matches, key=lambda node: stamp(node['createdAt']))
    status = latest['latestStatus']
    state = status['state'].lower() if status is not None else 'unknown'
    if status is not None and state not in DEPLOY_STATES:
        raise ValueError()
    environment = latest['latestEnvironment'] or latest['originalEnvironment']
    safe = isinstance(environment, str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,39}', environment)
    return {'environment': environment if safe else 'Deployment', 'state': state,
            'url': f'https://github.com/{repo}/deployments',
            'updatedAt': iso((status or latest)['createdAt'])}


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
    expected = rollup is not None and rollup.get('state') in ('PENDING', 'EXPECTED')
    state = ('failed' if counts['failed'] else 'running' if counts['running'] or expected
             else 'cancelled' if counts['cancelled'] else 'passed' if counts['passed'] else 'none')
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
    return (pr['reviewDecision'] == 'APPROVED' and pr['mergeable'] == 'MERGEABLE'
            and pr['mergeStateStatus'] in ('CLEAN', 'HAS_HOOKS')
            and ci in ('passed', 'none'))


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
