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
        self.assertEqual([r['id'] for r in task_rows(s,10000)],['recent','tie','done','older'])
    def test_order_independent_and_no_mutation(self):
        s=self.state();before=list(s['tasks']);first=[r['id'] for r in task_rows(s,10000)];self.assertEqual(s['tasks'],before)
        s['tasks'].reverse();self.assertEqual([r['id'] for r in task_rows(s,10000)],first)

    def test_running_first_then_waiting_then_terminal_with_web_parity(self):
        import json, shutil, subprocess
        statuses=['waiting_user','failed','pending','running','paused','succeeded','waiting_external','awaiting_review','cancelled']
        s={'tasks':[],'runs':[],'activity':[]}
        for index,status in enumerate(statuses):
            key='item-'+str(index)
            s['tasks'].append({'id':key,'name':key,'project':'fixture','created':1})
            s['runs'].append({'id':'run-'+key,'task_id':key,'status':status,'started':1,'updated':100000,'finished':None})
            s['activity'].append({'task_id':key,'created':10 if status=='running' else 1000+index,'stage':'progress'})
        s['tasks'].append({'id':'running-new','name':'Running new','project':'fixture','created':1})
        s['runs'].append({'id':'run-new','task_id':'running-new','status':'running','started':1,'updated':1,'finished':None})
        s['activity'].append({'task_id':'running-new','created':20,'stage':'testing'})
        before=json.dumps(s)
        rows=task_rows(s,200000)
        self.assertEqual([row['id'] for row in rows[:2]],['running-new','item-3'])
        self.assertTrue(all(row['status'] in {'waiting_user','waiting_external','awaiting_review','pending','paused'} for row in rows[2:7]))
        self.assertTrue(all(row['status'] in {'succeeded','cancelled','failed'} for row in rows[7:]))
        self.assertEqual(json.dumps(s),before)
        if shutil.which('node'):
            result=subprocess.check_output(['node','-e',"require('./web/workspace.js'); const fs=require('fs');const s=JSON.parse(fs.readFileSync(0,'utf8'));process.stdout.write(JSON.stringify(PanelWorkspace.rows(s.tasks,s.runs,'all','',s).map(row=>row.task.id)));"],input=json.dumps(s),text=True)
            self.assertEqual(json.loads(result),[row['id'] for row in rows])
