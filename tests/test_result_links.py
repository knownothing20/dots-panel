from contextlib import closing
"""Synthetic explicit result observations; no account or network fixtures."""
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from dots_panel.app import Store
from dots_panel.result_links import decode_import, validate_import, MAX_IMPORT_BYTES


def fixture():
    return {'schema_version':'dots-panel.external-result.v1','repository':'example/results','ref':'main','status_path':'data/status.json','index_path':'data/index.json','checked_at':datetime.now(timezone.utc).isoformat(), 'fetch_error':None,
      'observation':{'latest':{'calendar_date':'2025-01-01','run_id':'example-run','collected_at':'2025-01-01T00:00:00Z','status':'degraded','selected_count':0,'stale':None},
      'index':{'generated_at':'2025-01-01T00:00:00Z','entry_count':1,'latest_date':'2025-01-01'},
      'evidence':{'status_sha':'a'*40,'index_sha':'b'*40,'status_url':'https://github.com/example/results/blob/main/data/status.json','index_url':'https://github.com/example/results/blob/main/data/index.json'}}}


class ResultLinkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name)/'private')
        self.store.schedule_register('example', 'Example', 'Synthetic')
    def tearDown(self): self.temp.cleanup()
    def test_success_is_result_not_scheduler_connection(self):
        before=self.store.snapshot()['schedules'][0]
        self.store.schedule_result_import('example', fixture())
        row=self.store.snapshot()['schedules'][0]
        self.assertEqual({k:v for k,v in row.items() if k!='external_result'}, {k:v for k,v in before.items() if k!='external_result'})
        result=row['external_result']
        self.assertEqual(result['platform_configuration'],'unverified')
        self.assertEqual(result['sync_mode'],'manual')
        self.assertIsNone(result['observation']['latest']['stale'])
    def test_failure_retains_last_good(self):
        original=self.store.schedule_result_import('example',fixture())
        failed=fixture();failed.update(observation=None,fetch_error='Connector unavailable')
        result=self.store.schedule_result_import('example',failed)
        self.assertEqual(result['observation'],original['observation'])
        self.assertEqual(result['last_good_at'],original['last_good_at'])
        self.assertEqual(result['fetch_error'],'Connector unavailable')
        refreshed=self.store.schedule_result_import('example',fixture())
        self.assertIsNone(refreshed['fetch_error'])
    def test_first_failure_has_no_result(self):
        failed=fixture();failed.update(observation=None,fetch_error='Unavailable')
        result=self.store.schedule_result_import('example',failed)
        self.assertIsNone(result['observation']);self.assertIsNone(result['last_good_at'])
    def test_unknown_schedule_rejected(self):
        with self.assertRaises(ValueError):self.store.schedule_result_import('absent',fixture())
    def test_rebinding_and_out_of_order_rejected(self):
        self.store.schedule_result_import('example',fixture())
        for key,value in [('ref','other'),('checked_at','2025-01-02T00:00:00Z')]:
            item=fixture();item[key]=value
            if key=='ref':
                for k in ('status_url','index_url'):item['observation']['evidence'][k]=item['observation']['evidence'][k].replace('/main/','/other/')
            with self.assertRaises(ValueError):self.store.schedule_result_import('example',item)
    def test_validation(self):
        for key,value in [('schema_version','v2'),('repository','user@evil/path'),('ref','../main'),('status_path','/etc/passwd'),('index_path','a/../b'),('checked_at','2025-01-01'),('checked_at','2999-01-01T00:00:00Z')]:
            item=fixture();item[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):validate_import(item)
        for section,key,value in [('latest','selected_count',True),('latest','stale','false'),('latest','calendar_date','2025-02-31'),('latest','status','<script>'),('latest','run_id','x'*201),('evidence','status_url','https://evil.example'),('evidence','status_sha','oops'),('index','entry_count',-1)]:
            item=fixture();item['observation'][section][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):validate_import(item)
    def test_unknown_fields_rejected(self):
        item=fixture();item['enabled']=True
        with self.assertRaises(ValueError):validate_import(item)
    def test_json_bounds_duplicate_and_nonfinite(self):
        for raw in (b' '* (MAX_IMPORT_BYTES+1), b'{"a":1,"a":2}',b'{"a":NaN}',b'\xff',b'['*2000):
            with self.assertRaises(ValueError):decode_import(raw)
    def test_backup_restore_preserves_association(self):
        self.store.schedule_result_import('example',fixture())
        destination=Path(self.temp.name)/'restore'
        restored=Store(destination)
        with closing(sqlite3.connect(self.store.path)) as source,closing(sqlite3.connect(restored.path)) as target:source.backup(target)
        self.assertEqual(self.store.snapshot()['schedules'],restored.snapshot()['schedules'])
    def test_old_readonly_schema_tolerated(self):
        with self.store.connect() as db:db.execute('DROP TABLE schedule_results')
        self.assertNotIn('external_result',self.store.snapshot()['schedules'][0])
