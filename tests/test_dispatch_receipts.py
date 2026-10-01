"""Synthetic, isolated receipt/dispatch regressions. Never dispatches a real worker."""
import copy
import json
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from dots_panel.app import Store
from dots_panel.desktop_view import ReadOnlyStore, participant_caption, participant_observation, run_participant_names
from dots_panel.progress import dispatch_check, task_progress


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / 'data')
        self.store.register('goal', 'Synthetic goal', 'Tests')

    def receive(self, **changes):
        args = dict(task_id='goal', request_id='request-1', note='Implement and test one goal', reason='Awaiting available executor', evidence='Synthetic accepted request', next_step='Verify executor, then dispatch')
        args.update(changes)
        return self.store.receive(**args)

    def test_atomic_waiting_without_running_or_agent(self):
        result = self.receive()
        s = self.store.snapshot()
        self.assertEqual(result['status'], 'waiting_external')
        self.assertEqual(s['runs'][0]['status'], 'waiting_external')
        self.assertIsNone(s['runs'][0]['finished'])
        self.assertEqual(s['runs'][0]['lifecycle_reason'], 'Awaiting available executor')
        self.assertEqual(len(s['events']), 1)
        self.assertEqual(s['activity'][0]['stage'], 'received')
        self.assertEqual(s['agents'], [])
        self.assertEqual(len(ReadOnlyStore(self.store.directory).snapshot()['open_runs']), 1)

    def test_concurrent_coordinator_worker_receipt_is_one_run(self):
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: self.receive(), range(6)))
        self.assertEqual(len({r['run_id'] for r in results}), 1)
        self.assertEqual(sum(not r['deduplicated'] for r in results), 1)
        s = self.store.snapshot()
        self.assertEqual((len(s['runs']), len(s['events']), len(s['activity'])), (1, 1, 1))

    def test_conflict_rejected_terminal_retry_and_later_request(self):
        old = self.receive()['run_id']
        with self.assertRaises(ValueError):
            self.receive(note='Different content')
        self.store.transition(old, 'cancelled', 'Synthetic stop', 'Test result')
        self.assertEqual(self.receive()['status'], 'cancelled')
        new = self.receive(request_id='request-2')['run_id']
        self.assertNotEqual(old, new)
        self.assertEqual(len(self.store.snapshot()['runs']), 2)
        with self.assertRaises(ValueError):
            self.store.transition(old, 'running', 'Cannot reopen', 'Synthetic')

    def test_failure_rolls_back_receipt_run_and_events(self):
        with self.store.connect() as db:
            db.execute("CREATE TRIGGER reject_receipt_event BEFORE INSERT ON activity BEGIN SELECT RAISE(FAIL,'Synthetic failure'); END")
        with self.assertRaises(Exception):
            self.receive()
        with self.store.connect() as db:
            for table in ('runs', 'events', 'task_receipts', 'activity'):
                self.assertEqual(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0], 0)

    def test_task_scope_unknown_and_blank_receipt(self):
        self.store.register('second', 'Second goal', 'Tests')
        one = self.receive()['run_id']
        two = self.receive(task_id='second')['run_id']
        self.assertNotEqual(one, two)
        for args in ({'task_id':'missing'}, {'request_id':' '}, {'reason':' '}, {'evidence':' '}, {'next_step':' '}):
            with self.assertRaises(ValueError):
                self.receive(**args)
        self.assertEqual(len(self.store.snapshot()['runs']), 2)

    def test_dispatch_read_is_byte_preserving(self):
        self.store.agent_register('worker', 'Synthetic worker')
        before = self.store.path.read_bytes()
        result = subprocess.run([sys.executable, '-m', 'dots_panel', '--data-dir', str(self.store.directory), 'dispatch-check', 'goal', 'worker'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['assessment'], 'unverified')
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_cli_receipt_and_legacy_start(self):
        result = subprocess.run([sys.executable, '-m', 'dots_panel', '--data-dir', str(self.store.directory), 'receive', 'goal', '--request-id', 'cli-request', '--note', 'Synthetic', '--reason', 'Pending dispatch', '--evidence', 'Test', '--next-step', 'Dispatch'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'waiting_external')
        legacy = self.store.start('goal')
        self.assertEqual(next(r['status'] for r in self.store.snapshot()['runs'] if r['id']==legacy), 'running')

    def test_dispatch_check_never_initializes_data(self):
        missing = Path(self.tmp.name)/'not-created'
        result = subprocess.run([sys.executable, '-m', 'dots_panel', '--data-dir', str(missing), 'dispatch-check', 'goal', 'worker'], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(missing.exists())


class AssignmentIdentityTests(unittest.TestCase):
    def setUp(self):
        self.s = {'tasks':[{'id':'goal'}, {'id':'other'}], 'runs':[{'id':'run','task_id':'goal','status':'running','started':50}], 'agents':[{'id':'worker','name':'Assigned worker','status':'running','observed_at':100}, {'id':'owner','name':'Old owner','status':'idle','observed_at':90}], 'agent_run_assignments':[{'agent_id':'worker','run_id':'run','assigned_at':80}], 'agent_assignments':[{'task_id':'goal','agent_id':'owner'}], 'stale_after_seconds':120}

    def test_identity_survives_expiry_unknown_idle_and_missing_primary(self):
        for status in ('running','idle','unknown'):
            self.s['agents'][0]['status'] = status
            for assignments in (self.s['agent_assignments'], []):
                s = dict(self.s, agent_assignments=assignments)
                p = task_progress(s, 'goal', 400)
                self.assertEqual(p['lead']['agent']['id'], 'worker')
                self.assertEqual(p['active_participants'], [])
                self.assertIn('Assigned participant', participant_caption(p, 'en'))
                self.assertEqual(p['current_run_id'], 'run')
                self.assertIn('current state unconfirmed', participant_observation(p['lead']['agent'], s, 'en', 400))
        self.assertEqual(run_participant_names(self.s, 'run', 'en'), 'Assigned worker')

    def test_current_run_scope_does_not_borrow_waiting_participant(self):
        self.s['runs'].append({'id':'new','task_id':'goal','status':'waiting_external','started':200})
        p = task_progress(self.s, 'goal', 400)
        self.assertEqual(p['current_run_id'], 'new')
        self.assertEqual(p['assigned_participants'], [])
        self.assertEqual(p['lead']['agent']['id'], 'owner')
        self.assertEqual(len(p['open_runs']), 2)
        self.assertEqual(run_participant_names(self.s, 'run'), 'Assigned worker')

    def test_new_topic_does_not_reanimate_older_assignment(self):
        self.s['runs'].append({'id':'other-run','task_id':'other','status':'running','started':85})
        self.s['agent_run_assignments'].append({'agent_id':'worker','run_id':'other-run','assigned_at':90})
        p = task_progress(self.s, 'goal', 110)
        self.assertEqual(p['lead']['agent']['id'], 'worker')
        self.assertEqual(p['active_participants'], [])
        self.assertEqual(task_progress(self.s, 'other', 110)['active_participants'][0]['id'], 'worker')
        self.s['runs'][-1]['status'] = 'succeeded'
        self.assertEqual(task_progress(self.s, 'goal', 110)['active_participants'], [])

    def test_only_narrow_other_topic_conflict_is_reported(self):
        before=copy.deepcopy(self.s)
        result=dispatch_check(self.s, 'other', 'worker', 110)
        self.assertEqual(result['assessment'], 'recorded_conflict')
        self.assertEqual(result['conflicts'][0]['run_id'], 'run')
        self.assertTrue(result['platform_check_required'])
        self.assertEqual(dispatch_check(self.s, 'goal', 'worker', 110)['assessment'], 'unverified')
        self.assertEqual(self.s, before)

    def test_history_waiting_stale_and_preassignment_are_not_busy(self):
        for status in ('waiting_external','waiting_user','awaiting_review','paused','succeeded','failed','cancelled'):
            s=copy.deepcopy(self.s);s['runs'][0]['status']=status
            self.assertEqual(dispatch_check(s, 'other', 'worker', 110)['conflicts'], [])
        for observed in (None, 50, 500):
            s=copy.deepcopy(self.s);s['agents'][0]['observed_at']=observed
            self.assertEqual(dispatch_check(s, 'other', 'worker', 400)['conflicts'], [])
        for status in ('idle','unknown','blocked','unavailable'):
            s=copy.deepcopy(self.s);s['agents'][0]['status']=status
            self.assertEqual(dispatch_check(s, 'other', 'worker', 110)['conflicts'], [])
        s=copy.deepcopy(self.s);s['agent_run_assignments'].append({'agent_id':'worker','run_id':'latest-finished','assigned_at':95})
        self.assertEqual(dispatch_check(s, 'other', 'worker', 110)['conflicts'], [])
        s['runs'].append({'id':'latest-finished','task_id':'other','status':'succeeded','started':90})
        self.assertEqual(dispatch_check(s, 'other', 'worker', 110)['conflicts'], [])
        s['agent_run_assignments'][1]['assigned_at']=80
        self.assertEqual(dispatch_check(s, 'other', 'worker', 110)['conflicts'], [])

if __name__ == '__main__':
    unittest.main()
