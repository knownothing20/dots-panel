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


class NativeAgentDirectoryTests(unittest.TestCase):
    def viewer(self):
        view=Dashboard.__new__(Dashboard);view.language='en';view.timezone='UTC';view.muted='gray';view.fg='black';view.bg='white';view.tk=Mock();view.root=Mock()
        view.scroll_area=Mock();view.label=Mock();view.card_grid=Mock();view.compact_row=Mock();view.filter_chip=Mock();view.render_page=Mock();view.t=lambda x:x
        view.snapshot=fixture();view.snapshot['agents'][0]['observed_at']=time.time();view.selected_agent=None
        return view

    def test_history_hidden_filters_compact_cards_and_detail_evidence(self):
        view=self.viewer();historical=copy.deepcopy(view.snapshot['agents'][0]);historical.update(id='old',name='History',identity_source='historical',identity_verification='historical')
        view.snapshot['agents'].append(historical);view.render_agents()
        self.assertEqual(view.compact_row.call_count,1)
        summary=view.compact_row.call_args.args[2]
        self.assertIn('Meaningful task',summary);self.assertNotIn('Identity checked',summary);self.assertNotIn('Status observed',summary)
        view.toggle_agent_history();view.compact_row.reset_mock();view.render_agents();self.assertEqual(view.compact_row.call_count,2)
        view.set_agent_filter('running');view.compact_row.reset_mock();view.render_agents();self.assertEqual(view.compact_row.call_count,2)
        view.selected_agent='one';view.compact_row.reset_mock();view.render_agents();details=view.compact_row.call_args_list[0].args[2]
        self.assertIn('Identity checked at',details);self.assertIn('Status observed at',details)

    def test_unverified_identity_has_separate_closed_disclosure(self):
        view=self.viewer();unknown=copy.deepcopy(view.snapshot['agents'][0]);unknown.update(id='unknown',name='Unverified example',identity_verification='unknown')
        view.snapshot['agents'].append(unknown);view.agent_count_help_open=True;view.render_agents()
        self.assertEqual(view.compact_row.call_count,1)
        labels=[call.args[1] for call in view.filter_chip.call_args_list]
        self.assertIn('1  Verified agents',labels);self.assertIn('0  State unconfirmed',labels)
        self.assertTrue(any('Unverified identities · 1' in text for text in labels))
        view.toggle_agent_unknown();view.compact_row.reset_mock();view.render_agents()
        self.assertEqual(view.compact_row.call_count,2)
        self.assertEqual(view.compact_row.call_args.args[3],'Unverified identities')

    def test_standby_expiration_changes_refresh_signature(self):
        view=self.viewer();view.page='agents';view.selected_task=None;view.workspace_filter='all';view.search_query=Mock();view.search_query.get.return_value=''
        view.snapshot=fixture('idle')
        with patch('dots_panel.desktop_view.time.time',return_value=110):before=view.view_signature()
        with patch('dots_panel.desktop_view.time.time',return_value=300):after=view.view_signature()
        self.assertNotEqual(before,after)

    def test_agent_details_have_their_own_scroll_identity(self):
        view=self.viewer();view.page='agents';view.selected_task=None;view.selected_agent=None
        self.assertEqual(view.viewport_key(),('agents',None))
        view.selected_agent='one';self.assertEqual(view.viewport_key(),('agents','one'))
        view.page='conversations';view.selected_task='task';self.assertEqual(view.viewport_key(),('conversations','task'))


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
