"""GitHub CI end to end through a disposable reader and fake executables."""
import json
import os
from http.server import ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request

import pytest

import machine
from agents_service import AgentsService, outcome
from ci_service import CI_SOURCE_ID, CIService
from ci_workspace import PREFERENCE
from github_ci import GitHubError
from install_reader import install
from owner_auth import OwnerAuth, authenticated_open
import server
from sources_service import SourcesService
from test_sources import NOW, Reader

CI = '/api/sources/v1/ci'
STAMP = NOW.isoformat()

GIT = """
import sys
from pathlib import Path
args = sys.argv[1:]
workspace = Path.cwd().name
if workspace == 'not-a-repo':
    print('fatal: not a git repository', file=sys.stderr)
    sys.exit(128)
if workspace == 'unreadable':
    print('fatal: unable to read repo', file=sys.stderr)
    sys.exit(128)
if args[:1] == ['symbolic-ref']:
    if workspace == 'detached':
        sys.exit(1)
    print('feature/session')
elif args[3].startswith('branch.'):
    sys.exit(1)
elif args[3] == 'remote.origin.url':
    if len(args) != 5 or not args[4].startswith('^(https://github'):
        sys.exit(6)
    print('git@github.com:demo/kestrel.git')
else:
    sys.exit(6)
"""

GH = """
import json, os, sys
from pathlib import Path

assert set(os.environ).isdisjoint(('GH_TOKEN', 'GITHUB_TOKEN', 'GH_DEBUG', 'HTTPS_PROXY'))
args = sys.argv[1:]
options = json.loads(Path(__file__).with_name('response.json').read_text())
if args[0] == 'config':
    assert args[1] == 'get' and args[-2:] == ['--host', 'github.com']
    if options.get('override'):
        print('override')
    sys.exit(0)
assert args[0] == 'api' and args[2:4] == ['--hostname', 'github.com']
if options.get('signed_out'):
    print('Authenticate with gh auth login', file=sys.stderr)
    sys.exit(4)
if options.get('not_found'):
    print(json.dumps({'data':{'repository':None},'errors':[{'type':'NOT_FOUND','path':['repository']}]}))
    sys.exit(1)
stamp = options['stamp']
repo = 'demo/kestrel'
if args[1] == 'graphql':
    query = next(arg for arg in args if arg.startswith('query='))
    sha = options['sha'] * 40
    assert 'mutation' not in query and 'owner=demo' in args and 'repo=kestrel' in args
    def connection(nodes):
        return {'nodes':nodes,'pageInfo':{'hasNextPage':False}}
    def pull(branch, number=17, **updates):
        return {'number':number,'updatedAt':stamp,'state':'OPEN','isDraft':False,
            'title':'Fix the build', 'reviewDecision':None,'mergeable':'MERGEABLE',
            'mergeStateStatus':'CLEAN','headRefName':branch,
            'headRepository':{'nameWithOwner':repo},
            'statusCheckRollup':{'state':'SUCCESS'},'author':{'login':'helper'},
            'reviewRequests':connection([]), **updates}
    if 'viewer { login }' in query:
        requests = connection([{'requestedReviewer':{'login':'owner'}}])
        reads = [
            dict(pull('feature/session'), reviewRequests=requests),
            dict(pull('unwatched',18), author={'login':'owner'}, reviewDecision='APPROVED'),
            dict(pull('unwatched',19), author={'login':'owner'}, reviewDecision='CHANGES_REQUESTED'),
            dict(pull('unwatched',20), author={'login':'owner'}),
            dict(pull('unwatched',21), author={'login':'owner'}, isDraft=True),
            pull('not-watched-and-not-authored',22),
            pull('feature/session',23,reviewDecision='APPROVED',statusCheckRollup={'state':'FAILURE'}),
            pull('feature/session',24,reviewDecision='APPROVED',mergeable='CONFLICTING',mergeStateStatus='DIRTY'),
            pull('feature/session',25,reviewDecision='APPROVED',statusCheckRollup={'state':'PENDING'}),
        ]
        print(json.dumps({'data':{'viewer':{'login':'owner'},
            'repository':{'pullRequests':connection(reads)}}}))
    else:
        branch = next(arg.split('=',1)[1] for arg in args if arg.startswith('branch='))
        completed = options['ci'] != 'running'
        conclusion = {'failed':'FAILURE','passed':'SUCCESS','running':None}[options['ci']]
        if branch != 'feature/session':
            completed, conclusion = True, 'SUCCESS'
        checks = [{'__typename':'CheckRun','status':'COMPLETED' if completed else 'IN_PROGRESS',
                   'conclusion':conclusion,'startedAt':stamp,'completedAt':stamp if completed else None}]
        assert 'tipDeployments: deployments' in query
        assert 'deployments(first: 30' in query
        deploy = {'ref':None,'createdAt':stamp,'latestEnvironment':'Preview','originalEnvironment':'Preview',
                  'latestStatus':{'state':'SUCCESS','createdAt':stamp}}
        ref = {'target':{'oid':sha,'statusCheckRollup':{'contexts':connection(checks)},
                         'tipDeployments':connection([deploy])},
            'associatedPullRequests':connection([{'number':17,'headRefOid':sha,'repository':{'nameWithOwner':repo},'statusCheckRollup':None}])}
        data = {'ref':None if options.get('deleted_branch') else ref, 'deployments':connection([])}
        if 'ended=true' in args:
            data['historical'] = connection([dict(pull(branch), state='MERGED', title=options['unsafe_title'])])
        print(json.dumps({'data':{'repository':data}}))
else:
    sys.exit(6)
"""


@pytest.fixture
def fake_cli(tmp_path, monkeypatch):
    binary = tmp_path/'bin'
    binary.mkdir()
    for name, body in [('git', GIT), ('gh', GH)]:
        executable = binary/name
        executable.write_text(f'#!{sys.executable}\n'+body)
        executable.chmod(0o700)
    monkeypatch.setenv('PATH', str(binary))
    monkeypatch.setenv('GH_DEBUG', 'must-not-inherit')
    monkeypatch.setenv('HTTPS_PROXY', 'must-not-inherit')
    response = {'ci':'failed','sha':'a','stamp':STAMP,'unsafe_title':str(tmp_path)}

    def set_response(**values):
        response.update(values)
        (binary/'response.json').write_text(json.dumps(response))

    set_response()
    return binary, set_response


class WorkspaceReader(Reader):
    def __init__(self, root, worktree):
        super().__init__()
        self.root, self.worktree = root, worktree
        self.rows[0].update(worktreePath=str(worktree), branch='feature/session',
                            pendingRuntimeRequest={'kind':'user_input','blocking':True})
        self.rows += [
            {'id':'b','projectId':'p','title':'Other agent','status':'running','updatedAt':STAMP},
            {'id':'c','projectId':'p','title':'Finished agent','status':'completed',
             'updatedAt':STAMP,'latestRunCompletedAt':STAMP,'branch':'feature/session'},
        ]

    def shell(self):
        descriptor, shell = super().shell()
        shell['projects'][0]['workspaceRoot'] = str(self.root)
        return descriptor, shell


@pytest.fixture
def local_reader(tmp_path):
    home = Path.home()
    data = home/'data'
    root, worktree = tmp_path/'repo', tmp_path/'worktree'
    root.mkdir()
    worktree.mkdir()
    upstream = WorkspaceReader(root, worktree)
    legacy = AgentsService(data, lambda _: upstream, lambda: NOW)
    legacy.store.mutate('nagi-t3.json', {}, lambda value:value.update(
        version=1, origin='http://127.0.0.1:3773', credentialFile=str(data/'unused.json')))
    source = SourcesService(legacy, local_home=home)
    source.ci.monotonic = Monotonic()
    with ThreadingHTTPServer(('127.0.0.1',0), server.Handler) as httpd:
        httpd.service, httpd.sources, httpd.owner_auth = legacy, source, OwnerAuth(data)
        worker = threading.Thread(target=httpd.serve_forever,daemon=True)
        worker.start()
        origin = f'http://127.0.0.1:{httpd.server_port}'

        def api(path, body=None):
            request = Request(origin+path, data=json.dumps(body).encode() if body is not None else None,
                              headers={'Content-Type':'application/json','X-Progress-Desk':'1'})
            with authenticated_open(request, data, timeout=2) as response:
                return json.load(response)

        try:
            yield source, api, httpd.server_port
        finally:
            httpd.shutdown()
            worker.join(timeout=2)
            source.close()


class Monotonic:
    now = 0

    def __call__(self):
        return self.now


def poll(source):
    source.poll(force=True)
    if source.ci.future:
        source.ci.future.result(timeout=8)


def repoll(source):
    ci = source.ci
    ci.monotonic.now = max(ci.due, *(s.due for s in [*ci.branches.values(), *ci.pulls.values()]), 0) + 1
    ci.schedule()
    source.ci.future.result(timeout=8)


def test_watched_ci_and_notification_survive_reservation_and_restart(fake_cli, local_reader, tmp_path):
    source, api, _ = local_reader
    _, set_response = fake_cli
    assert api(CI+'/settings') == {'version':1,'enabled':False}
    assert api(CI)['ci']['reason'] == 'disabled'
    assert source.ci.future is None
    with pytest.raises(HTTPError) as denial:
        from urllib.request import urlopen
        urlopen(f'http://127.0.0.1:{local_reader[2]}'+CI+'/settings',timeout=1)
    assert denial.value.code == 401
    with pytest.raises(HTTPError) as malformed:
        api(CI+'/settings', {'enabled':1})
    assert malformed.value.code == 400

    api(CI+'/settings',{'enabled':True})
    poll(source)
    repoll(source)
    snapshot = api(CI)['ci']
    assert snapshot['status'] == 'ok'
    assert len(snapshot['data']['rows']) == 1
    row = snapshot['data']['rows'][0]
    assert set(row['agentIds']) == {'a','b','c'}
    assert row['pr'] == {'number':17,'url':'https://github.com/demo/kestrel/pull/17'}
    assert row['ci']['data']['state'] == 'failed'
    assert row['ci']['data']['failed'] == 1
    assert row['deploy']['data']['state'] == 'success'
    assert str(tmp_path) not in json.dumps(snapshot)

    endpoint = '/api/sources/v1/notifications'
    recorded = api(endpoint)['events']
    assert len(recorded) == 1
    event = recorded[0]
    assert event['sourceId'] == CI_SOURCE_ID
    assert event['event']['kind'] == 'ci_failed'
    from linux.agent_notifications import banner, valid_event
    from linux.tray import read_ci_failed
    assert valid_event(event['event'])
    assert banner(event['event']) == ('demo/kestrel','CI checks failed.')
    assert read_ci_failed(f'http://127.0.0.1:{local_reader[2]}',
                          lambda request, *, timeout: authenticated_open(request, source.directory, timeout=timeout))
    request = {'sourceId':CI_SOURCE_ID,'id':event['event']['id']}
    lease = api(endpoint+'/reserve', request)['lease']
    assert not api(endpoint)['events']
    assert api(endpoint+'/release',dict(request,reservation=lease['reservation']))['released']
    lease = api(endpoint+'/reserve', request)['lease']
    assert api(endpoint+'/claim',dict(request,reservation=lease['reservation']))['claimed']

    set_response(ci='running')
    repoll(source)
    assert api(CI)['ci']['data']['rows'][0]['ci']['data']['state'] == 'running'
    set_response(ci='passed')
    repoll(source)
    assert api(CI)['ci']['data']['rows'][0]['ci']['data']['state'] == 'passed'
    set_response(ci='failed')
    repoll(source)
    assert api(endpoint)['events'] == []

    restarted = SourcesService(source.legacy, local_home=source.local_home)
    restarted.ci.monotonic = Monotonic()
    try:
        poll(restarted)
        assert restarted.ci.settings()['enabled']
        assert not restarted.ci.delivery.notifications()
        set_response(sha='b')
        repoll(restarted)
        assert len(restarted.ci.delivery.notifications()) == 1
    finally:
        restarted.close()
    assert str(tmp_path) not in (source.directory/'nagi-source-github-ci-state.json').read_text()


def test_attention_prs_and_ended_results_include_merge_state(fake_cli, local_reader, tmp_path):
    source, api, _ = local_reader
    _, response = fake_cli
    response(deleted_branch=True)
    api(CI+'/settings',{'enabled':True})
    poll(source)
    repoll(source)
    pulls = api(CI+'/pulls')['pulls']['data']
    assert pulls['count'] == 3 and pulls['omitted'] is False
    assert {row['number']:row['why'] for row in pulls['rows']} == {
        17:'review_requested',18:'ready_to_merge',19:'changes_requested'}
    ended = api(CI+'/ended')['ended']['data']
    assert ended['rows'] == [{'agentId':'c','repo':'demo/kestrel','number':17,
                               'title':'Pull request #17','url':'https://github.com/demo/kestrel/pull/17',
                               'ci':'passed','mergeState':'merged','updatedAt':STAMP}]
    assert str(tmp_path) not in json.dumps(ended)
    assert api(CI)['ci']['status'] == 'quiet'
    assert api('/api/sources/v1/status')['ci']['state'] == 'ok'


def test_setup_and_github_failures_are_closed(fake_cli, local_reader):
    source, api, _ = local_reader
    binary, set_response = fake_cli
    set_response(signed_out=True)
    api(CI+'/settings',{'enabled':True})
    poll(source)
    repoll(source)
    reading = api(CI)['ci']['data']['rows'][0]['ci']
    assert reading == {'status':'not_set_up','attemptedAt':STAMP,'checkedAt':None,
                       'reason':'gh_signed_out','data':None}
    assert api(CI+'/pulls')['pulls']['reason'] == 'gh_signed_out'
    set_response(signed_out=False,not_found=True)
    repoll(source)
    assert api(CI)['ci']['data']['rows'][0]['ci']['reason'] == 'repo_not_found'
    set_response(not_found=False,override=True)
    repoll(source)
    assert api(CI)['ci']['reason'] == 'cannot_reach_github'
    (binary/'gh').unlink()
    repoll(source)
    assert api(CI)['ci']['reason'] == 'gh_missing'


def test_status_launcher_uses_real_owner_proof_and_machine_snapshot(fake_cli, local_reader, monkeypatch):
    source, api, port = local_reader
    monkeypatch.delenv('NAGI_DATA_DIR',raising=False)
    monkeypatch.delenv('NAGI_PORT',raising=False)
    _, set_response = fake_cli
    set_response(ci='failed')
    api(CI+'/settings',{'enabled':True})
    poll(source)
    repoll(source)
    monkeypatch.setattr(machine,'read_load',lambda _:{
        'cpuLoadPercent':40.0,'memoryPressurePercent':70.0,'gpu':None})
    source.machine.poll()
    assert api('/api/sources/v1/machine')['machine']['data']['gpu'] is None
    install(sys.platform, source.directory, port, sys.executable, source.local_home)
    launcher = source.local_home/'.local/bin/nagi'

    def execute(*args):
        return subprocess.run([str(launcher),'status',*args],capture_output=True,text=True,timeout=2)

    future = NOW.replace(hour=NOW.hour+1).isoformat()
    claude = {'id':'account','label':'Claude 1','windows':[{
        'remainingPercent':12,'checkedAt':STAMP,'resetsAt':future}]}
    source.legacy.providers['claude'] = outcome('ok',STAMP,STAMP,data={'accounts':[claude]})
    assert execute().stdout.strip() == '2 running · 1 asks you · CI ✗ kestrel · Claude 12%'
    waybar = json.loads(execute('--waybar').stdout)
    assert waybar['class'] == ['asks-you','ci-failed']
    data = json.loads(execute('--json').stdout)
    assert data['agents'] == {'running':2,'waitingOnYou':1,'stuck':0}
    assert data['machine']['data'] == {'cpuLoadPercent':40.0,'memoryPressurePercent':70.0,'gpu':None}
    assert execute('--quiet').returncode == 1
    import socket
    with socket.socket() as unused:
        unused.bind(('127.0.0.1',0))
        closed_port = str(unused.getsockname()[1])
        assert execute('--port',closed_port).stdout.strip() == 'nagi ?'
        assert execute('--port',closed_port,'--quiet').returncode == 2
        unused.listen(2)  # Accept a connection in the kernel and never answer the HMAC challenge.
        started = time.monotonic()
        assert execute('--port',closed_port).stdout.strip() == 'nagi ?'
        assert time.monotonic()-started < 1.2


def test_claude_hook_passes_only_normalized_workspace(fake_cli, tmp_path):
    from nagi_store import LocalStore
    data = Path.home()/'data'
    store = LocalStore(data)
    store.mutate(PREFERENCE, {}, lambda value:value.update(enabled=True))
    source = 'c'*32
    cwd = tmp_path/'workspace'
    cwd.mkdir()
    hook = Path(__file__).resolve().parents[1]/'claude_hook.py'
    input_event = {'hook_event_name':'UserPromptSubmit','session_id':'s','cwd':str(cwd)}
    env = {**os.environ,'CLAUDE_CODE_ENTRYPOINT':'cli'}
    env.pop('CLAUDE_AGENT_SDK_VERSION',None)
    result = subprocess.run([sys.executable,'-I','-B',str(hook),str(data),source],
                            input=json.dumps(input_event),text=True,capture_output=True,timeout=2,env=env)
    assert (result.returncode,result.stdout,result.stderr) == (0,'','')
    raw = (data/f'claude-{source}.jsonl').read_text()
    assert str(cwd) not in raw
    assert json.loads(raw)['github'] == ['demo/kestrel','feature/session']


def test_machine_projection_and_partial_sampler(monkeypatch):
    monkeypatch.setattr(machine,'cpu_load',lambda _:121.5)
    monkeypatch.setattr(machine,'linux_memory',lambda:(100, 69))
    monkeypatch.setattr(machine.shutil,'which',lambda *a,**kw:'/dev/null')
    monkeypatch.setattr(machine,'machine_command',lambda _: '40, 100, 200\n99, 180, 300\n')
    result = machine.read_load('linux')
    assert result == {'cpuLoadPercent':121.5,'memoryPressurePercent':69.0,
                      'gpu':{'utilizationPercent':99,'memoryUsedBytes':280*1024**2,
                             'memoryTotalBytes':500*1024**2}}
    monkeypatch.setattr(machine,'machine_command',lambda _: 'N/A, 100, 200\n')
    assert machine.read_load('linux')['gpu'] is None



def test_unwatchable_workspaces_are_quiet_but_git_read_errors_are_partial(fake_cli, tmp_path):
    from nagi_store import LocalStore
    from status_summary import ci_summary
    for name in ('not-a-repo', 'detached', 'unreadable'):
        (tmp_path/name).mkdir()
    locations = [('old-claude', 'active', None),
                 ('folder', 'active', (str(tmp_path/'not-a-repo'), 'main', None)),
                 ('detached', 'active', (str(tmp_path/'detached'), None, None))]
    time_source = Monotonic()
    ci = CIService(LocalStore(Path.home()/'data'), Path.home(), lambda:NOW,
                   lambda:(locations, False), monotonic=time_source)
    try:
        ci.configure(True)
        ci.schedule()
        ci.future.result(timeout=3)
        assert ci.read()['status'] == 'quiet'
        assert ci.read()['data'] == {'rows':[], 'omitted':False}
        assert ci_summary(ci.read()) == {'state':'ok', 'failedRepos':[]}

        locations.append(('unreadable', 'active', (str(tmp_path/'unreadable'), None, None)))
        time_source.now = 30
        ci.schedule()
        ci.future.result(timeout=3)
        assert ci.read()['reason'] == 'coverage_incomplete'
        assert ci_summary(ci.read())['state'] == 'unknown'
    finally:
        ci.close(wait=True)


@pytest.fixture
def scheduled_ci(monkeypatch):
    from nagi_store import LocalStore
    import ci_service

    attempts, pull_attempts = [], []
    rows, states, problems = [], {}, {}
    time_source = Monotonic()

    class GitHubFixture:
        stop_reason = None

        def __init__(self, *_):
            pass

        def checks(self, repo, branch, ended):
            key = repo, branch
            attempts.append((time_source.now, key, ended))
            if reason := problems.get(key):
                if reason in ('gh_signed_out', 'rate_limited'):
                    self.stop_reason = reason
                raise GitHubError(reason)
            check, deploy = states.get(key, ('passed', None))
            return ('a'*40, None, {'state':check}, {'state':deploy} if deploy else None, None, False)

        def waiting_pulls(self, repo, _):
            pull_attempts.append((time_source.now, repo))
            return [], False

    monkeypatch.setattr(ci_service, 'GitHub', GitHubFixture)
    ci = CIService(LocalStore(Path.home()/'data'), Path.home(), lambda:NOW,
                   lambda:(rows, False), monotonic=time_source)
    ci.configure(True)

    def run(at):
        time_source.now = at
        ci.schedule()
        if ci.future:
            ci.future.result(timeout=3)
        return {key for time, key, _ in attempts if time == at}

    try:
        yield ci, rows, states, problems, pull_attempts, run
    finally:
        ci.close(wait=True)


def watch(rows, repo, branch, mode='active'):
    rows.append((branch, mode, [repo, branch]))
    return repo, branch


def test_fast_polls_are_branch_local_and_expire_for_stalled_work(scheduled_ci):
    ci, rows, states, _, pulls, run = scheduled_ci
    running = watch(rows, 'demo/app', 'expected-check')
    deploying = watch(rows, 'demo/app', 'pending-deploy')
    passing = watch(rows, 'demo/app', 'passing')
    ended = watch(rows, 'demo/finished', 'ended', 'ended')
    states[running] = 'running', None
    states[deploying] = 'passed', 'pending'
    assert run(0) == {running, deploying, passing, ended}
    assert run(30) == {running, deploying}
    assert run(60) == {running, deploying}
    assert run(120) == {running, deploying, passing}
    assert sorted(pulls) == [(0, 'demo/app'), (0, 'demo/finished'), (120, 'demo/app')]
    assert run(600) == {running, deploying, passing, ended}
    assert run(630) == set()
    assert ci.branches[ended].due == 1200
    assert ci.branches[running].due == ci.branches[deploying].due == 720
    assert run(720) == {running, deploying, passing}


def test_a_bad_repo_has_its_own_backoff(scheduled_ci):
    ci, rows, states, problems, _, run = scheduled_ci
    good = watch(rows, 'demo/good', 'running')
    bad = watch(rows, 'demo/bad', 'unreachable')
    states[good] = 'running', None
    problems[bad] = 'repo_not_found'
    assert run(0) == {good, bad}
    assert ci.due == 30
    assert run(30) == {good}
    assert run(60) == {good, bad}
    assert run(90) == {good}
    assert ci.branches[bad].due == 180
    assert ci.read()['data']['rows'][1]['ci']['reason'] == 'repo_not_found'

    problems[good] = 'cannot_reach_github'
    assert run(120) == {good}
    assert ci.due == 180
    assert run(150) == set()


@pytest.mark.parametrize('reason,intervals', [('gh_signed_out',(60,120,180,180)),
                                              ('rate_limited',(240,480,960,1800))])
def test_global_errors_back_off_all_rows_and_allow_recovery(scheduled_ci, reason, intervals):
    ci, rows, states, problems, _, run = scheduled_ci
    rate_limited = watch(rows, 'demo/bad', 'bad')
    healthy = watch(rows, 'demo/good', 'healthy')
    states[healthy] = 'running', None
    problems[rate_limited] = reason
    at = 0
    for interval in intervals:
        attempted = run(at)
        assert rate_limited in attempted
        assert ci.due == at + interval
        assert run(ci.due-1) == set()
        at += interval
    problems.clear()
    assert run(at) == {healthy, rate_limited}
    assert ci.due == at + 30


def test_a_quiet_cursor_does_not_make_local_t3_partial():
    from status_summary import agent_counts
    def source(harness, environment, running):
        return {'source':{'harness':harness,'placement':'local'},'agents':{
            'status':'ok','data':{'environmentId':environment,'counts':{
                'running':running,'waitingOnYou':0,'stuck':0}}}}
    totals, partial = agent_counts([source('t3','t3',2),source('cursor','cursor',0)])
    assert totals['running'] == 2 and partial is False
    totals, partial = agent_counts([source('t3','t3',2),source('cursor','cursor',1)])
    assert totals['running'] == 2 and partial is True



def test_deployments_choose_the_newest_branch_or_sha_match():
    from github_ci import deployment
    old = {'createdAt':'2026-11-13T10:00:00Z','latestEnvironment':'Preview','originalEnvironment':None,
           'latestStatus':{'state':'SUCCESS','createdAt':'2026-11-13T10:01:00Z'},'ref':None}
    branch = dict(old, createdAt='2026-11-13T11:00:00Z',
                  ref={'prefix':'refs/heads/','name':'feature'}, latestEnvironment='Branch Preview')
    tag = dict(old, createdAt='2026-11-13T12:00:00Z', ref={'prefix':'refs/tags/','name':'feature'})
    repo = {'nodes':[tag, branch], 'pageInfo':{'hasNextPage':False}}
    matches = deployment('demo/kestrel','feature',repo,{'nodes':[old]})
    assert matches['environment'] == 'Branch Preview'
    matches = deployment('demo/kestrel','feature',repo,{'nodes':[dict(old, createdAt='2026-11-13T13:00:00Z')]})
    assert matches['environment'] == 'Preview'


def test_required_check_without_any_jobs_keeps_branch_pending():
    from github_ci import check_rollup
    rollup = {'state':'EXPECTED','contexts':{'nodes':[],'pageInfo':{'hasNextPage':False}}}
    projected = check_rollup(rollup,'https://github.com/demo/kestrel/actions')
    assert projected['state'] == 'running'
    assert projected['total'] == projected['running'] == 0
