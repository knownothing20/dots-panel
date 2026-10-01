"""Accurate cumulative counts, conservative working state and compact native UI."""
import copy
import json
import subprocess
import shutil
import time
import unittest
from unittest.mock import Mock,patch
from dots_panel.agent_directory import agent_directory, directory_work_label
from dots_panel.desktop_view import Dashboard


def fixture(status='running'):
    return {'agents':[{'id':'one','name':'Example','status':status,'observed_at':100,'identity_verification':'observed','identity_source':'manual','identity_observed_at':90,'identity_evidence':'Verified synthetic executor match'}],
            'tasks':[{'id':'task','name':'Meaningful task'}],
            'runs':[{'id':'run','task_id':'task','status':'running','started':70}],
            'agent_run_assignments':[{'run_id':'run','agent_id':'one','assigned_at':80,'work_type':'development'}],
            'stale_after_seconds':120}


class AgentDirectoryTests(unittest.TestCase):
    def test_fresh_working_and_expiration_keep_recent_task(self):
        s=fixture();before=copy.deepcopy(s)
        self.assertEqual(agent_directory(s,220)['counts']['running'],1)
        row=agent_directory(s,220.01)['rows'][0]
        self.assertEqual(row['state'],'unconfirmed');self.assertIn('Recent task · Meaningful task',directory_work_label(row,'en'))
        self.assertEqual(s,before)

    def test_identity_evidence_is_required(self):
        for update in ({'identity_evidence':''},{'identity_verification':'unknown'},{'identity_source':'unknown'},{'identity_observed_at':None},{'identity_observed_at':121}):
            s=fixture();s['agents'][0].update(update)
            result=agent_directory(s,120)
            self.assertEqual(result['counts']['running'],0)
            self.assertEqual(result['counts']['all'],0)
            self.assertEqual(result['counts']['profiles'],1)
            self.assertEqual(result['counts']['unconfirmed'],0)
            self.assertEqual(result['counts']['unverified'],1)
            self.assertFalse(result['rows'][0]['verified'])
            self.assertEqual(result['rows'][0]['reason'],'identity')

    def test_recent_standby_never_completes_its_task(self):
        s=fixture('idle');self.assertEqual(agent_directory(s,110)['counts']['idle'],1)
        self.assertEqual(s['runs'][0]['status'],'running')
        self.assertEqual(agent_directory(s,230)['counts']['idle'],0)
        self.assertEqual(agent_directory(s,230)['counts']['unconfirmed'],1)

    def test_history_and_duplicate_ids_count_once(self):
        s=fixture();s['agents'][0]['identity_verification']='historical';s['agents'].append(copy.deepcopy(s['agents'][0]))
        result=agent_directory(s,110)
        self.assertEqual(result['counts']['all'],0);self.assertEqual(result['counts']['profiles'],1);self.assertEqual(result['counts']['historical'],1)
        self.assertEqual(result['counts']['unconfirmed'],0);self.assertEqual(result['counts']['running'],0)

    def test_missing_refs_old_observation_and_terminal_newest_do_not_work(self):
        mutations=[lambda s:s['runs'].clear(),lambda s:s['tasks'].clear(),lambda s:s['agent_run_assignments'].clear(),
                   lambda s:s['agent_run_assignments'][0].update(assigned_at=105),lambda s:s['runs'][0].update(status='succeeded')]
        for mutate in mutations:
            s=fixture();mutate(s);self.assertEqual(agent_directory(s,110)['counts']['running'],0)
        s=fixture();s['runs'].append({'id':'finished','task_id':'task','status':'succeeded','started':90})
        s['agent_run_assignments'].append({'run_id':'finished','agent_id':'one','assigned_at':95})
        row=agent_directory(s,110)['rows'][0]
        self.assertEqual(row['reason'],'terminal');self.assertEqual(row['work'][0]['run_id'],'finished')

    def test_tied_topics_are_ambiguous_and_primary_is_not_proof(self):
        s=fixture();s['tasks'].append({'id':'other','name':'Other task'});s['runs'].append({'id':'other-run','task_id':'other','status':'running','started':70})
        s['agent_run_assignments'].append({'run_id':'other-run','agent_id':'one','assigned_at':80})
        self.assertEqual(agent_directory(s,110)['rows'][0]['reason'],'conflict')
        s=fixture();s['agent_run_assignments']=[];s['agent_assignments']=[{'task_id':'task','agent_id':'one','assigned_at':10}]
        row=agent_directory(s,110)['rows'][0]
        self.assertEqual(row['state'],'unconfirmed');self.assertIn('Linked task',directory_work_label(row,'en'))

    def test_terminal_and_open_tie_keeps_open_run_for_current_work(self):
        s=fixture();s['runs'].append({'id':'closed','task_id':'task','status':'succeeded','started':90})
        s['agent_run_assignments'].insert(0,{'run_id':'closed','agent_id':'one','assigned_at':80})
        row=agent_directory(s,110)['rows'][0]
        self.assertEqual(row['state'],'running');self.assertEqual(row['work'][0]['run_id'],'run')

    def test_every_open_lifecycle_is_an_association_not_an_execution_signal(self):
        for status in ('running','waiting_user','waiting_external','awaiting_review'):
            s=fixture();s['runs'][0]['status']=status
            self.assertEqual(agent_directory(s,110)['counts']['running'],1)
            s['agents'][0]['status']='unknown'
            self.assertEqual(agent_directory(s,110)['counts']['running'],0)

    def test_invalid_status_times_cannot_inflate_counts(self):
        paused=fixture();paused['runs'][0]['status']='paused';self.assertEqual(agent_directory(paused,110)['rows'][0]['reason'],'paused')
        for value in (None,True,'100',float('nan'),float('inf'),200):
            s=fixture();s['agents'][0]['observed_at']=value
            self.assertEqual(agent_directory(s,110)['counts']['running'],0)

    def test_counts_partition_profiles_and_keep_known_blocked_states(self):
        s=fixture();s['agents']=[]
        for i,status in enumerate(('running','idle','blocked','unavailable','unknown')):
            a=fixture(status)['agents'][0];a['id']='p'+str(i);s['agents'].append(a)
            s['agent_run_assignments'].append({'run_id':'run','agent_id':a['id'],'assigned_at':80})
        counts=agent_directory(s,110)['counts']
        self.assertEqual(counts['all'],5);self.assertEqual(sum(counts[k] for k in ('running','idle','blocked','unavailable','unconfirmed')),5)
        self.assertEqual(counts['blocked'],1);self.assertEqual(counts['unavailable'],1)

    @unittest.skipUnless(shutil.which("node"), "Optional JavaScript parity check requires Node")
    def test_python_web_model_parity(self):
        scenarios=[]
        for status in ('running','idle','unknown','blocked','unavailable'):
            for now in (110,220,221):scenarios.append({'snapshot':fixture(status),'now':now})
        h=fixture();h['agents'][0]['identity_source']='historical';scenarios.append({'snapshot':h,'now':110})
        h=fixture();h['runs'][0]['status']='succeeded';scenarios.append({'snapshot':h,'now':110})
        output=subprocess.check_output(['node','-e',"require('./web/workspace.js');let input='';process.stdin.on('data',x=>input+=x);process.stdin.on('end',()=>console.log(JSON.stringify(JSON.parse(input).map(s=>PanelAgents.directory(s.snapshot,s.now)))));"],input=json.dumps(scenarios).encode())
        self.assertEqual(json.loads(output),[agent_directory(s['snapshot'],s['now']) for s in scenarios])


class ActivityParticipantViewTests(unittest.TestCase):
    def test_agent_page_and_shortcut_target_removed(self):
        from dots_panel.desktop_view import PAGE_NAMES
        self.assertNotIn('agents',PAGE_NAMES);self.assertEqual(len(PAGE_NAMES),7)
        self.assertFalse(hasattr(Dashboard,'render_agents'))

class UnfinishedRunSummaryTests(unittest.TestCase):
    def test_paused_history_is_retained_but_not_counted_as_parallel(self):
        from dots_panel.progress import task_progress
        state={'tasks':[{'id':'task','name':'Synthetic scheduled result'}],'runs':[
            {'id':'old','task_id':'task','status':'paused','started':1,'note':'Historical record'},
            {'id':'new','task_id':'task','status':'waiting_external','started':2,'note':'Old initial instruction','next_step':'Wait for the first actual result'}]}
        before=copy.deepcopy(state);result=task_progress(state,'task',10)
        self.assertEqual(result['current_run_id'],'new');self.assertEqual(len(result['open_runs']),2)
        self.assertEqual(len(result['unpaused_runs']),1)
        self.assertEqual(result['current_step'],'Wait for the first actual result')
        self.assertEqual(state,before)
