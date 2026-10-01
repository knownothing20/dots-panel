"""Read-only diagnostics, manual setup evidence and three end-to-end workflows."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from dots_panel.app import ROOT, Store
from dots_panel.doctor import install_doctor, doctor_rows
from dots_panel.desktop_view import display_signature


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)

    def report(self): return install_doctor(ROOT, self.temp.name)

    def test_checks_do_not_imply_account_or_scheduler_setup(self):
        report = self.report()
        self.assertTrue(report['read_only'])
        self.assertEqual({row['status'] for row in report['checks']}, {'ok'})
        self.assertTrue(all(row['status']=='unknown' for row in report['observations'].values()))
        self.assertEqual(self.store.snapshot()['schedules'], [])

    def test_missing_data_cli_does_not_initialize(self):
        target = Path(self.temp.name)/'absent'
        command = [sys.executable,'-m','dots_panel','--data-dir',str(target),'doctor']
        result = subprocess.run(command,cwd=ROOT,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse(target.exists())
        checks = {row['id']:row['status'] for row in json.loads(result.stdout)['checks']}
        self.assertEqual(checks['schema'],'missing')

    def test_repeated_doctor_does_not_write_database_or_paths(self):
        path = self.store.path
        before = (path.read_bytes(),path.stat().st_mtime_ns)
        listing = {str(p.relative_to(self.temp.name)) for p in Path(self.temp.name).rglob('*')}
        for _ in range(4): self.report()
        self.assertEqual(before,(path.read_bytes(),path.stat().st_mtime_ns))
        self.assertEqual(listing,{str(p.relative_to(self.temp.name)) for p in Path(self.temp.name).rglob('*')})

    def test_legacy_schema_report_does_not_migrate(self):
        with self.store.connect() as db: db.execute('DROP TABLE installation_observations')
        report = self.report()
        self.assertEqual(next(row['status'] for row in report['checks'] if row['id']=='schema'),'migration_required')
        with self.store.connect() as db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='installation_observations'").fetchone())

    def test_symlink_and_unsafe_data_are_not_opened(self):
        linked = Path(self.temp.name)/'linked'
        linked.symlink_to(self.temp.name,target_is_directory=True)
        with patch('dots_panel.doctor.sqlite3.connect') as connect:
            result = install_doctor(ROOT, linked)
        connect.assert_not_called()
        self.assertIn('unsafe',{row['status'] for row in result['checks']})
        Path(self.temp.name).chmod(0o755)
        try:
            with patch('dots_panel.doctor.sqlite3.connect') as connect: install_doctor(ROOT,self.temp.name)
            connect.assert_not_called()
        finally: Path(self.temp.name).chmod(0o700)

    def test_permission_probes_and_no_private_leakage(self):
        private = Path(self.temp.name)/'unrelated-credentials.txt'
        private.write_text('SYNTHETIC_SECRET_NOT_FOR_DISCOVERY')
        report = self.report()
        encoded = json.dumps(report)
        self.assertNotIn('SYNTHETIC_SECRET_NOT_FOR_DISCOVERY', encoded)
        self.assertNotIn(self.temp.name, encoded)
        self.assertNotIn(str(ROOT), encoded)
        with patch('dots_panel.doctor.os.access',return_value=False): denied = self.report()
        self.assertNotEqual(next(row['status'] for row in denied['checks'] if row['id']=='source_writable'),'ok')

    def test_bundled_source_failure_not_account_failure(self):
        report = install_doctor(Path(self.temp.name)/'no-source',self.temp.name)
        self.assertEqual(next(row['status'] for row in report['checks'] if row['id']=='bundled_skill'),'unavailable')
        self.assertEqual(report['observations']['account_task_skill']['status'],'unknown')

    def register_skill(self,key,origin):
        now=time.time()-5
        self.store.skill_upsert(key,'Synthetic skill','Test purpose','Test scenario',now,user_installed=True,status='available',version_status='saved_verified',version_note='Synthetic saved content checked')
        self.store.skill_origin(key,origin,'unknown' if origin=='project_bundled' else 'not_applicable',now,repo_url='https://github.com/example/panel' if origin=='project_bundled' else None)

    def test_account_observation_requires_correct_manual_metadata(self):
        with self.assertRaises(ValueError): self.store.installation_observe('account_task_skill','verified','Evidence',time.time(),skill_id='missing')
        self.register_skill('workflow','project_bundled')
        self.store.installation_observe('account_task_skill','verified','Supported account content checked',time.time(),skill_id='workflow')
        self.assertEqual(self.report()['observations']['account_task_skill']['status'],'verified')
        self.assertEqual(self.report()['observations']['account_personal_skill']['status'],'unknown')
        with self.assertRaises(ValueError): self.store.installation_observe('account_personal_skill','verified','Evidence',time.time(),skill_id='workflow')

    def test_personal_skill_never_classified_as_project_bundle(self):
        self.register_skill('personal','personal')
        self.store.installation_observe('account_personal_skill','verified','Private account rules checked',time.time(),skill_id='personal')
        self.assertEqual(self.report()['observations']['account_personal_skill']['status'],'verified')
        with self.assertRaises(ValueError): self.store.installation_observe('account_task_skill','verified','Evidence',time.time(),skill_id='personal')
        self.assertFalse((ROOT/'skills/personal').exists())

    def test_scheduler_configuration_is_not_execution(self):
        now=time.time()-2
        self.store.installation_observe('scheduler_configuration','verified','Synthetic setup receipt',now,reference='synthetic-schedule')
        report=self.report()['observations']
        self.assertEqual(report['scheduler_configuration']['status'],'verified')
        self.assertEqual(report['scheduler_execution']['status'],'unknown')
        with self.assertRaises(ValueError): self.store.installation_observe('scheduler_execution','verified','Run evidence',now+1,reference='wrong-reference')
        self.store.installation_observe('scheduler_execution','verified','Synthetic completed execution receipt',now+1,reference='synthetic-schedule')
        self.assertEqual(self.report()['observations']['scheduler_execution']['status'],'verified')
        self.store.installation_observe('scheduler_configuration','verified','Changed configuration',now+2,reference='synthetic-new-schedule')
        self.assertEqual(self.report()['observations']['scheduler_execution']['status'],'unknown')
        self.assertEqual(self.store.snapshot()['schedules'], [])

    def test_observation_validation_and_append_only_history(self):
        for component,status,evidence,observed in [('bad','verified','Evidence',time.time()),('scheduler_configuration','approved','Evidence',time.time()),('scheduler_configuration','unknown','',time.time()),('scheduler_configuration','unknown','Evidence',time.time()+10000)]:
            with self.assertRaises(ValueError): self.store.installation_observe(component,status,evidence,observed)
        self.store.installation_observe('scheduler_configuration','unknown','No evidence yet',time.time()-1)
        self.store.installation_observe('scheduler_configuration','failed','Explicit failure observation',time.time())
        with self.store.connect() as db: self.assertEqual(db.execute('SELECT count(*) FROM installation_observations').fetchone()[0],2)
        self.assertEqual(self.report()['observations']['scheduler_configuration']['status'],'failed')

    def test_duplicate_configuration_does_not_invalidate_execution(self):
        when=time.time()-2
        values=('scheduler_configuration','verified','Same configuration',when)
        self.store.installation_observe(*values,reference='synthetic')
        self.store.installation_observe('scheduler_execution','verified','Execution checked',when+1,reference='synthetic')
        result=self.store.installation_observe(*values,reference='synthetic')
        self.assertTrue(result['duplicate'])
        self.assertEqual(self.report()['observations']['scheduler_execution']['status'],'verified')
        with self.assertRaises(ValueError): self.store.installation_observe('scheduler_configuration','verified','Conflicting evidence',when,reference='synthetic')

    def test_ui_labels_and_refresh_signature(self):
        report=self.report()
        local_en,manual_en=doctor_rows(report,'en')
        self.assertTrue(any(title=='Scheduler execution verification' and state=='Unverified' for title,state in manual_en))
        self.assertNotEqual(doctor_rows(report,'zh'),(local_en,manual_en))
        first=self.store.snapshot();second=self.store.snapshot()
        self.assertEqual(display_signature(first),display_signature(second))


class EndToEndAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(self.temp.name);self.store.register('goal','Synthetic goal','Example');self.run=self.store.start('goal')

    def finish_text(self,verification='passed'):
        record=self.store.closeout_record(self.run,'Requested result','Explicit text-only scope',verification,'Synthetic observed result','No external or OS testing',no_artifact_reason='Requested text-only result')
        self.store.closeout(self.run,record['record_id'])

    def test_normal_delivery_success(self):
        source=Path(self.temp.name)/'result.txt';source.write_text('Synthetic verified deliverable')
        artifact=self.store.artifact_add('goal',source,'Final result')
        self.store.artifact_designate(artifact['id'],'final','Final fixture content reviewed')
        self.store.artifact_delivery(artifact['id'],'sent','Synthetic successful send receipt',time.time())
        record=self.store.closeout_record(self.run,'Requested output delivered','Synthetic output','passed','Content assertion passed','No external service tested',[artifact['id']])
        self.store.closeout(self.run,record['record_id'])
        snapshot=self.store.snapshot()
        self.assertEqual(snapshot['runs'][0]['status'],'succeeded')
        self.assertNotIn('user_open_confirmed',{r['status'] for r in snapshot['artifacts'][0]['delivery_observations']})
        self.assertEqual(snapshot['about']['doctor']['observations']['scheduler_execution']['status'],'unknown')

    def test_wait_then_resume_same_run(self):
        self.store.transition(self.run,'waiting_user','Scope decision needed','Synthetic question','Await decision')
        self.store.update(self.run,message='No decision yet')
        self.assertEqual(self.store.snapshot()['runs'][0]['status'],'waiting_user')
        self.store.transition(self.run,'running','Scope confirmed','Synthetic explicit answer','Complete text-only review',from_status='waiting_user')
        self.finish_text('untested')
        self.assertEqual(len(self.store.snapshot()['tasks']),1)
        self.assertEqual(len(self.store.snapshot()['runs']),1)
        self.assertEqual(self.store.snapshot()['runs'][0]['closeout']['verification'],'untested')

    def test_interrupted_paused_recovery_preserves_binding(self):
        when=time.time()-2
        self.store.bind('goal','cloud_thread','synthetic-thread','cloud',None,'interrupted',when)
        self.assertEqual(self.store.snapshot()['runs'][0]['status'],'running')
        self.store.transition(self.run,'paused','Observed interruption','Synthetic executor observation','Resume when connection returns')
        self.store.bind('goal','cloud_thread','synthetic-thread','cloud',None,'running',when+1)
        self.store.transition(self.run,'running','Observed recovery','Synthetic resumed executor','Finish current goal',from_status='paused')
        self.finish_text()
        snapshot=self.store.snapshot()
        self.assertEqual(snapshot['bindings'][0]['thread_id'],'synthetic-thread')
        self.assertEqual(snapshot['runs'][0]['status'],'succeeded')
        self.assertEqual(len(snapshot['runs']),1)
