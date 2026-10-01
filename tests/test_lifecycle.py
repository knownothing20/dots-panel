from closeout_fixture import prepare_success
"""Explicit lifecycle records; isolated synthetic stores, never executor control."""
import json
import subprocess
import sys
import tempfile
import time
import unittest

from dots_panel.app import Store, OPEN_STATUSES, STATUSES, ROOT, agent_work
from dots_panel.desktop_view import ReadOnlyStore, STATUS, translate, task_rows, workspace_rows, pipeline_counts


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.store.register('sample', 'Synthetic lifecycle', 'Example')
        self.run = self.store.start('sample')

    def change(self, status, **kw):
        values = dict(reason='Observed reason', evidence='Synthetic verified observation', next_step='Continue the stated step')
        values.update(kw)
        if status == 'succeeded' and self.row()['status'] in OPEN_STATUSES:
            prepare_success(self.store, self.run)
        return self.store.transition(self.run, status, **values)

    def row(self):
        return self.store.snapshot()['runs'][0]

    def test_normal_completion_and_legacy_finish(self):
        self.store.update(self.run, message='Checks passed')
        prepare_success(self.store, self.run)
        self.store.update(self.run, status='succeeded')
        self.assertEqual(self.row()['status'], 'succeeded')
        self.assertIsNotNone(self.row()['finished'])
        with self.assertRaises(ValueError): self.change('running')

    def test_wait_resume_review_complete_same_run(self):
        for status in ('waiting_user', 'running', 'waiting_external', 'paused', 'running', 'awaiting_review', 'succeeded'):
            with self.subTest(status=status):
                result = self.change(status)
                self.assertTrue(result['record_only'])
                row = self.row()
                self.assertEqual(row['id'], self.run)
                self.assertEqual(row['status'], status)
                self.assertEqual(row['lifecycle_reason'], 'Observed reason')
                self.assertEqual(row['finished'] is None, status not in STATUSES)
        self.assertEqual(len(self.store.snapshot()['events']), 7)
        self.assertEqual(len(self.store.snapshot()['tasks']), 1)
        timeline = self.store.snapshot()['activity']
        timeline = [event for event in timeline if event['stage'] != 'closeout']
        self.assertEqual(len(timeline), 7)
        self.assertEqual({event['stage'] for event in timeline}, {'state_changed'})
        self.assertEqual(pipeline_counts(self.store.snapshot()), {'planned': 0, 'in_progress': 0, 'verified': 0})

    def test_all_open_state_transitions(self):
        for origin in OPEN_STATUSES:
            for destination in (*OPEN_STATUSES, *STATUSES):
                if origin == destination:
                    continue
                with self.subTest(origin=origin, destination=destination):
                    run = self.store.start('sample')
                    if origin != 'running':
                        self.store.transition(run, origin, 'Reason', 'Evidence', 'Next')
                    if destination == 'succeeded': prepare_success(self.store, run)
                    result = self.store.transition(run, destination, 'Reason', 'Evidence', 'Next', origin)
                    self.assertEqual(result['status'], destination)

    def test_invalid_transitions_leave_no_partial_write(self):
        before = self.row()
        for status in ('running', 'pending', 'interrupted', 'idle', 'unknown'):
            with self.subTest(status=status), self.assertRaises(ValueError): self.change(status)
        self.assertEqual(self.row()['status'], before['status'])
        self.assertEqual(self.store.snapshot()['events'], [])
        self.change('cancelled')
        for status in (*OPEN_STATUSES, *STATUSES):
            with self.assertRaises(ValueError): self.change(status)

    def test_required_reason_evidence_and_next_step(self):
        for field in ('reason', 'evidence', 'next_step'):
            for value in ('', '  ', 'x'*2001, '\x00', None):
                with self.subTest(field=field, value=str(value)[:20]), self.assertRaises(ValueError):
                    self.change('waiting_user', **{field:value})
        self.assertEqual(self.row()['status'], 'running')
        self.assertEqual(self.store.snapshot()['events'], [])

    def test_terminal_next_step_optional(self):
        self.change('succeeded', next_step='')
        self.assertEqual(self.row()['next_step'], '')

    def test_expected_state_prevents_stale_write(self):
        self.change('waiting_user', from_status='running')
        with self.assertRaisesRegex(ValueError, 'refresh'):
            self.change('succeeded', from_status='running')
        self.assertEqual(self.row()['status'], 'waiting_user')
        self.assertEqual(len(self.store.snapshot()['events']), 1)
        with self.assertRaises(ValueError): self.change('running', from_status='invalid')
        with self.assertRaises(ValueError): self.store.transition('missing', 'paused', 'Reason', 'Evidence', 'Next')

    def test_logs_heartbeat_never_implicitly_resume(self):
        self.change('waiting_external')
        self.store.update(self.run, message='Still awaiting external result')
        self.store.update(self.run)
        self.assertEqual(self.row()['status'], 'waiting_external')
        self.assertIsNone(self.row()['finished'])
        self.assertEqual(self.row()['next_step'], 'Continue the stated step')

    def test_legacy_finish_clears_obsolete_waiting_details(self):
        self.change('waiting_user')
        self.store.update(self.run, status='cancelled')
        self.assertEqual(self.row()['status'], 'cancelled')
        self.assertEqual(self.row()['next_step'], '')
        self.assertEqual(self.row()['lifecycle_reason'], '')
        self.assertIn('waiting_user', self.store.snapshot()['events'][0]['message'])

    def test_interruption_and_executor_idle_are_independent(self):
        self.store.bind('sample', 'cloud_thread', 'synthetic-session', 'cloud', None, 'interrupted', time.time()-1)
        self.store.agent_register('owner', 'Synthetic owner')
        self.store.agent_assign('sample', 'owner')
        self.store.agent_observe('owner', 'idle', time.time()-1)
        snapshot = self.store.snapshot()
        self.assertEqual(snapshot['runs'][0]['status'], 'running')
        self.assertEqual(agent_work(snapshot, snapshot['agents'][0])['current'], [])
        self.change('paused')
        snapshot = self.store.snapshot()
        self.assertEqual(snapshot['bindings'][0]['observed_status'], 'interrupted')
        self.assertEqual(snapshot['agents'][0]['status'], 'idle')
        self.assertEqual(len(agent_work(snapshot, snapshot['agents'][0])['unfinished']), 1)
        self.assertEqual(agent_work(snapshot, snapshot['agents'][0])['recent'], [])

    def test_staleness_does_not_change_waiting_state(self):
        self.change('waiting_external')
        with self.store.connect() as db:
            db.execute('UPDATE runs SET updated=0 WHERE id=?', (self.run,))
            db.execute('UPDATE activity SET created=0')
        row = self.row()
        self.assertTrue(row['stale'])
        self.assertEqual(row['status'], 'waiting_external')
        self.assertIsNone(row['finished'])

    def test_native_labels_and_filters(self):
        names = {'waiting_user': 'Waiting for user', 'waiting_external': 'Waiting for external result', 'paused': 'Recorded as paused', 'awaiting_review': 'Awaiting review'}
        for status, english in names.items():
            self.change(status)
            self.assertEqual(translate(STATUS[status], 'en'), english)
            rows = task_rows(self.store.snapshot(), time.time(), 'en')
            self.assertEqual(workspace_rows(rows, status)[0]['status'], status)
            self.assertEqual(rows[0]['run']['next_step'], 'Continue the stated step')

    def test_cli_validates_and_records(self):
        command = [sys.executable, '-m', 'dots_panel', '--data-dir', self.temp.name, 'transition', self.run, '--status', 'waiting_user', '--reason', 'Question pending', '--evidence', 'Synthetic request']
        rejected = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        self.assertNotEqual(rejected.returncode, 0)
        accepted = subprocess.run(command + ['--next-step', 'Await answer', '--from-status', 'running'], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertEqual(json.loads(accepted.stdout)['status'], 'waiting_user')

    def test_legacy_database_and_read_only_compatibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp)
            store.register('legacy', 'Legacy', 'Example')
            run = store.start('legacy', 'Original note')
            with store.connect() as db:
                # Remove only additive columns; preserve foreign-key targets.
                for field in ('lifecycle_reason', 'next_step', 'lifecycle_evidence'):
                    db.execute(f'ALTER TABLE runs DROP COLUMN {field}')
            old = ReadOnlyStore(tmp).snapshot()['runs'][0]
            self.assertEqual(old['lifecycle_reason'], '')
            upgraded = Store(tmp).snapshot()['runs'][0]
            self.assertEqual(upgraded['id'], run)
            self.assertEqual(upgraded['note'], 'Original note')
            self.assertEqual(upgraded['status'], 'running')
            self.assertEqual(upgraded['next_step'], '')
            self.assertEqual(Store(tmp).snapshot()['runs'][0], upgraded)
            Store(tmp).transition(run, 'waiting_user', 'Reason', 'Evidence', 'Next')
            self.assertEqual(ReadOnlyStore(tmp).snapshot()['runs'][0]['status'], 'waiting_user')
