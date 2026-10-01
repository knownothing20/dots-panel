"""Evidence gates and delivery observations use synthetic private fixtures only."""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from dots_panel.app import Store, artifact_delivery_label, verification_label, ROOT
from dots_panel.desktop_view import ReadOnlyStore, pipeline_counts


class CloseoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.store.register('task', 'Synthetic task', 'Example')
        self.run = self.store.start('task')
        source = Path(self.temp.name)/'output.txt'
        source.write_text('Synthetic output')
        self.artifact = self.store.artifact_add('task', source, 'Synthetic output')

    def record(self, **kw):
        values = dict(summary='Useful result', scope='Synthetic output inspection', verification='passed', evidence='Content inspected', limits='External service was not tested', artifact_ids=[self.artifact['id']])
        values.update(kw)
        return self.store.closeout_record(self.run, **values)['record_id']

    def deliver(self, status='sent'):
        self.store.artifact_designate(self.artifact['id'], 'final', 'Reviewed final version')
        return self.store.artifact_delivery(self.artifact['id'], status, 'Synthetic delivery receipt', time.time())

    def row(self):
        return self.store.snapshot()['latest_runs'][0]

    def test_new_runs_require_gate_on_every_success_route(self):
        self.assertEqual(self.row()['closeout_required'], 1)
        calls = [lambda: self.store.update(self.run, status='succeeded'),
                 lambda: self.store.transition(self.run, 'succeeded', 'Done', 'Claimed result'),
                 lambda: self.store.closeout(self.run, 'missing')]
        for call in calls:
            with self.assertRaises(ValueError): call()
        self.assertEqual(self.row()['status'], 'running')
        self.assertEqual(self.store.snapshot()['closeouts'], [])

    def test_gate_requires_final_and_delivery(self):
        record = self.record()
        with self.assertRaisesRegex(ValueError, 'final'): self.store.closeout(self.run, record)
        self.store.artifact_designate(self.artifact['id'], 'final', 'Final evidence')
        with self.assertRaisesRegex(ValueError, 'delivery'): self.store.closeout(self.run, record)
        self.store.artifact_delivery(self.artifact['id'], 'accepted', 'Transport receipt', time.time())
        self.store.closeout(self.run, record)
        self.assertEqual(self.row()['status'], 'succeeded')
        self.assertIsNotNone(self.row()['closeout']['completed_at'])
        label = artifact_delivery_label(self.store.snapshot()['artifacts'][0], 'en')
        self.assertIn('Transport accepted', label)
        self.assertIn('User open unverified', label)

    def test_finish_and_transition_use_same_gate(self):
        for method in ('finish','transition'):
            run = self.store.start('task')
            self.deliver()
            self.store.closeout_record(run, 'Summary', 'Scope', 'passed', 'Evidence', 'No external tests', [self.artifact['id']])
            if method == 'finish': self.store.update(run, status='succeeded')
            else: self.store.transition(run, 'succeeded', 'Result', 'Evidence', from_status='running')
            result = next(item for item in self.store.snapshot()['runs'] if item['id']==run)
            self.assertEqual(result['status'], 'succeeded')
            self.assertIsNotNone(result['closeout']['completed_at'])

    def test_failed_verification_never_succeeds(self):
        record = self.record(verification='failed')
        self.deliver()
        for call in (lambda: self.store.closeout(self.run, record), lambda: self.store.update(self.run, status='succeeded'), lambda: self.store.transition(self.run, 'succeeded', 'Done', 'Evidence')):
            with self.assertRaisesRegex(ValueError, 'Failed verification'): call()
        self.assertEqual(self.row()['status'], 'running')
        self.store.update(self.run, status='failed')
        self.assertEqual(self.row()['status'], 'failed')

    def test_untested_scope_and_no_artifact_reason_are_honest(self):
        record = self.record(verification='untested', scope='First-pass text-only review', evidence='Manual first-pass discussion completed', limits='No tests executed; implementation remains unverified', artifact_ids=[], no_artifact_reason='Requested a chat-only assessment')
        self.store.closeout(self.run, record)
        self.assertEqual(self.row()['closeout']['verification'], 'untested')
        self.assertEqual(verification_label('untested','en'), 'Untested')
        self.assertEqual(pipeline_counts(self.store.snapshot())['verified'], 1)  # only prior archival event

    def test_required_fields_and_artifact_exclusivity(self):
        for field in ('summary','scope','evidence','limits'):
            for bad in ('', '  ', None):
                with self.subTest(field=field,bad=bad), self.assertRaises(ValueError): self.record(**{field:bad})
        for kw in (dict(artifact_ids=[]), dict(no_artifact_reason='Both present'), dict(artifact_ids=[self.artifact['id']]*2), dict(verification='unknown')):
            with self.assertRaises(ValueError): self.record(**kw)
        self.assertEqual(self.store.snapshot()['closeouts'], [])

    def test_superseded_record_is_rejected(self):
        old = self.record()
        new = self.record(summary='Newer evidence')
        self.deliver()
        with self.assertRaisesRegex(ValueError, 'superseded'): self.store.closeout(self.run, old)
        self.store.closeout(self.run, new)
        self.assertEqual(len(self.store.snapshot()['closeouts']), 2)

    def test_changed_output_rejects_stale_evidence(self):
        record = self.record()
        self.deliver()
        (Path(self.temp.name)/self.artifact['relative_path']).write_text('Changed after evidence')
        with self.assertRaises(ValueError): self.store.closeout(self.run, record)
        self.assertEqual(self.row()['status'], 'running')
        self.assertIsNone(self.row()['closeout']['completed_at'])

    def test_missing_output_and_final_demotion_reject(self):
        record = self.record()
        self.deliver()
        self.store.artifact_designate(self.artifact['id'], 'draft', 'Needs correction')
        with self.assertRaisesRegex(ValueError, 'final'): self.store.closeout(self.run, record)
        self.store.artifact_designate(self.artifact['id'], 'final', 'Corrected designation')
        (Path(self.temp.name)/self.artifact['relative_path']).unlink()
        with self.assertRaises(OSError): self.store.closeout(self.run, record)
        self.assertEqual(self.row()['status'], 'running')

    def test_other_task_output_rejected(self):
        self.store.register('other','Other','Example')
        other = self.store.start('other')
        with self.assertRaisesRegex(ValueError, 'another task'):
            self.store.closeout_record(other, 'Summary','Scope','passed','Evidence','Limits',[self.artifact['id']])

    def test_records_and_delivery_observations_append_without_assuming_open(self):
        original = self.store.snapshot()['artifacts'][0]
        self.assertEqual(original['designation'], 'unclassified')
        self.assertEqual(original['delivery_observations'], [])
        self.deliver('sent')
        self.store.artifact_delivery(self.artifact['id'], 'accepted', 'Transport accepted version', time.time())
        artifact = self.store.snapshot()['artifacts'][0]
        self.assertEqual(len(artifact['delivery_observations']), 2)
        self.assertNotIn('user_open_confirmed', {d['status'] for d in artifact['delivery_observations']})
        for field in ('id','relative_path','sha256','created','title','size'):
            self.assertEqual(artifact[field], original[field])
        self.store.artifact_delivery(self.artifact['id'], 'user_open_confirmed', 'User explicitly confirmed opening version', time.time())
        self.assertIn('User open confirmed', artifact_delivery_label(self.store.snapshot()['artifacts'][0],'en'))

    def test_delivery_timestamp_evidence_validation(self):
        for status in ('archived','read','approved'):
            with self.assertRaises(ValueError): self.store.artifact_delivery(self.artifact['id'], status, 'Evidence', time.time())
        for observed in (0, time.time()+10000):
            with self.assertRaises(ValueError): self.store.artifact_delivery(self.artifact['id'], 'sent', 'Evidence', observed)
        for bad in ('',None):
            with self.assertRaises(ValueError): self.store.artifact_delivery(self.artifact['id'], 'sent', bad, time.time())
        self.assertEqual(self.store.snapshot()['artifacts'][0]['delivery_observations'], [])

    def test_legacy_run_preserved_and_marked(self):
        with self.store.connect() as db:
            db.execute('ALTER TABLE runs DROP COLUMN closeout_required')
        migrated = Store(self.temp.name)
        self.assertEqual(migrated.snapshot()['runs'][0]['closeout_required'], 0)
        migrated.update(self.run, status='succeeded')
        before = migrated.snapshot()['runs'][0]
        after = Store(self.temp.name).snapshot()['runs'][0]
        self.assertEqual(before, after)
        self.assertIsNone(after['closeout'])
        self.assertEqual(after['status'],'succeeded')
        newer = migrated.start('task')
        with self.assertRaises(ValueError): migrated.update(newer, status='succeeded')

    def test_read_only_old_database_optional_tables(self):
        with self.store.connect() as db:
            for table in ('closeout_completions','closeout_artifacts','closeout_records','artifact_delivery','artifact_designations'):
                db.execute('DROP TABLE '+table)
        snapshot = ReadOnlyStore(self.temp.name).snapshot()
        self.assertEqual(snapshot['closeouts'], [])
        self.assertEqual(snapshot['artifacts'][0]['designation'], 'unclassified')
        self.assertIsNone(snapshot['runs'][0]['closeout'])

    def test_cli_cannot_bypass_gate_and_accepts_untested_closeout(self):
        base=[sys.executable,'-m','dots_panel','--data-dir',self.temp.name]
        result=subprocess.run(base+['finish',self.run,'--status','succeeded'],cwd=ROOT,text=True,capture_output=True)
        self.assertNotEqual(result.returncode,0)
        result=subprocess.run(base+['closeout-record',self.run,'--summary','Review outcome','--scope','Text-only assessment','--verification','untested','--evidence','Requested review completed','--limits','No tests executed','--no-artifact-reason','Chat-only result'],cwd=ROOT,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        record=json.loads(result.stdout)['record_id']
        result=subprocess.run(base+['closeout',self.run,'--record',record],cwd=ROOT,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['verification'],'untested')
