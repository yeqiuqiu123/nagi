"""GitHub CLI reads and closed CI/deployment projections."""
import os
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import quote, urlencode

from agents_projection import stamp
from ci_workspace import env_path, run_bounded
from jsonio import strict_json_loads

QUERY = """
query($owner: String!, $repo: String!, $ref: String!) {
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
      associatedPullRequests(first: 1, states: [OPEN]) {
        nodes { number headRefOid isCrossRepository }
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
        self.env = {'HOME': str(home), 'PATH': path, 'LC_ALL': 'C',
                    'GH_HOST': 'github.com', 'GH_PROMPT_DISABLED': '1',
                    'GH_NO_UPDATE_NOTIFIER': '1', 'GH_NO_EXTENSION_UPDATE_NOTIFIER': '1',
                    'GH_TELEMETRY': 'false', 'NO_COLOR': '1'}
        for key in ('GH_CONFIG_DIR', 'XDG_CONFIG_HOME', 'DBUS_SESSION_BUS_ADDRESS',
                    'XDG_RUNTIME_DIR'):
            if value := os.environ.get(key):
                self.env[key] = value
        # gh supports API-host and socket overrides in its own config. Probe
        # their presence through gh without reading the values or its auth store.
        for key in ('api_host', 'http_unix_socket'):
            code, _, _ = self.command('config', 'get', key, '--host', 'github.com', discard=True)
            if code != 1:
                raise GitHubError('cannot_reach_github')

    def command(self, *args, discard=False):
        if not self.active():
            raise GitHubError('disabled')
        try:
            return run_bounded([self.executable, *args], env=self.env, cwd=self.home,
                               timeout=4, output_limit=MAX_OUTPUT,
                               stderr_limit=0 if discard else 8192, discard=discard)
        except FileNotFoundError:
            raise GitHubError('gh_missing') from None
        except ValueError:
            raise GitHubError('invalid_response') from None
        except (OSError, subprocess.SubprocessError):
            raise GitHubError('cannot_reach_github') from None

    def api(self, endpoint, *args):
        code, raw, detail = self.command('api', endpoint, '--hostname', 'github.com', *args)
        if code:
            raise GitHubError(failure_reason(detail))
        try:
            return strict_json_loads(raw, MAX_OUTPUT)
        except (ValueError, TypeError, RecursionError):
            raise GitHubError('invalid_response') from None

    def graphql(self, query, **fields):
        variables = [arg for key, value in fields.items() for arg in ('-f', f'{key}={value}')]
        result = self.api('graphql', '-f', 'query=' + query, *variables)
        if not isinstance(result, dict) or result.get('errors'):
            raise GitHubError('invalid_response')
        return result.get('data')

    def checks(self, repo, branch):
        owner, name = repo.split('/')
        try:
            repository = self.graphql(QUERY, owner=owner, repo=name, ref='refs/heads/' + branch)['repository']
            ref = repository['ref']
            if ref is None:
                raise GitHubError('branch_unavailable')
            commit = ref['target']
            sha = commit['oid']
            if not isinstance(sha, str) or not SHA.fullmatch(sha):
                raise ValueError()
            pr = next((node for node in ref['associatedPullRequests']['nodes']
                       if node['headRefOid'] == sha and node['isCrossRepository'] is False), None)
            url = f'https://github.com/{repo}'
            link = {'number': number(pr['number']), 'url': f"{url}/pull/{number(pr['number'])}"} if pr else None
            checks_url = link['url'] if link else f'{url}/actions?' + urlencode({'query': 'branch:' + branch})
            return sha, link, check_rollup(commit['statusCheckRollup'], checks_url)
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
