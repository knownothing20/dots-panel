import http.client
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
from dots_panel.app import Store, Metrics, ROOT, make_server


class PanelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_connection_closes_after_commit_and_rollback(self):
        with self.store.connect() as db:
            db.execute("INSERT INTO tasks(id,name,project,created) VALUES('saved','Example','Demo',0)")
        with self.assertRaises(sqlite3.ProgrammingError): db.execute('SELECT 1')
        self.assertEqual(self.store.snapshot()['tasks'][0]['id'], 'saved')
        with self.assertRaises(RuntimeError):
            with self.store.connect() as failed:
                failed.execute("INSERT INTO tasks(id,name,project,created) VALUES('rolled-back','Example','Demo',0)")
                raise RuntimeError('Expected transaction failure')
        with self.assertRaises(sqlite3.ProgrammingError): failed.execute('SELECT 1')
        self.assertEqual(len(self.store.snapshot()['tasks']), 1)

    def test_repeated_snapshots_close_every_connection(self):
        original = sqlite3.connect
        connections = []
        def record(*args, **kwargs):
            connection = original(*args, **kwargs)
            connections.append(connection)
            return connection
        with patch('dots_panel.app.sqlite3.connect', side_effect=record):
            for _ in range(50): self.store.snapshot()
        self.assertEqual(len(connections), 100)  # Snapshot plus read-only doctor connection per poll
        for connection in connections:
            with self.assertRaises(sqlite3.ProgrammingError): connection.execute('SELECT 1')

    def test_lifecycle_and_private_activity(self):
        self.store.register('sample', '测试任务', '公开示例')
        run = self.store.start('sample')
        self.store.update(run, message='测试已开始')
        self.store.update(run)
        record = self.store.closeout_record(run, 'Verified test output', 'Unit test fixture', 'passed', 'Assertions passed', 'Synthetic fixture only', no_artifact_reason='No deliverable file in this unit test')
        self.store.closeout(run, record['record_id'])
        self.store.activity('公开示例', 'assistant', 'testing', '测试完成')
        state = self.store.snapshot()
        self.assertEqual(state['runs'][0]['status'], 'succeeded')
        self.assertIn('测试已开始', [event['message'] for event in state['events']])
        self.assertEqual(state['activity'][0]['message'], '测试完成')
        with self.assertRaises(ValueError): self.store.update(run)

    def test_no_implicit_tasks(self):
        state = self.store.snapshot()
        self.assertEqual(state['tasks'], [])
        self.assertEqual(state['activity'], [])
        with self.assertRaises(sqlite3.IntegrityError): self.store.start('unknown')

    def test_stale_is_not_failure(self):
        self.store.register('sample', 'Task', 'Example')
        run = self.store.start('sample')
        with self.store.connect() as db: db.execute('UPDATE runs SET updated=0 WHERE id=?', (run,))
        row = self.store.snapshot()['runs'][0]
        self.assertTrue(row['stale'])
        self.assertEqual(row['status'], 'running')

    def test_runtime_separation_and_input_limits(self):
        with self.assertRaises(ValueError): Store(ROOT / 'runtime')
        for key in ('../bad', 'UPPER', ''):
            with self.assertRaises(ValueError): self.store.register(key, 'Task', 'Example')
        with self.assertRaises(ValueError): self.store.register('ok', 'x' * 121, 'Example')
        with self.assertRaises(ValueError): self.store.activity('Example', 'invalid', 'test', 'message')

    def test_runtime_permissions_and_symlinks(self):
        self.assertEqual(self.store.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.store.directory / 'db').stat().st_mode & 0o777, 0o700)
        with tempfile.TemporaryDirectory() as temp:
            insecure = Path(temp) / 'insecure'
            insecure.mkdir(mode=0o755)
            with self.assertRaises(ValueError): Store(insecure)
            link = Path(temp) / 'linked'
            link.symlink_to(self.store.directory)
            with self.assertRaises(ValueError): Store(link)
            valid = Store(Path(temp) / 'valid')
            valid.path.chmod(0o644)
            with self.assertRaises(ValueError): Store(valid.directory)

    def test_task_stage_association(self):
        self.store.register('sample', 'Task', 'Example')
        self.store.activity('Example', 'assistant', 'testing', 'Checked', 'sample', 'verified')
        event = self.store.snapshot()['activity'][0]
        self.assertEqual(event['task_id'], 'sample')
        self.assertEqual(event['state'], 'verified')
        with self.assertRaises(ValueError): self.store.activity('Example','assistant','testing','Checked','missing')
        with self.assertRaises(ValueError): self.store.activity('Example','assistant','testing','Checked',state='guess')

    def test_schedule_registry_never_claims_live_scheduler(self):
        self.store.schedule_register('example', 'Example schedule', 'Example')
        item = self.store.snapshot()['schedules'][0]
        self.assertEqual(item['state'], 'disconnected')
        self.assertIsNone(item['next_run'])
        with self.assertRaises(ValueError): self.store.schedule_register('bad', 'Task', 'Example', state='running')
        with self.assertRaises(ValueError): self.store.schedule_register('bad', 'Task', 'Example', next_run=float('nan'))

    def test_software_allowlist_and_detection(self):
        self.store.software_register('panel', 'Panel', 'Local dashboard', 'dots-panel')
        item = self.store.snapshot()['software'][0]
        self.assertTrue(item['available'])
        self.assertIsNone(item['running'])
        self.assertEqual(item['controls'], ['close_current_viewer'])
        self.assertNotIn('path', item)
        with self.assertRaises(ValueError): self.store.software_register('bad','App','Unknown','shell')
        with self.assertRaises(ValueError): self.store.software_register('bad','App','Unknown','python -c code')

    def test_manual_updates_are_not_heartbeats(self):
        self.store.register('manual', 'Task', 'Example')
        run = self.store.start('manual')
        with self.store.connect() as db: db.execute('UPDATE runs SET updated=0 WHERE id=?', (run,))
        old = self.store.snapshot()['runs'][0]
        self.assertTrue(old['stale'])
        self.assertEqual(old['tracking_mode'], 'manual')
        self.store.activity('Example', 'assistant', 'implementation', 'Actual progress', 'manual')
        self.assertFalse(self.store.snapshot()['runs'][0]['stale'])
        self.store.register('managed', 'Task', 'Example', tracking_mode='heartbeat')
        managed = self.store.start('managed')
        with self.store.connect() as db: db.execute('UPDATE runs SET updated=0 WHERE id=?', (managed,))
        self.store.activity('Example', 'assistant', 'implementation', 'Summary only', 'managed')
        row = next(row for row in self.store.snapshot()['runs'] if row['id'] == managed)
        self.assertTrue(row['stale'])
        self.assertEqual(row['progress_updated'], 0)

    def test_legacy_tasks_migrate_to_manual(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / 'db').mkdir(mode=0o700)
            path = directory / 'db/panel.sqlite3'
            with closing(sqlite3.connect(path)) as db:
                db.execute('CREATE TABLE tasks(id TEXT PRIMARY KEY,name TEXT,project TEXT,created REAL)')
                db.execute("INSERT INTO tasks VALUES('old','Example','Demo',0)")
                db.commit()
            path.chmod(0o600)
            migrated = Store(directory).snapshot()
            self.assertEqual(migrated['tasks'][0]['tracking_mode'], 'manual')
            self.assertEqual(migrated['schedules'], [])
            self.assertEqual(migrated['software'], [])

    def test_lifecycle_survives_recent_run_window(self):
        self.store.register('older', 'Older task', 'Example')
        self.store.register('busy', 'Other task', 'Example')
        older = self.store.start('older')
        record = self.store.closeout_record(older, 'Verified test output', 'Unit test fixture', 'passed', 'Assertions passed', 'Synthetic fixture only', no_artifact_reason='No deliverable file in this unit test')
        self.store.closeout(older, record['record_id'])
        with self.store.connect() as db:
            created = db.execute('SELECT started FROM runs WHERE id=?', (older,)).fetchone()[0]
            for index in range(101):
                db.execute("INSERT INTO runs(id,task_id,status,started,updated,finished,note) VALUES(?,?,?,?,?,?,?)", (f'example-{index}', 'busy', 'succeeded', created+index+1, created+index+1, created+index+1, ''))
        snapshot = self.store.snapshot()
        self.assertFalse(any(run['id'] == older for run in snapshot['runs']))
        task = next(task for task in snapshot['tasks'] if task['id'] == 'older')
        self.assertEqual(task['latest_status'], 'succeeded')

    def test_seven_web_pages(self):
        from html.parser import HTMLParser
        class Pages(HTMLParser):
            def __init__(self): super().__init__(); self.pages=[]; self.nav=[]
            def handle_starttag(self, tag, attrs):
                attrs=dict(attrs)
                if 'data-page' in attrs: self.pages.append(attrs['data-page'])
                if 'data-nav' in attrs: self.nav.append(attrs['data-nav'])
        parser=Pages()
        parser.feed((ROOT / 'web/index.html').read_text())
        self.assertEqual(set(parser.pages), {'overview','conversations','agents','schedules','software','rules','about'})
        self.assertEqual(len(parser.pages), 7)
        self.assertEqual(parser.nav, parser.pages)

    def test_web_markup_is_balanced_and_ids_unique(self):
        from html.parser import HTMLParser
        class Markup(HTMLParser):
            voids = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
            def __init__(self): super().__init__(); self.stack=[]; self.ids=[]; self.errors=[]
            def handle_starttag(self, tag, attrs):
                attributes=dict(attrs)
                if 'id' in attributes:self.ids.append(attributes['id'])
                if tag not in self.voids:self.stack.append(tag)
            def handle_endtag(self, tag):
                if not self.stack or self.stack[-1]!=tag:self.errors.append(tag)
                else:self.stack.pop()
        parser=Markup();parser.feed((ROOT / 'web/index.html').read_text())
        self.assertEqual(parser.errors, [])
        self.assertEqual(parser.stack, [])
        self.assertEqual(len(parser.ids),len(set(parser.ids)))
        self.assertIn('workspace-search',parser.ids)
        self.assertIn('workspace-tabs',parser.ids)

    def test_metrics_minimal_identity(self):
        state = Metrics(self.temp.name).collect()
        self.assertNotIn('hostname', state)
        self.assertNotIn('username', state)
        self.assertNotIn('path', state)
        self.assertGreater(state['disk_total'], 0)
        with patch('dots_panel.app.read', return_value=None):
            unavailable = Metrics(self.temp.name).collect()
            self.assertIsNone(unavailable['memory_total'])
            self.assertIsNone(unavailable['cpu_quota_cores'])

    def test_http_boundaries(self):
        server = make_server(self.store, 0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            def request(method, path, headers=None):
                conn = http.client.HTTPConnection('127.0.0.1', server.server_port)
                conn.request(method, path, headers=headers or {})
                response = conn.getresponse()
                result = response.status, dict(response.getheaders()), response.read()
                conn.close()
                return result
            self.assertEqual(server.server_address[0], '127.0.0.1')
            code, headers, data = request('GET', '/api/state')
            self.assertEqual(code, 200)
            self.assertEqual(json.loads(data)['tasks'], [])
            self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
            self.assertNotIn('Access-Control-Allow-Origin', headers)
            self.assertEqual(request('GET', '/../../etc/passwd')[0], 404)
            self.assertEqual(request('GET', '/api/state', {'Host':'evil.example'})[0], 403)
            self.assertEqual(request('GET', '/', {'Sec-Fetch-Site':'cross-site'})[0], 403)
            self.assertEqual(request('POST', '/api/state')[0], 405)
            self.assertEqual(request('GET', '/')[0], 200)
            self.assertEqual(request('GET', '/app.js')[0], 200)
        finally:
            server.shutdown(); server.server_close(); worker.join()


if __name__ == '__main__': unittest.main()
