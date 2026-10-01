import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from dots_panel.app import Store, project_rules, verified_skill_url
from dots_panel.desktop_view import Dashboard, ReadOnlyStore, PAGE_NAMES, translate

class RulesTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/'data')
    def test_catalog_single_source_bilingual_and_levels(self):
        rules=project_rules();self.assertEqual(rules['version'],'1.0.0')
        ids=[]
        for group in rules['groups']:
            for rule in group['items']:
                ids.append(rule['id']);self.assertIn(rule['level'],('enforced','workflow','planned'))
                for field in ('title','body'):
                    self.assertTrue(rule[field]['zh']);self.assertTrue(rule[field]['en'])
                if rule['id'] in ('inbox','shared','portable','discovery'):self.assertEqual(rule['level'],'planned')
                if rule['id']=='source-data':self.assertEqual(rule['level'],'workflow')
        self.assertEqual(len(ids),len(set(ids)))
        self.assertEqual(self.store.snapshot()['rules']['groups'],rules['groups'])
    def test_skill_link_private_and_strict(self):
        url='https://chatgpt.com/skills?skill_id=example-skill'
        self.store.rules_skill(url);self.assertEqual(self.store.snapshot()['rules']['skill_url'],url)
        self.assertNotIn('skill_url',project_rules())
        for bad in ['javascript:alert(1)','https://chatgpt.com.evil/skills?skill_id=a','https://chatgpt.com/skills?skill_id=x&token=a','https://user@chatgpt.com/skills?skill_id=x']:
            with self.assertRaises(ValueError): verified_skill_url(bad)
    def test_legacy_readonly_has_rules(self):
        with self.store.connect() as db:db.execute('DROP TABLE rules_config')
        rules=ReadOnlyStore(self.store.directory).snapshot()['rules']
        self.assertIsNone(rules['skill_url']);self.assertTrue(rules['groups'])
    def test_navigation(self):
        self.assertEqual(list(PAGE_NAMES)[-2:],['rules','about'])
        self.assertEqual(translate('规则','en'),'Rules')
    def test_html_is_metadata_only(self):
        self.store.register('sample','Sample','Example')
        p=Path(self.temp.name)/'example.html';p.write_text('<script>alert(1)</script>')
        result=self.store.artifact_add('sample',p,'HTML code',kind='other')
        self.assertTrue(result['relative_path'].endswith('.html'))
        with self.assertRaises(ValueError):self.store.artifact_text(result['id'])
        with self.assertRaises(ValueError):self.store.artifact_png(result['id'])
    def test_manual_refresh_has_one_timer(self):
        view=Dashboard.__new__(Dashboard);view.timer='old'
        view.root=SimpleNamespace(after_cancel=Mock(),after=Mock(return_value='new'))
        view.store=SimpleNamespace(snapshot=lambda:{})
        view.metrics=SimpleNamespace(collect=lambda:{})
        view.language='zh';view.scroll_dragging=True;view.update_health=Mock()
        view.refresh();view.root.after_cancel.assert_called_once_with('old')
        self.assertEqual(view.root.after.call_count,1);self.assertEqual(view.timer,'new')
        self.assertFalse(view.read_error);self.assertGreater(view.last_successful_refresh,0)
