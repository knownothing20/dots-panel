from closeout_fixture import prepare_success
"""Needs-attention is derived, read-only and limited to actual recorded lifecycle."""
import tempfile
import time
import unittest
from dots_panel.app import Store, attention_items, attention_draft
from dots_panel.desktop_view import Dashboard, task_rows


class AttentionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)

    def task(self, key, status):
        self.store.register(key, 'Task '+key, 'Example')
        run = self.store.start(key)
        if status == 'succeeded': prepare_success(self.store, run)
        if status != 'running': self.store.transition(run, status, 'Actual reason '+key, 'Synthetic evidence', 'Next step '+key)
        return run

    def test_empty_no_fabricated_questions(self):
        self.assertEqual(attention_items(self.store.snapshot()), {'action_required': [], 'external': []})
        self.task('running', 'running')
        self.assertEqual(attention_items(self.store.snapshot())['action_required'], [])

    def test_groups_preserve_reason_and_next_step(self):
        for status in ('waiting_user','paused','awaiting_review','waiting_external','succeeded'):
            self.task(status, status)
        queue = attention_items(self.store.snapshot())
        self.assertEqual({r['run']['status'] for r in queue['action_required']}, {'waiting_user','paused','awaiting_review'})
        self.assertEqual(len(queue['external']), 1)
        for item in queue['action_required'] + queue['external']:
            self.assertEqual(item['run']['lifecycle_reason'], 'Actual reason '+item['task']['id'])
            self.assertEqual(item['run']['next_step'], 'Next step '+item['task']['id'])

    def test_latest_only_and_terminal_clears_queue(self):
        self.task('one', 'waiting_user')
        newest = self.store.start('one')
        self.assertEqual(attention_items(self.store.snapshot())['action_required'], [])
        self.store.transition(newest, 'awaiting_review', 'Ready', 'Evidence', 'Review')
        self.assertEqual(len(attention_items(self.store.snapshot())['action_required']), 1)
        prepare_success(self.store, newest)
        self.store.transition(newest, 'succeeded', 'Accepted', 'Review evidence')
        self.assertEqual(attention_items(self.store.snapshot())['action_required'], [])

    def test_duplicates_and_equal_timestamps_are_stable(self):
        task = {'id':'one','name':'One'}
        state = {'tasks':[task,task], 'runs':[
            {'id':'a','task_id':'one','started':1,'status':'waiting_user'},
            {'id':'z','task_id':'one','started':1,'status':'paused'},
            {'id':'z','task_id':'one','started':1,'status':'paused'}]}
        queue = attention_items(state)
        self.assertEqual(len(queue['action_required']), 1)
        self.assertEqual(queue['action_required'][0]['run']['id'], 'z')

    def test_latest_wait_survives_history_limit(self):
        waiting = self.task('waiting', 'waiting_user')
        self.store.register('busy', 'Busy', 'Example')
        for _ in range(105): self.store.start('busy')
        snapshot = self.store.snapshot()
        self.assertEqual(len(snapshot['runs']), 100)
        self.assertNotIn(waiting, {r['id'] for r in snapshot['runs']})
        self.assertEqual(attention_items(snapshot)['action_required'][0]['run']['id'], waiting)
        row = next(r for r in task_rows(snapshot, time.time()) if r['id']=='waiting')
        self.assertEqual(row['run']['lifecycle_reason'], 'Actual reason waiting')

    def test_queue_reads_never_modify_state(self):
        self.task('one', 'paused')
        before = self.store.snapshot()
        for _ in range(3): attention_items(before)
        after = self.store.snapshot()
        for field in ('tasks','runs','latest_runs','events','activity'):
            self.assertEqual(before[field], after[field])

    def test_copyable_draft_requires_user_input(self):
        task = {'id':'one','name':'<script>literal</script>'}
        run = {'lifecycle_reason':'A decision is needed','next_step':'Select scope'}
        for language in ('zh','en'):
            draft = attention_draft(task, run, language)
            self.assertIn(task['name'], draft)
            self.assertIn(run['lifecycle_reason'], draft)
            self.assertIn(run['next_step'], draft)
        self.assertIn('[please fill in]', attention_draft(task, run, 'en'))
        self.assertIn('[请填写]', attention_draft(task, run, 'zh'))

    def test_native_open_suggestion_and_back_flow(self):
        panel = Dashboard.__new__(Dashboard)
        rendered = []
        panel.render_page = lambda: rendered.append((panel.page, panel.selected_task))
        panel.open_task('one', advice=True)
        self.assertTrue(panel.show_attention_advice)
        self.assertEqual(rendered[-1], ('conversations','one'))
        panel.go_back()
        self.assertEqual(rendered[-1], ('conversations',None))
        panel.open_task('two')
        self.assertFalse(panel.show_attention_advice)
