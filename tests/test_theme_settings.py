"""The reader's validated `theme` preference (design/themes/project-bar.md, Persistence)."""
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from agents_service import AgentsService,DEFAULTS
from sources_service import SourcesService
from test_agents_v2 import Reader,NOW

DEFAULT_THEME={'name':'violet','appearance':'system','colors':{}}
CUSTOM={'name':'tide','appearance':'dark','colors':{'accent':'#ff8800','claude':'#9a7bf0','t3':'#2bb3c0'}}
BASE={'endedExpiryHours':24,'stuckMinutes':15,'limitAlertPercent':10}


class ThemeSettings(TestCase):
    def setUp(self):
        self.directory=Path(self.enterContext(TemporaryDirectory()));self.reader=Reader()
        self.enterContext(patch('agents_service.AgentsService.read_machine',lambda s,a:setattr(s,'machine',{'status':'unsupported'})))
        self.service=self.new();self.path=self.directory/'nagi-settings.json'
    def new(self):return AgentsService(self.directory,lambda _:self.reader,lambda:NOW)

    def test_defaults_include_the_default_theme_and_are_never_shared(self):
        self.assertEqual(DEFAULTS['theme'],DEFAULT_THEME)
        resource=self.service.settings_resource()
        self.assertEqual(resource['settings']['theme'],DEFAULT_THEME);self.assertEqual(resource['defaults']['theme'],DEFAULT_THEME)
        # Callers get copies: changing one never changes the factory values.
        resource['settings']['theme']['colors']['accent']='#000000';resource['defaults']['theme']['name']='tide'
        self.service.settings()['theme']['colors']['claude']='#000000'
        saved=self.service.save_settings(dict(BASE));saved['theme']['colors']['codex']='#000000'
        self.assertEqual(DEFAULTS['theme'],DEFAULT_THEME)
        self.assertEqual(self.service.settings_resource()['settings']['theme'],DEFAULT_THEME)

    def test_round_trip_through_a_restart_in_a_private_file(self):
        saved=self.service.save_settings(dict(BASE,theme=CUSTOM))
        self.assertEqual(saved['theme'],CUSTOM)
        self.assertEqual(self.new().settings(),dict(BASE,theme=CUSTOM))
        self.assertEqual(json.loads(self.path.read_text())['theme'],CUSTOM)
        self.assertEqual(self.path.stat().st_mode&0o777,0o600)
        self.assertEqual(self.new().settings_resource()['defaults']['theme'],DEFAULT_THEME)
        # Colours come back in role order whatever order they were posted in.
        self.service.save_settings(dict(BASE,theme={'name':'graphite','appearance':'light','colors':{'t3':'#000000','accent':'#ffffff'}}))
        self.assertEqual(list(self.new().settings()['theme']['colors']),['accent','t3'])

    def test_every_malformed_theme_is_refused_and_nothing_is_written(self):
        self.service.save_settings(dict(BASE,theme=CUSTOM));before=self.path.read_bytes()
        bad=[None,True,1,'violet',[],[CUSTOM],{},
             {'name':'violet','appearance':'system'},
             dict(CUSTOM,extra=1),
             dict(CUSTOM,name='solarized'),dict(CUSTOM,name='Violet'),dict(CUSTOM,name=None),dict(CUSTOM,name=['tide']),
             dict(CUSTOM,appearance='auto'),dict(CUSTOM,appearance=True),dict(CUSTOM,appearance=0),
             dict(CUSTOM,colors=['#ff8800']),dict(CUSTOM,colors=None),dict(CUSTOM,colors='#ff8800'),dict(CUSTOM,colors=True),
             dict(CUSTOM,colors={'rose':'#ff7aa5'}),dict(CUSTOM,colors={'amber':'#e6c84a'}),dict(CUSTOM,colors={'green':'#00ff00'}),
             dict(CUSTOM,colors={'accent':'#FF8800'}),dict(CUSTOM,colors={'accent':'#f80'}),dict(CUSTOM,colors={'accent':'ff8800'}),
             dict(CUSTOM,colors={'accent':'#ff88001'}),dict(CUSTOM,colors={'accent':'#ff880g'}),dict(CUSTOM,colors={'accent':' #ff8800'}),
             dict(CUSTOM,colors={'accent':'#ff8800\n'}),dict(CUSTOM,colors={'accent':0xff8800}),dict(CUSTOM,colors={'accent':None}),
             dict(CUSTOM,colors={'accent':True}),dict(CUSTOM,colors={'accent':['#ff8800']}),dict(CUSTOM,colors={'accent':{'hex':'#ff8800'}})]
        for theme in bad:
            with self.subTest(theme=theme):
                with self.assertRaises(ValueError) as caught:self.service.save_settings(dict(BASE,theme=theme))
                self.assertEqual(str(caught.exception),'Invalid local settings')
                self.assertEqual(self.path.read_bytes(),before)
        for body in (dict(BASE,theme=CUSTOM,unknown=1),dict(BASE,Theme=CUSTOM),dict(BASE,stuckMinutes=True,theme=CUSTOM)):
            with self.assertRaises(ValueError):self.service.save_settings(body)
            self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(self.new().settings()['theme'],CUSTOM)

    def test_a_post_without_theme_keeps_the_stored_theme(self):
        self.service.save_settings(dict(BASE,theme=CUSTOM))
        # An older panel or the Mac app posts only the numbers.
        saved=self.service.save_settings({'endedExpiryHours':48,'stuckMinutes':20,'limitAlertPercent':'off'})
        self.assertEqual(saved,{'endedExpiryHours':48,'stuckMinutes':20,'limitAlertPercent':'off','theme':CUSTOM})
        self.assertEqual(self.new().settings()['theme'],CUSTOM)
        self.service.save_settings({'endedExpiryHours':48,'stuckMinutes':20})
        self.assertEqual(json.loads(self.path.read_text())['theme'],CUSTOM)
        # A body with theme replaces it whole.
        self.service.save_settings(dict(BASE,theme={'name':'graphite','appearance':'system','colors':{}}))
        self.assertEqual(self.new().settings()['theme'],{'name':'graphite','appearance':'system','colors':{}})

    def test_a_file_without_theme_reads_as_the_default_without_a_write(self):
        for stored,expected in (({'endedExpiryHours':48,'stuckMinutes':20,'limitAlertPercent':20},{'endedExpiryHours':48,'stuckMinutes':20,'limitAlertPercent':20}),
                                ({'endedExpiryHours':48,'stuckMinutes':20},{'endedExpiryHours':48,'stuckMinutes':20,'limitAlertPercent':10}),
                                ({'stuckAfterSeconds':901,'endedWithinHours':48},{'endedExpiryHours':48,'stuckMinutes':16,'limitAlertPercent':10})):
            with self.subTest(stored=stored):
                raw=json.dumps(stored);self.path.write_text(raw);self.path.chmod(0o600)
                self.assertEqual(self.new().settings(),dict(expected,theme=DEFAULT_THEME))
                self.assertEqual(self.service.warnings(),[])
                self.assertEqual(self.path.read_text(),raw)

    def test_a_bad_theme_in_the_file_falls_back_to_defaults_with_a_warning(self):
        self.path.write_text(json.dumps(dict(BASE,theme=dict(CUSTOM,colors={'rose':'#ff7aa5'}))));self.path.chmod(0o600)
        self.assertEqual(self.service.settings(),dict(BASE,theme=DEFAULT_THEME))
        self.assertEqual(self.service.warnings(),['settings_invalid'])
        # The next valid save repairs it, keeping no part of the bad theme.
        self.service.save_settings({'endedExpiryHours':30,'stuckMinutes':15})
        self.assertEqual(self.service.warnings(),[])
        self.assertEqual(json.loads(self.path.read_text())['theme'],DEFAULT_THEME)

    def test_glance_settings_carry_the_theme(self):
        self.service.save_settings(dict(BASE,theme=CUSTOM))
        sources=SourcesService(self.new())
        self.assertEqual(sources.glance('linux')['settings'],dict(BASE,theme=CUSTOM))
        self.assertEqual(copy.deepcopy(self.service.settings_resource()['settings']['theme']),CUSTOM)
