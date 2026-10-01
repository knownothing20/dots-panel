from contextlib import closing
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from dots_panel.app import Store
from dots_panel.platform_schedules import validate_import


def fixture():
    return {'schema_version':'dots-panel.platform-schedule.v1','platform':'dot','task_id':'synthetic-platform-task','title':'Example daily task','enabled':True,'timezone':'Asia/Shanghai','timing_mode':'exact_schedule','schedule':'BEGIN:VEVENT\nDTSTART;TZID=Asia/Shanghai:20261002T080000\nRRULE:FREQ=DAILY;BYHOUR=8;BYMINUTE=0;BYSECOND=0\nEND:VEVENT','last_run_at':None,'next_run_at':None,'observed_at':datetime.now(timezone.utc).isoformat()}

class PlatformScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name)/'private')
        self.store.schedule_register('example','Example','Synthetic')
    def tearDown(self):self.temp.cleanup()
    def test_valid_snapshot_no_guessed_next_or_execution(self):
        before=self.store.snapshot()['schedules'][0]
        data=fixture();result=self.store.schedule_platform_import('example',data)
        self.assertIsNone(result['next_run_at']);self.assertIsNone(result['last_run_at'])
        self.assertEqual(result['first_scheduled_execution'],'unverified');self.assertEqual(result['sync_mode'],'manual')
        row=self.store.snapshot()['schedules'][0]
        self.assertEqual(row['state'],'disconnected');self.assertEqual(row['updated'],before['updated'])
        self.assertEqual(row['platform_observation'],result)
    def test_hourly_observation_preserves_platform_last_run(self):
        d=fixture();d.update(schedule='BEGIN:VEVENT\nDTSTART:20260930T132216Z\nRRULE:FREQ=HOURLY\nEND:VEVENT',timing_mode='condition_watch',last_run_at='2026-09-30T13:22:16Z')
        result=self.store.schedule_platform_import('example',d)
        self.assertEqual(result['last_run_at'],d['last_run_at']);self.assertIsNone(result['next_run_at'])
    def test_idempotent_and_conflicting_same_time_rejected(self):
        d=fixture();first=self.store.schedule_platform_import('example',d)
        self.assertEqual(self.store.schedule_platform_import('example',d),first)
        d['enabled']=False
        with self.assertRaises(ValueError):self.store.schedule_platform_import('example',d)
    def test_monotonic_and_reassociation(self):
        d=fixture();self.store.schedule_platform_import('example',d)
        for changes in ({'observed_at':'2025-01-01T00:00:00Z'},{'task_id':'other-task'}):
            bad=dict(d,**changes)
            with self.assertRaises(ValueError):self.store.schedule_platform_import('example',bad)
    def test_duplicate_platform_identity_and_missing_registry(self):
        d=fixture();self.store.schedule_platform_import('example',d)
        self.store.schedule_register('second','Second','Synthetic')
        for key in ('second','absent'):
            with self.assertRaises(ValueError):self.store.schedule_platform_import(key,d)
    def test_types_fields_dates_and_timezone(self):
        for key,value in [('schema_version','v2'),('enabled',1),('platform','other'),('task_id','https://example.com'),('title','x'*121),('timezone','../etc'),('timezone','Unknown/Place'),('timing_mode','run_now'),('observed_at','2026-01-01'),('observed_at','2999-01-01T00:00:00Z'),('last_run_at','2999-01-01T00:00:00Z')]:
            d=fixture();d[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):validate_import(d)
        d=fixture();d['prompt']='not permitted'
        with self.assertRaises(ValueError):validate_import(d)
    def test_rrule_validation(self):
        original=fixture()['schedule']
        for schedule in (original+'\nURL:https://evil', original.replace('BYHOUR=8','BYHOUR=99'),original.replace('FREQ=DAILY','FREQ=DAILY;FREQ=HOURLY'),original.replace('Asia/Shanghai','Europe/London'),original.replace('RRULE:','COMMAND:'),original.replace('20261002','20260231'),original.replace('BYHOUR=8','BYFOO=1'),original+'x'):
            d=fixture();d['schedule']=schedule
            with self.subTest(schedule=schedule),self.assertRaises(ValueError):validate_import(d)
    def test_restore_preserves_observation(self):
        self.store.schedule_platform_import('example',fixture());restored=Store(Path(self.temp.name)/'restored')
        with closing(sqlite3.connect(self.store.path)) as source,closing(sqlite3.connect(restored.path)) as target:source.backup(target)
        self.assertEqual(self.store.snapshot()['schedules'],restored.snapshot()['schedules'])
    def test_platform_import_preserves_independent_result_snapshot(self):
        from test_result_links import fixture as result_fixture
        before=self.store.schedule_result_import('example',result_fixture())
        self.store.schedule_platform_import('example',fixture())
        self.assertEqual(self.store.snapshot()['schedules'][0]['external_result'],before)
    def test_legacy_readonly_schema(self):
        with self.store.connect() as db:db.execute('DROP TABLE platform_schedules')
        self.assertNotIn('platform_observation',self.store.snapshot()['schedules'][0])
