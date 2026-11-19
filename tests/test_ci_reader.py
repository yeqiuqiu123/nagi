"""GitHub CI end to end through a disposable reader and fake executables."""
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
import threading
from urllib.error import HTTPError
from urllib.request import Request

import pytest

import machine
from agents_service import AgentsService
from ci_service import CI_SOURCE_ID
from install_reader import install
from owner_auth import OwnerAuth, authenticated_open
import server
from sources_service import SourcesService
from test_sources import NOW, Reader

CI = '/api/sources/v1/ci'
STAMP = NOW.isoformat()

GIT = """
import sys
args = sys.argv[1:]
if args[:1] == ['symbolic-ref']:
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
        ref = {'target':{'oid':sha,'statusCheckRollup':{'contexts':connection(checks)}},
            'associatedPullRequests':connection([{'number':17,'headRefOid':sha,'isCrossRepository':False}])}
        data = {'ref':None if options.get('deleted_branch') else ref}
        if 'ended=true' in args:
            data['historical'] = connection([dict(pull(branch), state='MERGED', title=options['unsafe_title'])])
        print(json.dumps({'data':{'repository':data}}))
elif args[1].startswith('repos/'+repo+'/deployments?'):
    import urllib.parse
    ref = urllib.parse.parse_qs(args[1].split('?')[1])['ref'][0]
    print(json.dumps([{'ref':ref,'id':11,'environment':'Preview','created_at':stamp}]))
elif args[1]=='repos/'+repo+'/deployments/11/statuses?per_page=1':
    print(json.dumps([{'state':'success','created_at':stamp,'environment':'Preview'}]))
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


def poll(source):
    source.poll(force=True)
    if source.ci.future:
        source.ci.future.result(timeout=8)


def repoll(source):
    source.ci.due = 0
    source.ci.schedule()
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
    assert pulls['count'] == 4 and pulls['omitted'] is False
    assert {row['number']:row['why'] for row in pulls['rows']} == {
        17:'review_requested',18:'ready_to_merge',19:'changes_requested',20:'ready_to_merge'}
    ended = api(CI+'/ended')['ended']['data']
    assert ended['rows'] == [{'agentId':'c','repo':'demo/kestrel','number':17,
                               'title':'Pull request #17','url':'https://github.com/demo/kestrel/pull/17',
                               'ci':'passed','mergeState':'merged','updatedAt':STAMP}]
    assert str(tmp_path) not in json.dumps(ended)
    assert api(CI)['ci']['data']['rows'][0]['ci']['reason'] == 'branch_unavailable'


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
    set_response(signed_out=False,override=True)
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

    assert execute().stdout.strip() == '2 running · 1 asks you · CI ✗ kestrel'
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
