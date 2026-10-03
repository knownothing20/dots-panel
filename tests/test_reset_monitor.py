import json,os,sqlite3,tempfile,unittest
from pathlib import Path
from dots_panel.reset_monitor import initialize,DirectoryMonitor,inspect_path
from dots_panel.reset_events import migrate,insert_event,read_events

class ResetMonitorTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.target=self.root/'target';self.target.mkdir();self.state=self.root/'state'
  initialize(self.state,{'source':str(self.target)});self.m=DirectoryMonitor(self.state)
 def tearDown(self):self.m.close();self.tmp.cleanup()
 def test_present_missing_recovery_and_double_time(self):
  self.assertEqual(self.m.sample(1000)['events'][0]['event_type'],'baseline_present')
  self.target.rmdir();e=self.m.sample(1060)['events'][0];self.assertEqual(e['event_type'],'path_missing');self.assertEqual((e['last_present_at'],e['first_missing_at']),(1000,1060))
  self.assertEqual(self.m.sample(1120)['events'],[])
  self.target.mkdir();self.assertEqual(self.m.sample(1180)['events'][0]['event_type'],'path_reappeared')
  row=read_events(self.m.db)[0];self.assertIn('+00:00',row['observed_at_utc']);self.assertIn('+08:00',row['observed_at_beijing']);self.assertFalse(row['reset_cause_confirmed'])
 def test_replacement_and_gap(self):
  self.m.sample(1000);self.target.rename(self.root/'old');self.target.mkdir()
  events=self.m.sample(1600)['events'];self.assertEqual({e['event_type'] for e in events},{'observation_gap','identity_changed'})
 def test_first_missing_not_fake_reset(self):
  self.target.rmdir();event=self.m.sample(1000)['events'][0];self.assertEqual(event['event_type'],'initial_absent');self.assertEqual(event['evidence_level'],'unknown');self.assertNotIn('last_present_at',event)
 def test_backward_clock(self):
  self.m.sample(1000);self.assertEqual(self.m.sample(900)['events'][0]['event_type'],'clock_rollback')
 def test_no_symlink_scan_or_recursive_content(self):
  secret=self.root/'secret';secret.mkdir();(secret/'payload').write_text('private');self.target.rmdir();self.target.symlink_to(secret,target_is_directory=True)
  self.assertEqual(inspect_path(self.target)['state'],'unreadable');self.assertEqual(self.m.sample(1000)['events'][0]['event_type'],'inspection_error')
 def test_state_loss_no_reinitialize(self):
  self.m.sample(1000);p=self.state/'monitor.sqlite3';p.rename(self.state/'retained.sqlite3')
  with self.assertRaises(FileNotFoundError):self.m.sample(1060)
  self.assertFalse(p.exists())
 def test_init_under_monitored_root_rejected(self):
  with self.assertRaises(ValueError):initialize(self.target/'state',{'s':str(self.target)})
 def test_restart_retains_baseline(self):
  self.m.sample(1000);self.m.close();self.m=DirectoryMonitor(self.state)
  self.assertEqual(self.m.sample(1060)['events'],[]);self.assertEqual(len(self.m.export()),1)
 def test_reimport_exact_event_idempotent_conflict_atomic(self):
  e=self.m.sample(1000)['events'][0];db=sqlite3.connect(':memory:');migrate(db)
  self.assertTrue(insert_event(db,e));self.assertFalse(insert_event(db,e))
  with self.assertRaises(ValueError):insert_event(db,{**e,'summary':'different'})
 def test_missing_panel_never_created(self):
  self.m.config.update(panel_data=str(self.root/'absent-panel'),expected_panel_identity='panel-fixture')
  with self.assertRaises(FileNotFoundError):self.m.import_into_panel()
  self.assertFalse((self.root/'absent-panel').exists())
 def test_existing_migrated_panel_import(self):
  data=self.panel_fixture();self.m.config.update(panel_data=str(data),expected_panel_identity='panel-fixture');self.m.sample(1000)
  self.assertEqual(self.m.import_into_panel()['new_events'],1);self.assertEqual(self.m.import_into_panel()['new_events'],0)
 def panel_fixture(self,binding=True):
  data=self.root/'data';(data/'db').mkdir(parents=True,mode=0o700);(data/'config').mkdir(mode=0o700)
  identity=data/'config/backup-identity.json';identity.write_text(json.dumps({'schema':'dots-panel.backup.v2','identity':'panel-fixture'}));os.chmod(identity,0o600)
  dbpath=data/'db/panel.sqlite3';db=sqlite3.connect(dbpath);migrate(db)
  for name in ('tasks','runs','artifacts'):db.execute('CREATE TABLE '+name+'(id TEXT PRIMARY KEY)')
  if binding:db.execute("INSERT INTO reset_installation_binding VALUES(1,'panel-fixture','Synthetic explicit identity verification')")
  db.commit();db.close();os.chmod(dbpath,0o600);return data
 def test_matching_schema_without_identity_binding_rejected(self):
  data=self.panel_fixture(binding=False);self.m.config.update(panel_data=str(data),expected_panel_identity='panel-fixture');self.m.sample(1000)
  with self.assertRaises(ValueError):self.m.import_into_panel()
  db=sqlite3.connect(data/'db/panel.sqlite3');self.assertEqual(db.execute('SELECT count(*) FROM reset_events').fetchone()[0],0);db.close()
 def test_wrong_installation_identity_rejected(self):
  data=self.panel_fixture();self.m.config.update(panel_data=str(data),expected_panel_identity='different');self.m.sample(1000)
  with self.assertRaises(ValueError):self.m.import_into_panel()
 def test_path_replaced_during_sqlite_connect_rejected(self):
  from unittest.mock import patch
  data=self.panel_fixture();self.m.config.update(panel_data=str(data),expected_panel_identity='panel-fixture');self.m.sample(1000)
  path=data/'db/panel.sqlite3';real=sqlite3.connect
  def replace_then_connect(*args,**kwargs):
   path.rename(data/'db/original.sqlite3');new=real(path);migrate(new);new.close();os.chmod(path,0o600);return real(*args,**kwargs)
  with patch('dots_panel.reset_events.sqlite3.connect',side_effect=replace_then_connect):
   with self.assertRaises(ValueError):self.m.import_into_panel()
  db=real(path);self.assertEqual(db.execute('SELECT count(*) FROM reset_events').fetchone()[0],0);db.close()
 def test_init_panel_missing_expected_identity_rejected(self):
  data=self.panel_fixture()
  with self.assertRaises(ValueError):initialize(self.root/'new-state',{'source':str(self.target)},panel_data=data)
  self.assertFalse((self.root/'new-state').exists())
 def test_reset_list_readonly(self):
  from dots_panel.reset_events import ResetStoreMixin
  data=self.panel_fixture();dummy=type('Dummy',(),{'directory':data})()
  before=(data/'db/panel.sqlite3').read_bytes();result=ResetStoreMixin.reset_list(dummy)
  self.assertTrue(result['read_only']);self.assertEqual(before,(data/'db/panel.sqlite3').read_bytes())

if __name__=='__main__':unittest.main()
