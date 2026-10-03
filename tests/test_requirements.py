import concurrent.futures
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from dots_panel.app import Store
from dots_panel.desktop_view import ReadOnlyStore


class RequirementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name)
        self.store.register('one', 'Synthetic requirement activity', 'Test')
        self.at = time.time()

    def tearDown(self):
        self.tmp.cleanup()

    def receive(self, source='request-one', **changes):
        args = dict(task_id='one', source_event_id=source, observed_at=self.at, summary='Original requirement summary', evidence='Explicit synthetic request', reason='Dispatch pending', next_step='Verify the executor')
        args.update(changes)
        return self.store.requirement_receive(**args)

    def create(self, **changes):
        args = dict(task_id='one', source_event_id='create', observed_at=self.at, summary='Original requirement summary', evidence='Explicit synthetic request')
        args.update(changes)
        return self.store.requirement_create(**args)

    def card(self, key):
        return next(c for c in self.store.requirement_list('one') if c['id'] == key)

    def state(self, key, status, source, **changes):
        args = dict(requirement_id=key, status=status, expected_event_id=self.card(key)['current_event_id'], source_event_id=source, observed_at=time.time(), evidence_kind='start', evidence_ref='evidence-'+source, evidence='Observed synthetic action')
        args.update(changes)
        return self.store.requirement_transition(**args)

    def assignment(self, run):
        self.store.agent_register('actor', 'Sprout', portrait='bloom-mint')
        self.store.agent_identity('actor', 'manual', 'observed', 'Verified synthetic actor', time.time())
        return self.store.agent_run_assign(run, 'actor', 'development')['assignment_id']

    def test_atomic_intake_replay_and_terminal_retry(self):
        value = self.receive(); key=value['requirement_id']; run=value['run_id']
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT status FROM runs WHERE id=?',(run,)).fetchone()[0], 'waiting_external')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM requirements').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM requirement_receipts').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM task_receipts').fetchone()[0], 1)
        self.assertEqual(self.card(key)['run_ids'], [run]);self.assertEqual(self.card(key)['current_owner_event_id'],0)
        self.store.transition(run, 'cancelled', 'Synthetic cancellation', 'Actual test event')
        self.assertEqual(self.receive()['run_id'], run);self.assertTrue(self.receive()['deduplicated'])
        with self.assertRaises(ValueError):self.receive(summary='A different request')
        with self.assertRaises(ValueError):self.receive('new',run_id=run)

    def test_rollback_after_requirement_and_run_writes(self):
        with patch('dots_panel.requirement_sync._link', side_effect=RuntimeError('Injected write failure')):
            with self.assertRaises(RuntimeError):self.receive()
        with self.store.connect() as db:
            for table in ('requirements','runs','requirement_events','requirement_receipts','task_receipts'):
                self.assertEqual(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0)
        self.assertFalse(self.receive()['deduplicated'])

    def test_rollback_on_receipt_insert_failure(self):
        with self.store.connect() as db:
            db.execute("CREATE TRIGGER fail_receipt BEFORE INSERT ON requirement_receipts BEGIN SELECT RAISE(ABORT,'Injected receipt failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.receive()
        with self.store.connect() as db:
            for table in ('requirements','runs','requirement_events','requirement_receipts','task_receipts'):
                self.assertEqual(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0)

    def test_original_and_all_event_tables_immutable(self):
        q=self.receive()
        with self.store.connect() as db:
            for table in ('requirements','requirement_events','requirement_receipts','requirement_stream'):
                with self.assertRaises(sqlite3.IntegrityError):db.execute('DELETE FROM '+table)
            with self.assertRaises(sqlite3.IntegrityError):db.execute("UPDATE requirements SET summary='Changed'")
        self.assertEqual(self.card(q['requirement_id'])['summary'],'Original requirement summary')

    def test_creation_source_conflicts_and_idempotency(self):
        q=self.create();self.assertEqual(self.create()['id'],q['id'])
        with self.assertRaises(ValueError):self.create(summary='Different')
        with self.assertRaises(ValueError):self.create(observed_at=self.at-1)

    def test_cas_out_of_order_and_late_duplicate(self):
        q=self.create();key=q['id'];event=self.state(key,'in_progress','start')
        with self.assertRaises(ValueError):self.state(key,'blocked','block',expected_event_id=q['current_event_id'],next_step='Read source')
        with self.assertRaises(ValueError):self.state(key,'blocked','old',observed_at=self.at-1,next_step='Read source')
        block=self.state(key,'blocked','block',next_step='Read source')
        result=self.state(key,'in_progress','start',expected_event_id=q['current_event_id'],observed_at=event['observed_at'])
        self.assertTrue(result['deduplicated']);self.assertEqual(self.card(key)['current_event_id'],block['id'])
        with self.assertRaises(ValueError):self.state(key,'in_progress','start',expected_event_id=q['current_event_id'],observed_at=event['observed_at'],evidence='changed')

    def test_two_competing_cas_writers(self):
        q=self.create();at=time.time()
        def write(status):
            try:return self.state(q['id'],status,status,expected_event_id=q['current_event_id'],observed_at=at,next_step='Check')
            except ValueError:return None
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results=list(pool.map(write,['in_progress','blocked']))
        self.assertEqual(sum(result is not None for result in results),1)

    def test_only_linked_results_can_enter_acceptance(self):
        q=self.receive();key=q['requirement_id'];run=q['run_id']
        p=self.store.progress_update(run,'Finished synthetic work',result='A reviewable result',evidence='Executed test')['id']
        self.state(key,'in_progress','start')
        with self.assertRaises(ValueError):self.state(key,'pending_acceptance','ready',evidence_kind='result',evidence_ref=p)
        self.store.requirement_link(key,'result','progress',p,'result-link',time.time(),'Explicit result association')
        ready=self.state(key,'pending_acceptance','ready',evidence_kind='result',evidence_ref=p)
        for kind,ref in [('result','accepted'),('acceptance',p),('acceptance','result-link'),('acceptance','ready')]:
            with self.assertRaises(ValueError):self.state(key,'completed','accept-'+ref,evidence_kind=kind,evidence_ref=ref)
        completed=self.state(key,'completed','accepted',evidence_kind='acceptance',evidence_ref='actual-user-approval')
        self.assertFalse(self.card(key)['bookmarked']);self.assertEqual(len(self.card(key)['status_history']),4)
        with self.assertRaises(ValueError):self.state(key,'in_progress','worker-late')
        self.state(key,'in_progress','reopen',evidence_kind='reopen',evidence_ref='authorized-reopen')
        self.assertTrue(self.card(key)['bookmarked'])

    def test_completion_without_pending_is_rejected(self):
        q=self.create()
        with self.assertRaises(ValueError):self.state(q['id'],'completed','done',evidence_kind='acceptance')

    def test_cross_task_targets_and_assignment_rejected(self):
        q=self.receive();key=q['requirement_id']
        self.store.register('two','Other synthetic activity','Test');run=self.store.start('two');assignment=self.assignment(run)
        with self.assertRaises(ValueError):self.store.requirement_link(key,'run','run',run,'cross-link',time.time(),'Incorrect association')
        with self.assertRaises(ValueError):self.store.requirement_assign(key,assignment,'cross-owner',time.time(),0,'Incorrect association')
        with self.assertRaises(ValueError):self.receive('cross-intake',run_id=run)

    def test_owner_snapshot_replay_does_not_reinterpret_profile(self):
        q=self.receive();key=q['requirement_id'];assignment=self.assignment(q['run_id']);at=time.time()
        result=self.store.requirement_assign(key,assignment,'owner',at,0,'Confirmed actual dispatch')
        self.store.agent_profile('actor',name='A new name')
        replay=self.store.requirement_assign(key,assignment,'owner',at,0,'Confirmed actual dispatch')
        self.assertTrue(replay['deduplicated']);self.assertEqual(replay['owner']['name'],result['owner']['name'])
        with self.assertRaises(ValueError):self.store.requirement_assign(key,assignment,'owner-2',time.time(),0,'Confirmed again')

    def test_legacy_receive_reconciles_exact_receipt(self):
        old=self.store.receive('one','request-one','Original requirement summary','Dispatch pending','Explicit synthetic request','Verify the executor')
        new=self.receive();self.assertEqual(new['run_id'],old['run_id'])
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM runs').fetchone()[0],1)

    def test_selected_old_task_and_feed_exceed_overview_window(self):
        q=self.receive()
        with self.store.connect() as db:
            db.execute('INSERT INTO events(run_id,created,message) VALUES(?,?,?)',(q['run_id'],time.time(),'Old visible event'))
        with self.store.connect() as db:
            db.executemany('INSERT INTO tasks(id,name,project,created) VALUES(?,?,?,?)',[(f'x{i}',f'New {i}','Test',time.time()+i) for i in range(505)])
        snap=self.store.snapshot();self.assertNotIn('one',{t['id'] for t in snap['tasks']});self.assertIn(q['requirement_id'],{r['id'] for r in snap['requirements']})
        selected=ReadOnlyStore(self.tmp.name).snapshot(selected_task_id='one')
        self.assertIn('one',{t['id'] for t in selected['tasks']});self.assertIn(q['run_id'],{r['id'] for r in selected['runs']});self.assertTrue(selected['requirement_events'])
        self.assertTrue(any(e['message']=='Old visible event' for e in selected['events']))

    def test_readonly_requirement_commands_do_not_migrate(self):
        q=self.receive();dbpath=Path(self.tmp.name)/'db/panel.sqlite3'
        with sqlite3.connect(dbpath) as db:before=db.execute('PRAGMA schema_version').fetchone()[0]
        for command in ('requirement-list','requirement-sync-status','requirement-diagnose'):
            done=subprocess.run([sys.executable,'-m','dots_panel','--data-dir',self.tmp.name,command,'one'],capture_output=True,text=True)
            self.assertEqual(done.returncode,0,done.stderr);json.loads(done.stdout)
        with sqlite3.connect(dbpath) as db:self.assertEqual(db.execute('PRAGMA schema_version').fetchone()[0],before)
        absent=Path(self.tmp.name)/'missing'
        done=subprocess.run([sys.executable,'-m','dots_panel','--data-dir',str(absent),'requirement-list','one'],capture_output=True)
        self.assertNotEqual(done.returncode,0);self.assertFalse(absent.exists())

    def test_diagnose_and_sync_do_not_complete_or_guess_messages(self):
        q=self.receive();key=q['requirement_id'];p=self.store.progress_update(q['run_id'],'Output exists',evidence='Actual result')['id']
        self.store.requirement_link(key,'result','progress',p,'link',time.time(),'Explicit link')
        audit=ReadOnlyStore(self.tmp.name).requirement_sync_status('one');self.assertEqual(audit['upstream_message_coverage'],'not_connected');self.assertEqual(audit['findings'][0]['findings'],['assignment_unconfirmed'])
        self.assertEqual(len(self.store.requirement_diagnose('one')['findings']),1);self.assertEqual(self.card(key)['status'],'received')
