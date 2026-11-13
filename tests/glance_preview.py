"""Disposable glance states for review: the real reader, projection and HTTP code,
fed by a synthetic T3 source with fictional titles. Never reads T3 or real data.

Run: python3 -B tests/glance_preview.py [--port 47870]
Prints one JSON line {scenario: {"origin", "dataDir"}}; each scenario is its own
loopback reader with a temporary data directory. Ctrl-C (or SIGTERM) stops them all.
Mint a page with owner_auth.launch_url(origin, '/glance', dataDir).
"""
import argparse
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import signal
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import server
from agents_service import AgentsService
from owner_auth import OwnerAuth
from t3_reader import NotConfigured, Unavailable


def iso(at):
    return at.isoformat()


def thread(identity, project, title, status, *, start, active, model='gpt-6.1-sol', provider='codex', parent=None, ended=None, request=None):
    row = {'id': identity, 'projectId': project, 'title': title, 'status': status, 'updatedAt': iso(active),
           'latestRunId': 'run-' + identity, 'latestRunStartedAt': iso(start), 'providerInstanceId': provider,
           'modelSelection': {'model': model}}
    if parent:
        row['lineage'] = {'parentThreadId': parent}
    if ended:
        row['latestRunCompletedAt'] = iso(ended)
    if request:
        row['pendingRuntimeRequest'] = request
    return row


PROJECTS = [{'id': 'harbor', 'title': 'Harbor Website'}, {'id': 'ledger', 'title': 'Ledger'}, {'id': 'atlas', 'title': 'Atlas'}]
OPUS = 'claude-opus-5-5'


def calm(now):
    m = lambda n: now - timedelta(minutes=n)
    s = lambda n: now - timedelta(seconds=n)
    rows = [
        thread('h-parent', 'harbor', 'Harbor booking flow overhaul', 'completed', start=m(14), active=m(10), model=OPUS, provider='claudeAgent', ended=m(10)),
        thread('h-child', 'harbor', 'Harbor: Card checkout and receipt emails', 'running', start=m(7), active=s(3), parent='h-parent'),
        thread('l-parent', 'ledger', 'Resume Ledger v2 reconciliation', 'completed', start=m(240), active=m(200), model=OPUS, provider='claudeAgent', ended=m(200)),
        thread('l-child', 'ledger', 'Ledger CI: fix the nightly import suite failures (run 4410)', 'running', start=m(209), active=s(9), parent='l-parent'),
        thread('a-top', 'atlas', 'Atlas map tiles and offline cache', 'running', start=m(6), active=s(1), model=OPUS, provider='claudeAgent'),
    ]
    for i in range(6):
        rows.append(thread(f'h-done-{i}', 'harbor', 'Harbor copy review pass', 'completed', start=m(300 + i), active=m(290 - i), ended=m(290 - i), parent='h-parent'))
    for i in range(3):
        rows.append(thread(f'l-fail-{i}', 'ledger', 'Ledger schema probe', 'failed', start=m(130), active=m(120 - i), ended=m(120 - i), parent='l-parent'))
    rows.append(thread('a-stop', 'atlas', 'Atlas tile renderer spike', 'interrupted', start=m(50), active=m(41), ended=m(41), model=OPUS, provider='claudeAgent'))
    rows.append(thread('a-done', 'atlas', 'Atlas release notes', 'completed', start=m(70), active=m(60), ended=m(60), model=OPUS, provider='claudeAgent'))
    return rows


def window(identity, label, minutes, used, resets, checked):
    return {'id': identity, 'label': label, 'windowDurationMins': minutes, 'usedPercent': used, 'resetsAt': iso(resets), 'checkedAt': iso(checked)}


def providers(now, codex_fails=False):
    checked = now - timedelta(minutes=2)
    codex = [{'instanceId': 'codex', 'driver': 'codex', 'enabled': True, 'installed': True,
              'usageLimits': {'unavailable': {'reason': 'probe_failed'}} if codex_fails else
              {'checkedAt': iso(checked), 'windows': [window('primary', 'Weekly', 10080, 100, now + timedelta(days=3, hours=15), checked)]}},
             {'instanceId': 'codex_secondary', 'driver': 'codex', 'enabled': True, 'installed': True,
              'usageLimits': {'unavailable': {'reason': 'probe_failed'}} if codex_fails else
              {'checkedAt': iso(checked), 'windows': [window('primary', 'Weekly', 10080, 33, now + timedelta(days=1, hours=15), checked)]}}]
    claude = {'instanceId': 'claudeAgent', 'driver': 'claudeAgent', 'enabled': True, 'installed': True,
              'usageLimits': {'checkedAt': iso(checked), 'windows': [
                  window('five_hour', 'Session', 300, 4, now + timedelta(hours=1), checked),
                  window('seven_day', 'Weekly', 10080, 9, now + timedelta(days=1, hours=17), checked),
                  window('seven_day_fable', 'Weekly · Fable', 10080, 3, now + timedelta(days=1, hours=17), checked)]}}
    return codex + [claude]


class Source:
    """A synthetic T3 shell + config, shaped like the protocol-2 reader."""
    def __init__(self, rows, provider_list, failure=None, block=False, environment='preview:1'):
        self.rows, self.providers, self.failure, self.environment = rows, provider_list, failure, environment
        self.gate = threading.Event()
        if not block:
            self.gate.set()

    def shell(self):
        self.gate.wait()
        if self.failure:
            raise self.failure('synthetic')
        return {'environmentId': self.environment}, {'projects': copy.deepcopy(PROJECTS), 'threads': copy.deepcopy(self.rows)}

    def config(self):
        return {'providers': copy.deepcopy(self.providers)}

    def detail(self, identity):
        return {'hasMoreHistory': False, 'projection': {'turnItems': []}}


def scenarios(now):
    m = lambda n: now - timedelta(minutes=n)
    out = {}
    out['calm'] = Source(calm(now), providers(now))
    stuck = calm(now)
    # A stuck Claude row beside a running Claude row: silence yellow against Claude terracotta.
    stuck[4]['updatedAt'] = iso(now - timedelta(minutes=17, seconds=4))
    stuck.append(thread('a-run', 'atlas', 'Atlas: Offline tile index migration', 'running', start=m(4), active=now - timedelta(seconds=6), model=OPUS, provider='claudeAgent'))
    out['stuck'] = Source(stuck, providers(now))
    asks = calm(now)
    asks[4]['updatedAt'] = iso(m(4))
    asks[4]['pendingRuntimeRequest'] = {'kind': 'user_input'}
    out['asks'] = Source(asks, providers(now))
    both = copy.deepcopy(stuck)
    both[4]['updatedAt'] = iso(m(4))
    both[4]['pendingRuntimeRequest'] = {'kind': 'approval'}
    out['both'] = Source(both, providers(now))
    out['unreachable'] = Source(calm(now - timedelta(minutes=3)), providers(now - timedelta(minutes=3)))
    out['never'] = Source([], [], failure=Unavailable)
    out['notpaired'] = Source([], [], failure=NotConfigured)
    out['checking'] = Source([], [], block=True)
    out['limits'] = Source(calm(now), providers(now, codex_fails=True))
    out['quiet'] = Source([r for r in calm(now) if r['status'] != 'running' and r['id'] not in ('h-parent', 'l-parent')]
                          + [thread('h-parent', 'harbor', 'Harbor booking flow overhaul', 'completed', start=m(30), active=m(19), model=OPUS, provider='claudeAgent', ended=m(19))], providers(now))
    out['empty'] = Source([], providers(now))
    over = calm(now)
    over += [
        thread('l-child2', 'ledger', 'Ledger: Split the importer into streaming stages so large statement files stop timing out', 'running', start=m(25), active=m(6), parent='l-parent'),
        thread('l-child3', 'ledger', 'Ledger: Audit currency rounding against the bank export', 'running', start=m(3), active=m(1), parent='l-parent', model=OPUS, provider='claudeAgent'),
        thread('h-child2', 'harbor', 'Harbor: Accessibility pass on the booking calendar keyboard paths', 'running', start=m(12), active=now - timedelta(seconds=40), parent='h-parent'),
        thread('a-parent2', 'atlas', 'Atlas search relevance study', 'completed', start=m(90), active=m(80), model=OPUS, provider='claudeAgent', ended=m(80)),
        thread('a-child2', 'atlas', 'Atlas: Rebuild the place-name index with transliteration variants', 'running', start=m(18), active=m(8), parent='a-parent2'),
        thread('a-queued', 'atlas', 'Atlas: Re-run the tile cache warm-up', 'queued', start=m(1), active=m(1), parent='a-parent2'),
    ]
    over[3]['updatedAt'] = iso(now - timedelta(minutes=17, seconds=4))
    out['overflow'] = Source(over, providers(now))
    return out


PEERS = [{'addresses': ['100.80.1.2'], 'dns': 'studio.tail.ts.net', 'label': 'Studio Mac', 'online': True},
         {'addresses': ['100.80.1.3'], 'dns': 'office.tail.ts.net', 'label': 'Office Linux', 'online': False}]
REMOTE_ROWS = lambda now: [thread('r-top', 'ledger', 'Ledger: Quarterly close checklist', 'running', start=now - timedelta(minutes=22),
                                  active=now - timedelta(seconds=30), model=OPUS, provider='claudeAgent')]


def source_service(directory, now, scenario):
    """A real SourcesService with fake discovery, issuing and readers: no T3, no Tailscale."""
    from sources_service import SourcesService
    from sources_transport import SourceError, write_credential
    legacy = AgentsService(directory, lambda _d: Source([], []), lambda: datetime.now(timezone.utc))
    local = Source(calm(now), providers(now), environment='preview:local')
    remote = Source(REMOTE_ROWS(now), providers(now, codex_fails=True), environment='preview:remote')

    def detector(origin):
        if scenario == 'src-errors' and '127.0.0.1' in origin:
            raise Unavailable('not running')
        return {'environmentId': 'preview:local' if '127.0.0.1' in origin else 'preview:remote', 'orchestrationProtocolVersion': 2}

    def exchange(*_args):
        if scenario == 'src-errors':
            raise SourceError('pairing_invalid', 422)
        return 'synthetic-observer-access-token'

    service = SourcesService(legacy, detector=detector, inventory=lambda: copy.deepcopy(PEERS),
                             issuer=lambda path: write_credential(path, 'synthetic-observer-access-token'), exchange=exchange,
                             reader_factory=lambda policy: local if '127.0.0.1' in policy['origin'] else remote)
    owner = 'preview-owner'
    if scenario == 'src-firstread':
        # Another computer connects (its one verifying read succeeds), then every read after fails.
        verified = remote.shell
        def first_then_fail():
            remote.shell = lambda: (_ for _ in ()).throw(Unavailable('synthetic'))
            return verified()
        remote.shell = first_then_fail
    if scenario == 'src-multiapp':
        # Fixture only: pretend a second app (Pi) is available so setup can be exercised with
        # several apps. Production's catalog is untouched; Pi's own test still refuses honestly.
        honest = service.catalog
        def catalog():
            value = honest()
            for item in value['harnesses']:
                if item['id'] == 'pi':
                    item.update(available=True, status='available', capabilities={**item['capabilities'], 'agents': True, 'limits': True})
            return value
        service.catalog = catalog
    if scenario in ('src-single', 'src-multi'):
        configuration = {'adapterId': 't3', 'label': 'This computer', 'placement': {'kind': 'local'}, 'mode': 'protocol2', 'options': {'port': 3773}}
        tested = service.test({'configuration': configuration}, owner)
        service.connect({'testId': tested['testId'], 'expectedRevision': 0}, owner)
    if scenario == 'src-multi':
        peer = service.discover({'adapterIds': ['t3'], 'placement': {'kind': 'tailscale'}}, owner)['peers'][0]['peerRef']
        configuration = {'adapterId': 't3', 'label': 'Computer 2', 'placement': {'kind': 'tailscale', 'peerRef': peer},
                         'mode': 'protocol2', 'options': {'port': 3773}, 'pairing': 'TEST23456789'}
        tested = service.test({'configuration': configuration}, owner)
        service.connect({'testId': tested['testId'], 'expectedRevision': 1}, owner)
        service.poll(force=True)
        remote.failure = Unavailable  # Computer 2 stops answering after one good read
        for entry_service in service.services.values():
            entry_service.last_poll = None
        service.poll(force=True)
    elif scenario == 'src-single':
        service.poll(force=True)
    return legacy, service


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=47870)
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    base = Path(tempfile.mkdtemp(prefix='nagi-preview-'))
    base.chmod(0o700)
    servers, out = [], {}
    named = list(scenarios(now).items()) + [(name, None) for name in ('src-empty', 'src-errors', 'src-single', 'src-multi', 'src-multiapp', 'src-firstread')]
    for offset, (name, source) in enumerate(named):
        if source is None:
            directory = base / name
            directory.mkdir(mode=0o700)
            legacy, sources = source_service(directory, now, name)
            httpd = ThreadingHTTPServer(('127.0.0.1', args.port + offset), server.Handler)
            httpd.owner_auth = OwnerAuth(directory)
            httpd.service, httpd.sources = legacy, sources
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            servers.append(httpd)
            out[name] = {'origin': f'http://127.0.0.1:{args.port + offset}', 'dataDir': str(directory)}
            continue
        directory = base / name
        directory.mkdir(mode=0o700)
        clock = {'at': now}
        service = AgentsService(directory, lambda _d, source=source: source, lambda clock=clock: datetime.now(timezone.utc))
        if name == 'unreachable':
            service.clock = lambda: now - timedelta(minutes=3)
            service.poll(force=True)
            source.failure = Unavailable
            service.clock = lambda: datetime.now(timezone.utc)
            service.config_at = None
        if name == 'checking':  # the first poll stays in flight, holding the poll gate
            threading.Thread(target=service.poll, kwargs={'force': True}, daemon=True).start()
        else:
            service.poll(force=True)
        httpd = ThreadingHTTPServer(('127.0.0.1', args.port + offset), server.Handler)
        httpd.owner_auth = OwnerAuth(directory)
        httpd.service = service
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        servers.append(httpd)
        out[name] = {'origin': f'http://127.0.0.1:{args.port + offset}', 'dataDir': str(directory)}
    print(json.dumps(out), flush=True)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    try:
        stop.wait()
    except KeyboardInterrupt:
        pass
    for httpd in servers:
        httpd.shutdown()


if __name__ == '__main__':
    main()
