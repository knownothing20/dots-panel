import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from dots_panel.app import Store
from dots_panel.execution_config import normalize_config, config_label, dispatch_plan


class ExecutionConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'data')
        self.store.register('goal','Synthetic goal','Fixture');self.run=self.store.start('goal')
        self.store.agent_register('a','One');self.store.agent_identity('a','manual','observed','Synthetic identity',time.time())
    def tearDown(self):self.tmp.cleanup()
    def config(self,model='gpt-6-astra',effort='xhigh'):
        return dict(requested_model=model,requested_effort=effort,config_verification='requested',config_provider='synthetic dispatch',config_observed_at=100.,config_evidence='Explicit request accepted; actual runtime unavailable')
    def test_request_is_not_actual(self):
        config=normalize_config(**self.config());self.assertIsNone(config['actual_model']);self.assertIsNone(config['actual_effort'])
        self.assertIn('实际未知',config_label(config));self.assertFalse(dispatch_plan()['dispatches'])
        for bad in ({'requested_model':'x'},dict(self.config(),actual_model='gpt-6-astra',actual_effort='xhigh'),dict(self.config(),config_verification='verified'),dict(self.config(),config_evidence=None)):
            with self.assertRaises(ValueError):normalize_config(**bad)
    def test_config_change_new_episode_preserves_event(self):
        a=self.store.agent_run_assign(self.run,'a','development',**self.config())['assignment_id']
        self.assertEqual(a,self.store.agent_run_assign(self.run,'a','development',**self.config())['assignment_id'])
        self.store.progress_update(self.run,'Build','Done','Test','Synthetic',source_event_id='event',assignment_id=a)
        b=self.store.agent_run_assign(self.run,'a','development',**self.config(effort='ultra'))['assignment_id'];self.assertNotEqual(a,b)
        data=self.store.snapshot();episodes={e['id']:e for e in data['assignment_episodes']}
        self.assertEqual(episodes[a]['requested_effort'],'xhigh');self.assertIsNotNone(episodes[a]['ended_at'])
        event=next(r for r in data['activity'] if r.get('assignment_id')==a)
        self.assertEqual(event['attribution']['execution_config']['requested_effort'],'xhigh')
        self.assertIsNone(event['attribution']['execution_config']['actual_model'])
        with self.store.connect() as db:
            with self.assertRaises(sqlite3.IntegrityError):db.execute('UPDATE assignment_episodes SET requested_effort=? WHERE id=?',('low',a))
    def test_terminal_config_change_blocked(self):
        a=self.store.agent_run_assign(self.run,'a','development',**self.config())['assignment_id'];self.store.update(self.run,'cancelled')
        self.assertEqual(a,self.store.agent_run_assign(self.run,'a','development',**self.config())['assignment_id'])
        with self.assertRaises(ValueError):self.store.agent_run_assign(self.run,'a','development',**self.config(effort='high'))
    def test_legacy_unknown_and_migration_repeat(self):
        self.store.agent_run_assign(self.run,'a')
        data=Store(self.store.directory).snapshot();e=data['assignment_episodes'][0]
        self.assertEqual(e['config_verification'],'unknown');self.assertIsNone(e['requested_model']);self.assertIsNone(e['actual_model'])
    def test_verified_needs_real_fields_provenance(self):
        config=dict(self.config(),config_verification='verified',actual_model='observed-model',actual_effort='high')
        a=self.store.agent_run_assign(self.run,'a','development',**config)['assignment_id']
        e=next(e for e in self.store.snapshot()['assignment_episodes'] if e['id']==a)
        self.assertEqual(e['actual_model'],'observed-model');self.assertEqual(e['requested_model'],'gpt-6-astra')

if __name__=='__main__':unittest.main()
