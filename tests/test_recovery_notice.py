"""New privacy checks for the explicitly incomplete restoration marker."""
import json,tempfile,unittest
from pathlib import Path
from dots_panel.app import Store
class RecoveryNoticeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name)/'private');self.path=self.store.directory/'config/recovery.json'
    def tearDown(self):self.temp.cleanup()
    def write(self,content):self.path.write_text(json.dumps(content));self.path.chmod(0o600)
    def test_absent_marker_is_none(self):self.assertIsNone(self.store.snapshot()['recovery'])
    def test_marker_displays_fixed_notice_not_arbitrary_data(self):
        self.write({'source_kind':'retained_records','incomplete':True,'private_secret':'do-not-expose','notice_zh':'arbitrary'})
        result=self.store.snapshot()['recovery'];self.assertTrue(result['incomplete'])
        self.assertIn('历史不完整',result['notice_zh']);self.assertNotIn('do-not-expose',json.dumps(result));self.assertNotIn('arbitrary',json.dumps(result))
    def test_world_readable_marker_ignored(self):
        self.write({'source_kind':'retained_records','incomplete':True});self.path.chmod(0o644)
        self.assertIsNone(self.store.snapshot()['recovery'])
    def test_symlink_marker_ignored(self):
        other=Path(self.temp.name)/'external.json';other.write_text('{}');self.path.symlink_to(other)
        self.assertIsNone(self.store.snapshot()['recovery'])
    def test_malformed_and_oversize_marker_ignored(self):
        self.path.write_text('[');self.path.chmod(0o600);self.assertIsNone(self.store.snapshot()['recovery'])
        self.path.write_text(' '*5000);self.assertIsNone(self.store.snapshot()['recovery'])
