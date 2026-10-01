import tempfile
import unittest
from pathlib import Path
from dots_panel.desktop_view import load_preferences, save_preferences


class MotionPreferenceTests(unittest.TestCase):
    def test_local_setting_preserves_language_timezone(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)/'data'
            directory.mkdir()
            save_preferences(directory, language='en', timezone='Asia/Shanghai')
            save_preferences(directory, reduced_motion=True)
            self.assertEqual(load_preferences(directory), {'language':'en','timezone':'Asia/Shanghai','reduced_motion':True})
            save_preferences(directory, timezone='UTC')
            self.assertTrue(load_preferences(directory)['reduced_motion'])
    def test_non_boolean_motion_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                save_preferences(Path(tmp)/'data', reduced_motion='false')
