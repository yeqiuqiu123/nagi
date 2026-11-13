"""Synthetic native consumer checks; no desktop notification or runtime access."""
import copy
from datetime import timedelta
from unittest import TestCase
from unittest.mock import Mock

from test_sources import NOW

from agents_projection import links
from linux.agent_notifications import APP_ID, NOTIFICATIONS_API, NotificationConsumer


def event(identity='a',kind='failed'):
    return {'id':identity*64,'kind':kind,'threadId':'thread','projectId':'project',
            'threadTitle':'Thread','projectTitle':'Project','occurredAt':NOW.isoformat(),
            'links':links('environment','thread')}


def reservation(item):
    return {'version':1,'reserved':True,'lease':{'reservation':'r'*43,
            'expiresAt':(NOW+timedelta(seconds=30)).isoformat(),'event':item}}


class SourceNotificationConsumer(TestCase):
    def consumer(self):
        send=Mock(return_value=True)
        consumer=NotificationConsumer('unused',send,Mock())
        return consumer,send

    def test_each_delivery_carries_its_source_and_preserves_the_native_id(self):
        first,second=event(),event('b','stuck')
        consumer,send=self.consumer()
        consumer.request=Mock(side_effect=[{'version':1,'events':[{'sourceId':'legacy-t3','event':first},
                                          {'sourceId':'b'*32,'event':second}]},
                                          reservation(first),{'version':1,'claimed':True,'event':first},
                                          reservation(second),{'version':1,'claimed':True,'event':second}])
        consumer.poll()
        self.assertEqual(send.call_count,2)
        self.assertEqual([call.args[0]['id'] for call in send.call_args_list],[first['id'],second['id']])
        self.assertEqual(APP_ID,'local.nagi.notifications')
        requests=consumer.request.call_args_list
        self.assertEqual(requests[0].args,(NOTIFICATIONS_API,))
        self.assertEqual(requests[1].args,(NOTIFICATIONS_API+'/reserve',{'sourceId':'legacy-t3','id':first['id']}))
        self.assertEqual(requests[2].args,(NOTIFICATIONS_API+'/claim',{'sourceId':'legacy-t3','id':first['id'],'reservation':'r'*43}))
        self.assertEqual(requests[3].args,(NOTIFICATIONS_API+'/reserve',{'sourceId':'b'*32,'id':second['id']}))
        self.assertEqual(requests[4].args,(NOTIFICATIONS_API+'/claim',{'sourceId':'b'*32,'id':second['id'],'reservation':'r'*43}))

    def test_rejected_send_releases_only_the_reserved_source(self):
        item=event()
        consumer,send=self.consumer()
        send.return_value=False
        consumer.request=Mock(side_effect=[{'version':1,'events':[{'sourceId':'c'*32,'event':item}]},
                                          reservation(item),{'version':1,'released':True,'event':item}])
        consumer.poll()
        self.assertEqual(consumer.request.call_args.args,(NOTIFICATIONS_API+'/release',
                         {'sourceId':'c'*32,'id':item['id'],'reservation':'r'*43}))

    def test_old_or_malformed_envelopes_never_send_or_fall_back(self):
        valid={'version':1,'events':[{'sourceId':'legacy-t3','event':event()}]}
        invalid=[{'version':2,'events':[event()]},{'version':True,'events':[]},
                 {'version':1,'events':[event()]},dict(valid,secret='synthetic'),
                 {'version':1,'events':[{'sourceId':'../private','event':event()}]},
                 {'version':1,'events':[{'sourceId':None,'event':event()}]},
                 {'version':1,'events':[{'sourceId':'legacy-t3','event':dict(event(),kind='control')}]},
                 {'version':1,'events':[{'sourceId':'legacy-t3','event':dict(event(),links={'desktop':'file:///x','web':'file:///x'})}]}]
        for response in invalid:
            with self.subTest(response=response):
                consumer,send=self.consumer()
                consumer.request=Mock(return_value=response)
                consumer.poll()
                send.assert_not_called()
                consumer.request.assert_called_once_with(NOTIFICATIONS_API)

    def test_mismatched_or_malformed_lease_cannot_send_another_event(self):
        for change in ('different_event','bad_reservation','wrong_version'):
            with self.subTest(change=change):
                item=event()
                lease=reservation(copy.deepcopy(item))
                if change=='different_event':lease['lease']['event']['id']='b'*64
                if change=='bad_reservation':lease['lease']['reservation']='bad'
                if change=='wrong_version':lease['version']=2
                consumer,send=self.consumer()
                consumer.request=Mock(side_effect=[{'version':1,'events':[{'sourceId':'legacy-t3','event':item}]},lease,{}])
                consumer.poll()
                send.assert_not_called()
                if change=='different_event':
                    self.assertEqual(consumer.request.call_args.args,(NOTIFICATIONS_API+'/release',
                                     {'sourceId':'legacy-t3','id':item['id'],'reservation':'r'*43}))
