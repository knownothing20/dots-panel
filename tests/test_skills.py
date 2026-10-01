import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from dots_panel.app import Store, project_rules, skill_status_label, skill_version_label
from dots_panel.desktop_view import ReadOnlyStore, agent_text


class SkillCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / 'data')
        self.observed = time.time() - 10

    def write(self, **changes):
        args = dict(key='example-skill', name='示例工具', purpose='简短用途', when_used='示例场景',
                    observed_at=self.observed, user_installed=True, name_en='Example skill',
                    purpose_en='Example purpose', when_used_en='Example situation')
        args.update(changes)
        return self.store.skill_upsert(**args)

    def test_empty_and_private(self):
        self.assertEqual(self.store.snapshot()['rules']['skills'], [])
        self.write()
        row = ReadOnlyStore(self.store.directory).snapshot()['rules']['skills'][0]
        self.assertEqual(row['scope'], 'user_installed')
        self.assertEqual(row['status'], 'unknown')
        self.assertEqual(row['version_status'], 'unverified')
        self.assertIsNone(row['url'])
        self.assertNotIn('skills', project_rules())
        self.assertEqual(agent_text(row, 'purpose', 'en'), 'Example purpose')
        self.assertEqual(agent_text(row, 'purpose', 'zh'), '简短用途')

    def test_legacy_readonly_missing_table(self):
        with self.store.connect() as db:
            db.execute('DROP TABLE user_skills')
        self.assertEqual(ReadOnlyStore(self.store.directory).snapshot()['rules']['skills'], [])
        Store(self.store.directory)
        self.assertEqual(self.store.snapshot()['rules']['skills'], [])

    def test_update_and_duplicate_preserve_one_identity(self):
        self.assertFalse(self.write()['duplicate'])
        self.assertTrue(self.write()['duplicate'])
        self.write(observed_at=self.observed + 1, name='更新', purpose_en='')
        rows = self.store.snapshot()['rules']['skills']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['name'], '更新')
        self.assertEqual(agent_text(rows[0], 'purpose', 'en'), '简短用途')
        for change in ({'name': 'Conflict'}, {'observed_at': self.observed - 1}):
            with self.assertRaises(ValueError):
                self.write(**change)

    def test_user_scope_required(self):
        for value in (False, None, 'system', 1):
            with self.assertRaises(ValueError):
                self.write(user_installed=value)
        for key in ('../system', 'system/private', 'a'*101):
            with self.assertRaises(ValueError):
                self.write(key=key)

    def test_validation(self):
        for fields in ({'name': ''}, {'purpose': 'x'*501}, {'when_used': '\0'}, {'observed_at': float('nan')},
                       {'observed_at': time.time()+301}, {'observed_at': '2026-01-01T00:00:00'},
                       {'status': 'enabled'}, {'version_status': 'latest'}, {'version_status': 'saved_verified'},
                       {'status': 'unavailable', 'version_status': 'saved_verified', 'version_note': 'Example'}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.write(**fields)
        self.write(status='available', version_status='saved_verified', version_note='Saved content checked; no version number')
        self.assertIn('checked', skill_version_label('saved_verified', 'en'))

    def test_links_strict_and_clear_on_full_update(self):
        for url in ('javascript:alert(1)', 'https://chatgpt.com.evil/skills?skill_id=x',
                    'https://chatgpt.com/skills?skill_id=x&token=x', 'https://user@chatgpt.com/skills?skill_id=x',
                    'https://chatgpt.com/skills?skill_id=x\n', 'https://chatgpt.com:443/skills?skill_id=x'):
            with self.assertRaises(ValueError):
                self.write(url=url)
        self.write(url='https://chatgpt.com/skills?skill_id=example-skill')
        self.write(observed_at=self.observed+1)
        self.assertIsNone(self.store.snapshot()['rules']['skills'][0]['url'])

    def test_labels_are_conservative_bilingual(self):
        for value in ('available', 'unavailable', 'unknown'):
            self.assertNotEqual(skill_status_label(value), skill_status_label(value, 'en'))
        self.assertEqual(skill_version_label('latest', 'en'), 'Version unverified')

    def test_cli_requires_scope_and_accepts_registration(self):
        cmd = [sys.executable, '-m', 'dots_panel', '--data-dir', str(self.store.directory), 'skill-upsert',
               'example-cli', '--name', 'Example', '--purpose', 'Purpose', '--when-used', 'When',
               '--observed-at', str(self.observed)]
        # ISO with timezone is the CLI timestamp contract.
        cmd[-1] = '2026-01-01T00:00:00Z'
        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        result = subprocess.run(cmd + ['--user-installed'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['id'], 'example-cli')

    def test_native_render_filters_scope_and_binds_each_safe_link(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from dots_panel.desktop_view import Dashboard
        viewer = Dashboard.__new__(Dashboard)
        viewer.language = 'en'
        viewer.panel = viewer.muted = viewer.fg = viewer.accent = '#000'
        widget = lambda *a, **k: SimpleNamespace(pack=lambda **kw: None, pack_forget=lambda: None)
        viewer.tk = SimpleNamespace(Frame=widget)
        viewer.scroll_area = widget
        labels, buttons = [], []
        viewer.label = lambda parent, caption, *a, **kw: (labels.append(caption) or widget())
        viewer.filter_chip = lambda parent, caption, action: (buttons.append((caption, action)) or widget())
        self.write(url='https://chatgpt.com/skills?skill_id=example-first')
        row = self.store.snapshot()['rules']['skills'][0]
        viewer.snapshot = {'rules': {'skills': [row, dict(row, id='second', url='https://chatgpt.com/skills?skill_id=example-second'), dict(row, scope='system', name_en='Excluded')]}}
        viewer.render_rules()
        self.assertNotIn('Excluded', labels)
        self.assertIn('Example purpose', labels)
        links = [action for caption, action in buttons if caption == 'Manage ↗']
        self.assertEqual(len(links), 2)
        with patch('webbrowser.open') as open_url:
            links[0](); links[1]()
            self.assertEqual([call.args[0] for call in open_url.call_args_list],
                             ['https://chatgpt.com/skills?skill_id=example-first', 'https://chatgpt.com/skills?skill_id=example-second'])
        labels.clear(); buttons.clear()
        viewer.snapshot = {'rules': {'skills': [dict(row, url='javascript:alert(1)')]}}
        viewer.render_rules()
        self.assertFalse(buttons)
