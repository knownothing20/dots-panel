import tempfile
import time
import unittest
from pathlib import Path
from dots_panel.app import Store
from dots_panel.collaborative_activity import guard_project_closeout


class CollaborationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name)/'data')
        self.store.register('goal','Goal','Fixture')
        self.run = self.store.start('goal')
        for key in ('a','b'):
            self.store.agent_register(key,key)
            self.store.agent_identity(key,'manual','observed','Synthetic verified identity',time.time())
    def tearDown(self):
        self.tmp.cleanup()
    def assign(self,role='development',agent='a'):
        return self.store.agent_run_assign(self.run,agent,role)['assignment_id']
    def progress(self,assignment,source='step'):
        return self.store.progress_update(self.run,'Implement','Checked','Review','Synthetic test',source_event_id=source,assignment_id=assignment)
    def test_modes_independent_and_no_implicit_team(self):
        self.assign();self.assign('review','b')
        task=next(t for t in self.store.snapshot()['tasks'] if t['id']=='goal')
        self.assertEqual(task['collaboration_mode'],'single')
        self.store.activity_structure('goal',collaboration_mode='team',reason='Two scoped participants')
        task=self.store.snapshot()['tasks'][0]
        self.assertEqual((task['activity_kind'],task['collaboration_mode'],task['parent_task_id']),('task','team',None))
    def test_role_history_and_event_snapshot(self):
        first=self.assign();self.progress(first)
        second=self.assign('review');self.assertNotEqual(first,second)
        self.assertTrue(self.progress(first)['deduplicated'])
        self.assertEqual(second,self.assign('review'))
        self.store.agent_profile('a',name='Changed')
        data=self.store.snapshot();episodes=data['assignment_episodes']
        self.assertEqual(len(episodes),2)
        self.assertIsNotNone(next(e for e in episodes if e['id']==first)['ended_at'])
        row=next(r for r in data['activity'] if r.get('assignment_id')==first)
        self.assertEqual(row['work_type_at_event'],'development')
        self.assertEqual(row['attribution']['actor_name'],'a')
        from dots_panel.agent_identity import portrait_spec
        expected=portrait_spec({'portrait':row['attribution']['portrait']})
        self.assertEqual(row['attribution']['portrait_spec'],expected)
        self.store.agent_profile('a',portrait='wave-amber')
        frozen=self.store.collaboration_timeline('goal')['rows'][0]['attribution']
        self.assertEqual(frozen['portrait_spec'],expected)
        with self.assertRaises(ValueError):self.store.progress_update(self.run,'Different step',evidence='Test',source_event_id='old',assignment_id=first)
    def test_attribution_dedup_conflict(self):
        a=self.assign();self.assertFalse(self.progress(a)['deduplicated']);self.assertTrue(self.progress(a)['deduplicated'])
        b=self.assign('review','b')
        with self.assertRaises(ValueError):self.progress(b)
    def test_assignment_mismatch_and_unverified(self):
        self.store.register('other','Other','Fixture');other=self.store.start('other')
        a=self.assign()
        with self.assertRaises(ValueError):self.store.progress_update(other,'Do',evidence='Test',assignment_id=a)
        self.store.agent_identity('b','historical','historical','Cannot verify',time.time())
        b=self.assign('review','b')
        with self.assertRaises(ValueError):self.progress(b)
    def test_terminal_assignment_changes_rejected(self):
        a=self.assign()
        self.store.update(self.run,'cancelled')
        self.assertEqual(self.assign(),a)
        with self.assertRaises(ValueError):self.assign('review')
    def test_migration_idempotent_preserves_legacy(self):
        self.assign();again=Store(self.store.directory)
        self.assertEqual(len(again.snapshot()['assignment_episodes']),1)
        with self.store.connect() as db:
            db.execute('DELETE FROM assignment_episodes')
        again=Store(self.store.directory);data=again.snapshot()
        self.assertEqual(data['assignment_episodes'][0]['provenance'],'legacy_snapshot')
        self.assertEqual(data['tasks'][0]['mode_source'],'explicit')
        with self.assertRaises(ValueError):self.progress(data['assignment_episodes'][0]['id'])
    def test_project_links_and_closeout(self):
        self.store.register('project','Project','Fixture',activity_kind='project',collaboration_mode='team')
        self.store.activity_structure('goal',parent_task_id='project',reason='Separate child deliverable')
        with self.store.connect() as db:
            with self.assertRaises(ValueError):guard_project_closeout(db,'project')
            db.execute("UPDATE runs SET status='succeeded',finished=? WHERE id=?",(time.time(),self.run))
            guard_project_closeout(db,'project')
        with self.assertRaises(ValueError):self.store.activity_structure('project',parent_task_id='goal',reason='Invalid')
        with self.assertRaises(ValueError):self.store.activity_structure('project',activity_kind='task',reason='Invalid')
        with self.assertRaises(ValueError):self.store.activity_structure('goal',parent_task_id='goal',reason='Invalid')
    def test_project_closeout_blocks_all_success_paths(self):
        self.store.register('p','Parent','Fixture',activity_kind='project')
        self.store.activity_structure('goal',parent_task_id='p',reason='Child')
        run=self.store.start('p')
        record=self.store.closeout_record(run,'Done','Scope','passed','Synthetic','Test',no_artifact_reason='No file')['record_id']
        for action in (lambda:self.store.closeout(run,record),lambda:self.store.update(run,'succeeded'),lambda:self.store.transition(run,'succeeded','Done','Test')):
            with self.assertRaises(ValueError):action()
    def test_timeline_full_scope_filter_pagination(self):
        self.store.register('p','Parent','Fixture',activity_kind='project')
        self.store.activity_structure('goal',parent_task_id='p',reason='Child')
        a=self.assign();self.progress(a)
        self.store.activity('Fixture','assistant','research','Unknown legacy author','goal')
        self.assertEqual(len(self.store.collaboration_timeline('p')['rows']),0)
        result=self.store.collaboration_timeline('p',True,agent_id='a',work_type='development',child_task_id='goal')
        self.assertEqual(result['total'],1)
        self.assertEqual(result['rows'][0]['attribution']['actor_display_id'],'a')
        for i in range(105):self.store.activity('Fixture','system','check',str(i),'goal')
        result=self.store.collaboration_timeline('p',True,limit=10)
        self.assertGreater(result['total'],100);self.assertTrue(result['has_more'])
        with self.assertRaises(ValueError):self.store.collaboration_timeline('p',False,child_task_id='goal')
    def test_migration_rollback_preserves_records(self):
        import sqlite3
        from dots_panel.collaborative_activity import migrate
        db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
        db.executescript("CREATE TABLE tasks(id TEXT PRIMARY KEY); CREATE TABLE runs(id TEXT,status TEXT,finished REAL); CREATE TABLE agent_run_assignments(run_id TEXT,agent_id TEXT,work_type TEXT,assigned_at REAL); CREATE TABLE agents(id TEXT PRIMARY KEY); INSERT INTO tasks VALUES('keep'); INSERT INTO runs VALUES('r','running',NULL); INSERT INTO agent_run_assignments VALUES('r','a','review',1);")
        class FailSeed:
            def execute(self,sql,*args):
                if sql.startswith('INSERT INTO assignment_episodes VALUES'):
                    raise sqlite3.OperationalError('Synthetic seed failure')
                return db.execute(sql,*args)
        with self.assertRaises(sqlite3.OperationalError):migrate(FailSeed())
        self.assertEqual([r[1] for r in db.execute('PRAGMA table_info(tasks)')],['id'])
        self.assertEqual(db.execute('SELECT id FROM tasks').fetchone()[0],'keep')
        self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='assignment_episodes'").fetchone())
        db.close()
    def test_http_timeline_validation_and_readonly(self):
        import http.client,json,threading
        from dots_panel.app import make_server
        server=make_server(self.store,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port)
            connection.request('GET','/api/collaboration-timeline?task_id=goal&limit=1')
            response=connection.getresponse();self.assertEqual(response.status,200);self.assertEqual(json.loads(response.read())['task_id'],'goal')
            for query in ('task_id=goal&limit=0','task_id=goal&include_children=oops','task_id=goal&task_id=goal','task_id=goal&unexpected=x'):
                connection.request('GET','/api/collaboration-timeline?'+query);response=connection.getresponse();self.assertEqual(response.status,400);response.read()
            connection.close()
        finally:
            server.shutdown();server.server_close();thread.join()
    def test_ingest_attribution_retry_and_history(self):
        self.store.bind('goal','cloud_thread','fixture-thread','cloud',None,'running',time.time())
        a=self.assign();observed=time.time()
        first=self.store.ingest('goal','event','assistant','testing','verified','Test result',observed,assignment_id=a)
        self.assign('review')
        retry=self.store.ingest('goal','event','assistant','testing','verified','Test result',observed,assignment_id=a)
        self.assertTrue(retry['duplicate']);self.assertEqual(first['activity_id'],retry['activity_id'])
        with self.assertRaises(ValueError):self.store.ingest('goal','event','assistant','testing','verified','Changed',observed,assignment_id=a)
        row=self.store.collaboration_timeline('goal')['rows'][0]
        self.assertTrue(row['attribution']['actor_short_id'])
    def test_explicit_assignment_after_legacy_snapshot(self):
        a=self.assign()
        with self.store.connect() as db:db.execute('DELETE FROM assignment_episodes')
        self.store=Store(self.store.directory)
        legacy=self.store.snapshot()['assignment_episodes'][0]['id']
        current=self.assign()
        self.assertNotEqual(legacy,current)
        self.assertEqual(len(self.store.snapshot()['assignment_episodes']),2)
        self.progress(current)

    def test_native_readonly_and_attributed_log(self):
        from dots_panel.desktop_view import ReadOnlyStore
        a=self.assign();self.store.update(self.run,message='Measured result',assignment_id=a)
        reader=ReadOnlyStore(self.store.directory)
        result=reader.collaboration_timeline('goal',agent_id='a')
        self.assertEqual(result['total'],1)
        self.assertEqual(result['rows'][0]['kind'],'event')
        self.assertEqual(result['rows'][0]['attribution']['work_type'],'development')
        self.store.assignment_end(a,'Observed role finished')
        with self.assertRaises(ValueError):self.store.update(self.run,message='New result',assignment_id=a)
    def test_failed_structure_does_not_mutate(self):
        self.store.register('p','Project','Fixture',activity_kind='project')
        self.store.activity_structure('goal',parent_task_id='p',reason='Child')
        with self.assertRaises(ValueError):self.store.activity_structure('goal',parent_task_id='missing',reason='Bad')
        row=next(t for t in self.store.snapshot()['tasks'] if t['id']=='goal')
        self.assertEqual(row['parent_task_id'],'p')

    def test_immutable_db_role(self):
        a=self.assign()
        import sqlite3
        with self.store.connect() as db:
            with self.assertRaises(sqlite3.IntegrityError):db.execute("UPDATE assignment_episodes SET work_type='review' WHERE id=?",(a,))

if __name__=='__main__':unittest.main()
