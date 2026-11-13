"""Quota notification generations, source selection and native delivery fixtures."""
import copy
import json
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

from agents_service import AgentsService, DEFAULTS, outcome, validate_limit_event
from linux.agent_notifications import NotificationConsumer, PANEL_APP_ID, banner, open_panel, valid_event
from sources_service import SourcesService
from test_agents_v2 import NOW, Reader


class LimitAlerts(TestCase):
    def setUp(self):
        self.directory=Path(self.enterContext(TemporaryDirectory()));self.now=NOW
        self.reader=Reader();self.reader.rows=[];self.service=self.new()
        self.provider={'driver':'codex','instanceId':'account','installed':True,'enabled':True,
                       'usageLimits':{'checkedAt':NOW.isoformat(),'windows':[{'id':'primary','usedPercent':92,
                           'windowDurationMins':300,'resetsAt':(NOW+timedelta(hours=1)).isoformat()}]}}
        self.reader.providers=[self.provider]

    def new(self):
        service=AgentsService(self.directory,lambda _:self.reader,lambda:self.now)
        service.read_machine=lambda _:None
        return service

    def poll(self):
        self.service.poll(force=True);self.service.record_limit_alerts(self.service.settings())
        return self.service.notifications(include_limits=True)

    def advance(self,minutes=1,*,used=None,reset=None):
        self.now+=timedelta(minutes=minutes);self.provider['usageLimits']['checkedAt']=self.now.isoformat()
        window=self.provider['usageLimits']['windows'][0]
        if used is not None:window['usedPercent']=used
        if reset:window['resetsAt']=reset

    def test_once_per_account_window_reset_with_durable_claim_release(self):
        events=self.poll();self.assertEqual(len(events),1);event=events[0]
        self.assertEqual(event['kind'],'low_limit');self.assertEqual(event['remainingPercent'],8)
        self.assertEqual(event['accountLabel'],'Codex 1');validate_limit_event(event)
        self.assertEqual(self.service.notifications(),[], 'Legacy v2 notifications keep their old event dialect')
        self.assertIsNone(self.service.reserve(event['id']))
        lease=self.service.reserve(event['id'],include_limits=True);self.assertIsNotNone(lease)
        self.assertEqual(self.service.notifications(include_limits=True),[])
        self.service.claim(event['id'],lease['reservation'],release=True,include_limits=True)
        self.assertEqual(len(self.service.notifications(include_limits=True)),1)
        lease=self.service.reserve(event['id'],include_limits=True);self.service.claim(event['id'],lease['reservation'],include_limits=True)
        self.assertEqual(self.poll(),[])
        self.advance(used=98);self.assertEqual(self.poll(),[])
        self.service=self.new();self.advance();self.assertEqual(self.poll(),[])
        self.provider['usageLimits']['windows'][0]['resetsAt']=(NOW+timedelta(hours=1)).isoformat().replace('+00:00','Z')
        self.advance();self.assertEqual(self.poll(),[], 'Equivalent reset timestamp spellings are the same window')
        self.advance(reset=(self.now+timedelta(hours=2)).isoformat())
        self.assertEqual(len(self.poll()),1)

    def test_threshold_crossing_secondary_windows_and_stale_or_failed_evidence(self):
        self.provider['usageLimits']['windows'][0]['usedPercent']=89
        self.assertEqual(self.poll(),[])
        self.advance(used=90);self.assertEqual(len(self.poll()),1)
        self.provider['usageLimits']['windows'].append({'id':'secondary','usedPercent':95,'windowDurationMins':10080,
                                                       'resetsAt':(NOW+timedelta(days=1)).isoformat()})
        self.advance();events=self.poll();self.assertEqual(len(events),2)
        self.now+=timedelta(minutes=16)
        self.assertEqual(self.poll(),[])
        self.assertEqual(self.service.providers['codex']['status'],'last_known')
        from t3_reader import Unavailable
        self.reader.failure=Unavailable
        self.assertEqual(self.poll(),[])

    def test_off_setting_and_threshold_change_cannot_replay_cached_check(self):
        self.service.save_settings(dict(DEFAULTS,limitAlertPercent='off'))
        self.assertEqual(self.poll(),[])
        self.service.save_settings(DEFAULTS)
        self.assertEqual(self.poll(),[])
        self.advance();events=self.poll();self.assertEqual(len(events),1)
        self.service.save_settings(dict(DEFAULTS,limitAlertPercent=20));self.advance()
        self.assertEqual([e['id'] for e in self.poll()],[events[0]['id']])
        self.now=NOW+timedelta(hours=2)
        self.assertEqual(self.service.notifications(include_limits=True),[])

    def test_settings_validation_migration_and_persistence(self):
        for value in (1,50,'off',10):
            submitted=dict(DEFAULTS,limitAlertPercent=value)
            self.assertEqual(self.service.save_settings(submitted)['limitAlertPercent'],value)
            self.assertEqual(self.new().settings()['limitAlertPercent'],value)
        for value in (True,False,0,51,'10','OFF',10.0,None,{},[]):
            with self.assertRaises(ValueError):self.service.save_settings(dict(DEFAULTS,limitAlertPercent=value))
        self.assertEqual(self.service.save_settings({'stuckMinutes':15,'endedExpiryHours':24})['limitAlertPercent'],10)
        self.assertEqual((self.directory/'nagi-settings.json').stat().st_mode&0o777,0o600)

    def test_corrupt_journal_does_not_replay_low_limits(self):
        self.assertEqual(len(self.poll()),1)
        path=self.directory/self.service.journal_name
        path.write_text('{malformed')
        self.service=self.new();self.advance()
        self.assertEqual(self.poll(),[])
        self.assertTrue(self.service.journal_warning)

    def test_linux_low_event_reserves_claims_and_click_opens_panel_only(self):
        event=self.poll()[0];self.assertTrue(valid_event(event))
        self.assertEqual(banner(event)[0],'Codex 1 · 8% left');self.assertTrue(banner(event)[1].startswith('resets '))
        panel=Mock();opener=Mock();send=Mock(side_effect=lambda e,clicked:(clicked(),True)[1])
        consumer=NotificationConsumer('unused',send,opener,on_panel=panel)
        consumer.request=Mock(side_effect=[{'version':1,'events':[{'sourceId':'a'*32,'event':event}]},
                                           {'version':1,'reserved':True,'lease':{'reservation':'r'*43,
                                            'expiresAt':(NOW+timedelta(seconds=30)).isoformat(),'event':event}},
                                           {'version':1,'claimed':True,'event':event}])
        consumer.poll();panel.assert_called_once();opener.assert_not_called()
        self.assertEqual(consumer.request.call_args.args[0],'/api/sources/v1/notifications/claim')
        for bad in (dict(event,remainingPercent=True),dict(event,remainingPercent=float('nan')),
                    dict(event,links={'desktop':'file:///private','web':None}),dict(event,accountLabel='bad\nvalue'),dict(event,secret='no')):
            self.assertFalse(valid_event(bad))

    def test_pending_alerts_follow_settings_and_claude_precedence(self):
        event=self.poll()[0]
        sources=SourcesService(self.service,local_home=self.directory);self.addCleanup(sources.close)
        local={'id':'legacy-t3','harness':'t3','placement':'local'}
        direct={'id':'a'*32,'harness':'claude','placement':'this_computer'}
        self.provider['driver']='claudeAgent';self.provider['usageLimits']['windows'][0]['id']='five_hour'
        self.advance();self.poll()
        direct_service=Mock();direct_service.providers={'claude':copy.deepcopy(self.service.providers['claude'])}
        with patch.object(sources,'registry',return_value={'sources':[local,direct]}),patch.object(sources,'service_for',side_effect=lambda e:self.service if e==local else direct_service):
            claude=next(e for e in self.service.notifications(include_limits=True) if e['provider']=='claude')
            self.assertFalse(sources.limit_alert_allowed(local,claude))
            # A failed direct read still owns local Claude alerts: the fallback never alerts twice.
            direct_service.providers['claude']['status']='unavailable'
            self.assertFalse(sources.limit_alert_allowed(local,claude))
        with patch.object(sources,'registry',return_value={'sources':[local]}),patch.object(sources,'service_for',return_value=self.service):
            self.assertTrue(sources.limit_alert_allowed(local,claude))
            self.service.save_settings(dict(DEFAULTS,limitAlertPercent='off'))
            self.assertFalse(sources.limit_alert_allowed(local,event))

    def test_linux_panel_activation_uses_a_fixed_action_without_a_url(self):
        gio=Mock();glib=Mock();bus=gio.bus_get_sync.return_value
        self.assertTrue(open_panel(gio,glib,'http://127.0.0.1:47831'))
        args=bus.call_sync.call_args.args
        self.assertEqual(args[:4],(PANEL_APP_ID,'/local/nagi/panel','org.gtk.Actions','Activate'))
        self.assertEqual(glib.Variant.call_args.args,('(sava{sv})',('open',[],{})))
