import tempfile,time,unittest
from pathlib import Path
from dots_panel.app import Store,agent_work
class ParallelAgentTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=Store(Path(self.tmp.name)/'data')
  self.s.register('goal','Goal','Fixture')
  for a in ('a','b'):self.s.agent_register(a,a);self.s.agent_observe(a,'running',time.time())
 def tearDown(self):self.tmp.cleanup()
 def test_parallel_idempotent_preserves_owner(self):
  self.s.agent_assign('goal','a');r=self.s.start('goal')
  for a in ('a','b','b'):self.s.agent_run_assign(r,a,'testing')
  d=self.s.snapshot();self.assertEqual(len(d['agent_run_assignments']),2);self.assertEqual(d['agent_assignments'][0]['agent_id'],'a')
  for a in d['agents']:self.assertEqual(len(agent_work(d,a)['current']),1)
 def test_latest_completed_does_not_hide_open_run(self):
  self.s.agent_assign('goal','a');first=self.s.start('goal');second=self.s.start('goal')
  with self.s.connect() as db:db.execute("UPDATE runs SET status='succeeded' WHERE id=?",(second,))
  d=self.s.snapshot();w=agent_work(d,d['agents'][0]);self.assertEqual(w['unfinished'][0]['run_id'],first);self.assertEqual(len(w['recent']),1)
 def test_scoped_does_not_inherit_unrelated_run(self):
  first=self.s.start('goal');second=self.s.start('goal');self.s.agent_run_assign(first,'b')
  d=self.s.snapshot();w=agent_work(d,next(a for a in d['agents'] if a['id']=='b'));self.assertEqual([r['run_id'] for r in w['current']],[first])
 def test_missing_reference_rejected(self):
  with self.assertRaises(ValueError):self.s.agent_run_assign('missing','a')
if __name__=='__main__':unittest.main()
