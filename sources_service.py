"""Owner-only source registry and setup operations; stdlib, closed T3 allowlist."""
import copy
import fcntl
import json
import os
import re
import secrets
import stat
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

from agents_projection import display, project_agents, stamp, text
from agents_service import AgentsService, outcome
from ci_service import CIService, CI_SOURCE_ID
from nagi_store import LocalStore
from local_sources import binding, owned_root
from source_adapters import ADAPTERS, COVERAGE, FLAGS
from sources_transport import (
    SourceError,
    exchange_pairing,
    issue_local,
    local_cli,
    manual_pairing_target,
    pairing_target,
    private_directory,
    tailnet_inventory,
)
from t3_reader import T3Reader, Unavailable, Unsupported, source_origin

MAX_SOURCES=16
MAX_ENVELOPE_BYTES=8*1024*1024
SOURCE_READ_SECONDS=20
TEST_SECONDS=120
REGISTRY = 'nagi-sources.json'
LEGACY = 'legacy-t3'
HANDLE = re.compile(r'[A-Za-z0-9_-]{43}')
SOURCE_ID = re.compile(r'(?:legacy-t3|[0-9a-f]{32})')
CATALOG = (
    ('t3', 'T3 Code', 't3_protocol2'),
    ('openbot', 'OpenBot', 'openbot_export_required'),
    ('pi', 'Pi', 'pi_sidecar_required'),
    ('omp', 'oh-my-pi', 'omp_pi_family_planned'),  # Pi family; listed honestly, not selectable yet
    ('codex', 'Codex', 'codex_direct'),
    ('claude', 'Claude Code', 'claude_direct'),
    ('hermes', 'Hermes', 'hermes_scoped_export_required'),
    ('openclaw', 'OpenClaw', 'openclaw_scoped_gateway_required'),
    ('opencode', 'OpenCode', 'opencode_versioned_adapter_required'),
    ('cursor', 'Cursor', 'cursor_direct'),
)
HARNESS_IDS = {item[0] for item in CATALOG}
HARNESS_ORDER={item[0]:index for index,item in enumerate(CATALOG)}


def source_sort_key(entry):
    return HARNESS_ORDER[entry['harness']],entry['label'],entry['id']
UNVERIFIED = dict.fromkeys(COVERAGE, 'unverified')


def exact(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= set(value) <= set(required) | set(optional):
        raise SourceError('invalid_request')


def handle(value):
    if not isinstance(value, str) or not HANDLE.fullmatch(value):
        raise SourceError('invalid_request')
    return value


def source_id(value):
    if not isinstance(value, str) or not SOURCE_ID.fullmatch(value):
        raise SourceError('invalid_request')
    return value


def revision(value):
    if type(value) is not int or value < 0:
        raise SourceError('invalid_request')
    return value


def label(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 80:
        raise SourceError('invalid_request')
    return display(value, 80, 'This computer')


def tag(entry):
    return {key: entry[key] for key in ('id', 'harness', 'label', 'placement')}


class PrivateConfiguration(dict):
    def __repr__(self):
        return '<private source configuration>'
    __str__ = __repr__


class BoundedReader:
    """Four shared I/O slots; a fresh T3 client carries its whole-read deadline."""
    def __init__(self,reader,slots,deadline=None):
        self._reader,self._slots,self._deadline=reader,slots,deadline
        if deadline is not None and isinstance(reader,T3Reader):
            reader._source_deadline=deadline

    def __getattr__(self,name):
        value=getattr(self._reader,name)
        if name not in ('shell','config','detail','liveness','favicon_url','asset'):
            return value
        def read(*args,**kwargs):
            remaining=8 if self._deadline is None else self._deadline-time.monotonic()
            if remaining<=0 or not self._slots.acquire(timeout=remaining):
                raise Unavailable()
            try:
                if self._deadline is not None and time.monotonic()>=self._deadline:
                    raise Unavailable()
                return value(*args,**kwargs)
            finally:
                self._slots.release()
        return read


class SourcesService:
    def __init__(self, legacy_service, *, detector=None, inventory=None, issuer=None,
                 exchange=None, reader_factory=None, local_home=None):
        self.legacy = legacy_service
        self.clock = legacy_service.clock
        self.directory = private_directory(legacy_service.store.directory)
        self.store = LocalStore(self.directory)
        self.local_home = Path(local_home) if local_home is not None else Path.home()
        self.detector = detector or ADAPTERS['t3'].detect
        self.inventory = inventory or tailnet_inventory
        self.issuer = issuer or issue_local
        self.exchange = exchange or exchange_pairing
        self.reader_factory = reader_factory or T3Reader.from_policy
        self.lock = threading.RLock()
        self.read_slots=threading.BoundedSemaphore(4)
        self.executor=ThreadPoolExecutor(max_workers=4,thread_name_prefix='nagi-source')
        self.pending={}
        self.closed=False
        self._test_timer=None
        self._timer_deadline=None
        self._timer_generation=0
        original=getattr(legacy_service,'_source_base_factory',legacy_service.factory)
        legacy_service._source_base_factory=original
        legacy_service.factory=lambda directory: BoundedReader(original(directory),self.read_slots)
        self.peers, self.tests, self.services = {}, {}, {}
        self.ci = CIService(self.store, self.local_home, self.clock, self.ci_candidates)

    def detect_origin(self,origin):
        if not self.read_slots.acquire(timeout=8):
            raise Unavailable()
        try:
            return self.detector(origin)
        finally:
            self.read_slots.release()

    def catalog(self):
        return {'version': 1, 'harnesses': [
            {'id': key, 'displayName': name, 'iconKey': key, 'available': key in ADAPTERS,
             'status': 'available' if key in ADAPTERS else 'coming_soon',
             'capabilities': dict(ADAPTERS[key].potential_capabilities) if key in ADAPTERS else dict.fromkeys(FLAGS, False),
             'copyKey': copy_key, **({'beta':True} if key=='cursor' else {})} for key, name, copy_key in CATALOG]}

    def schema(self, harness):
        if harness not in HARNESS_IDS:
            raise SourceError('not_found', 404)
        if harness in ADAPTERS:
            return ADAPTERS[harness].configuration_schema()
        return {'version': 1, 'harness': harness, 'available': False, 'modes': [],
                'capabilities': dict.fromkeys(FLAGS, False), 'requirements': ['coming_soon']}

    def legacy_entry(self):
        # An invalid legacy file must not prevent recovery through the wizard.
        # Never repair it, follow its links or read a credential while importing.
        try:
            policy=self.store.read('nagi-t3.json',None)
            if policy is None:return None
            policy=ADAPTERS['t3'].configure(policy)
            local=source_origin(policy['origin'])[0]=='loopback'
            return {'id':LEGACY,'harness':'t3','label':'This computer' if local else 'Computer 2',
                    'placement':'local' if local else 'tailscale','policy':policy,'ownedCredential':False}
        except (OSError,ValueError,TypeError,KeyError,SourceError,RecursionError):
            return None

    def validate_registry(self, value):
        exact(value, ('version', 'revision', 'sources'))
        if type(value['version']) is not int or value['version'] != 1:
            raise ValueError()
        revision(value['revision'])
        if not isinstance(value['sources'], list) or len(value['sources']) > MAX_SOURCES:
            raise ValueError()
        ids, origins = set(), set()
        for entry in value['sources']:
            exact(entry, ('id', 'harness', 'label', 'placement', 'policy', 'ownedCredential'),('environmentId',))
            if 'environmentId' in entry:text(entry['environmentId'])
            source_id(entry['id'])
            if entry['harness'] not in ADAPTERS or type(entry['ownedCredential']) is not bool:
                raise ValueError()
            if label(entry['label']) != entry['label']:
                raise ValueError()
            policy = ADAPTERS[entry['harness']].configure(entry['policy'])
            if entry['harness']!='t3':
                if (entry['placement']!='this_computer' or entry['ownedCredential'] or entry['id']==LEGACY
                        or entry['id'] in ids or policy['home']!=str(self.local_home)):
                    raise ValueError()
                key=(entry['harness'],policy['home'])
                if key in origins:raise ValueError()
                ids.add(entry['id']);origins.add(key)
                continue
            if entry['placement'] not in ('local','tailscale'):raise ValueError()
            if (source_origin(policy['origin'])[0] == 'loopback') != (entry['placement'] == 'local'):
                raise ValueError()
            if entry['id'] in ids or policy['origin'] in origins:
                raise ValueError()
            if entry['ownedCredential']:
                if entry['id'] == LEGACY or Path(policy['credentialFile']) != self.directory / 'source-secrets' / (entry['id'] + '.json'):
                    raise ValueError()
            elif entry['id'] != LEGACY:
                raise ValueError()
            ids.add(entry['id'])
            origins.add(policy['origin'])

    def registry(self):
        try:
            value = self.store.read(REGISTRY, None)
            if value is None:
                old = self.legacy_entry()
                value = {'version': 1, 'revision': 0, 'sources': [old] if old else []}
            self.validate_registry(value)
            return value
        except (OSError, ValueError, TypeError, KeyError, SourceError, RecursionError):
            raise SourceError('storage_unavailable', 503) from None

    @contextmanager
    def lifecycle(self, *, shared=False, source=None):
        name='.nagi-sources.lock' if source is None else f'.nagi-source-{source}-lock'
        fd = os.open(self.directory / name, os.O_RDONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise SourceError('storage_unavailable', 503)
            fcntl.flock(fd, fcntl.LOCK_SH if shared else fcntl.LOCK_EX)
            yield
        finally:
            try:
                if source is not None and not any(e['id']==source for e in self.registry()['sources']):
                    self.store.unlink_owned(name,expected=os.fstat(fd))
            except (OSError,ValueError,SourceError):
                pass  # Never replace an unsafe inode or mask the original failure.
            finally:
                os.close(fd)

    @contextmanager
    def transaction(self):
        # Separate from LocalStore's write lock: serializes issuance and lifecycle
        # changes across processes, while parallel source reads share the lock.
        with self.lifecycle():
            yield

    def persist(self, registry):
        self.validate_registry(registry)
        def write(current):
            current.clear()
            current.update(registry)
        self.store.mutate(REGISTRY, {}, write)

    def service_for(self, entry):
        if entry['id'] == LEGACY:
            return self.legacy
        identity = entry['id']
        service = self.services.get(identity)
        if service is None:
            policy = dict(entry['policy'])
            def factory(_):
                return BoundedReader(self.reader_factory(policy),self.read_slots,time.monotonic()+SOURCE_READ_SECONDS)
            service = AgentsService(self.directory, factory, self.clock, source_id=identity)
            service.adapter_id=entry['harness']
            service.policy=policy
            if entry['harness']=='cursor':
                at=self.clock().isoformat()
                service.providers={'cursor':{**outcome('unavailable',at,reason='checking'),'warnings':[]}}
            # This computer's settings and machine metrics are shared. No second
            # settings cache/file and no remote host metrics are exposed.
            service.read_machine = lambda _: None
            self.services[identity] = service
        return service

    def legacy_active(self):
        return any(e['id']==LEGACY for e in self.registry()['sources'])

    def poll_legacy(self):
        # V2 reads participate in the same lifecycle lock as envelope reads;
        # disconnect cannot race an old native client into another source read.
        with self.lifecycle(shared=True,source=LEGACY):
            if self.store.read(REGISTRY,None) is None or self.legacy_active():
                self.legacy.poll()
            else:
                with self.legacy.lock:
                    at=self.clock().isoformat()
                    self.legacy.agents=outcome('not_set_up',at,reason='not_configured')
                    self.legacy.providers={k:{**outcome('not_set_up',at,reason='not_configured'),'warnings':[]} for k in ('codex','claude')}
                    self.legacy.icon_sources={}
                    self.legacy.read_machine(at)

    def _read_source(self,entry,service,force):
        # Readers share lifecycle locks; disconnect waits for existing I/O and a
        # queued task rechecks selection before it can begin any source read.
        with self.lifecycle(shared=True,source=entry['id']):
            if not any(e['id']==entry['id'] for e in self.registry()['sources']):
                return
            try:
                service.poll(force=force)
                # Selected direct readers own local provider alerts, including
                # during outages; an overlapping T3 fallback must not alert twice.
                with self.lock:
                    direct=self.direct_limit_owners()
                    t3_codex=self.t3_reads_codex()
                suppressed=(tuple(direct) if entry['harness']=='t3' and entry['placement']=='local'
                            else ('codex',) if entry['harness']=='codex' and t3_codex else ())
                with service.lock:service.record_limit_alerts(self.legacy.settings(),suppressed=suppressed)
            except Exception:  # noqa: BLE001 - isolate adapters and never expose provider text.
                with service.lock:
                    service.last_poll=self.clock()
                    at=service.last_poll.isoformat()
                    service.agents=service.failed('unavailable',at,'invalid_source',service.agents if service.agents.get('data') else None)
                    service.providers={k:{**service.failed('unavailable',at,'invalid_source',v if v.get('data') else None,self.clock()),'warnings':[]}
                                       for k,v in service.providers.items()}

    def ci_candidates(self):
        active, ended = [], []
        incomplete = False
        now = self.clock()
        with self.lock:
            for entry in self.registry()['sources']:
                if entry['harness'] not in ('claude', 'codex', 't3') or entry['placement']=='tailscale':
                    continue
                service = self.service_for(entry)
                with service.lock:
                    if (service.agents['status'] not in ('ok', 'quiet') or service.last_poll is None
                            or not 0 <= (now - service.last_poll).total_seconds() <= 90):
                        incomplete = True
                        continue
                    incomplete |= bool((service.agents['data'] or {}).get('omittedRows')
                                       or 'coverage_incomplete' in (service.agents['data'] or {}).get('warnings', []))
                    for candidate in service.ci_workspaces:
                        (active if candidate[1]=='active' else ended).append(candidate)
        return active + ended, incomplete

    def poll(self, force=False):
        with self.lock:
            if self.closed:
                return
            entries=self.registry()['sources']
            self.pending={key:future for key,future in self.pending.items() if not future.done()}
            active={entry['id'] for entry in entries}
            self.services={key:service for key,service in self.services.items() if key in active}
            for entry in entries:
                service=self.service_for(entry)
                if entry['id'] in self.pending:
                    continue
                if not force and service.last_poll is not None and 0<=(self.clock()-service.last_poll).total_seconds()<20:
                    continue
                self.pending[entry['id']]=self.executor.submit(self._read_source,entry,service,force)
            waiting=list(self.pending.values())
        if force:
            for future in waiting:
                future.result()
        self.ci.schedule()

    def close(self,*,wait=True):
        with self.lock:
            self.closed=True
            if self._test_timer is not None:self._test_timer.cancel()
            self._test_timer=None
            for record in self.tests.values():
                record.get('configuration',{}).pop('pairing',None)
            self.tests.clear()
        self.executor.shutdown(wait=wait,cancel_futures=True)
        self.ci.close(wait)

    @staticmethod
    def bound_sources(sources):
        # Keep all source identities. Remove the largest payload, never an entire
        # source or a healthy neighbour, and expose a closed coverage warning.
        def size(value):
            return len(json.dumps(value,ensure_ascii=False,separators=(',',':')).encode())
        total=sum(size(source) for source in sources)
        if total<=MAX_ENVELOPE_BYTES-16384:
            return sources
        measures=[]
        for source in sources:
            for kind,measure in [('agents',source['agents']),*source['limits'].items()]:
                if measure.get('data') is not None:
                    measures.append((size(measure['data']),source,kind,measure))
        for amount,source,kind,measure in sorted(measures,key=lambda item:item[0],reverse=True):
            measure.update(status='unavailable',reason='coverage_incomplete',data=None)
            source['coverage']['agents' if kind=='agents' else 'limits']='partial'
            if 'response_truncated' not in source['warnings']:
                source['warnings'].append('response_truncated')
            total-=amount-64
            if total<=MAX_ENVELOPE_BYTES-16384:
                break
        return sources

    def read_sources(self):
        self.poll()
        with self.lock:
            registry = self.registry()
            result = []
            for entry in sorted(registry['sources'], key=source_sort_key):
                service = self.service_for(entry)
                with service.lock:
                    adapter=ADAPTERS.get(entry['harness'])
                    result.append({'source': tag(entry), 'capabilities': dict(adapter.potential_capabilities) if adapter else dict.fromkeys(FLAGS,False),
                                   'agents': copy.deepcopy(service.agents), 'limits': copy.deepcopy(service.providers),
                                   'coverage': dict(getattr(adapter,'coverage',COVERAGE)), 'warnings': service.warnings()})
            return {'version': 1, 'revision': registry['revision'], 'sources': self.bound_sources(result)}

    def glance(self, platform):
        resource = self.read_sources()
        # Explicit owner-selected preferred observation, local Claude only.
        # The underlying T3 snapshot stays intact for immediate fallback.
        if any(s['source']['harness']=='claude' and self.fresh_limits(s['limits']['claude']) for s in resource['sources']):
            for source in resource['sources']:
                if source['source']['harness']=='t3' and source['source']['placement']=='local':
                    source['limits']['claude']={**outcome('unsupported',self.clock().isoformat(),reason='preferred_direct_source'),'warnings':[]}
        return {'version': 1, 'dtoVersion': 2, 'extensions': ['nullable_links'],
                'platform': platform, 'checkedAt': self.clock().isoformat(), 'sources': resource['sources'],
                'settings': self.legacy.settings(), 'warnings': self.legacy.warnings()+
                (['response_truncated'] if any('response_truncated' in s['warnings'] for s in resource['sources']) else [])}

    def fresh_limits(self,value):
        try:
            return (value['status']=='ok' and -5<=(self.clock()-stamp(value['checkedAt'])).total_seconds()<=900
                    and bool(value['data']['accounts']))
        except (KeyError,ValueError,TypeError):return False

    def _arm_test_expiry(self):
        if self.closed or not self.tests:
            if self._test_timer is not None:self._test_timer.cancel()
            self._test_timer=None;self._timer_deadline=None
            self._timer_generation+=1
            return
        now=time.monotonic()
        delay=min(max(0,min((v['expires']-self.clock()).total_seconds(),v.get('deadline',float('inf'))-now))
                  for v in self.tests.values())
        deadline=now+delay
        if self._test_timer is not None and self._timer_deadline<=deadline:return
        if self._test_timer is not None:self._test_timer.cancel()
        self._timer_generation+=1
        timer=threading.Timer(delay,self._purge_tests,args=(self._timer_generation,))
        timer.daemon=True
        self._test_timer=timer;self._timer_deadline=deadline
        timer.start()

    def _purge_tests(self,generation):
        with self.lock:
            if self.closed or generation!=self._timer_generation:return
            self._test_timer=None;self._timer_deadline=None
            self.expire()

    def expire(self):
        with self.lock:
            now=self.clock();monotonic=time.monotonic()
            self.peers={k:v for k,v in self.peers.items() if v['expires']>now}
            for key,value in list(self.tests.items()):
                if value['expires']<=now or value.get('deadline',float('inf'))<=monotonic:
                    value.get('configuration',{}).pop('pairing',None)
                    self.tests.pop(key,None)
            self._arm_test_expiry()

    def peer(self, reference, owner):
        handle(reference)
        item = self.peers.get(reference)
        if not item or item['owner'] != owner or item['expires'] <= self.clock():
            raise SourceError('peer_expired', 409)
        return item['peer']

    def discover(self, value, owner):
        exact(value, ('adapterIds', 'placement'))
        ids = value['adapterIds']
        if (not isinstance(ids, list) or not ids or len(ids) > len(CATALOG)
                or any(not isinstance(k, str) or k not in HARNESS_IDS for k in ids) or len(set(ids)) != len(ids)):
            raise SourceError('invalid_request')
        placement = value['placement']
        exact(placement, ('kind',), ('peerRef',))
        if placement['kind'] not in ('local', 'this_computer', 'tailscale') or ('peerRef' in placement and placement['kind'] != 'tailscale'):
            raise SourceError('invalid_request')
        peers,warnings,candidates=[],[],[]
        if placement['kind']=='tailscale':
            if 'peerRef' in placement:
                with self.lock:
                    self.expire()
                    peer=copy.deepcopy(self.peer(placement['peerRef'],owner))
                peers=[{'peerRef':placement['peerRef'],'label':peer['label'],'online':peer['online']}]
            else:
                try:found=self.inventory()
                except Exception:  # noqa: BLE001 - never expose discovery diagnostics.
                    found=[];warnings.append('tailscale_unavailable')
                with self.lock:
                    self.expire()
                    if len(found)+len(self.peers)>512:raise SourceError('capacity_reached',503)
                    expires=self.clock()+timedelta(minutes=5)
                    for peer in found:
                        reference=secrets.token_urlsafe(32)
                        self.peers[reference]={'peer':peer,'owner':owner,'expires':expires}
                        peers.append({'peerRef':reference,'label':peer['label'],'online':peer['online']})
        for harness in ids:
            installed,running,evidence='unknown','unknown',[]
            if placement['kind'] in ('local','this_computer') and harness in ADAPTERS and harness!='t3':
                import shutil
                from codex_usage import codex_home
                root=codex_home(self.local_home) if harness=='codex' else self.local_home/('.'+harness)
                if root.is_dir():evidence.append('data_found')
                if any(shutil.which(binary) for binary in (('cursor','cursor-agent') if harness=='cursor' else (harness,))):evidence.append('binary_found')
                installed='yes' if evidence else 'no'
            if placement['kind'] in ('local','this_computer') and harness=='t3':
                try:
                    local_cli()
                    installed,evidence='yes',['binary_found']
                except SourceError:installed='no'
                try:
                    self.detect_origin('http://127.0.0.1:3773')
                    running='yes';evidence.append('endpoint_found')
                except Exception:  # noqa: BLE001 - probe failures remain unknown.
                    running='unknown'
            expires=self.clock()+timedelta(minutes=5)
            references=[p['peerRef'] for p in peers] if placement['kind']=='tailscale' else [None]
            for reference in references:
                candidates.append({'candidateId':secrets.token_urlsafe(32),'harness':harness,
                                   'placement':placement['kind'],'peerRef':reference,'installed':installed,
                                   'running':running,'readable':'unknown','evidence':evidence,
                                   'expiresAt':expires.isoformat()})
        return {'version':1,'candidates':candidates,'peers':peers,'warnings':warnings}

    def configuration(self, value, owner):
        exact(value, ('adapterId', 'label', 'placement', 'mode', 'options'), ('pairing',))
        if not isinstance(value['adapterId'], str) or value['adapterId'] not in HARNESS_IDS:
            raise SourceError('invalid_request')
        clean_label = label(value['label'])
        placement = value['placement']
        exact(placement, ('kind',), ('peerRef',))
        if value['adapterId'] in ADAPTERS and value['adapterId']!='t3':
            exact(placement,('kind',));exact(value['options'],())
            if (placement['kind'] not in ('local','this_computer') or 'pairing' in value
                    or (value['adapterId']=='cursor' and placement['kind']!='this_computer')):
                raise SourceError('invalid_request')
            adapter=ADAPTERS[value['adapterId']]
            if value['mode'] not in adapter.configuration_schema()['modes']:raise SourceError('invalid_request')
            policy={'version':1,'home':str(self.local_home)}
            if value['adapterId']=='codex':policy.update(version=2,usageOptIn=True)
            return PrivateConfiguration(adapterId=value['adapterId'],label=clean_label,placement='this_computer',
                                        policy=adapter.configure(policy))
        exact(value['options'],('port',),('origin',) if placement.get('kind')=='manual' else ())
        if 'origin' in value['options'] and not isinstance(value['options']['origin'],str):
            raise SourceError('invalid_request')
        port = value['options']['port']
        if type(port) is not int or not 1 <= port <= 65535:
            raise SourceError('invalid_request')
        if not isinstance(value['mode'],str) or not 0<len(value['mode'])<=64:
            raise SourceError('invalid_request')
        if placement.get('kind')=='local':
            if set(placement)!={'kind'} or 'pairing' in value:
                raise SourceError('invalid_request')
        elif placement.get('kind')=='manual':
            exact(placement,('kind',))
            if 'pairing' not in value or not isinstance(value['pairing'],str):
                raise SourceError('invalid_request')
        elif placement.get('kind')=='tailscale':
            exact(placement,('kind','peerRef'))
            self.peer(placement['peerRef'],owner)
            if 'pairing' not in value or not isinstance(value['pairing'],str):
                raise SourceError('invalid_request')
        else:
            raise SourceError('invalid_request')
        if value['adapterId'] != 't3':
            return None
        if value['mode'] != 'protocol2':
            raise SourceError('invalid_request')
        if placement=={'kind':'manual'}:
            try:
                origin,token=manual_pairing_target(value['pairing'],value['options'].get('origin'))
            except (ValueError,TypeError):
                raise SourceError('pairing_invalid',422) from None
            return PrivateConfiguration(label=clean_label,placement='local' if source_origin(origin)[0]=='loopback' else 'tailscale',
                                        origin=origin,pairing=token)
        if placement == {'kind': 'local'}:
            if 'pairing' in value:
                raise SourceError('invalid_request')
            if port != 3773:
                raise SourceError('local_pairing_unavailable', 422)
            return PrivateConfiguration(label=clean_label, placement='local', origin=f'http://127.0.0.1:{port}', pairing=None)
        exact(placement, ('kind', 'peerRef'))
        if placement['kind'] != 'tailscale' or 'pairing' not in value:
            raise SourceError('invalid_request')
        peer = self.peer(placement['peerRef'], owner)
        try:
            origin, token = pairing_target(value['pairing'], peer, port)
        except (ValueError, TypeError):
            raise SourceError('pairing_invalid', 422) from None
        return PrivateConfiguration(label=clean_label, placement='tailscale', origin=origin, pairing=token)

    def test(self, value, owner):
        exact(value, ('configuration',))
        with self.lock:
            if self.closed:raise SourceError('storage_unavailable',503)
            self.expire()
            configuration = self.configuration(value['configuration'], owner)
        status, reason, requirement, successful = 'not_set_up', 'not_configured', [], False
        if configuration is None:
            status, reason, requirement = 'unsupported', 'protocol_unsupported', ['coming_soon']
        elif configuration.get('adapterId'):
            adapter=ADAPTERS[configuration['adapterId']]
            requirement=adapter.configuration_schema()['requirements']
            try:
                from codex_usage import codex_home
                root=owned_root(codex_home(self.local_home) if configuration['adapterId']=='codex' else self.local_home/('.'+configuration['adapterId']))
                if configuration['adapterId'] in ('claude','cursor'):
                    if configuration['adapterId']=='cursor':
                        from cursor_hooks import settings
                    else:
                        from claude_hooks import settings
                    settings(self.local_home)
                # Codex usage can work without any session rollouts.
                successful=True
            except Exception:status,reason='unavailable','local_data_missing'
        else:
            requirement = ['local_auto_pair' if configuration['pairing'] is None else 'pairing_exchange']
            try:
                descriptor=self.detect_origin(configuration['origin'])
                configuration['environmentId']=text(descriptor.get('environmentId',descriptor.get('id')))
                successful = True
            except Unsupported:
                status, reason = 'unsupported', 'protocol_unsupported'
            except Exception:  # noqa: BLE001 - isolate adapter errors without exposing provider text.
                status, reason = 'unavailable', 'cannot_reach_source'
        identity, expires = None, None
        if successful:
            with self.lock:
                self.expire()
                if self.closed:raise SourceError('storage_unavailable',503)
                if len(self.tests) >= 128:
                    raise SourceError('capacity_reached', 503)
                identity, expires = secrets.token_urlsafe(32), self.clock() + timedelta(seconds=TEST_SECONDS)
                self.tests[identity] = {'owner': owner, 'expires': expires, 'deadline':time.monotonic()+TEST_SECONDS, 'configuration': configuration}
                self._arm_test_expiry()
        summary = {'status': status, 'checkedAt': None, 'reason': reason}
        return {'version': 1, 'testId': identity, 'expiresAt': expires.isoformat() if expires else None,
                'capabilities': dict(ADAPTERS[configuration.get('adapterId','t3')].potential_capabilities) if configuration else dict.fromkeys(FLAGS, False),
                'coverage': dict(UNVERIFIED), 'agents': summary,
                'limits': {k: dict(summary) for k in (('cursor',) if configuration and configuration.get('adapterId')=='cursor' else ('codex','claude'))},
                'requirements': requirement, 'warnings': []}

    def connection_bindings(self,registry):
        bindings=[]
        for entry in registry['sources']:
            if entry['harness']!='t3':continue
            legacy=entry['id']==LEGACY
            live=self.legacy_entry() if legacy else entry
            if live is None:continue
            policy=live['policy']
            environment=None if legacy else entry.get('environmentId')
            if environment is None and not legacy:
                try:
                    journal=self.store.read(f"nagi-source-{entry['id']}-state.json",{})
                    AgentsService.validate_journal(journal)
                    environment=journal.get('cache',{}).get('agents',{}).get('data',{}).get('environmentId')
                    if environment is not None:text(environment)
                except (OSError,ValueError,TypeError,KeyError):environment=None
            if environment is None:
                try:
                    descriptor=self.detect_origin(policy['origin'])
                    environment=text(descriptor.get('environmentId',descriptor.get('id')))
                except Exception:  # noqa: BLE001 - an offline source must not disable setup.
                    environment=None
            if legacy:
                entry['policy']=dict(policy);entry['placement']=live['placement']
                entry.pop('environmentId',None)
            if environment is not None:entry['environmentId']=environment
            bindings.append((policy,environment))
        return bindings

    def connect(self, value, owner):
        exact(value, ('testId', 'expectedRevision'))
        handle(value['testId'])
        revision(value['expectedRevision'])
        with self.transaction():
            registry = self.registry()
            if registry['revision'] != value['expectedRevision']:
                raise SourceError('configuration_changed', 409)
            with self.lock:
                self.expire()
                test = self.tests.get(value['testId'])
                if not test or test['owner'] != owner:
                    raise SourceError('test_expired', 409)
                if test['configuration'].get('adapterId'):
                    return self.connect_local(registry,test,value['testId'])
                target_origin=test['configuration']['origin']
                target_environment=test['configuration']['environmentId']
                if len(registry['sources'])>=MAX_SOURCES:raise SourceError('capacity_reached',503)
            # Identity probes must not hold the feed/state lock. The registry
            # writer lock still serializes revision checks and session issuance.
            bindings=self.connection_bindings(registry)
            if any(source_origin(policy['origin'])==source_origin(target_origin)
                   or environment==target_environment for policy,environment in bindings):
                raise SourceError('source_exists',409)
            with self.lock:
                self.expire()
                test=self.tests.get(value['testId'])
                if not test or test['owner']!=owner:raise SourceError('test_expired',409)
                configuration=test['configuration']
                self.tests.pop(value['testId'])
                self._arm_test_expiry()
            identity = secrets.token_hex(16)
            directory = private_directory(self.directory / 'source-secrets')
            credential = directory / (identity + '.json')
            committed = False
            try:
                if configuration['pairing'] is None:
                    self.issuer(credential)
                else:
                    from sources_transport import write_credential
                    token = self.exchange(configuration['origin'], configuration['pairing'])
                    write_credential(credential, token)
                policy = ADAPTERS['t3'].configure({'version': 1, 'origin': configuration['origin'], 'credentialFile': str(credential)})
                # Real credential parser enforces exact read-only scope and owner
                # file safety, even when the provider/CLI is injected in tests.
                T3Reader.from_policy(policy)
                reader=BoundedReader(self.reader_factory(policy),self.read_slots,time.monotonic()+SOURCE_READ_SECONDS)
                descriptor, snapshot = reader.shell()
                if descriptor.get('environmentId',descriptor.get('id')) != configuration['environmentId']:
                    raise SourceError('connection_failed',422)
                project_agents(descriptor, snapshot, [], self.legacy.settings(), {}, self.clock())
                entry = {'id': identity, 'harness': 't3', 'label': configuration['label'],
                         'placement': configuration['placement'], 'policy': policy, 'ownedCredential': True,
                         'environmentId':configuration['environmentId']}
                registry['sources'].append(entry)
                registry['revision'] += 1
                self.persist(registry)
                committed = True
                return {'version': 1, 'revision': registry['revision'], 'source': tag(entry),
                        'capabilities': dict(FLAGS), 'coverage': dict(COVERAGE)}
            except SourceError:
                raise
            except OSError:
                raise SourceError('storage_unavailable', 503) from None
            except Exception:  # noqa: BLE001 - isolate adapter errors without exposing provider text.
                raise SourceError('connection_failed', 422) from None
            finally:
                if not committed:
                    credential.unlink(missing_ok=True)

    def disconnect(self, value):
        exact(value, ('sourceId', 'expectedRevision'))
        identity = source_id(value['sourceId'])
        revision(value['expectedRevision'])
        with self.transaction():
            registry = self.registry()
            if registry['revision'] != value['expectedRevision']:
                raise SourceError('configuration_changed', 409)
            entry = next((e for e in registry['sources'] if e['id'] == identity), None)
            if entry is None:
                return {'version': 1, 'revision': registry['revision'], 'disconnected': False}
            with self.lock:
                service = self.service_for(entry)
            # Wait for this source's in-flight poll, then retire delivery before
            # unpublishing. Another source's journal and leases remain untouched.
            with self.lifecycle(source=identity),service.poll_gate,service.lock:
                if entry['harness'] in ('claude','cursor'):
                    if entry['harness']=='cursor':
                        from cursor_hooks import edit
                    else:
                        from claude_hooks import edit
                    try:edit(entry['policy']['home'],self.directory,identity,remove=True)
                    except Exception:raise SourceError('hook_remove_failed',422) from None
                registry['sources'].remove(entry)
                registry['revision']+=1
                try:self.persist(registry)
                except Exception:
                    if entry['harness'] in ('claude','cursor') and any(e['id']==identity for e in self.registry()['sources']):
                        try:edit(entry['policy']['home'],self.directory,identity)
                        except Exception:raise SourceError('hook_install_failed',422) from None
                    raise
                service.revision+=1
                # Registry publication is the visibility boundary; remove cache
                # names atomically only after reads/claims have been excluded.
                service.store.remove(service.journal_name)
                if entry['ownedCredential']:
                    private_directory(self.directory/'source-secrets')
                    LocalStore(self.directory/'source-secrets').unlink_owned(identity+'.json')
                if entry['harness'] in ('claude','cursor'):
                    # The hook log and its lock belong to this source alone.
                    for name in (entry['harness']+'-'+identity+'.jsonl',entry['harness']+'-'+identity+'.jsonl.1','.'+entry['harness']+'-'+identity+'.lock'):
                        try:service.store.unlink_owned(name)
                        except (OSError,ValueError):pass
                at=self.clock().isoformat()
                service.agents=outcome('not_set_up',at,reason='not_configured')
                service.providers={k:{**outcome('not_set_up',at,reason='not_configured'),'warnings':[]}
                                   for k in ('codex','claude')}
                service.icon_sources.clear();service.icon_cache.clear()
            with self.lock:self.services.pop(identity,None)
            return {'version': 1, 'revision': registry['revision'], 'disconnected': True}

    def connect_local(self,registry,test,test_id):
        configuration=test['configuration'];harness=configuration['adapterId']
        if any(e['harness']==harness and e['policy']==configuration['policy'] for e in registry['sources']):
            raise SourceError('source_exists',409)
        if len(registry['sources'])>=MAX_SOURCES:raise SourceError('capacity_reached',503)
        identity=secrets.token_hex(16)
        self.tests.pop(test_id);self._arm_test_expiry()
        installed=False
        try:
            if harness in ('claude','cursor'):
                if harness=='cursor':
                    from cursor_hooks import edit
                else:
                    from claude_hooks import edit
                try:edit(configuration['policy']['home'],self.directory,identity)
                except Exception:raise SourceError('hook_install_failed',422) from None
                installed=True
            entry={'id':identity,'harness':harness,'label':configuration['label'],'placement':'this_computer',
                   'policy':dict(configuration['policy']),'ownedCredential':False}
            registry['sources'].append(entry);registry['revision']+=1
            self.persist(registry)
        except Exception:
            if installed:
                try:edit(configuration['policy']['home'],self.directory,identity,remove=True)
                except Exception:raise SourceError('hook_remove_failed',422) from None
            raise
        adapter=ADAPTERS[harness]
        return {'version':1,'revision':registry['revision'],'source':tag(entry),
                'capabilities':dict(adapter.potential_capabilities),'coverage':dict(adapter.coverage)}

    def notifications(self):
        with self.lock:
            events=[{'sourceId':e['id'],'event':event} for e in self.registry()['sources']
                    for event in self.service_for(e).notifications(include_limits=True)
                    if event['kind']!='low_limit' or self.limit_alert_allowed(e,event)]
            with self.ci.lock:
                if self.ci.enabled:
                    events.extend({'sourceId':CI_SOURCE_ID,'event':e} for e in self.ci.delivery.notifications())
            events.sort(key=lambda e:(e['event']['occurredAt'],e['sourceId'],e['event']['id']))
            return {'version':1,'events':events[:256]}

    def t3_reads_codex(self):
        """A local T3 whose Codex limits are fresh right now; a saved but failing T3 doesn't count."""
        return any(e['harness']=='t3' and e['placement']=='local' and self.fresh_limits(self.service_for(e).providers.get('codex'))
                   for e in self.registry()['sources'])

    def direct_limit_owners(self):
        # Claude: the direct source owns local Claude alerts (T3 shows one Claude account).
        # Codex: a local T3 that is reading Codex sees every account it runs, the direct reader
        # only the one signed in to ~/.codex, so a working local T3 keeps Codex alerts; when it
        # isn't reading, the direct source alerts so nothing goes silent.
        t3_codex=self.t3_reads_codex()
        return {e['harness'] for e in self.registry()['sources']
                if e['harness']=='claude' or (e['harness']=='codex' and e.get('policy',{}).get('usageOptIn') is True and not t3_codex)}

    def delivered_elsewhere(self,entry,event):
        """Ownership can move between sources (T3 starts or stops reading). A window another
        source already alerted for, at the same provider reset instant, never alerts again."""
        try:reset=stamp(event['resetsAt'])
        except (KeyError,ValueError,TypeError):return False
        for other in self.registry()['sources']:
            if other['id']==entry['id']:continue
            for seen in self.service_for(other).journal().get('events',[]):
                try:
                    if (seen.get('kind')=='low_limit' and seen.get('claimed') and seen['provider']==event['provider']
                            and seen['windowLabel']==event['windowLabel'] and stamp(seen['resetsAt'])==reset):return True
                except (KeyError,ValueError,TypeError):continue
        return False

    def limit_alert_allowed(self,entry,event):
        threshold=self.legacy.settings()['limitAlertPercent']
        if threshold=='off' or event['remainingPercent']>threshold:return False
        if (entry['harness']=='t3' and entry['placement']=='local'
                and event['provider'] in self.direct_limit_owners()):return False
        if event['provider']=='codex' and self.delivered_elsewhere(entry,event):return False
        if entry['harness']=='codex' and event['provider']=='codex':
            if self.t3_reads_codex():return False
            # The reader updates this on every observation, including failures.
            return event['accountId']==getattr(self.service_for(entry),'codex_account_key',None)
        return True

    def notification_action(self, action, value):
        exact(value, ('sourceId', 'id') if action == 'reserve' else ('sourceId', 'id', 'reservation'))
        if value['sourceId'] == CI_SOURCE_ID:
            with self.ci.lock:
                if not self.ci.enabled:
                    raise SourceError('not_found', 404)
                return self.delivery_action(self.ci.delivery, action, value)
        identity = source_id(value['sourceId'])
        with self.lifecycle(shared=True,source=identity):
            entry = next((e for e in self.registry()['sources'] if e['id'] == identity), None)
            if entry is None:
                raise SourceError('not_found', 404)
            with self.lock:
                service = self.service_for(entry)
            return self.delivery_action(service, action, value, entry)

    def delivery_action(self, service, action, value, entry=None):
        try:
            if action == 'reserve':
                if entry is not None:
                    event=next((e for e in service.journal().get('events',[]) if e['id']==value['id']),None)
                    if event and event['kind']=='low_limit' and not self.limit_alert_allowed(entry,event):
                        return {'version':1,'reserved':False,'lease':None}
                lease = service.reserve(value['id'],include_limits=True)
                return {'version': 1, 'reserved': lease is not None, 'lease': lease}
            event = service.claim(value['id'], value['reservation'], release=action == 'release',include_limits=True)
            return {'version': 1, 'released' if action == 'release' else 'claimed': event is not None, 'event': event}
        except (ValueError, TypeError):
            raise SourceError('invalid_request') from None

    def project_icon(self, key):
        with self.lock:
            work=[(e['id'],self.service_for(e)) for e in self.registry()['sources']]
        for identity,service in work:
            with self.lifecycle(shared=True,source=identity):
                if any(e['id']==identity for e in self.registry()['sources']):
                    result=service.project_icon(key)
                    if result:
                        return result
        return None
