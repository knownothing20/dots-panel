"""Recovery tests for manual release metadata, no external operations."""
import tempfile,time,unittest
from pathlib import Path
from dots_panel.app import Store
class ReconstructedReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name)/'private')
    def tearDown(self):self.temp.cleanup()
    def test_no_observation_is_unknown(self):
        r=self.store.snapshot()['about']['release'];self.assertEqual(r['release_status'],'unknown');self.assertIsNone(r['checked_at'])
    def test_manual_observation_requires_evidence_fields(self):
        with self.assertRaises(ValueError):self.store.release_observe('https://github.com/example/project','published','unknown',time.time())
        with self.assertRaises(ValueError):self.store.release_observe('https://github.com/example/project','unknown','matched',time.time())
    def test_record_does_not_claim_publication(self):
        self.store.release_observe('https://github.com/example/project','unpublished','unknown',time.time())
        r=self.store.snapshot()['about']['release'];self.assertEqual(r['release_status'],'unpublished');self.assertIsNone(r['remote_commit'])
    def test_unsafe_links_rejected(self):
        for url in ('https://user@github.com/example/project','https://github.com.evil/example/project','https://github.com/example/project?token=x'):
            with self.assertRaises(ValueError):self.store.release_observe(url,'unknown','unknown',time.time())
    def test_stale_observation_rejected(self):
        now=time.time();self.store.release_observe('https://github.com/example/project','unpublished','unknown',now)
        with self.assertRaises(ValueError):self.store.release_observe('https://github.com/example/project','unknown','unknown',now-1)
