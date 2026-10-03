"""Regression gates for live database loss and bound existing-only reset imports."""
import hashlib
import http.client
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from dots_panel.app import Store, make_server

EVENT={'event_id':'synthetic-reset-1','observed_at':1000,'event_type':'baseline_present','evidence_level':'observed','summary':'Synthetic baseline','source_kind':'manual','source_reference':'synthetic-observation','target_label':'synthetic-source'}

class ExistingStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.data=self.root/'data';self.events=self.root/'events.json';self.events.write_text(json.dumps([EVENT]))
    def tearDown(self):self.tmp.cleanup()
    def cli(self,*args):
        return subprocess.run([sys.executable,'-m','dots_panel','--data-dir',str(self.data),*args],capture_output=True,text=True)
    def identity(self):
        path=self.data/'config/backup-identity.json';path.write_text(json.dumps({'schema':'dots-panel.backup.v2','identity':'synthetic-installation'}));path.chmod(0o600)
    def test_existing_store_snapshot_loss_never_recreates_database(self):
        store=Store(self.data);store.path.unlink()
        for operation in (store.snapshot,lambda:store.register('test','Example','Test')):
            with self.assertRaises((OSError,sqlite3.Error)):operation()
            self.assertFalse(store.path.exists())
    def test_loss_during_connect_never_recreates_database(self):
        store=Store(self.data);original=sqlite3.connect
        def remove_then_connect(*args,**kwargs):
            store.path.unlink();return original(*args,**kwargs)
        with patch('dots_panel.app.sqlite3.connect',side_effect=remove_then_connect):
            with self.assertRaises(sqlite3.Error):store.snapshot()
        self.assertFalse(store.path.exists())
    def test_http_failure_after_loss_has_no_new_zero_byte_database(self):
        store=Store(self.data);server=make_server(store,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            def get():
                conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5);conn.request('GET','/api/state');res=conn.getresponse();status=res.status;res.read();conn.close();return status
            self.assertEqual(get(),200);store.path.unlink();self.assertEqual(get(),503);self.assertFalse(store.path.exists())
        finally:server.shutdown();server.server_close();thread.join()
    def test_explicit_constructor_can_still_initialize(self):
        store=Store(self.data);self.assertTrue(store.path.exists());store.register('example','Example','Test');self.assertEqual(store.snapshot()['tasks'][0]['id'],'example')
    def test_existing_writer_missing_path_never_creates_anything(self):
        with self.assertRaises(OSError):Store.existing_writer(self.data)
        self.assertFalse(self.data.exists())
    def test_reset_import_missing_data_never_initializes(self):
        result=self.cli('reset-import','--file',str(self.events),'--expected-identity','synthetic-installation');self.assertNotEqual(result.returncode,0);self.assertFalse(self.data.exists())
    def test_reset_import_identity_flag_required_before_any_creation(self):
        result=self.cli('reset-import','--file',str(self.events));self.assertNotEqual(result.returncode,0);self.assertIn('--expected-identity',result.stderr);self.assertFalse(self.data.exists())
    def test_reset_import_fake_schema_does_not_migrate_or_mutate(self):
        (self.data/'db').mkdir(parents=True,mode=0o700);self.data.chmod(0o700);(self.data/'config').mkdir(mode=0o700);self.identity()
        path=self.data/'db/panel.sqlite3'
        with sqlite3.connect(path) as db:db.execute('CREATE TABLE unrelated(id INTEGER)')
        path.chmod(0o600);before=hashlib.sha256(path.read_bytes()).hexdigest()
        result=self.cli('reset-import','--file',str(self.events),'--expected-identity','synthetic-installation');self.assertNotEqual(result.returncode,0);self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)
        with sqlite3.connect(path) as db:self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(),[('unrelated',)])
    def test_reset_import_matching_identity_unbound_rejected(self):
        store=Store(self.data);self.identity();before=store.path.read_bytes()
        result=self.cli('reset-import','--file',str(self.events),'--expected-identity','synthetic-installation');self.assertNotEqual(result.returncode,0);self.assertEqual(store.path.read_bytes(),before)
        with store.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM reset_events').fetchone()[0],0)
    def test_bound_import_retry_and_wrong_identity_are_safe(self):
        store=Store(self.data);self.identity();store.reset_bind('synthetic-installation','Synthetic identity confirmed')
        with store.connect() as db:version=db.execute('PRAGMA schema_version').fetchone()[0]
        for expected in (1,0):
            result=self.cli('reset-import','--file',str(self.events),'--expected-identity','synthetic-installation');self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads(result.stdout)['imported'],expected)
        wrong=self.cli('reset-import','--file',str(self.events),'--expected-identity','different');self.assertNotEqual(wrong.returncode,0)
        with store.connect() as db:self.assertEqual(db.execute('PRAGMA schema_version').fetchone()[0],version);self.assertEqual(db.execute('SELECT COUNT(*) FROM reset_events').fetchone()[0],1)
