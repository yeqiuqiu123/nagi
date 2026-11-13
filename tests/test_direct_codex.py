"""Bounded rollout readers use synthetic sessions and no auth/sqlite files."""
import copy
import json
import os
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from agents_service import AgentsService, DEFAULTS
from codex_source import (HEAD_BYTES, TAIL_BYTES, project_rollouts, rate_windows,
                          read_rollout, rollout_files)
from sources_service import SourcesService
from test_direct_claude import NOW


class DirectCodex(TestCase):
    def setUp(self):
        self.home=Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(patch.dict(os.environ,{'HOME':str(self.home),'CODEX_HOME':''}))
        self.day=self.home/'.codex/sessions'/NOW.strftime('%Y/%m/%d');self.day.mkdir(parents=True,mode=0o700)
        self.root=self.home/'nagi';self.root.mkdir(mode=0o700)
        self.now=NOW
        self.legacy=AgentsService(self.root,clock=lambda:self.now);self.legacy.read_machine=lambda _:None
        self.sources=SourcesService(self.legacy,local_home=self.home);self.addCleanup(self.sources.close)

    def write(self,name='standalone',*,origin='codex_cli_rs',source='cli',events=None,meta_extra=None):
        meta={'id':name,'originator':origin,'source':source,'cwd':'/private/Project','creator_account_id':'creation-only',**(meta_extra or {})}
        records=[{'timestamp':NOW.isoformat(),'type':'session_meta','payload':meta}]
        records+=events if events is not None else [self.event('task_started',turn_id='r')]
        path=self.day/('rollout-'+name+'.jsonl')
        path.write_text(''.join(json.dumps(v)+'\n' for v in records));return path

    def event(self,kind,at=NOW,**fields):
        return {'timestamp':at.isoformat(),'type':'event_msg','payload':{'type':kind,**fields}}

    def quota(self,*,account=None,at=NOW,**fields):
        rate={'limit_id':'codex','primary':{'used_percent':92,'window_minutes':300,'resets_at':(NOW+timedelta(hours=1)).timestamp()},
              'secondary':{'used_percent':30,'window_minutes':10080,'resets_at':(NOW+timedelta(days=1)).timestamp()},**fields}
        if account is not None:rate['account_id']=account
        return self.event('token_count',at=at,rate_limits=rate)

    def project(self,paths):return project_rollouts(paths,'source',self.now,DEFAULTS)

    def test_lifecycle_lineage_title_and_t3_exclusion(self):
        parent=self.write(events=[self.event('task_started',turn_id='run'),self.quota()])
        child=self.write('child',source={'subagent':{'thread_spawn':{'parent_thread_id':'standalone','depth':1}}},
                         events=[self.event('task_started'),self.event('task_complete')])
        t3=self.write('hosted',origin='T3 Code',events=[self.event('task_started')])
        unknown=self.write('unknown',origin='custom-orchestrator')
        fork=self.write('fork',meta_extra={'forked_from_id':'standalone'})
        data,rows,modes,limits=self.project([parent,child,t3,unknown,fork])
        self.assertEqual(set(rows),{'standalone','child','fork'});self.assertIsNone(rows['fork']['parentId'])
        self.assertEqual(rows['child']['parentId'],'standalone');self.assertEqual(rows['standalone']['title'],'Codex session')
        self.assertEqual(data['counts'],{'running':2,'waitingOnYou':0,'stuck':0,'ended':1})
        self.assertEqual(limits['reason'],'account_unverified')
        self.assertNotIn('creation-only',json.dumps(data));self.assertNotIn('/private/',json.dumps(data))

    def test_explicit_event_account_provenance_windows_and_dated_checks(self):
        # account_id is an explicit synthetic future event extension. The real
        # installed writer has no such field, and remains account_unverified.
        p=self.write(events=[self.quota(account='account-one'),self.quota(account='account-one')])
        _,_,_,limits=self.project([p]);self.assertEqual(limits['status'],'ok')
        self.assertEqual(len(limits['data']['accounts']),1)
        a=limits['data']['accounts'][0];self.assertEqual(a['label'],'Codex 1')
        self.assertNotEqual(a['id'],'account-one');self.assertEqual([w['id'] for w in a['windows']],['codex/primary','codex/secondary'])
        self.assertEqual(a['windows'][0]['remainingPercent'],8)
        self.assertEqual(a['windows'][0]['checkedAt'],NOW.isoformat())
        self.now+=timedelta(minutes=16)
        _,_,_,limits=self.project([p]);self.assertEqual(limits['status'],'unavailable');self.assertIsNone(limits['data'])

    def test_bad_nullable_expired_and_multi_bucket_limits(self):
        p=self.write(events=[self.quota(account='a'),self.quota(account='a',limit_id='spark'),self.quota(account='b')])
        limits=self.project([p])[3];self.assertEqual(len(limits['data']['accounts']),2)
        self.assertEqual(sorted(len(a['windows']) for a in limits['data']['accounts']),[2,4])
        self.assertEqual(rate_windows({'primary':None,'secondary':None},NOW.isoformat(),NOW),[])
        for bad in (True,float('nan'),-1,101):
            event=self.quota();rate=event['payload']['rate_limits'];rate['primary']['used_percent']=bad
            with self.assertRaises(ValueError):rate_windows(rate,NOW.isoformat(),NOW)
        self.assertEqual(rate_windows({'primary':{'used_percent':10,'window_minutes':300,'resets_at':1}},NOW.isoformat(),NOW),[])

    def test_rotation_truncation_torn_records_and_symlinks(self):
        path=self.write(events=[self.event('task_started')]);path.write_bytes(path.read_bytes()+b'{torn')
        self.assertEqual(self.project([path])[0]['counts']['running'],1)
        path.rename(path.with_suffix('.old'))
        self.write(events=[self.event('task_complete')])
        data,rows,_,_=self.project([path]);self.assertEqual(data['counts']['ended'],1);self.assertIsNone(rows['standalone']['startedAt'])
        path.write_text('{broken\n');self.assertEqual(self.project([path])[0]['omittedRows'],1)
        path.unlink();outside=self.home/'secret';outside.write_text('do not read')
        path.symlink_to(outside)
        with self.assertRaises(OSError):read_rollout(path)
        self.assertEqual(rollout_files(self.home,NOW)[0],[])

    def test_file_and_byte_budgets_and_stale_start(self):
        path=self.write()
        with path.open('ab') as stream:
            for _ in range(15000):stream.write(b'{"type":"response_item","payload":{"private":"discard"}}\n')
            stream.write((json.dumps(self.event('task_complete'))+'\n').encode())
        meta,records=read_rollout(path);self.assertEqual(meta['id'],'standalone');self.assertLess(len(json.dumps(records)),TAIL_BYTES*2)
        for i in range(70):self.write(str(i))
        files,truncated=rollout_files(self.home,NOW);self.assertTrue(truncated);self.assertEqual(len(files),64)
        self.now+=timedelta(minutes=16)
        data,_,_,_=self.project([self.day/'rollout-0.jsonl'])
        self.assertEqual(data['counts']['running'],0);self.assertIn('stale_source',data['warnings'])

    def test_wizard_connect_disconnect_never_writes_harness(self):
        self.write();before=sorted(p.relative_to(self.home/'.codex') for p in (self.home/'.codex').rglob('*'))
        config={'configuration':{'adapterId':'codex','label':'This computer','placement':{'kind':'this_computer'},'mode':'rollouts','options':{}}}
        tested=self.sources.test(config,'owner');self.assertIsNotNone(tested['testId'])
        connected=self.sources.connect({'testId':tested['testId'],'expectedRevision':0},'owner')
        self.sources.poll(force=True)
        source=self.sources.read_sources()['sources'][0]
        self.assertEqual(source['agents']['data']['counts']['running'],1)
        self.assertFalse(source['capabilities']['stuckDetection'])
        self.sources.disconnect({'sourceId':connected['source']['id'],'expectedRevision':1})
        self.assertEqual(sorted(p.relative_to(self.home/'.codex') for p in (self.home/'.codex').rglob('*')),before)
