"""Synthetic compatibility fixtures for the four-file 1.1.2 follow-up contract."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from dots_panel.app import Store
from dots_panel.followup import _disposition, migrate, technical_failure

DISPOSITIONS={'blocked_requires_authority','coordinator_followup','coordinator_diagnosis','coordinator_closeout_check','wait_with_owner','checkpoint_required','needs_executor_observation','no_flag'}
ENVELOPE={'schema','checked_at','task_scope','receipts','run_count','source','record_only','scheduler_hook','backup_result'}
RECEIPT={'task_id','run_id','checked_at','lifecycle','latest_progress_at','executor_status','executor_observation','checkpoint','disposition','reason','next_action','notification','record_only'}

class Contract112Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name);self.store=Store(self.root/'data');self.store.register('scope','Synthetic scoped activity','Test');self.run=self.store.start('scope');self.now=time.time()
        with self.store.connect() as db:db.execute('UPDATE runs SET started=? WHERE id=?',(self.now-1000,self.run))
    def tearDown(self):self.temp.cleanup()
    def checkpoint(self,source='event-1',at=None,blocker='none',goal='incomplete'):
        return self.store.followup_checkpoint(self.run,goal,'Synthetic remaining work',blocker,'coordinator','Inspect the result','Actual result received','Synthetic evidence',source,self.now-5 if at is None else at)
    def observation(self,status='running',at=None):
        return {'run_id':self.run,'status':status,'provider':'synthetic-provider','observed_at':self.now if at is None else at,'evidence':'Synthetic supported observation'}
    def audit(self,observations=None,**kw):return self.store.followup_audit(['scope'],now=self.now+1,executor_observations=observations,**kw)
    def progress(self):
        self.store.progress_update(self.run,'Inspect synthetic result','A result to inspect','Continue','Synthetic observation')
        with self.store.connect() as db:db.execute('UPDATE progress_updates SET created=? WHERE run_id=?',(self.now,self.run))
    def test_exact_v1_envelope_receipt_and_null_observation(self):
        result=self.audit();self.assertEqual(set(result),ENVELOPE);self.assertEqual(result['schema'],'dots-panel.followup-audit.v1');self.assertEqual(result['scheduler_hook'],'not_verified_by_audit');self.assertEqual(result['backup_result'],'separate_not_inferred');row=result['receipts'][0]
        self.assertTrue(RECEIPT<=set(row));self.assertIsNone(row['checkpoint']);self.assertIsNone(row['executor_observation']);self.assertEqual(row['executor_status'],'unknown');self.assertEqual(row['disposition'],'checkpoint_required');self.assertEqual(row['notification'],'not_sent_by_audit');self.assertTrue(row['record_only'])
    def test_valid_five_field_list_through_real_readonly_cli(self):
        self.checkpoint();self.progress();f=self.root/'observations.json';f.write_text(json.dumps([self.observation()]));before=self.store.path.read_bytes()
        env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'src'),'PYTHONDONTWRITEBYTECODE':'1'}
        run=subprocess.run([sys.executable,'-m','dots_panel','--data-dir',str(self.store.directory),'followup-audit','--task-id','scope','--executor-observations',str(f)],capture_output=True,text=True,env=env)
        self.assertEqual(run.returncode,0,run.stderr);result=json.loads(run.stdout);self.assertEqual(result['receipts'][0]['executor_status'],'running');self.assertEqual(result['receipts'][0]['disposition'],'no_flag');self.assertEqual(self.store.path.read_bytes(),before)
    def test_observation_validation_rejects_nonlist_extra_fields_duplicates(self):
        row=self.observation()
        for value in ({self.run:row},[{**row,'extra':'unsupported'}],[{k:v for k,v in row.items() if k!='evidence'}],[row,row],[row]*10001):
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(ValueError):self.audit(value)
    def test_observation_time_and_status_validation(self):
        for value in (-1,float('nan'),float('inf'),True,self.now+2,'2026-10-03T00:00:00Z'):
            with self.assertRaises(ValueError):self.audit([self.observation(at=value)])
        for state in ('busy','succeeded',None):
            with self.assertRaises(ValueError):self.audit([self.observation(status=state)])
    def test_observation_scope_is_not_broadened(self):
        self.store.register('other','Other synthetic activity','Test');other=self.store.start('other')
        with self.assertRaises(ValueError):self.audit([{**self.observation(),'run_id':other}])
        with self.assertRaises(ValueError):self.audit([{**self.observation(),'run_id':'missing'}])
    def test_observation_older_than_300_seconds_stays_unknown(self):
        self.checkpoint();self.progress();result=self.audit([self.observation(at=self.now-301)],stale_seconds=86400)['receipts'][0]
        self.assertEqual(result['executor_status'],'unknown');self.assertEqual(result['executor_observation']['status'],'running');self.assertFalse(result['executor_observation_fresh']);self.assertEqual(result['disposition'],'needs_executor_observation');self.assertEqual(result['executor_observation_max_age_seconds'],300)
    def test_stale_interval_contract_bounds(self):
        for threshold in (0,86401,-1,float('nan'),True):
            with self.assertRaises(ValueError):self.audit(stale_seconds=threshold)
        self.audit(stale_seconds=1);self.audit(stale_seconds=86400)
    def test_fresh_idle_returns_residual_scope_to_coordinator(self):
        self.checkpoint();self.progress();row=self.audit([self.observation('idle')])['receipts'][0]
        self.assertEqual(row['disposition'],'coordinator_followup');self.assertEqual(row['reason'],'executor_idle_with_residual_scope')
    def test_all_contract_dispositions_are_reachable_with_evidence(self):
        p={'created':1000,'current_step':'Synthetic work','result':'Observed result'};o={'status':'running','observed_at':1000};base={'goal_status':'incomplete','blocker_class':'none'}
        cases=[({**base,'blocker_class':'security'},p,o,'blocked_requires_authority'),({**base,'blocker_class':'internal_handoff'},p,o,'coordinator_followup'),({**base,'blocker_class':'failure'},p,o,'coordinator_diagnosis'),({**base,'goal_status':'complete'},p,o,'coordinator_closeout_check'),({**base,'blocker_class':'external_wait'},p,None,'wait_with_owner'),(None,p,o,'checkpoint_required'),(base,p,None,'needs_executor_observation'),(base,p,o,'no_flag')]
        found=set()
        for checkpoint,progress,observation,expected in cases:
            actual=_disposition(checkpoint,progress,observation,1001,3600);self.assertEqual(actual[0],expected);found.add(actual[0])
        self.assertEqual(found,DISPOSITIONS)
    def test_safety_failure_handoff_flags_override_recent_progress(self):
        for blocker,expected in [('security','blocked_requires_authority'),('access','blocked_requires_authority'),('approval','blocked_requires_authority'),('failure','coordinator_diagnosis'),('internal_handoff','coordinator_followup')]:
            actual=_disposition({'goal_status':'incomplete','blocker_class':blocker},{'created':1000,'current_step':'Recent','result':'Good'}, {'status':'running','observed_at':1000},1001,3600)
            self.assertEqual(actual[0],expected)
    def test_no_flag_has_recent_progress_reason(self):
        self.checkpoint();self.progress();row=self.audit([self.observation()])['receipts'][0];self.assertEqual(row['disposition'],'no_flag');self.assertEqual(row['reason'],'recent_progress')
    def test_cleared_hint_and_negation_match_contract(self):
        self.assertFalse(technical_failure('ERR_123 cleared'));self.assertTrue(technical_failure('ERR_123 not cleared'))
    def test_new_checkpoint_uuid_hash_source_time_and_delayed_retry(self):
        first=self.checkpoint();self.assertEqual(str(uuid.UUID(first['checkpoint_id'])),first['checkpoint_id']);self.assertEqual(len(first['content_sha256']),64)
        newer=self.checkpoint('newer',self.now-1,'access');retry=self.checkpoint();self.assertTrue(retry['deduplicated']);self.assertEqual(retry['checkpoint_id'],first['checkpoint_id']);self.assertEqual(self.audit()['receipts'][0]['checkpoint']['id'],newer['checkpoint_id'])
        self.assertEqual(self.audit()['receipts'][0]['checkpoint']['observed_at'],self.now-1)
    def test_reused_source_changed_fields_or_time_rejected(self):
        self.checkpoint()
        with self.assertRaises(ValueError):self.checkpoint(at=self.now-4)
        with self.assertRaises(ValueError):self.checkpoint(blocker='failure')
    def test_new_checkpoint_time_cannot_predate_run_or_be_future(self):
        for at in (self.now-1001,time.time()+1):
            with self.assertRaises(ValueError):self.checkpoint(at=at)
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM followup_checkpoints').fetchone()[0],0)
    def test_terminal_retry_is_stable_new_checkpoint_rejected(self):
        old=self.checkpoint();self.store.update(self.run,'cancelled');self.assertEqual(self.checkpoint()['checkpoint_id'],old['checkpoint_id'])
        with self.assertRaises(ValueError):self.checkpoint('new-after-terminal')
    def test_checkpoint_update_and_delete_rejected(self):
        self.checkpoint()
        with self.store.connect() as db:
            with self.assertRaises(sqlite3.IntegrityError):db.execute("UPDATE followup_checkpoints SET observed_at=0")
            with self.assertRaises(sqlite3.IntegrityError):db.execute('DELETE FROM followup_checkpoints')
    def test_legacy_identity_and_unknown_time_not_backfilled(self):
        with self.store.connect() as db:
            db.execute('DROP TABLE followup_checkpoints')
            db.execute('CREATE TABLE followup_checkpoints(id INTEGER PRIMARY KEY,run_id TEXT,source_event_id TEXT,observed_at REAL,created REAL,goal_status TEXT,remaining_scope TEXT,blocker_class TEXT,next_owner TEXT,next_action TEXT,recheck_condition TEXT,evidence TEXT,content_sha256 TEXT)')
            db.execute('INSERT INTO followup_checkpoints VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(7,self.run,None,None,self.now,'unknown','Legacy scope','unknown','coordinator','Inspect legacy evidence','Actual evidence available','Retained legacy fact','legacy-hash'))
            before=tuple(db.execute('SELECT * FROM followup_checkpoints').fetchone());migrate(db);after=tuple(db.execute('SELECT * FROM followup_checkpoints').fetchone());self.assertEqual(after[:-1],before);self.assertIsNone(after[-1])
        row=self.audit()['receipts'][0]['checkpoint'];self.assertEqual(row['id'],7);self.assertEqual(row['identity_kind'],'legacy_local_id');self.assertFalse(row['source_time_known']);self.assertIsNone(row['source_event_id']);self.assertIsNone(row['observed_at'])
    def test_cli_does_not_add_unsupported_handoff(self):
        env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'src'),'PYTHONDONTWRITEBYTECODE':'1'}
        result=subprocess.run([sys.executable,'-m','dots_panel','--data-dir',str(self.root/'missing'),'followup-audit','--task-id','scope','--handoff'],capture_output=True,text=True,env=env)
        self.assertNotEqual(result.returncode,0);self.assertIn('unrecognized arguments: --handoff',result.stderr);self.assertFalse((self.root/'missing').exists())
