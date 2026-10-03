import tempfile,time,unittest,sqlite3
from pathlib import Path
from dots_panel.app import Store
from dots_panel.followup import migrate,FollowupStoreMixin,technical_failure

class FollowupTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'data');self.store.register('goal','Goal','Fixture');self.run=self.store.start('goal')
  with self.store.connect() as db:migrate(db)
 def tearDown(self):self.tmp.cleanup()
 def checkpoint(self,source='event',at=1000,blocker='none'):
  return FollowupStoreMixin.followup_checkpoint(self.store,self.run,'incomplete','Tests and delivery',blocker,'coordinator','Review result','Result available','Synthetic evidence',source,at)
 def audit(self,**kwargs):return FollowupStoreMixin.followup_audit(self.store,['goal'],**kwargs)
 def test_exact_retry_and_source_order(self):
  old=self.checkpoint();new=self.checkpoint('later',1100,'security');self.assertEqual(old['checkpoint_id'],self.checkpoint()['checkpoint_id'])
  self.assertEqual(self.audit(now=1100)['receipts'][0]['checkpoint']['id'],new['checkpoint_id'])
  with self.assertRaises(ValueError):self.checkpoint('event',1000,'access')
 def test_security_flag_even_recent_progress(self):
  self.checkpoint(blocker='security');self.store.progress_update(self.run,'Checking','Check ready','Wait','Synthetic')
  self.assertIn('unresolved_security',self.audit()['receipts'][0]['flags'])
 def test_all_open_runs_explicit_scope(self):
  second=self.store.start('goal');self.store.register('unrelated','Other','Fixture');self.store.start('unrelated')
  result=self.audit();self.assertEqual(result['open_run_count'],2);self.assertEqual(result['scope'],['goal']);self.assertTrue(result['read_only'])
 def test_source_identity_immutable(self):
  self.checkpoint()
  with self.store.connect() as db:
   with self.assertRaises(sqlite3.IntegrityError):db.execute("UPDATE followup_checkpoints SET next_owner='other'")
 def test_narrow_failure_hint(self):
  for s in ('failed older test','The former ERR_12 was resolved','ERR_A fixed'):self.assertFalse(technical_failure(s))
  for s in ('ERR_42','Traceback (most recent call last)','ERR_A was not resolved','ERR_A 尚未修复'):self.assertTrue(technical_failure(s))
 def test_missing_checkpoint_not_success_or_liveness(self):
  r=self.audit()['receipts'][0];self.assertIn('missing_checkpoint',r['flags']);self.assertEqual(r['executor_state'],'unknown')
 def test_terminal_cannot_new_checkpoint_but_retry_idempotent(self):
  old=self.checkpoint();self.store.update(self.run,'cancelled');self.assertEqual(self.checkpoint()['checkpoint_id'],old['checkpoint_id'])
  with self.assertRaises(ValueError):self.checkpoint('new',1100)

if __name__=='__main__':unittest.main()
