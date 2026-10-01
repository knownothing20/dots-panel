import unittest
from dots_panel.desktop_view import task_rows
class ActivityOrderTests(unittest.TestCase):
    def state(self):
        tasks=[{'id':i,'name':i,'project':'x','created':1} for i in ('done','older','recent','tie')]
        runs=[dict(id=i,task_id=i,status='succeeded' if i=='done' else 'running',started=5,updated=9999,finished=1000 if i=='done' else None) for i in ('done','older','recent','tie')]
        return dict(tasks=tasks,runs=runs,activity=[dict(task_id='recent',created=20,stage='testing'),dict(task_id='tie',created=20,stage='testing'),dict(task_id='older',created=9000,stage='heartbeat')])
    def test_unfinished_first_meaningful_ties(self):
        self.assertEqual([r['id'] for r in task_rows(self.state(),10000)],['recent','tie','older','done'])
    def test_parallel_finished_does_not_hide_open(self):
        s=self.state();s['runs'].append(dict(id='backup',task_id='older',status='succeeded',started=30,finished=40,updated=40))
        rows=task_rows(s,10000);self.assertEqual(rows[0]['id'],'older');self.assertEqual(rows[0]['status'],'running')
    def test_terminal_failed_stays_terminal(self):
        s=self.state();s['runs'][1]['status']='failed'
        self.assertEqual([r['id'] for r in task_rows(s,10000)],['recent','tie','older','done'])
    def test_order_independent_and_no_mutation(self):
        s=self.state();before=list(s['tasks']);first=[r['id'] for r in task_rows(s,10000)];self.assertEqual(s['tasks'],before)
        s['tasks'].reverse();self.assertEqual([r['id'] for r in task_rows(s,10000)],first)
