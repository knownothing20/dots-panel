import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from dots_panel.desktop_view import (DEFAULT_TIMEZONE, Dashboard, timestamp_label, validate_timezone,
    save_preferences, save_language, load_preferences, load_language, schedule_platform_view, schedule_result_view)

class TimezoneSettingsTests(unittest.TestCase):
    def test_default_and_year_boundary(self):
        self.assertEqual(DEFAULT_TIMEZONE, 'Asia/Shanghai')
        self.assertEqual(timestamp_label('2026-12-31T18:00:00Z'), '2027-01-01 02:00:00 Asia/Shanghai (UTC+08:00)')
        self.assertEqual(timestamp_label(0,'UTC'), '1970-01-01 00:00:00 UTC (UTC+00:00)')

    def test_dst_spring_and_fall(self):
        self.assertIn('01:59:00 America/Los_Angeles (UTC-08:00)', timestamp_label('2026-03-08T09:59:00Z','America/Los_Angeles'))
        self.assertIn('03:01:00 America/Los_Angeles (UTC-07:00)', timestamp_label('2026-03-08T10:01:00Z','America/Los_Angeles'))
        self.assertIn('UTC-07:00',timestamp_label('2026-11-01T08:30:00Z','America/Los_Angeles'))
        self.assertIn('UTC-08:00',timestamp_label('2026-11-01T09:30:00Z','America/Los_Angeles'))
        self.assertIn('UTC+01:00',timestamp_label('2026-07-01T00:00:00Z','Europe/London'))
        self.assertIn('UTC+00:00',timestamp_label('2026-12-01T00:00:00Z','Europe/London'))

    def test_invalid_no_silent_timezone_assumption(self):
        for value in ('../UTC','Mars/Olympus','',None):
            with self.assertRaises(ValueError): validate_timezone(value)
        self.assertIn('timezone unknown',timestamp_label('2026-01-01T00:00:00'))

    def test_preferences_preserve_legacy_and_other_settings(self):
        with tempfile.TemporaryDirectory() as d:
            save_language(d,'en')
            self.assertEqual(load_language(d),'en')
            save_preferences(d,timezone='Europe/London')
            save_language(d,'auto')
            self.assertEqual(load_preferences(d),{'language':'auto','timezone':'Europe/London'})
            path=Path(d)/'config/ui.json';p=load_preferences(d);p['future_setting']=True;path.write_text(json.dumps(p))
            save_preferences(d,timezone='Asia/Shanghai')
            self.assertTrue(load_preferences(d)['future_setting'])
            before=path.read_bytes()
            with self.assertRaises(ValueError):save_preferences(d,timezone='Invalid/Zone')
            self.assertEqual(path.read_bytes(),before)

    def test_malformed_preferences_not_destroyed(self):
        with tempfile.TemporaryDirectory() as d:
            save_language(d,'zh');path=Path(d)/'config/ui.json';path.write_text('{broken')
            with self.assertRaises(ValueError):save_preferences(d,timezone='UTC')
            self.assertEqual(path.read_text(),'{broken')

    def test_invalid_input_does_not_change_view_or_data(self):
        view=Dashboard.__new__(Dashboard);view.language='en';view.timezone='Asia/Shanghai';view.page='settings'
        view.timezone_input=Mock();view.timezone_input.get.return_value='Invalid/Zone';view.settings_error=Mock()
        view.change_timezone()
        self.assertEqual(view.timezone,'Asia/Shanghai');self.assertEqual(view.page,'settings')
        self.assertIn('Invalid',view.settings_error.configure.call_args.kwargs['text'])

    def test_save_error_applies_session_with_warning(self):
        view=Dashboard.__new__(Dashboard);view.language='en';view.store=Mock();view.timezone_input=Mock();view.timezone_input.get.return_value='UTC';view.render_page=Mock();view.update_health=Mock()
        view.workspace_filter='waiting_user';view.page='settings';view.scroll_positions={'overview':.4}
        with patch('dots_panel.desktop_view.save_preferences',side_effect=OSError('readonly')):view.change_timezone()
        self.assertTrue(view.preference_error);self.assertEqual(view.timezone,'UTC');self.assertEqual(view.workspace_filter,'waiting_user');self.assertEqual(view.scroll_positions,{'overview':.4})

    def test_platform_observation_is_not_execution_success(self):
        data={'platform_observation':{'platform':'dot','task_id':'test','enabled':True,'timezone':'Asia/Shanghai','schedule':'08:00 daily','observed_at':0,'last_run_at':None,'next_run_at':None}}
        before=json.dumps(data)
        result=schedule_platform_view(data,'en','UTC');rows=dict(result['rows'])
        self.assertIn('Enabled',result['label']);self.assertEqual(rows['Next run'],'Unknown');self.assertEqual(rows['First scheduled execution'],'Not yet verified');self.assertEqual(before,json.dumps(data))
