"""Synthetic fixtures only. These tests never create or contact platform sessions."""
from pathlib import Path
import tempfile
import unittest
from dots_panel.app import Store, timestamp, verified_link


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)
        self.store.register('example', 'Example goal', 'Example project')

    def tearDown(self):
        self.temp.cleanup()

    def bind_example(self, observed_at=100):
        return self.store.bind('example', 'cloud_thread', 'example-thread-id', 'cloud', None, 'running', observed_at)

    def test_unbound_by_default(self):
        self.assertEqual(self.store.snapshot()['bindings'], [])
        with self.assertRaises(ValueError):
            self.store.ingest('example','event-1','assistant','implementation','in_progress','Safe summary',100)
        self.assertEqual(self.store.snapshot()['activity'], [])

    def test_binding_preserves_goal_and_identity(self):
        self.bind_example()
        binding = self.store.snapshot()['bindings'][0]
        self.assertEqual(binding['task_id'], 'example')
        self.assertEqual(binding['thread_id'], 'example-thread-id')
        self.assertEqual(binding['sync_mode'], 'manual')
        self.assertIsNone(binding['verified_url'])
        self.assertEqual(len(self.store.snapshot()['tasks']), 1)
        with self.assertRaises(ValueError):
            self.store.bind('example','cloud_thread','different-thread','cloud',None,'running',101)
        self.store.register('second','Another goal','Example project')
        with self.assertRaises(ValueError):
            self.store.bind('second','cloud_thread','example-thread-id','cloud',None,'running',101)

    def test_binding_requires_registered_goal_and_returned_id_shape(self):
        with self.assertRaises(ValueError):
            self.store.bind('missing','cloud_thread','example-thread','cloud',None,'created',100)
        with self.assertRaises(ValueError):
            self.store.bind('example','cloud_thread','/root/internal-worker','cloud',None,'created',100)
        with self.assertRaises(ValueError):
            self.store.bind('example','invented_source','example-thread','cloud',None,'created',100)

    def test_incremental_ingestion_is_idempotent_and_timestamped(self):
        self.bind_example()
        result=self.store.ingest('example','event-1','assistant','testing','verified','Public-safe result',110,'completed')
        duplicate=self.store.ingest('example','event-1','assistant','testing','verified','Must not overwrite',120,'failed')
        self.assertFalse(result['duplicate'])
        self.assertTrue(duplicate['duplicate'])
        self.assertEqual(result['activity_id'], duplicate['activity_id'])
        snapshot=self.store.snapshot()
        self.assertEqual(len(snapshot['activity']),1)
        event=snapshot['activity'][0]
        self.assertEqual(event['message'],'Public-safe result')
        self.assertEqual(event['source_event_id'],'event-1')
        self.assertEqual(event['created'],110)
        self.assertEqual(event['source_observed_at'],110)
        self.assertGreater(event['ingested_at'],110)
        self.assertEqual(snapshot['bindings'][0]['observed_status'],'completed')
        self.assertEqual(snapshot['runs'],[])

    def test_old_events_do_not_regress_observed_state(self):
        self.bind_example(200)
        self.store.ingest('example','older','assistant','planned','planned','Earlier summary',100,'created')
        self.assertEqual(self.store.snapshot()['bindings'][0]['observed_status'],'running')
        self.bind_example(50)
        self.assertEqual(self.store.snapshot()['bindings'][0]['observed_at'],200)

    def test_https_share_link_validation(self):
        self.assertEqual(verified_link('https://chatgpt.com/c/example-id'),'https://chatgpt.com/c/example-id')
        self.assertIsNone(verified_link(None))
        for value in ['codex://threads/example','javascript:alert(1)','http://chatgpt.com/c/example','https://evil.example/c/example','https://chatgpt.com.evil.example/c/example','https://user:secret@chatgpt.com/c/example','https://chatgpt.com:8080/c/example','https://chatgpt.com/ bad']:
            with self.subTest(value=value), self.assertRaises(ValueError): verified_link(value)

    def test_timezone_and_timestamp_validation(self):
        self.assertEqual(timestamp('1970-01-01T00:02:00+00:00'),120)
        for value in ['2026-01-01T00:00:00',float('inf'),float('nan'),-1,True]:
            with self.subTest(value=value), self.assertRaises(ValueError):timestamp(value)


if __name__=='__main__':unittest.main()
