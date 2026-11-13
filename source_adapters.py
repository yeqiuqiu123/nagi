"""Static source adapter boundary. T3 retains the existing protocol and projection."""
import copy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Protocol

from agents_projection import CyclicLineage, project_agents, stamp, text
from t3_reader import NotConfigured, T3Reader, Unavailable, Unsupported


@dataclass(frozen=True)
class Identity:
    id: str
    display_name: str
    icon_key: str


FLAGS = dict.fromkeys(('agents', 'lineage', 'limits', 'stuckDetection', 'asksYou', 'deepLinks'), True)
COVERAGE = dict.fromkeys(('agents', 'lineage', 'asksYou', 'stuck', 'deepLinks'), 'complete') | {'limits': 'account_dependent'}


class SourceAdapter(Protocol):
    identity: Identity
    potential_capabilities: dict

    def configuration_schema(self) -> dict: ...
    def configure(self, value: dict) -> dict: ...
    def detect(self, origin: str) -> dict: ...
    def read(self, service, now, settings, caches, force=False) -> dict: ...


class T3Adapter:
    identity = Identity('t3', 'T3 Code', 't3')
    potential_capabilities = FLAGS

    def configuration_schema(self):
        return {'version': 1, 'harness': 't3', 'available': True, 'modes': ['protocol2'],
                'capabilities': dict(FLAGS), 'requirements': ['read_only_pairing']}

    def configure(self, value):
        # Only the policy constructor is shared; network trust and secret custody
        # are enforced by the owner-only wizard and T3Reader respectively.
        from pathlib import Path

        from t3_reader import source_origin
        if (not isinstance(value, dict) or set(value) != {'version', 'origin', 'credentialFile'}
                or type(value['version']) is not int or value['version'] != 1
                or not isinstance(value['credentialFile'], str) or not Path(value['credentialFile']).is_absolute()):
            raise ValueError('Invalid source binding')
        source_origin(value['origin'])
        return dict(value)

    def detect(self, origin):
        reader = T3Reader.public(origin)
        descriptor = reader.get('/.well-known/t3/environment', authenticated=False)
        if not isinstance(descriptor, dict) or descriptor.get('orchestrationProtocolVersion') != 2:
            raise Unsupported()
        text(descriptor.get('environmentId', descriptor.get('id')))
        return descriptor

    def read(self, service, now, settings, caches, force=False):
        from agents_service import outcome
        attempted = now.isoformat()
        rows = modes = None
        icon_sources = {}
        success=False
        try:
            reader=service.factory(service.store.directory)
            descriptor,snapshot=reader.shell()
            try:
                # This server version has no discovery-free getConfig input. Its snapshot
                # is read through a five-minute cache, never re-discovered every 20 seconds.
                if force or service.config_at is None or not 0<=(now-service.config_at).total_seconds()<300:
                    service.config_at=now;service.config_valid=False
                    config=reader.config();service.config_cache=copy.deepcopy(config.get('providers',[]));service.config_valid=True
                config_ok=service.config_valid;providers=copy.deepcopy(service.config_cache) if config_ok else []
            except (Unavailable,OSError,ValueError,TypeError,KeyError,RecursionError):providers=[];config_ok=False
            if not isinstance(providers,list):providers=[];config_ok=False
            else:providers=[p for p in providers if isinstance(p,dict)]
            details={};candidates=[]
            for row in snapshot.get('threads',[]):
                try:
                    if (row.get('status')=='running' and (now-stamp(row['updatedAt'])).total_seconds()>=settings['stuckMinutes']*60
                            and not row.get('pendingRuntimeRequest') and not row.get('blockedOnThreadWait')):
                        text(row['id']);candidates.append(row)
                except (ValueError,TypeError,KeyError,AttributeError):continue
            def detail(row):
                try:
                    if hasattr(reader,'liveness'):return row['id'],reader.liveness(row['id'],row.get('latestRunId'),row.get('activityRunStartedAt') or row.get('latestRunStartedAt'))
                    return row['id'],reader.detail(row['id'])
                except Exception:return row.get('id'),None  # noqa: BLE001 - preserve unknown liveness on any reader failure.
            with ThreadPoolExecutor(max_workers=4) as pool:details.update(pool.map(detail,candidates[:32]))
            try:
                data,rows,modes=project_agents(descriptor,snapshot,providers,settings,details,now)
            except CyclicLineage:
                # Reject the snapshot; limits from the same read still stand.
                agents=service.failed('unavailable',attempted,'cyclic_lineage',caches.get('agents'));rows=modes=None
            else:
                icon_sources=service.attach_icons(data,snapshot)
                agents=outcome('ok' if data['projects'] or data['ended'] or data['omittedRows'] else 'quiet',attempted,attempted,data=data)
            limits=service.project_limits(providers,attempted,now,caches,config_ok)
            success=True
        except Exception as error:  # noqa: BLE001 - source failures become closed truth outcomes.
            status='not_set_up' if isinstance(error,NotConfigured) else 'unsupported' if isinstance(error,Unsupported) else 'unavailable'
            reason='not_configured' if status=='not_set_up' else 'protocol_unsupported' if status=='unsupported' else 'cannot_reach_t3' if isinstance(error,(Unavailable,OSError)) else 'invalid_source'
            agents=service.failed(status,attempted,reason,caches.get('agents'))
            limits={key:service.failed(status,attempted,'not_configured' if status=='not_set_up' else 'cannot_reach_t3',caches.get(key),now) for key in ('codex','claude')}
        for value in limits.values():value.setdefault('warnings',[])
        return {'agents':agents,'limits':limits,'rows':rows,'modes':modes,'icon_sources':icon_sources,'success':success}


ADAPTERS = {'t3': T3Adapter()}

from claude_source import ClaudeAdapter

ClaudeAdapter.identity = Identity('claude', 'Claude Code', 'claude')
ADAPTERS['claude'] = ClaudeAdapter()

from codex_source import CodexAdapter

CodexAdapter.identity = Identity('codex', 'Codex', 'codex')
ADAPTERS['codex'] = CodexAdapter()

from cursor_source import CursorAdapter

CursorAdapter.identity = Identity('cursor', 'Cursor', 'cursor')
ADAPTERS['cursor'] = CursorAdapter()
