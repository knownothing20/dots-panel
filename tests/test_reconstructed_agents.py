"""Tests for explicitly reconstructed CRUD over retained Agent schema."""
import tempfile
import time
import unittest
from pathlib import Path
from dots_panel.app import Store, agent_work

class ReconstructedAgentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name)/'private')
    def tearDown(self):self.temp.cleanup()
    def test_registration_is_unknown_not_running(self):
        self.store.agent_register('example','Example')
        row=self.store.snapshot()['agents'][0]
        self.assertEqual(row['status'],'unknown');self.assertIsNone(row['observed_at'])
    def test_profile_update_keeps_observation(self):
        self.store.agent_register('example','Example');observed=time.time()
        self.store.agent_observe('example','idle',observed,'Finished turn')
        self.store.agent_profile('example',name_en='English name',avatar='sky')
        row=self.store.snapshot()['agents'][0]
        self.assertEqual(row['status'],'idle');self.assertEqual(row['observed_at'],observed)
        self.assertEqual(row['name'],'Example');self.assertEqual(row['note'],'Finished turn')
    def test_stale_observation_rejected(self):
        self.store.agent_register('example','Example');observed=time.time()
        self.store.agent_observe('example','idle',observed)
        with self.assertRaises(ValueError):self.store.agent_observe('example','running',observed-1)
    def test_future_observation_rejected(self):
        self.store.agent_register('example','Example')
        with self.assertRaises(ValueError):self.store.agent_observe('example','running',time.time()+301)
    def test_invalid_keys_and_avatar_rejected(self):
        for key in ('../x','internal/path','', 'A'):
            with self.assertRaises(ValueError):self.store.agent_register(key,'Example')
        with self.assertRaises(ValueError):self.store.agent_register('example','Example','untrusted')
    def test_assignment_does_not_start_task(self):
        self.store.agent_register('example','Example');self.store.register('task','Task','Synthetic')
        self.store.agent_assign('task','example',work_type='testing')
        state=self.store.snapshot();self.assertEqual(state['runs'],[])
        self.assertEqual(state['agent_assignments'][0]['work_type'],'testing')
        self.assertEqual(agent_work(state,state['agents'][0])['current'],[])
    def test_assignment_replacement_explicit(self):
        for key in ('a','b'):self.store.agent_register(key,key)
        self.store.register('task','Task','Synthetic');self.store.agent_assign('task','a')
        with self.assertRaises(ValueError):self.store.agent_assign('task','b')
        self.store.agent_assign('task','b',replace=True)
        self.assertEqual(self.store.snapshot()['agent_assignments'][0]['agent_id'],'b')
    def test_assignment_rejects_unknown_references(self):
        with self.assertRaises(ValueError):self.store.agent_assign('missing','missing')
    def test_duplicate_registration_preserves_existing(self):
        self.store.agent_register('example','Original')
        with self.assertRaises(ValueError):self.store.agent_register('example','Replacement')
        self.assertEqual(self.store.snapshot()['agents'][0]['name'],'Original')

if __name__=='__main__':unittest.main()
