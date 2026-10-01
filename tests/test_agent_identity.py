"""Fixed local identities, provenance, portrait parity and safe additive migration."""
import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock
from dots_panel.app import Store
from dots_panel.agent_identity import PORTRAITS, portrait_spec, draw_portrait, identity_label
from dots_panel.desktop_view import Dashboard, ReadOnlyStore
from dots_panel.progress import agent_observation, task_participants


class AgentIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/'private')

    def test_rename_retains_key_assignments_status_and_previous_label(self):
        s=self.store;s.agent_register('one','Old task label',name_en='Old work')
        s.register('task','Independent task','Synthetic');run=s.start('task')
        s.agent_assign('task','one',work_type='development');s.agent_run_assign(run,'one','review')
        s.agent_observe('one','idle',time.time(),'Actual turn complete')
        before=s.snapshot();old=before['agents'][0]
        s.agent_profile('one','青芽',name_en='Qingya')
        after=s.snapshot();new=after['agents'][0]
        for key in ('id','created','status','observed_at','note','portrait','portrait_spec'):
            self.assertEqual(old[key],new[key])
        for key in ('tasks','runs','agent_assignments','agent_run_assignments','bindings'):
            self.assertEqual(before[key],after[key])
        self.assertEqual(new['previous_names'][0]['name'],'Old task label')
        self.assertEqual(new['previous_names'][0]['name_en'],'Old work')
        s.agent_profile('one','青芽',name_en='Qingya')
        self.assertEqual(len(s.snapshot()['agents'][0]['previous_names']),1)

    def test_legacy_upsert_retains_previous_labels_and_portrait(self):
        self.store.agent_upsert('one','Original','sky')
        before=self.store.snapshot()['agents'][0]
        self.store.agent_upsert('one','Revised','peach')
        after=self.store.snapshot()['agents'][0]
        self.assertEqual(after['portrait'],before['portrait'])
        self.assertEqual(after['previous_names'][0]['name'],'Original')

    def test_concurrent_registration_never_overwrites_a_profile(self):
        from concurrent.futures import ThreadPoolExecutor
        def register(name):
            try:
                self.store.agent_register('same',name)
                return name
            except ValueError:
                return None
        with ThreadPoolExecutor(max_workers=2) as executor:
            results=list(executor.map(register,('First','Second')))
        successful=[name for name in results if name is not None]
        self.assertEqual(len(successful),1)
        self.assertEqual(self.store.snapshot()['agents'][0]['name'],successful[0])

    def test_identity_is_separate_evidence_not_binding_or_status(self):
        s=self.store;s.agent_register('one','青芽');now=time.time()
        s.agent_identity('one','manual','observed','Matched through supported executor observation',now)
        a=s.snapshot()['agents'][0]
        self.assertEqual(a['identity_source'],'manual');self.assertEqual(a['identity_observed_at'],now)
        self.assertEqual(a['status'],'unknown');self.assertIsNone(a['observed_at']);self.assertEqual(s.snapshot()['bindings'],[])
        self.assertIn('not a permanent session',identity_label(a,'en'))
        for args in [('historical','observed','Evidence',now),('manual','historical','Evidence',now),('manual','observed','',now),('manual','observed','Evidence',now-1),('manual','observed','Evidence',time.time()+301)]:
            with self.assertRaises(ValueError):s.agent_identity('one',*args)

    def test_portrait_catalog_is_original_fixed_and_unique(self):
        self.assertEqual(len(PORTRAITS),48)
        specs=[portrait_spec({'id':'one','portrait':key}) for key in PORTRAITS]
        self.assertEqual(len({json.dumps(row['shapes'],sort_keys=True) for row in specs}),48)
        for spec in specs:
            self.assertTrue(all(shape['tag'] in ('rect','ellipse','polygon','polyline') for shape in spec['shapes']))
        a={'id':'one','name':'Alpha','avatar':'sky'}
        self.assertEqual(portrait_spec(a),portrait_spec(dict(a,name='Other name',work_type='review')))
        s=self.store;s.agent_register('one','青芽',portrait='wave-teal')
        s.agent_profile('one',avatar='peach',name_en='Qingya')
        self.assertEqual(s.snapshot()['agents'][0]['portrait'],'wave-teal')
        with self.assertRaises(ValueError):s.agent_profile('one',portrait='https://untrusted/image.svg')

    def test_upsert_locks_blank_legacy_portrait_before_changing_palette(self):
        s=self.store;s.agent_register('one','Original','sky')
        with s.connect() as db: db.execute("UPDATE agents SET portrait='' WHERE id='one'")
        before=s.snapshot()['agents'][0]['portrait_spec']
        s.agent_upsert('one','Revised','peach')
        after=s.snapshot()['agents'][0]
        self.assertTrue(after['portrait']);self.assertEqual(after['portrait_spec'],before)

    def test_automatic_portrait_allocation_uses_catalog_before_repeating(self):
        s=self.store
        for i in range(48):s.agent_register('profile-'+str(i),'Example '+str(i))
        agents=s.snapshot()['agents']
        self.assertEqual(len({a['portrait'] for a in agents}),48)
        s.agent_register('profile-48','Another identity')
        agents=s.snapshot()['agents']
        self.assertEqual(len(agents),49);self.assertEqual(len({a['id'] for a in agents}),49)
        self.assertEqual(len({a['portrait'] for a in agents}),48)

    def test_concurrent_new_profiles_allocate_different_portraits(self):
        from concurrent.futures import ThreadPoolExecutor
        def register(i):self.store.agent_register('new-'+str(i),'Example '+str(i))
        with ThreadPoolExecutor(max_workers=8) as executor:list(executor.map(register,range(16)))
        agents=self.store.snapshot()['agents']
        self.assertEqual(len({a['portrait'] for a in agents}),16)

    def test_native_uses_same_portrait_geometry(self):
        canvas=Mock();agent={'id':'one','portrait':'leaf-mint'}
        draw_portrait(canvas,agent)
        self.assertEqual(len(canvas.mock_calls),len(portrait_spec(agent)['shapes']))
        self.assertEqual(canvas.create_text.call_count,0)

    def test_additive_legacy_schema_migration_and_readonly_fallback(self):
        s=self.store;s.agent_register('old','Original','sky');s.register('task','Task','Synthetic');s.agent_assign('task','old')
        with s.connect() as db:
            for column in ('portrait','identity_source','identity_verification','identity_evidence','identity_observed_at'):
                db.execute('ALTER TABLE agents DROP COLUMN '+column)
            db.execute('DROP TABLE agent_profile_history')
        old=ReadOnlyStore(s.directory).snapshot()['agents'][0]
        self.assertEqual(old['previous_names'],[]);self.assertTrue(old['portrait_spec'])
        upgraded=Store(s.directory);a=upgraded.snapshot()['agents'][0]
        self.assertEqual(a['id'],'old');self.assertEqual(a['name'],'Original')
        self.assertEqual(a['identity_verification'],'unknown');self.assertEqual(upgraded.snapshot()['agent_assignments'][0]['agent_id'],'old')
        self.assertEqual(a['portrait'],old['portrait_spec']['key'])
        upgraded.agent_upsert('old','Original renamed','peach')
        renamed=upgraded.snapshot()['agents'][0]
        self.assertEqual(renamed['avatar'],'peach');self.assertEqual(renamed['portrait_spec'],old['portrait_spec'])
        Store(s.directory);self.assertEqual(len(upgraded.snapshot()['agents']),1)

    def test_historical_fresh_timestamp_never_claims_current_execution(self):
        a={'id':'old','status':'running','observed_at':100,'identity_verification':'historical'}
        state={'agents':[a],'tasks':[{'id':'task'}],'runs':[{'id':'run','task_id':'task','status':'running','started':1}], 'agent_run_assignments':[{'agent_id':'old','run_id':'run','assigned_at':1}]}
        self.assertFalse(agent_observation(a,state,now=101)['recent'])
        self.assertEqual(task_participants(state,'task',now=101)['active'],[])
        self.assertEqual(task_participants(state,'task',now=101)['assigned'][0]['id'],'old')

    def test_native_agents_render_fixed_avatar_and_separate_current_work(self):
        view=Dashboard.__new__(Dashboard);view.language='en';view.timezone='UTC';view.muted='gray';view.fg='black'
        view.scroll_area=Mock();view.label=Mock();view.card_grid=Mock();view.compact_row=Mock();view.selected_agent=None;view.tk=Mock();view.root=Mock();view.filter_chip=Mock();view.bg='white';view.t=lambda x:x;view.show_agent_history=True
        view.snapshot={'agents':[{'id':'one','name':'Qingya','status':'running','observed_at':1,'portrait':'wave-teal','identity_verification':'historical'}],'tasks':[{'id':'task','name':'Original work'}],'runs':[{'id':'run','task_id':'task','status':'running'}],'agent_run_assignments':[{'run_id':'run','agent_id':'one','work_type':'review'}]}
        view.detail_meta=True;view.render_task_participants(Mock(),'task');call=view.compact_row.call_args
        self.assertEqual(call.kwargs['avatar']['id'],'one');self.assertTrue(call.args[1].startswith('Panel ID '))
        self.assertIn('Review',call.args[2])
        agent=view.snapshot['agents'][0]
        agent.update(identity_source='manual',identity_observed_at=946684800,observed_at=1609459200)
        view.compact_row.reset_mock();view.render_task_participants(Mock(),'task');summary=view.compact_row.call_args_list[0].args[2]
        identity_line=next(line for line in summary.splitlines() if 'Identity checked at' in line)
        status_line=view.compact_row.call_args_list[0].args[3]
        self.assertIn('2000-01-01',identity_line);self.assertNotIn('2021-01-01',identity_line)
        self.assertIn('2021-01-01',status_line);self.assertNotIn('2000-01-01',status_line)

