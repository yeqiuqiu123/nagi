"""Disposable phase-1 lifecycle, isolation and fail-closed setup regressions."""
import copy
import hashlib
import io
import json
import multiprocessing
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
from agents_service import JOURNAL, AgentsService
from owner_auth import OwnerAuth, auth_headers
from sources_service import LEGACY, REGISTRY, SourcesService
from sources_transport import (
    ACCESS_TYPE,
    SourceError,
    bounded_command,
    exchange_pairing,
    issue_local,
    pairing_target,
    tailnet_inventory,
    write_credential,
)
from t3_reader import Unavailable, Unsupported

NOW = datetime(2026, 11, 13, 12, tzinfo=UTC)
BOOTSTRAP = 'TEST23456789'  # Synthetic code in T3's twelve-character bootstrap grammar.
ACCESS = 'synthetic-observer-access'
OWNER = 'synthetic-owner'
PEER = {'addresses': ['100.80.1.2'], 'dns': 'computer.tail.ts.net',
        'label': 'My computer', 'online': True}


class Reader:
    def __init__(self):
        self.failure = False
        self.rows = [{'id': 'a', 'projectId': 'p', 'title': 'Agent', 'status': 'running',
                      'updatedAt': NOW.isoformat(), 'latestRunId': 'r', 'latestRunStartedAt': NOW.isoformat()}]
    def shell(self):
        if self.failure:
            raise Unavailable('never expose ' + ACCESS)
        return {'environmentId': 'same-environment'}, {'projects': [{'id': 'p', 'title': 'Project'}], 'threads': copy.deepcopy(self.rows)}
    def config(self):
        return {'providers': []}
    def detail(self, _):
        return {'hasMoreHistory': False, 'projection': {'turnItems': []}}


def environment(origin):
    return hashlib.sha256(origin.encode()).hexdigest()


class EnvironmentReader:
    """Distinct T3 instances may have identical native thread/project IDs."""
    def __init__(self,reader,origin):self.reader,self.origin=reader,origin
    def shell(self):
        descriptor,snapshot=self.reader.shell()
        return {**descriptor,'environmentId':environment(self.origin)},snapshot
    def __getattr__(self,name):return getattr(self.reader,name)


class Sources(TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(TemporaryDirectory()))
        self.now = NOW
        self.reader = Reader()
        self.legacy = AgentsService(self.directory, lambda _: EnvironmentReader(self.reader,'http://127.0.0.1:3773'), lambda: self.now)
        self.enterContext(patch.object(AgentsService, 'read_machine', lambda *_: None))
        self.issuer = Mock(side_effect=lambda path: write_credential(path, ACCESS))
        self.exchange = Mock(return_value=ACCESS)
        self.detector = Mock(side_effect=lambda origin:{'environmentId':environment(origin),'orchestrationProtocolVersion':2})
        self.service = self.new()

    def new(self):
        service=SourcesService(self.legacy,detector=self.detector,inventory=lambda:[dict(PEER)],
                               issuer=self.issuer,exchange=self.exchange,reader_factory=lambda policy:EnvironmentReader(self.reader,policy['origin']))
        self.addCleanup(service.close)
        return service

    def configuration(self, *, remote=False, pairing=BOOTSTRAP, label='This computer'):
        placement = {'kind': 'local'}
        if remote:
            discovery = self.service.discover({'adapterIds': ['t3'], 'placement': {'kind': 'tailscale'}}, OWNER)
            placement = {'kind': 'tailscale', 'peerRef': discovery['peers'][0]['peerRef']}
        value = {'adapterId': 't3', 'label': label, 'placement': placement,
                 'mode': 'protocol2', 'options': {'port': 3773}}
        if remote:
            value['pairing'] = pairing
        return value

    def make_test(self, **kwargs):
        return self.service.test({'configuration': self.configuration(**kwargs)}, OWNER)

    def connect(self, *, remote=False, expected=0, label='This computer'):
        tested = self.make_test(remote=remote, label=label)
        return self.service.connect({'testId': tested['testId'], 'expectedRevision': expected}, OWNER)

    def legacy_policy(self):
        path = self.directory / 'legacy-credential.json'
        write_credential(path, ACCESS)
        value = {'version': 1, 'origin': 'http://127.0.0.1:3773', 'credentialFile': str(path)}
        self.legacy.store.mutate('nagi-t3.json', {}, lambda current: current.update(value))
        return path

    def test_catalog_is_honest_and_schema_is_closed(self):
        items = self.service.catalog()['harnesses']
        self.assertEqual([v['id'] for v in items], ['t3', 'openbot', 'pi', 'omp', 'codex', 'claude', 'hermes', 'openclaw', 'opencode', 'cursor'])
        # oh-my-pi is a Pi-family entry: listed, honest, and not selectable yet.
        omp = next(v for v in items if v['id'] == 'omp')
        self.assertEqual((omp['displayName'], omp['status'], omp['available'], omp['copyKey'], omp['iconKey']),
                         ('oh-my-pi', 'coming_soon', False, 'omp_pi_family_planned', 'omp'))
        self.assertEqual(self.service.schema('omp')['requirements'], ['coming_soon'])
        self.assertEqual(self.service.test({'configuration': {'adapterId': 'omp', 'label': 'This computer', 'placement': {'kind': 'local'},
                                                             'mode': 'protocol2', 'options': {'port': 3773}}}, OWNER)['testId'], None)
        for item in items:
            self.assertEqual(item['available'], item['id'] in ('t3','claude','codex','cursor'))
            self.assertEqual(any(item['capabilities'].values()), item['available'])
            self.assertEqual(self.service.schema(item['id'])['available'], item['available'])
        with self.assertRaises(SourceError) as error:
            self.service.schema('python.module')
        self.assertEqual(error.exception.status, 404)

    def manual(self,pairing=BOOTSTRAP,origin='http://100.80.1.2:47880'):
        options={'port':3773}
        if origin is not None:
            options['origin']=origin
        return {'configuration':{'adapterId':'t3','label':'Computer 2','placement':{'kind':'manual'},
                                 'mode':'protocol2','options':options,'pairing':pairing}}

    def test_manual_pairing_accepts_link_or_address_without_discovery(self):
        targets=[('http://100.80.1.2:47880/pair#token='+BOOTSTRAP,None,'http://100.80.1.2:47880'),
                 ('https://computer.tail.ts.net/pair#token='+BOOTSTRAP,None,'https://computer.tail.ts.net'),
                 ('t3code://pair?'+urlencode({'pairingUrl':'https://computer.tail.ts.net/pair#token='+BOOTSTRAP}),None,'https://computer.tail.ts.net'),
                 (BOOTSTRAP,'http://127.0.0.1:47881','http://127.0.0.1:47881'),
                 (BOOTSTRAP,'https://computer.tail.ts.net:443','https://computer.tail.ts.net')]
        self.service.inventory=Mock(side_effect=RuntimeError('discovery unavailable'))
        for pairing,origin,expected in targets:
            with self.subTest(expected=expected):
                tested=self.service.test(self.manual(pairing,origin),OWNER)
                self.assertIsNotNone(tested['testId'])
                self.assertEqual(tested['requirements'],['pairing_exchange'])
                self.assertEqual(self.detector.call_args.args,(expected,))
                self.assertNotIn(BOOTSTRAP,json.dumps(tested))
                self.assertNotIn(expected,json.dumps(tested))
        self.service.inventory.assert_not_called()
        self.issuer.assert_not_called()
        self.exchange.assert_not_called()

    def test_manual_loopback_exchanges_pairing_instead_of_issuing_a_cli_session(self):
        value=self.manual(origin='http://127.0.0.1:47881')
        tested=self.service.test(value,OWNER)
        value['configuration']['options']['origin']='http://10.0.0.1:47881'
        connected=self.service.connect({'testId':tested['testId'],'expectedRevision':0},OWNER)
        self.assertEqual(connected['source']['placement'],'local')
        self.exchange.assert_called_once_with('http://127.0.0.1:47881',BOOTSTRAP)
        self.issuer.assert_not_called()
        self.service.poll(force=True)
        wire=json.dumps(self.service.glance('linux'))
        for private in (BOOTSTRAP,ACCESS,'127.0.0.1',str(self.directory)):
            self.assertNotIn(private,wire)

    def test_manual_invalid_origins_fail_before_probe_or_secret_exchange(self):
        from test_tailnet_source import REJECTED
        rejected=[v for v in REJECTED if isinstance(v,str)]+['http://127.0.0.1:47880?',
                  'https://computer.tail.ts.net#','http://100.80.1.2:47880?#']
        for origin in rejected:
            with self.subTest(origin=origin),self.assertRaises(SourceError) as error:
                self.service.test(self.manual(origin=origin),OWNER)
            self.assertEqual(error.exception.code,'pairing_invalid')
        invalid=[self.manual(origin=None),self.manual('https://other.tail.ts.net/pair#token='+BOOTSTRAP),
                 self.manual('https://computer.tail.ts.net/pair?#token='+BOOTSTRAP,None),
                 self.manual('t3code://pair?'+urlencode({'pairingUrl':'https://computer.tail.ts.net/pair\n#token='+BOOTSTRAP}),None)]
        for value in invalid:
            with self.assertRaises(SourceError):
                self.service.test(value,OWNER)
        for change in ({'peerRef':'a'*43},{'origin':ACCESS}):
            value=self.manual()
            value['configuration']['placement'].update(change)
            with self.assertRaises(SourceError):
                self.service.test(value,OWNER)
        self.detector.assert_not_called()
        self.exchange.assert_not_called()
        self.issuer.assert_not_called()
        self.assertFalse((self.directory/REGISTRY).exists())

    def test_manual_explicit_origin_must_match_link_and_conflicts_use_canonical_ports(self):
        link='https://computer.tail.ts.net/pair#token='+BOOTSTRAP
        tested=self.service.test(self.manual(link,'https://computer.tail.ts.net:443'),OWNER)
        self.service.connect({'testId':tested['testId'],'expectedRevision':0},OWNER)
        tested=self.service.test(self.manual(origin='https://computer.tail.ts.net'),OWNER)
        with self.assertRaises(SourceError) as error:
            self.service.connect({'testId':tested['testId'],'expectedRevision':1},OWNER)
        self.assertEqual(error.exception.code,'source_exists')
        self.assertEqual(self.exchange.call_count,1)
        self.detector.reset_mock()
        with self.assertRaises(SourceError):
            self.service.test(self.manual(link,'https://other.tail.ts.net'),OWNER)
        self.detector.assert_not_called()

    def test_list_and_glance_sort_harness_before_label_and_id(self):
        # Future catalog kinds exercise the shared ordering even though phase 1
        # only configures T3. No unsupported adapter is enabled or persisted.
        entries=[{'id':f'{i:032x}','harness':harness,'label':label,'placement':'local'}
                 for i,harness,label in [(7,'codex','A'),(6,'omp','A'),(5,'pi','A'),(4,'openbot','Z'),
                                         (3,'t3','Zulu'),(2,'t3','Alpha'),(1,'t3','Alpha')]]
        self.service.registry=Mock(return_value={'version':1,'revision':0,'sources':entries})
        self.service.poll=Mock()
        self.service.service_for=Mock(return_value=self.legacy)
        for resource in (self.service.read_sources(),self.service.glance('linux')):
            self.assertEqual([v['source']['id'] for v in resource['sources']],[f'{i:032x}' for i in range(1,8)])

    def test_descriptor_test_is_not_pairing_or_a_live_roster(self):
        result = self.make_test()
        self.issuer.assert_not_called()
        self.exchange.assert_not_called()
        self.assertEqual(result['agents'], {'status': 'not_set_up', 'checkedAt': None, 'reason': 'not_configured'})
        self.assertTrue(all(v == 'unverified' for v in result['coverage'].values()))
        self.assertFalse((self.directory / REGISTRY).exists())
        self.assertFalse((self.directory / 'source-secrets').exists())
        self.assertIsNotNone(result['testId'])

    def test_failed_and_unsupported_tests_never_get_handles(self):
        for error, status in ((Unavailable(ACCESS), 'unavailable'), (Unsupported(ACCESS), 'unsupported')):
            self.detector.side_effect = error
            tested = self.make_test()
            self.assertEqual(tested['agents']['status'], status)
            self.assertIsNone(tested['testId'])
            self.assertNotIn(ACCESS, json.dumps(tested))
        value = self.configuration()
        value['adapterId'] = 'openclaw'
        tested = self.service.test({'configuration': value}, OWNER)
        self.assertEqual(tested['requirements'], ['coming_soon'])
        self.assertFalse(any(tested['capabilities'].values()))

    def test_local_connect_persists_owner_only_registry_and_secret_and_reads_back(self):
        connected = self.connect()
        identity = connected['source']['id']
        self.assertEqual(connected['revision'], 1)
        self.issuer.assert_called_once()
        restored=self.new()
        restored.poll(force=True)
        resource = restored.read_sources()
        self.assertEqual(resource['sources'][0]['source']['id'], identity)
        self.assertEqual(resource['sources'][0]['agents']['status'], 'ok')
        self.assertTrue((self.directory / f'nagi-source-{identity}-state.json').exists())
        self.assertEqual((self.directory / REGISTRY).stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.directory / 'source-secrets').stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.directory / 'source-secrets' / (identity + '.json')).stat().st_mode & 0o777, 0o600)
        raw = (self.directory / REGISTRY).read_text()
        self.assertNotIn(ACCESS, raw)
        wire = json.dumps(resource)
        for forbidden in (ACCESS, '127.0.0.1', 'credentialFile', str(self.directory)):
            self.assertNotIn(forbidden, wire)

    def test_remote_pair_is_exchanged_only_at_connect_and_never_saved(self):
        tested = self.make_test(remote=True)
        self.exchange.assert_not_called()
        self.assertNotIn(BOOTSTRAP, repr(self.service.tests))
        result = self.service.connect({'testId': tested['testId'], 'expectedRevision': 0}, OWNER)
        self.exchange.assert_called_once_with('http://100.80.1.2:3773', BOOTSTRAP)
        self.issuer.assert_not_called()
        self.assertEqual(result['source']['placement'], 'tailscale')
        wire = json.dumps(self.service.glance('linux'))
        for forbidden in (BOOTSTRAP, ACCESS, '100.80.1.2', PEER['dns']):
            self.assertNotIn(forbidden, wire)
        for path in self.directory.rglob('*'):
            if path.is_file():
                self.assertNotIn(BOOTSTRAP, path.read_text())

    def test_expired_invalid_and_other_owner_tests_fail_closed(self):
        tested = self.make_test()
        value = {'testId': tested['testId'], 'expectedRevision': 0}
        for owner in ('another owner',):
            with self.assertRaises(SourceError) as error:
                self.service.connect(value, owner)
            self.assertEqual(error.exception.code, 'test_expired')
        self.now += timedelta(minutes=2)
        with self.assertRaises(SourceError) as error:
            self.service.connect(value, OWNER)
        self.assertEqual(error.exception.code, 'test_expired')
        self.issuer.assert_not_called()
        with self.assertRaises(SourceError):
            self.service.connect({'testId': '../anything', 'expectedRevision': 0}, OWNER)

    def test_expired_peer_and_other_owner_peer_never_probe(self):
        value = self.configuration(remote=True)
        self.detector.reset_mock()
        with self.assertRaises(SourceError) as error:
            self.service.test({'configuration': value}, 'someone else')
        self.assertEqual(error.exception.code, 'peer_expired')
        self.now += timedelta(minutes=5)
        with self.assertRaises(SourceError) as error:
            self.service.test({'configuration': value}, OWNER)
        self.assertEqual(error.exception.code, 'peer_expired')
        self.detector.assert_not_called()

    def test_revision_conflict_and_duplicate_origin_do_not_issue(self):
        self.connect()
        for expected, code in ((0, 'configuration_changed'), (1, 'source_exists')):
            tested = self.make_test()
            with self.assertRaises(SourceError) as error:
                self.service.connect({'testId': tested['testId'], 'expectedRevision': expected}, OWNER)
            self.assertEqual(error.exception.code, code)
        self.assertEqual(self.issuer.call_count, 1)

    def test_concurrent_connects_mint_once_even_between_service_instances(self):
        one = self.make_test()
        other = self.new()
        two = other.test({'configuration': self.configuration()}, OWNER)
        barrier = threading.Barrier(2)
        def connect(pair):
            svc, tested = pair
            barrier.wait(5)
            try:
                return svc.connect({'testId': tested['testId'], 'expectedRevision': 0}, OWNER)
            except SourceError as error:
                return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(connect, [(self.service, one), (other, two)]))
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertIn('configuration_changed', results)
        self.assertEqual(self.issuer.call_count, 1)
        self.assertEqual(len(self.service.registry()['sources']), 1)

    def test_failed_pairing_consumes_test_redacts_error_and_cleans_credential(self):
        tested = self.make_test(remote=True)
        self.exchange.side_effect = RuntimeError(BOOTSTRAP + ACCESS)
        value = {'testId': tested['testId'], 'expectedRevision': 0}
        with self.assertRaises(SourceError) as error:
            self.service.connect(value, OWNER)
        self.assertEqual(str(error.exception), 'connection_failed')
        with self.assertRaises(SourceError) as retry:
            self.service.connect(value, OWNER)
        self.assertEqual(retry.exception.code, 'test_expired')
        self.assertFalse((self.directory / REGISTRY).exists())
        self.assertEqual(list((self.directory / 'source-secrets').iterdir()), [])

    def test_unsafe_or_broad_cli_credential_is_rejected_and_cleaned(self):
        def broad(path):
            path.write_text(json.dumps({'token': ACCESS, 'scopes': ['orchestration:read', 'orchestration:operate']}))
            path.chmod(0o600)
        self.issuer.side_effect = broad
        with self.assertRaises(SourceError) as error:
            self.connect()
        self.assertEqual(error.exception.code, 'connection_failed')
        self.assertEqual(list((self.directory / 'source-secrets').iterdir()), [])

    def test_authenticated_shell_is_required_before_commit(self):
        self.reader.failure = True
        with self.assertRaises(SourceError):
            self.connect()
        self.assertFalse((self.directory / REGISTRY).exists())
        self.assertEqual(list((self.directory / 'source-secrets').iterdir()), [])

    def test_legacy_migration_is_in_memory_and_preserves_notifications_and_credentials(self):
        credential = self.legacy_policy()
        self.legacy.poll(force=True)
        self.reader.rows[0].update(status='failed', latestRunCompletedAt=NOW.isoformat())
        self.legacy.poll(force=True)
        events = self.legacy.notifications()
        self.assertEqual(len(events), 1)
        paths = [credential, self.directory / 'nagi-t3.json', self.directory / JOURNAL]
        before = {path: path.read_bytes() for path in paths}
        original = self.service.registry()
        self.assertEqual(original['sources'][0]['id'], LEGACY)
        self.assertFalse((self.directory / REGISTRY).exists())
        self.assertEqual({path: path.read_bytes() for path in paths}, before)
        self.connect(remote=True)
        self.assertEqual({path: path.read_bytes() for path in paths}, before)
        migrated = self.new()
        self.assertEqual({k:v for k,v in migrated.registry()['sources'][0].items() if k!='environmentId'}, original['sources'][0])
        self.assertEqual(migrated.notifications()['events'][0], {'sourceId': LEGACY, 'event': events[0]})
        self.assertIs(migrated.service_for(original['sources'][0]), self.legacy)

    def test_no_policy_means_no_source_no_registry_write_and_legacy_not_set_up(self):
        # Independent default factory; the fixture legacy uses an injected reader.
        plain = SourcesService(AgentsService(self.directory))
        self.addCleanup(plain.close)
        self.assertEqual(plain.read_sources(), {'version': 1, 'revision': 0, 'sources': []})
        self.assertFalse((self.directory / REGISTRY).exists())
        plain.poll_legacy()
        self.assertEqual(plain.legacy.agents['status'], 'not_set_up')

    def test_multi_instance_failure_keeps_other_fresh_and_dated_cache_is_source_local(self):
        first = self.connect()['source']['id']
        second = self.connect(remote=True, expected=1, label='Computer 2')['source']['id']
        readers = {first: Reader(), second: Reader()}
        self.service.reader_factory = lambda policy: readers[Path(policy['credentialFile']).stem]
        self.service.poll(force=True)
        self.now += timedelta(seconds=30)
        readers[first].failure = True
        self.service.poll(force=True)
        values = {v['source']['id']: v for v in self.service.read_sources()['sources']}
        self.assertEqual(values[first]['agents']['status'], 'last_known')
        self.assertEqual(values[first]['agents']['checkedAt'], NOW.isoformat())
        self.assertEqual(values[second]['agents']['status'], 'ok')
        self.assertEqual(values[second]['agents']['checkedAt'], self.now.isoformat())
        self.assertNotIn(ACCESS, json.dumps(values))

    def test_multi_instance_ids_notifications_and_claims_are_independent(self):
        first = self.connect()['source']['id']
        second = self.connect(remote=True, expected=1, label='Computer 2')['source']['id']
        self.service.poll(force=True)
        self.reader.rows[0].update(status='failed', latestRunCompletedAt=NOW.isoformat())
        self.service.poll(force=True)
        events = self.service.notifications()['events']
        self.assertEqual(len(events), 2)
        self.assertEqual({e['sourceId'] for e in events},{first,second})
        self.assertNotEqual(events[0]['event']['id'], events[1]['event']['id'])
        entry = events[0]
        lease = self.service.notification_action('reserve', {'sourceId': entry['sourceId'], 'id': entry['event']['id']})['lease']
        self.assertIsNotNone(lease)
        claimed = self.service.notification_action('claim', {'sourceId': entry['sourceId'], 'id': entry['event']['id'], 'reservation': lease['reservation']})
        self.assertTrue(claimed['claimed'])
        self.assertEqual(len(self.service.notifications()['events']), 1)
        # Recreating service preserves source-local caches, conditions and claims.
        self.assertEqual(self.new().notifications(), self.service.notifications())
        self.assertEqual(self.legacy.notifications(), [])

    def test_disconnect_stops_reads_retires_only_its_events_and_deletes_only_owned_copy(self):
        credential = self.legacy_policy()
        remote = self.connect(remote=True)['source']['id']
        self.service.poll(force=True)
        self.reader.rows[0].update(status='failed', latestRunCompletedAt=NOW.isoformat())
        self.service.poll(force=True)
        self.assertEqual(len(self.service.notifications()['events']), 2)
        result = self.service.disconnect({'sourceId': remote, 'expectedRevision': 1})
        self.assertEqual(result, {'version': 1, 'revision': 2, 'disconnected': True})
        self.assertTrue(credential.exists())
        self.assertFalse((self.directory / 'source-secrets' / (remote + '.json')).exists())
        self.assertEqual([v['sourceId'] for v in self.service.notifications()['events']], [LEGACY])
        self.assertEqual(self.service.disconnect({'sourceId': remote, 'expectedRevision': 2})['disconnected'], False)
        with self.assertRaises(SourceError) as error:
            self.service.disconnect({'sourceId': LEGACY, 'expectedRevision': 1})
        self.assertEqual(error.exception.code, 'configuration_changed')
        self.service.disconnect({'sourceId': LEGACY, 'expectedRevision': 2})
        self.assertTrue(credential.exists())
        self.assertEqual(self.service.notifications()['events'], [])
        self.service.poll_legacy()
        self.assertEqual(self.legacy.agents['status'], 'not_set_up')

    def test_local_and_tailnet_discovery_are_read_only_and_hide_topology(self):
        with patch('sources_service.local_cli', return_value=(['t3'], None)):
            local = self.service.discover({'adapterIds': ['t3', 'codex'], 'placement': {'kind': 'local'}}, OWNER)
        self.assertEqual(local['candidates'][0]['installed'], 'yes')
        self.assertEqual(local['candidates'][0]['running'], 'yes')
        self.assertEqual(local['candidates'][0]['readable'], 'unknown')
        self.detector.reset_mock()
        remote = self.service.discover({'adapterIds': ['t3'], 'placement': {'kind': 'tailscale'}}, OWNER)
        self.detector.assert_not_called()
        self.assertEqual(remote['peers'][0]['label'], PEER['label'])
        self.assertEqual(remote['candidates'][0]['installed'], 'unknown')
        for secret in (PEER['addresses'][0], PEER['dns'], BOOTSTRAP, ACCESS):
            self.assertNotIn(secret, json.dumps(remote))
        self.issuer.assert_not_called()
        self.exchange.assert_not_called()
        self.assertFalse((self.directory / REGISTRY).exists())

    def test_tailscale_unavailable_is_not_an_empty_successful_remote_read(self):
        self.service.inventory = Mock(side_effect=RuntimeError(ACCESS))
        result = self.service.discover({'adapterIds': ['t3'], 'placement': {'kind': 'tailscale'}}, OWNER)
        self.assertEqual(result, {'version': 1, 'peers': [], 'candidates': [], 'warnings': ['tailscale_unavailable']})

    def test_source_capacity_is_sixteen_and_denial_never_pairs(self):
        entries=[]
        for i in range(16):
            identity=f'{i+1:032x}'
            entries.append({'id':identity,'harness':'t3','label':f'Computer {i+1}','placement':'tailscale',
                            'policy':{'version':1,'origin':f'http://100.80.1.{i+10}:3773',
                                      'credentialFile':str(self.directory/'source-secrets'/(identity+'.json'))},
                            'ownedCredential':True})
        self.service.persist({'version':1,'revision':1,'sources':entries})
        before=(self.directory/REGISTRY).read_bytes()
        tested=self.make_test()
        with self.assertRaises(SourceError) as error:
            self.service.connect({'testId':tested['testId'],'expectedRevision':1},OWNER)
        self.assertEqual(error.exception.code,'capacity_reached')
        self.assertEqual((self.directory/REGISTRY).read_bytes(),before)
        self.issuer.assert_not_called()
        self.exchange.assert_not_called()

    def test_pairing_in_progress_does_not_hold_healthy_feed_publication(self):
        first=self.connect()['source']['id']
        tested=self.make_test(remote=True)
        entered,release=threading.Event(),threading.Event()
        def exchange(*_):
            entered.set()
            if not release.wait(5):
                raise RuntimeError('fixture timeout')
            return ACCESS
        self.service.exchange=exchange
        with ThreadPoolExecutor(max_workers=1) as pool:
            connecting=pool.submit(self.service.connect,{'testId':tested['testId'],'expectedRevision':1},OWNER)
            try:
                self.assertTrue(entered.wait(5))
                self.service.poll(force=True)
                resource=self.service.read_sources()
                self.assertEqual(resource['sources'][0]['source']['id'],first)
                self.assertEqual(resource['sources'][0]['agents']['status'],'ok')
                self.assertFalse(connecting.done())
            finally:
                release.set()
            self.assertEqual(connecting.result(timeout=5)['revision'],2)

    def test_slow_source_does_not_hold_feed_or_healthy_source_publication(self):
        first=self.connect()['source']['id']
        second=self.connect(remote=True,expected=1)['source']['id']
        entered,release=threading.Event(),threading.Event()
        slow=Reader()
        def blocked():
            entered.set()
            if not release.wait(5):
                raise RuntimeError('fixture timeout')
            raise Unavailable()
        slow.shell=blocked
        self.service.reader_factory=lambda policy: slow if Path(policy['credentialFile']).stem==first else Reader()
        try:
            self.service.poll()
            self.assertTrue(entered.wait(5))
            self.service.pending[second].result(timeout=5)
            resource=self.service.read_sources()
            values={item['source']['id']:item for item in resource['sources']}
            self.assertEqual(values[first]['agents']['reason'],'checking')
            self.assertEqual(values[second]['agents']['status'],'ok')
        finally:
            release.set()
            self.service.poll(force=True)

    def test_oversized_payload_is_visible_without_dropping_another_source(self):
        first=self.connect()['source']['id']
        second=self.connect(remote=True,expected=1)['source']['id']
        large=Reader()
        large.rows=[dict(large.rows[0],id=str(i),title='A'*180) for i in range(200)]
        self.service.reader_factory=lambda policy: large if Path(policy['credentialFile']).stem==first else Reader()
        self.service.poll(force=True)
        with patch('sources_service.MAX_ENVELOPE_BYTES',40000):
            result=self.service.glance('linux')
        values={item['source']['id']:item for item in result['sources']}
        self.assertEqual(set(values),{first,second})
        self.assertEqual(values[first]['agents']['status'],'unavailable')
        self.assertEqual(values[first]['agents']['reason'],'coverage_incomplete')
        self.assertIsNone(values[first]['agents']['data'])
        self.assertEqual(values[second]['agents']['status'],'ok')
        self.assertEqual(result['warnings'],['response_truncated'])
        self.assertLess(len(json.dumps(result,ensure_ascii=False,separators=(',',':')).encode()),40000)
        # Wire truncation never changes the successful observation/cache itself.
        self.assertEqual(self.service.services[first].agents['status'],'ok')

    def test_changed_environment_identity_cannot_commit_a_tested_origin(self):
        self.detector.side_effect=None
        self.detector.return_value={'environmentId':'different-environment','orchestrationProtocolVersion':2}
        tested=self.make_test()
        with self.assertRaises(SourceError) as error:
            self.service.connect({'testId':tested['testId'],'expectedRevision':0},OWNER)
        self.assertEqual(error.exception.code,'connection_failed')
        self.assertEqual(list((self.directory/'source-secrets').iterdir()),[])
        self.assertFalse((self.directory/REGISTRY).exists())

    def test_registry_write_failure_cleans_secret_and_never_publishes(self):
        self.service.persist=Mock(side_effect=OSError(ACCESS))
        with self.assertRaises(SourceError) as error:
            self.connect()
        self.assertEqual((error.exception.status,str(error.exception)),(503,'storage_unavailable'))
        self.assertFalse((self.directory/REGISTRY).exists())
        self.assertEqual(list((self.directory/'source-secrets').iterdir()),[])

    def test_favicon_keys_are_namespaced_even_with_identical_native_ids(self):
        import project_icons
        self.connect()
        self.connect(remote=True,expected=1)
        keys=[]
        for entry in self.service.registry()['sources']:
            data={'environmentId':'same-environment','projects':[{'id':'p'}],'ended':[]}
            self.service.service_for(entry).attach_icons(data,{'projects':[{'id':'p','workspaceRoot':'/synthetic/project'}]})
            keys.append(data['projects'][0]['icon']['key'])
        self.assertNotEqual(keys[0],keys[1])
        self.assertNotIn(project_icons.key('same-environment','p'),keys)

    def test_disconnect_waits_for_inflight_read_and_cannot_resurrect_pending_delivery(self):
        connected=self.connect()
        entered,release,started,finished=(threading.Event() for _ in range(4))
        original=self.reader.shell
        def shell():
            entered.set()
            if not release.wait(5):
                raise RuntimeError('fixture timeout')
            return original()
        self.reader.shell=Mock(side_effect=shell)
        def disconnect():
            started.set()
            result=self.service.disconnect({'sourceId':connected['source']['id'],'expectedRevision':1})
            finished.set()
            return result
        with ThreadPoolExecutor(max_workers=2) as pool:
            reading=pool.submit(self.service.poll,True)
            self.assertTrue(entered.wait(5))
            removing=pool.submit(disconnect)
            self.assertTrue(started.wait(5))
            self.assertFalse(finished.wait(.05))
            release.set()
            reading.result(timeout=5)
            self.assertTrue(removing.result(timeout=5)['disconnected'])
        self.service.poll(force=True)
        self.assertEqual(self.reader.shell.call_count,1)
        self.assertEqual(self.service.notifications()['events'],[])
        self.assertEqual(self.service.registry()['sources'],[])

    def test_one_failed_journal_does_not_blank_another_source(self):
        first=self.connect()['source']['id']
        second=self.connect(remote=True,expected=1)['source']['id']
        self.service.poll(force=True)
        self.now+=timedelta(seconds=30)
        broken=self.service.services[first]
        with patch.object(broken.store,'mutate',side_effect=OSError(ACCESS)):
            self.service.poll(force=True)
        reads={v['source']['id']:v for v in self.service.read_sources()['sources']}
        self.assertEqual(reads[first]['agents']['status'],'last_known')
        self.assertEqual(reads[second]['agents']['status'],'ok')
        self.assertNotIn(ACCESS,json.dumps(reads))

    def test_private_registry_and_secret_paths_fail_closed(self):
        outside = self.directory / 'outside'
        outside.mkdir(mode=0o700)
        (self.directory / 'source-secrets').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(SourceError):
            self.connect()
        self.assertEqual(list(outside.iterdir()), [])
        (self.directory / 'source-secrets').unlink()
        (self.directory / REGISTRY).symlink_to(outside / 'registry')
        with self.assertRaises(SourceError) as error:
            self.service.registry()
        self.assertEqual(error.exception.code, 'storage_unavailable')
        self.assertFalse((outside / 'registry').exists())

    def test_schema_types_unknown_keys_and_capacity_fail_closed(self):
        for changes in ({'extra': ACCESS}, {'options': {'port': True}}, {'placement': {'kind': 'local', 'peerRef': 'x'}},
                        {'options': {'port': 80}}, {'label': ''}, {'mode': 'control'}, {'pairing': ACCESS}):
            value = self.configuration() | changes
            with self.assertRaises(SourceError):
                self.service.test({'configuration': value}, OWNER)
        for expected in (True, -1, '0', None):
            with self.assertRaises(SourceError):
                self.service.connect({'testId': 'a' * 43, 'expectedRevision': expected}, OWNER)
        self.service.tests = {str(i): {'expires': self.now + timedelta(minutes=1)} for i in range(128)}
        with self.assertRaises(SourceError) as error:
            self.make_test()
        self.assertEqual(error.exception.code, 'capacity_reached')


class PairingTransport(TestCase):
    def test_closed_pairing_link_parser_accepts_selected_peer_only(self):
        link = 'https://' + PEER['dns'] + '/pair#token=' + BOOTSTRAP
        self.assertEqual(pairing_target(link, PEER, 3773), ('https://' + PEER['dns'], BOOTSTRAP))
        app = 't3code://pair?' + urlencode({'pairingUrl': link})
        self.assertEqual(pairing_target(app, PEER, 3773), ('https://' + PEER['dns'], BOOTSTRAP))
        self.assertEqual(pairing_target(BOOTSTRAP, PEER, 3773), ('http://100.80.1.2:3773', BOOTSTRAP))
        invalid = [
            'http://10.0.0.2:3773/pair#token=' + BOOTSTRAP,
            'http://127.0.0.1:3773/pair#token=' + BOOTSTRAP,
            'http://100.80.1.3:3773/pair#token=' + BOOTSTRAP,
            'https://other.tail.ts.net/pair#token=' + BOOTSTRAP,
            'https://computer.tail.ts.net.evil/pair#token=' + BOOTSTRAP,
            'https://user@computer.tail.ts.net/pair#token=' + BOOTSTRAP,
            link.replace('/pair', '/other'), link + '&x=1', link.replace('/pair#', '/pair?x=1#'),
            't3code://pair?' + urlencode({'pairingUrl': link, 'extra': '1'}),
            't3code://threads?' + urlencode({'pairingUrl': link}),
            'bad token', 'expired', ' ' + BOOTSTRAP, BOOTSTRAP + '\n', 'file:///private/secret']
        for value in invalid:
            with self.subTest(value=value.split('#')[0]), self.assertRaises((SourceError, ValueError)):
                pairing_target(value, PEER, 3773)

    def response(self, status=200, **changes):
        response = Mock()
        response.status = status
        response.read.return_value = json.dumps({'access_token': ACCESS, 'issued_token_type': ACCESS_TYPE,
                                                'token_type': 'Bearer', 'expires_in': 900, 'scope': 'orchestration:read'} | changes).encode()
        connection = Mock()
        connection.getresponse.return_value = response
        return connection

    def exchange(self, connection):
        with patch('t3_reader.T3Reader.connection', return_value=connection), patch('sources_transport.IODeadline'):
            return exchange_pairing('http://100.80.1.2:3773', BOOTSTRAP)

    def test_manual_loopback_exchange_refuses_a_foreign_listener_before_sending(self):
        from t3_reader import OwnerConnection
        connection=OwnerConnection('127.0.0.1',47880)
        sock=Mock()
        connection.sock=sock
        with patch('t3_reader.T3Reader.connection',return_value=connection), \
             patch('http.client.HTTPConnection.connect'),patch('sys.platform','linux'), \
             patch('t3_reader.peer_uid',return_value=os.getuid()+1), \
             patch('http.client.HTTPConnection.request') as request,self.assertRaises(SourceError) as error:
            exchange_pairing('http://127.0.0.1:47880',BOOTSTRAP)
        self.assertEqual(error.exception.code,'connection_failed')
        request.assert_not_called()
        sock.close.assert_called_once()

    def test_token_exchange_uses_exact_official_form_and_no_secret_in_url_headers(self):
        connection = self.response()
        self.assertEqual(self.exchange(connection), ACCESS)
        args, kwargs = connection.request.call_args
        self.assertEqual(args, ('POST', '/oauth/token'))
        value = parse_qs(kwargs['body'].decode())
        self.assertEqual(value, {'grant_type': ['urn:ietf:params:oauth:grant-type:token-exchange'],
                                 'subject_token': [BOOTSTRAP],
                                 'subject_token_type': ['urn:t3:params:oauth:token-type:environment-bootstrap'],
                                 'requested_token_type': [ACCESS_TYPE], 'scope': ['orchestration:read'],
                                 'client_label': ['Nagi (read-only)'], 'client_device_type': ['desktop']})
        self.assertNotIn(BOOTSTRAP, str(kwargs['headers']))
        connection.close.assert_called_once()

    def test_scope_upgrades_downgrades_duplicates_and_missing_scope_are_rejected(self):
        for scope in ('', 'orchestration:operate', 'orchestration:read orchestration:operate',
                      'orchestration:read orchestration:read', ['orchestration:read'], None):
            with self.subTest(scope=scope), self.assertRaises(SourceError) as error:
                self.exchange(self.response(scope=scope))
            self.assertEqual(error.exception.code, 'scope_mismatch')

    def test_invalid_expired_redirect_and_malformed_exchange_never_echo_bodies(self):
        for status in (301, 302, 400, 401, 403, 410, 500):
            connection = self.response(status, error=BOOTSTRAP + ACCESS)
            with self.assertRaises(SourceError) as error:
                self.exchange(connection)
            self.assertEqual(str(error.exception), 'pairing_invalid')
            self.assertEqual(connection.request.call_count, 1)
        for changes in ({'expires_in': 0}, {'expires_in': True}, {'access_token': 'bad'}, {'token_type': 'DPoP'},
                        {'issued_token_type': 'different'}):
            with self.assertRaises(SourceError):
                self.exchange(self.response(**changes))
        connection = self.response()
        connection.getresponse.return_value.read.return_value = b'{"scope":"orchestration:read","scope":"evil"}'
        with self.assertRaises(SourceError) as error:
            self.exchange(connection)
        self.assertNotIn(ACCESS, str(error.exception))
        with patch('t3_reader.T3Reader.connection') as connect, self.assertRaises(ValueError):
            exchange_pairing('http://10.0.0.2:3773', BOOTSTRAP)
        connect.assert_not_called()

    def test_local_issue_uses_token_only_stdout_and_private_writer(self):
        directory = Path(self.enterContext(TemporaryDirectory()))
        path = directory / 'new-credential'
        # A fake CLI process emits synthetic stdout only into the real private
        # writer pipe. No T3 command/session is ever run during verification.
        command=[sys.executable,'-c','import sys;sys.stdout.write("synthetic-observer-access\\n")']
        with patch('sources_transport.local_cli',return_value=(command,None)), \
             patch('sys.stdout',new_callable=io.StringIO) as output,patch('sys.stderr',new_callable=io.StringIO) as errors:
            issue_local(path)
            self.assertEqual(output.getvalue()+errors.getvalue(),'')
        self.assertEqual(json.loads(path.read_text()),{'token':ACCESS,'scopes':['orchestration:read']})
        self.assertEqual(path.stat().st_mode&0o777,0o600)
        with patch('sources_transport.local_cli',return_value=([sys.executable,'-c','print("bad")'],None)),self.assertRaises(SourceError):
            issue_local(directory/'invalid')
        self.assertFalse((directory/'invalid').exists())

    def test_local_cli_command_is_fixed_read_only_and_does_not_run_discovery(self):
        from sources_transport import local_cli
        with patch('sources_transport.shutil.which',return_value='/synthetic/t3'):
            args,env=local_cli()
        self.assertLessEqual(set(env),{'HOME','PATH','LANG','USER','TMPDIR'})
        self.assertEqual(args,['/synthetic/t3','auth','session','issue','--scope','orchestration:read',
                               '--label','Nagi (read-only, this computer)','--ttl','365d',
                               '--token-only','--log-level','none'])
        self.assertEqual(str(SourceError(ACCESS)),'connection_failed')
        self.assertEqual(str(SourceError(BOOTSTRAP)),'connection_failed')

    def test_private_credential_writer_cannot_overwrite_or_follow_a_symlink(self):
        directory=Path(self.enterContext(TemporaryDirectory()))
        existing=directory/'existing'
        existing.write_text('preserve')
        link=directory/'link'
        link.symlink_to(existing)
        for path in (existing,link):
            with self.assertRaises(OSError):
                write_credential(path,ACCESS)
        self.assertEqual(existing.read_text(),'preserve')
        self.assertEqual(sorted(p.name for p in directory.iterdir()),['existing','link'])

    def test_global_io_slots_and_expired_whole_read_budget_fail_closed(self):
        import time

        from sources_service import BoundedReader
        from t3_reader import T3Reader
        slots=threading.BoundedSemaphore(4)
        lock=threading.Lock()
        active=peak=0
        full,release=threading.Event(),threading.Event()
        class Blocking:
            def shell(inner):
                nonlocal active,peak
                with lock:
                    active+=1
                    peak=max(peak,active)
                    if active==4:
                        full.set()
                if not release.wait(5):
                    raise RuntimeError('fixture timeout')
                with lock:
                    active-=1
        with ThreadPoolExecutor(max_workers=8) as pool:
            work=[pool.submit(BoundedReader(Blocking(),slots).shell) for _ in range(8)]
            try:
                self.assertTrue(full.wait(5))
                self.assertEqual(peak,4)
            finally:
                release.set()
            for future in work:
                future.result(timeout=5)
        self.assertEqual(peak,4)
        reader=T3Reader.public('http://127.0.0.1:47880')
        reader._source_deadline=time.monotonic()-1
        with patch.object(reader,'connection') as connect,self.assertRaises(Unavailable):
            reader.get('/.well-known/t3/environment',authenticated=False)
        connect.return_value.connect.assert_not_called()
        with self.assertRaises(Unavailable):
            BoundedReader(Reader(),slots,time.monotonic()-1).shell()

    def test_bounded_commands_timeout_limit_and_stderr_are_contained(self):
        self.assertEqual(bounded_command([sys.executable, '-c', 'print("ok",end="")']), b'ok')
        for script, kwargs in [('import time;time.sleep(5)', {'seconds': .05}), ('print("x"*100)', {'limit': 8}),
                               ('import sys;sys.stderr.write("never expose synthetic");sys.exit(1)', {})]:
            with self.subTest(script=script), self.assertRaises(SourceError) as error:
                bounded_command([sys.executable, '-c', script], **kwargs)
            self.assertNotIn('synthetic', str(error.exception))

    def test_tailscale_status_only_is_bounded_filters_addresses_and_never_scans(self):
        value = {'Peer': {'one': {'TailscaleIPs': ['10.0.0.2', '100.80.1.2', 'fd7a::1'],
                                  'DNSName': 'computer.tail.ts.net.', 'HostName': 'Computer', 'Online': True},
                           'other': {'TailscaleIPs': ['192.168.1.2']}}}
        with patch('sources_transport.shutil.which', return_value='/synthetic/tailscale'), \
             patch('sources_transport.bounded_command', return_value=json.dumps(value).encode()) as run:
            peers = tailnet_inventory()
        self.assertEqual(run.call_args.args[0], ['/synthetic/tailscale', 'status', '--json'])
        self.assertEqual(peers, [dict(PEER, label='Computer')])


class SourcesHTTP(TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(TemporaryDirectory()))
        self.reader = Reader()
        self.legacy = AgentsService(self.directory, lambda _: EnvironmentReader(self.reader,'http://127.0.0.1:3773'), lambda: NOW)
        self.sources = SourcesService(self.legacy, detector=Mock(side_effect=lambda origin:{'environmentId':environment(origin),'orchestrationProtocolVersion':2}),
                                      inventory=lambda: [dict(PEER)], issuer=lambda p: write_credential(p, ACCESS),
                                      exchange=lambda *_: ACCESS, reader_factory=lambda policy: EnvironmentReader(self.reader,policy['origin']))
        self.addCleanup(self.sources.close)
        self.auth = OwnerAuth(self.directory)
        # Explicit disposable development range. Never bind installed reader ports.
        for port in range(47880, 48000):
            try:
                self.http = ThreadingHTTPServer(('127.0.0.1', port), server.Handler)
                break
            except OSError:
                continue
        else:
            self.fail('No disposable test port available')
        self.http.owner_auth, self.http.service, self.http.sources = self.auth, self.legacy, self.sources
        self.auth.bind(self.http.server_port)
        self.origin = f'http://127.0.0.1:{self.http.server_port}'
        self.thread = threading.Thread(target=self.http.serve_forever)
        self.thread.start()
        self.addCleanup(self.thread.join, 5)
        self.addCleanup(self.http.server_close)
        self.addCleanup(self.http.shutdown)
        self.base = '/api/sources/v1'
        self.enterContext(patch.object(AgentsService, 'read_machine', lambda *_: None))

    def request(self, path, *, method='GET', value=None, raw=None, owner=True, headers=None, duplicates=()):
        if raw is None:
            raw = json.dumps(value).encode() if value is not None else b''
        values = {'Host': f'127.0.0.1:{self.http.server_port}'}
        if owner:
            values.update(auth_headers(self.origin, method, path, raw, self.directory))
        if method == 'POST':
            values.update({'Content-Type': 'application/json', 'X-Progress-Desk': '1', 'Content-Length': str(len(raw))})
        values.update(headers or {})
        connection = HTTPConnection('127.0.0.1', self.http.server_port, timeout=5)
        try:
            connection.putrequest(method, path, skip_host=True)
            for key, item in list(values.items()) + list(duplicates):
                connection.putheader(key, item)
            connection.endheaders(raw)
            response = connection.getresponse()
            body = response.read()
            return response.status, dict(response.headers), json.loads(body) if body else None
        finally:
            connection.close()

    def session(self):
        ticket = self.auth.issue('/glance')
        return self.auth.redeem(ticket, '/glance')['token']

    def config(self):
        return {'configuration': {'adapterId': 't3', 'mode': 'protocol2', 'label': 'This computer',
                                  'placement': {'kind': 'local'}, 'options': {'port': 3773}}}

    def test_all_source_routes_and_methods_deny_nonowners_before_work(self):
        for path in server.SOURCE_GET | server.SOURCE_POST | {self.base + '/schema/t3'}:
            for method in ('GET', 'HEAD', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'):
                with self.subTest(path=path, method=method):
                    status, _, _ = self.request(path, method=method, value={} if method == 'POST' else None, owner=False)
                    self.assertEqual(status, 401)
        self.assertFalse((self.directory / REGISTRY).exists())
        self.sources.detector.assert_not_called()

    def test_unknown_origin_crosssite_bad_host_and_foreign_uid_are_denied(self):
        for headers in ({'Origin': 'https://evil.example'}, {'Origin': 'null'}, {'Origin': ''},
                        {'Origin': 'http://localhost:' + str(self.http.server_port)},
                        {'Sec-Fetch-Site': 'cross-site'}, {'Host': 'localhost:' + str(self.http.server_port)},
                        {'Content-Type': 'text/plain'}, {'X-Progress-Desk': '0'}):
            with self.subTest(headers=headers):
                status, _, body = self.request(self.base + '/test', method='POST', value=self.config(), headers=headers)
                self.assertEqual((status, body), (403, {'error': 'origin_denied'}))
        # Generate proof before patching the same-user check on the private request.
        proof = auth_headers(self.origin, 'POST', self.base + '/test', json.dumps(self.config()).encode(), self.directory)
        with patch('server.same_user', return_value=False):
            self.assertEqual(self.request(self.base + '/test', method='POST', value=self.config(), owner=False, headers=proof)[0], 403)
        self.sources.detector.assert_not_called()

    def test_unknown_routes_queries_methods_and_strict_json(self):
        for path in (self.base + '?secret=anything', self.base + '/catalog?x=1', self.base + '/schema/unknown', self.base + '/missing'):
            self.assertEqual(self.request(path)[0], 404)
        self.assertEqual(self.request(self.base + '/connect')[0], 405)
        self.assertEqual(self.request(self.base + '/catalog', method='POST', value={})[0], 405)
        self.assertEqual(self.request(self.base, method='PUT')[0], 405)
        for raw in (b'{"configuration":{},"configuration":{}}', b'{"x":NaN}', b'{}', b'null', b'[]'):
            self.assertEqual(self.request(self.base + '/test', method='POST', raw=raw)[0], 400)
        self.assertEqual(self.request(self.base + '/test', method='POST', raw=b'x' * 4097)[0], 413)
        for duplicates in ([('Content-Length', '2')], [('Content-Type', 'application/json')], [('X-Progress-Desk', '1')], [('Transfer-Encoding', 'chunked')]):
            self.assertEqual(self.request(self.base + '/test', method='POST', value={}, duplicates=duplicates)[0], 400)
        self.sources.detector.assert_not_called()

    def test_browser_test_handle_is_bound_to_session_and_proofs_to_native_instance(self):
        first, second = self.session(), self.session()
        status, _, tested = self.request(self.base + '/test', method='POST', value=self.config(), owner=False, headers={'X-Nagi-Session': first})
        self.assertEqual(status, 200)
        value = {'testId': tested['testId'], 'expectedRevision': 0}
        self.assertEqual(self.request(self.base + '/connect', method='POST', value=value, owner=False, headers={'X-Nagi-Session': second})[2], {'error': 'test_expired'})
        self.assertEqual(self.request(self.base + '/connect', method='POST', value=value)[2], {'error': 'test_expired'})
        self.assertEqual(self.request(self.base + '/connect', method='POST', value=value, owner=False, headers={'X-Nagi-Session': first})[0], 200)

    def test_wizard_full_journey_and_exact_envelope_v2_compatibility(self):
        self.assertEqual(self.request(self.base + '/catalog')[0], 200)
        self.assertEqual(self.request(self.base + '/schema/t3')[2]['modes'], ['protocol2'])
        _, _, discovery = self.request(self.base + '/discover', method='POST', value={'adapterIds': ['t3'], 'placement': {'kind': 'tailscale'}})
        configuration = self.config()
        configuration['configuration']['placement'] = {'kind': 'tailscale', 'peerRef': discovery['peers'][0]['peerRef']}
        configuration['configuration']['pairing'] = BOOTSTRAP
        _, _, tested = self.request(self.base + '/test', method='POST', value=configuration)
        status, _, connected = self.request(self.base + '/connect', method='POST', value={'testId': tested['testId'], 'expectedRevision': 0})
        self.assertEqual(status, 200)
        self.sources.poll(force=True)
        status, headers, glance = self.request(self.base + '/glance')
        self.assertEqual(status, 200)
        self.assertEqual(set(glance), {'version', 'dtoVersion', 'extensions', 'platform', 'checkedAt', 'sources', 'settings', 'warnings'})
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertNotIn('Set-Cookie', headers)
        self.assertNotIn('Access-Control-Allow-Origin', headers)
        self.assertEqual(set(glance['sources'][0]), {'source', 'capabilities', 'agents', 'limits', 'coverage', 'warnings'})
        self.assertEqual(glance['sources'][0]['agents']['status'], 'ok')
        v2 = self.request('/api/glance')[2]
        self.assertEqual(set(v2), {'version', 'platform', 'checkedAt', 'agents', 'settings', 'warnings'})
        self.assertEqual(v2['version'], 2)
        self.assertEqual(set(self.request('/api/limits')[2]), {'version', 'platform', 'checkedAt', 'providers', 'machine'})
        _, _, disconnected = self.request(self.base + '/disconnect', method='POST', value={'sourceId': connected['source']['id'], 'expectedRevision': 1})
        self.assertTrue(disconnected['disconnected'])
        self.assertEqual(self.request(self.base)[2]['sources'], [])

    def test_pairing_and_upstream_failures_redact_http_errors_stdout_and_stderr(self):
        _, _, discovery = self.request(self.base + '/discover', method='POST', value={'adapterIds': ['t3'], 'placement': {'kind': 'tailscale'}})
        config = self.config()
        config['configuration']['placement'] = {'kind': 'tailscale', 'peerRef': discovery['peers'][0]['peerRef']}
        config['configuration']['pairing'] = 'http://10.0.0.2:3773/pair#token=' + BOOTSTRAP
        self.sources.detector.reset_mock()
        self.assertEqual(self.request(self.base + '/test', method='POST', value=config)[2], {'error': 'pairing_invalid'})
        self.sources.detector.assert_not_called()
        config['configuration']['pairing'] = BOOTSTRAP
        _, _, tested = self.request(self.base + '/test', method='POST', value=config)
        self.sources.exchange = Mock(side_effect=SourceError('pairing_invalid', 422))
        with patch('sys.stdout', new_callable=io.StringIO) as out, patch('sys.stderr', new_callable=io.StringIO) as err:
            result = self.request(self.base + '/connect', method='POST', value={'testId': tested['testId'], 'expectedRevision': 0})
            output = out.getvalue() + err.getvalue()
        self.assertEqual((result[0], result[2]), (422, {'error': 'pairing_invalid'}))
        self.assertEqual(output, '')
        for secret in (BOOTSTRAP, ACCESS, '100.80.1.2', '10.0.0.2'):
            self.assertNotIn(secret, json.dumps(result))

    def test_legacy_invalid_policy_keeps_its_original_v2_truth_response(self):
        legacy=AgentsService(self.directory)
        sources=SourcesService(legacy)
        self.addCleanup(sources.close)
        self.http.service,self.http.sources=legacy,sources
        legacy.store.mutate('nagi-t3.json',{},lambda value:value.update(version=1,invalid=True))
        status,_,body=self.request('/api/glance')
        self.assertEqual(status,200)
        self.assertEqual(body['agents']['status'],'unavailable')
        self.assertEqual(self.request(self.base)[0],200)
        self.assertEqual(self.request(self.base)[2]['sources'],[])
        self.assertEqual(self.request(self.base+'/catalog')[0],200)

    def test_manual_api_uses_session_test_binding_and_never_echoes_target(self):
        value={'configuration':{'adapterId':'t3','label':'Computer 2','placement':{'kind':'manual'},
                                'mode':'protocol2','options':{'port':3773},
                                'pairing':'https://manual.tail.ts.net/pair#token='+BOOTSTRAP}}
        status,_,tested=self.request(self.base+'/test',method='POST',value=value)
        self.assertEqual(status,200)
        self.assertNotIn(BOOTSTRAP,json.dumps(tested))
        status,_,connected=self.request(self.base+'/connect',method='POST',
                                        value={'testId':tested['testId'],'expectedRevision':0})
        self.assertEqual(status,200)
        self.sources.poll(force=True)
        for resource in (connected,self.request(self.base+'/glance')[2]):
            self.assertNotIn(BOOTSTRAP,json.dumps(resource))
            self.assertNotIn('manual.tail.ts.net',json.dumps(resource))
        value['configuration']['options']['origin']='http://192.168.1.2:47880'
        self.sources.detector.reset_mock()
        self.assertEqual(self.request(self.base+'/test',method='POST',value=value)[0],422)
        self.sources.detector.assert_not_called()
        self.assertEqual(self.request(self.base+'/test',method='POST',value=value,owner=False)[0],401)
        self.assertEqual(self.request(self.base+'/test',method='POST',value=value,headers={'Origin':'https://evil.example'})[0],403)

    def test_linux_notifier_upgrade_keeps_legacy_claims_and_delivers_new_sources(self):
        from linux.agent_notifications import NOTIFICATIONS_API, NotificationConsumer
        from owner_auth import authenticated_open
        credential=self.directory/'legacy-credential'
        write_credential(credential,ACCESS)
        self.legacy.store.mutate('nagi-t3.json',{},lambda value:value.update(
            version=1,origin='http://127.0.0.1:3773',credentialFile=str(credential)))
        self.legacy.poll(force=True)
        self.reader.rows[0].update(status='failed',latestRunCompletedAt=NOW.isoformat())
        self.legacy.poll(force=True)
        old=self.legacy.notifications()[0]
        lease=self.request('/api/notifications/reserve',method='POST',value={'id':old['id']})[2]['lease']
        self.assertTrue(self.request('/api/notifications/claim',method='POST',
                                    value={'id':old['id'],'reservation':lease['reservation']})[2]['claimed'])
        self.reader.rows[0].update(status='running',latestRunId='next-run')
        self.legacy.poll(force=True)
        value=self.config()
        value['configuration'].update(placement={'kind':'manual'},pairing=BOOTSTRAP,
                                      options={'port':3773,'origin':'http://100.80.1.2:47880'})
        tested=self.request(self.base+'/test',method='POST',value=value)[2]
        status,_,connected=self.request(self.base+'/connect',method='POST',
                                        value={'testId':tested['testId'],'expectedRevision':0})
        self.assertEqual(status,200)
        self.sources.poll(force=True)
        self.reader.rows[0].update(status='failed')
        self.sources.poll(force=True)
        sent,paths=[],[]
        def transport(request,timeout):
            paths.append((request.selector,json.loads(request.data) if request.data else None))
            return authenticated_open(request,self.directory,timeout=timeout)
        consumer=NotificationConsumer(self.origin,lambda event,clicked:(sent.append(event) or True),Mock(),transport=transport)
        consumer.poll()
        self.assertEqual(len(sent),2)
        self.assertNotIn(old['id'],[event['id'] for event in sent])
        writes=[body for path,body in paths if body is not None]
        self.assertEqual({body['sourceId'] for body in writes},{LEGACY,connected['source']['id']})
        self.assertTrue(all(path.startswith(NOTIFICATIONS_API) for path,_ in paths))
        # A new server/service/notifier reads the same durable journals. Confirmed
        # v2 legacy claims and newly acknowledged v1 deliveries must not replay.
        restored=SourcesService(AgentsService(self.directory))
        self.addCleanup(restored.close)
        self.http.sources=restored
        self.http.service=restored.legacy
        NotificationConsumer(self.origin,lambda event,clicked:(sent.append(event) or True),Mock(),transport=transport).poll()
        self.assertEqual(len(sent),2)
        self.assertEqual(restored.notifications()['events'],[])
        legacy_claims={event['id']:event['claimed'] for event in restored.legacy.journal()['events']}
        self.assertTrue(legacy_claims[old['id']])

    def test_notification_routes_require_source_and_keep_v2_delivery_protocol(self):
        _, _, tested = self.request(self.base + '/test', method='POST', value=self.config())
        _, _, connected = self.request(self.base + '/connect', method='POST', value={'testId': tested['testId'], 'expectedRevision': 0})
        self.sources.poll(force=True)
        self.reader.rows[0].update(status='failed', latestRunCompletedAt=NOW.isoformat())
        self.sources.poll(force=True)
        _, _, pending = self.request(self.base + '/notifications')
        entry = pending['events'][0]
        self.assertEqual(entry['sourceId'],connected['source']['id'])
        value = {'sourceId': entry['sourceId'], 'id': entry['event']['id']}
        _, _, reserved = self.request(self.base + '/notifications/reserve', method='POST', value=value)
        self.assertTrue(reserved['reserved'])
        self.assertEqual(self.request(self.base + '/notifications')[2]['events'], [])
        value['reservation'] = reserved['lease']['reservation']
        self.assertTrue(self.request(self.base + '/notifications/release', method='POST', value=value)[2]['released'])
        reserved = self.request(self.base + '/notifications/reserve', method='POST', value={k: v for k, v in value.items() if k != 'reservation'})[2]
        value['reservation'] = reserved['lease']['reservation']
        self.assertTrue(self.request(self.base + '/notifications/claim', method='POST', value=value)[2]['claimed'])
        self.assertEqual(self.request(self.base + '/notifications')[2]['events'], [])
        self.assertEqual(self.request('/api/notifications')[2]['events'], [])


def _process_connect(directory, barrier, queue):
    """Independent process, independent lock/store objects, same private registry."""
    try:
        legacy = AgentsService(Path(directory), lambda _: Reader(), lambda: NOW)
        def issue(path):
            fd = os.open(Path(directory) / 'issued', os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(b'issued\n')
            write_credential(path, ACCESS)
        service = SourcesService(legacy, detector=lambda _: {'environmentId': 'same-environment'}, issuer=issue, reader_factory=lambda _: Reader())
        tested = service.test({'configuration': {'adapterId': 't3', 'mode': 'protocol2', 'label': 'This computer',
                                               'placement': {'kind': 'local'}, 'options': {'port': 3773}}}, OWNER)
        barrier.wait(5)
        result = service.connect({'testId': tested['testId'], 'expectedRevision': 0}, OWNER)
        queue.put(result['revision'])
    except SourceError as error:
        queue.put(error.code)
    except Exception:  # noqa: BLE001 - report a closed fixture failure instead of leaking child diagnostics.
        queue.put('unexpected_error')


class CrossProcessConnect(TestCase):
    def test_two_processes_cannot_mint_two_sessions_before_atomic_commit(self):
        directory = Path(self.enterContext(TemporaryDirectory()))
        context = multiprocessing.get_context('spawn')
        barrier, queue = context.Barrier(2), context.Queue()
        workers = [context.Process(target=_process_connect, args=(str(directory), barrier, queue)) for _ in range(2)]
        try:
            for worker in workers:
                worker.start()
            results = [queue.get(timeout=10) for _ in workers]
            self.assertCountEqual(results, [1, 'configuration_changed'])
            for worker in workers:
                worker.join(5)
                self.assertEqual(worker.exitcode, 0)
            self.assertEqual((directory / 'issued').read_text(), 'issued\n')
        finally:
            for worker in workers:
                if worker.is_alive():
                    worker.terminate()
                worker.join(5)
            queue.close()
            queue.join_thread()
