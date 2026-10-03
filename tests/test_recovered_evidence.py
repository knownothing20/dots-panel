import json,os,tempfile,unittest
from pathlib import Path
from dots_panel.recovery_support import load_recovered_evidence

class RecoveredEvidenceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.data=Path(self.tmp.name);(self.data/'config').mkdir(mode=0o700);self.path=self.data/'config/recovered-evidence-ledger.json'
 def tearDown(self):self.tmp.cleanup()
 def write(self,events):
  self.path.write_text(json.dumps({'original_history_complete':False,'events':events}));os.chmod(self.path,0o600)
 def test_missing_remains_unknown(self):self.assertEqual(load_recovered_evidence(self.data)['status'],'not_recorded')
 def test_excludes_raw_transcripts_and_unknown_ids(self):
  self.write([{'evidence_id':'fixture:1','fact_summary':'Requested pause','known_original_run_id':None,'secret_field':'never display'}]);r=load_recovered_evidence(self.data)
  self.assertIsNone(r['events'][0]['known_original_run_id']);self.assertNotIn('secret_field',r['events'][0]);self.assertFalse(r['original_history_complete'])
 def test_symlink_refused(self):
  target=self.data/'other';target.write_text('{}');self.path.symlink_to(target);self.assertEqual(load_recovered_evidence(self.data)['status'],'unavailable')
 def test_duplicate_identity_refused(self):
  self.write([{'evidence_id':'fixture:1','fact_summary':'A'},{'evidence_id':'fixture:1','fact_summary':'B'}]);self.assertEqual(load_recovered_evidence(self.data)['status'],'unavailable')
if __name__=='__main__':unittest.main()
