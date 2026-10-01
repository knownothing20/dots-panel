import tempfile,time,unittest
from dots_panel.app import Store
from dots_panel.desktop_view import ReadOnlyStore,timeline_records,scroll_extent
from dots_panel.progress import task_progress

class ProgressTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.store=Store(self.tmp.name);self.store.register('task','Synthetic','Tests');self.run=self.store.start('task','Original scope')
 def record(self,**kwargs):
  values=dict(current_step='Render frames',result='Scene compiled',next_step='Check export',evidence='Synthetic renderer count');values.update(kwargs);return self.store.progress_update(self.run,**values)
 def test_updates_do_not_change_lifecycle_and_deduplicate(self):
  old=self.store.snapshot()['runs'][0].copy();first=self.record(completed=240,total=576,unit='frames',source_event_id='frame-240');second=self.record(completed=240,total=576,unit='frames',source_event_id='frame-240');self.assertTrue(second['deduplicated']);state=self.store.snapshot();self.assertEqual(len(state['progress_updates']),1);run=state['runs'][0]
  for field in ['status','started','finished','lifecycle_reason','next_step']:self.assertEqual(run[field],old[field])
  self.assertEqual(len([a for a in state['activity'] if a['stage']=='progress']),1)
  self.assertEqual(task_progress(state,'task')['counts']['completed'],240)
 def test_new_counts_are_meaningful_and_id_conflict_rejected(self):
  self.record(completed=1,total=10,unit='frames',source_event_id='sample-1')
  with self.assertRaises(ValueError):self.record(completed=2,total=10,unit='frames',source_event_id='sample-1')
  self.record(completed=2,total=10,unit='frames',source_event_id='sample-2');self.assertEqual(len(self.store.snapshot()['progress_updates']),2)
 def test_invalid_counts_and_terminal(self):
  for values in [dict(completed=11,total=10,unit='x'),dict(completed=-1,total=10,unit='x'),dict(completed=float('nan'),total=10,unit='x'),dict(completed=1),dict(completed=1,total=0,unit='x'),dict(completed=1,total=2)]:
   with self.assertRaises(ValueError):self.record(**values)
  self.store.transition(self.run,'cancelled','Stop','Synthetic stop')
  with self.assertRaises(ValueError):self.record()
 def test_read_only_legacy_without_table(self):
  self.assertEqual(ReadOnlyStore(self.tmp.name).snapshot()['progress_updates'],[])
 def test_fresh_participant_over_idle_owner_without_mutation(self):
  state={'runs':[{'id':'r','task_id':'t','status':'running'}],'agents':[{'id':'owner','status':'idle','observed_at':100},{'id':'active','status':'running','observed_at':190}],'agent_assignments':[{'task_id':'t','agent_id':'owner'}],'agent_run_assignments':[{'run_id':'r','agent_id':'active'}],'stale_after_seconds':120}
  self.assertEqual(task_progress(state,'t',200)['active_participants'][0]['id'],'active');self.assertEqual(task_progress(state,'t',400)['active_participants'],[]);self.assertEqual(state['agent_assignments'][0]['agent_id'],'owner')
 def test_canonical_timeline_sorts_start_notes_and_ties(self):
  s={'runs':[{'id':'r','task_id':'t','started':10,'note':'start'}],'activity':[{'id':'a','task_id':'t','created':20,'stage':'test','message':'activity'}],'events':[{'id':'e','run_id':'r','created':20,'message':'event'}]}
  self.assertEqual([r['message'] for r in timeline_records(s,'t')],['activity','event','start']);s['runs'][0]['started']=20
  self.assertEqual([r['kind'] for r in timeline_records(s,'t')],['activity','event','note'])
  s['runs'].append({'id':'old','task_id':'t','started':2,'note':'older start'});self.assertEqual(timeline_records(s,'t')[-1]['message'],'older start')
 def test_short_content_always_top_aligned(self):
  self.assertEqual(scroll_extent(200,600,.7),(600,0));self.assertEqual(scroll_extent(600,600,.2),(600,0));self.assertEqual(scroll_extent(1000,600,.8),(1000,.4));self.assertEqual(scroll_extent(1000,600,-.1),(1000,0))
 def test_concurrent_same_event_is_single_milestone(self):
  from concurrent.futures import ThreadPoolExecutor
  with ThreadPoolExecutor(max_workers=4) as pool:
   rows=list(pool.map(lambda _:self.record(source_event_id='same-verified-event'),range(4)))
  self.assertEqual(sum(not row['deduplicated'] for row in rows),1)
  self.assertEqual(len(self.store.snapshot()['progress_updates']),1)
 def test_heartbeat_does_not_change_meaningful_update(self):
  self.record();before=task_progress(self.store.snapshot(),'task')['updated_at'];self.store.update(self.run)
  self.assertEqual(task_progress(self.store.snapshot(),'task')['updated_at'],before);self.assertEqual(self.store.snapshot()['runs'][0]['progress_updated'],before)
 def test_source_id_scoped_to_run_and_snapshot_readonly(self):
  self.record(source_event_id='one');other=self.store.start('task');self.store.progress_update(other,'Other actual step',evidence='Synthetic',source_event_id='one')
  before=self.store.path.read_bytes() if hasattr(self.store,'path') else None
  self.assertEqual(len(ReadOnlyStore(self.tmp.name).snapshot()['progress_updates']),2)
  if before is not None:self.assertEqual(self.store.path.read_bytes(),before)
 def test_cli_progress_update_keeps_running(self):
  import subprocess,sys,json,os
  result=subprocess.run([sys.executable,'-m','dots_panel','--data-dir',self.tmp.name,'progress-update',self.run,'--current-step','Validate CLI','--evidence','Synthetic test','--source-event-id','cli-1'],capture_output=True,text=True)
  self.assertEqual(result.returncode,0,result.stderr);self.assertFalse(json.loads(result.stdout)['deduplicated']);self.assertEqual(self.store.snapshot()['runs'][0]['status'],'running')
 def test_new_run_does_not_inherit_completed_run_counts(self):
  self.record(completed=576,total=576,unit='frames');self.store.transition(self.run,'cancelled','Synthetic stop','Test')
  newer=self.store.start('task','Start new review')
  result=task_progress(self.store.snapshot(),'task');self.assertEqual(result['current_run_id'],newer);self.assertIsNone(result['counts']);self.assertEqual(result['current_step'],'Start new review')
 def test_waiting_review_drops_active_counts_and_uses_latest_milestone(self):
  self.record(completed=576,total=576,unit='frames');self.store.transition(self.run,'awaiting_review','Export ready','Synthetic export','User review')
  result=task_progress(self.store.snapshot(),'task');self.assertIsNone(result['counts']);self.assertIn('Export ready',result['current_step'])
 def test_new_ordinary_milestone_overrides_structured_step(self):
  self.record(completed=240,total=576,unit='frames');self.store.activity('Tests','assistant','review','Validated rendered output',task_id='task')
  result=task_progress(self.store.snapshot(),'task');self.assertEqual(result['current_step'],'Validated rendered output');self.assertIsNone(result['counts']);self.assertIsNone(result['latest'])

 def test_exact_lifecycle_mirror_is_not_repeated_in_timeline(self):
  self.store.transition(self.run,'waiting_user','Need a decision','Synthetic','Review the result')
  items=timeline_records(self.store.snapshot(),'task');messages=[r['message'] for r in items]
  self.assertEqual(sum('Need a decision' in m for m in messages),1)
 def test_newer_completed_parallel_run_does_not_hide_unfinished(self):
  self.record(current_step='Continue main work',completed=3,total=10,unit='checks')
  backup=self.store.start('task','Independent checkpoint')
  self.store.progress_update(backup,'Save checkpoint',evidence='Synthetic backup')
  self.store.transition(backup,'cancelled','Checkpoint test ended','Synthetic')
  result=task_progress(self.store.snapshot(),'task');self.assertEqual(result['current_run_id'],self.run);self.assertEqual(result['current_step'],'Continue main work');self.assertEqual(result['counts']['completed'],3);self.assertEqual(result['scope'],'run')
 def test_unscoped_ordinary_milestone_is_explicit_task_level(self):
  self.record();self.store.activity('Tests','assistant','review','Task-wide observation',task_id='task')
  result=task_progress(self.store.snapshot(),'task');self.assertEqual(result['scope'],'task');self.assertEqual(result['current_step'],'Task-wide observation');self.assertIsNone(result['counts'])
 def test_current_badge_preserves_waiting_run_under_finished_side_run(self):
  from dots_panel.desktop_view import task_rows
  self.store.transition(self.run,'waiting_user','Need approval','Synthetic','Review')
  other=self.store.start('task','Side run');self.store.transition(other,'cancelled','End side run','Synthetic')
  state=self.store.snapshot();self.assertEqual(state['latest_runs'][0]['id'],other);self.assertEqual(state['current_runs'][0]['id'],self.run)
  self.assertEqual(task_rows(state,time.time())[0]['status'],'waiting_user')
 def test_fresh_assigned_execution_leads_newer_waiting_run(self):
  from dots_panel.progress import current_run
  state={'runs':[{'id':'active','task_id':'task','status':'running','started':1},{'id':'waiting','task_id':'task','status':'waiting_user','started':2}],'agents':[{'id':'worker','status':'running','observed_at':100}],'agent_run_assignments':[{'run_id':'active','agent_id':'worker'}]}
  self.assertEqual(current_run(state,'task',110)['id'],'active');self.assertEqual(current_run(state,'task',500)['id'],'waiting')
  self.assertEqual(len(task_progress(state,'task',110)['open_runs']),2)
