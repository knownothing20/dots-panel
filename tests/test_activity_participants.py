import copy
import unittest
from unittest.mock import Mock,patch
from dots_panel.participants import activity_participants
from dots_panel.agent_identity import profile_short_ids
from dots_panel.desktop_view import Dashboard

class ParticipantTests(unittest.TestCase):
    def fixture(self):
        return {'agents':[{'id':'p'+str(i),'name':'Person '+str(i),'portrait':'leaf-sky'} for i in range(6)],'runs':[{'id':'r','task_id':'goal','status':'running','started':20},{'id':'old','task_id':'goal','status':'succeeded','started':1},{'id':'other','task_id':'elsewhere','status':'running','started':30}], 'agent_run_assignments':[{'run_id':'r','agent_id':'p'+str(i),'work_type':'development','assigned_at':i} for i in range(5)]+[{'run_id':'old','agent_id':'p0','work_type':'review','assigned_at':0},{'run_id':'other','agent_id':'p5','work_type':'research','assigned_at':10}]}
    def test_related_profiles_deduplicate_across_runs_and_preserve_role_records(self):
        s=self.fixture();before=copy.deepcopy(s);rows=activity_participants(s,'goal')
        self.assertEqual(len(rows),5);self.assertNotIn('p5',[r['agent']['id'] for r in rows]);self.assertEqual(len(next(r for r in rows if r['agent']['id']=='p0')['assignments']),1);self.assertEqual(s,before)
    def test_no_selected_run_never_recovers_old_joined_assignments(self):
        s=self.fixture();s['runs']=[];s['agent_run_assignments']=[{'run_id':'outside-window','task_id':'goal','agent_id':'p0','work_type':'writing'},{'run_id':'missing','task_id':'goal','agent_id':'unknown'}]
        self.assertEqual(activity_participants(s,'goal'),[])
    def test_parallel_open_runs_never_merge_rosters(self):
        s=self.fixture();s['runs'].append({'id':'new','task_id':'goal','status':'waiting_external','started':30})
        s['agent_run_assignments'].append({'run_id':'new','agent_id':'p5','work_type':'research','assigned_at':30})
        rows=activity_participants(s,'goal',100)
        self.assertEqual([r['agent']['id'] for r in rows],['p5']);self.assertEqual(rows[0]['assignments'][0]['run_id'],'new')
    def test_primary_owner_does_not_fill_an_unassigned_current_run(self):
        s=self.fixture();s['agent_run_assignments']=[];s['agent_assignments']=[{'task_id':'goal','agent_id':'p0','assigned_at':1}]
        self.assertEqual(activity_participants(s,'goal',100),[])
    def test_paused_or_terminal_selection_has_no_current_roster(self):
        for status in ('paused','succeeded','failed','cancelled'):
            s=self.fixture();s['runs']=[{**s['runs'][0],'status':status}]
            self.assertEqual(activity_participants(s,'goal',100),[])
    def test_ended_episodes_remain_history_and_latest_open_role_wins(self):
        s=self.fixture();before=copy.deepcopy(s)
        s['assignment_episodes']=[{'id':'closed','run_id':'r','agent_id':'p0','work_type':'review','assigned_at':1,'ended_at':10},
            {'id':'prior-role','run_id':'r','agent_id':'p1','work_type':'writing','assigned_at':1,'ended_at':10},
            {'id':'active-role','run_id':'r','agent_id':'p1','work_type':'editing','assigned_at':10,'ended_at':None}]
        unchanged=copy.deepcopy(s);rows=activity_participants(s,'goal',100)
        self.assertNotIn('p0',[r['agent']['id'] for r in rows]);self.assertEqual(next(r for r in rows if r['agent']['id']=='p1')['assignments'][0]['work_type'],'editing');self.assertEqual(s,unchanged)
        self.assertEqual(len(s['agent_run_assignments']),len(before['agent_run_assignments']))
    def test_current_projection_is_valid_without_history_window(self):
        s=self.fixture();s['current_runs']=[s['runs'][0]];s['runs']=[]
        self.assertEqual(len(activity_participants(s,'goal',100)),5)
    def test_invalid_future_or_wrong_task_associations_are_excluded(self):
        for values in ({'assigned_at':None},{'assigned_at':True},{'assigned_at':101},{'task_id':'another-task'}):
            s=self.fixture();s['agent_run_assignments']=[{**s['agent_run_assignments'][0],**values}]
            self.assertEqual(activity_participants(s,'goal',100),[])
    def test_duplicate_link_deduplicates_full_profile_key(self):
        s=self.fixture();s['agent_run_assignments'].append({**s['agent_run_assignments'][0],'assigned_at':25,'work_type':'review'})
        rows=activity_participants(s,'goal',100);self.assertEqual(len(rows),5)
        self.assertEqual(next(r for r in rows if r['agent']['id']=='p0')['assignments'][0]['work_type'],'review')
    def test_python_and_web_current_roster_parity(self):
        import json,shutil,subprocess
        if not shutil.which('node'):self.skipTest('Node is optional')
        scenarios=[]
        for status in ('running','waiting_external','paused','succeeded'):
            s=self.fixture();s['runs']=[{**s['runs'][0],'status':status}];scenarios.append(s)
        s=self.fixture();s['assignment_episodes']=[{'id':'end','run_id':'r','agent_id':'p0','assigned_at':1,'ended_at':10}];scenarios.append(s)
        result=subprocess.check_output(['node','-e',"require('./web/workspace.js');let s='';process.stdin.on('data',x=>s+=x);process.stdin.on('end',()=>console.log(JSON.stringify(JSON.parse(s).map(x=>PanelAgents.activityParticipants(x,'goal',100)))));"],input=json.dumps(scenarios).encode())
        expected=[[{k:v for k,v in row.items() if k!='short_id'} for row in activity_participants(s,'goal',100)] for s in scenarios]
        self.assertEqual(json.loads(result),expected)
    def test_short_id_uses_full_profile_id_not_name_or_role(self):
        s=self.fixture();before=profile_short_ids(s['agents']);s['agents'][0]['name']='New display'
        self.assertEqual(profile_short_ids(s['agents']),before);self.assertEqual(len(set(before.values())),6)
    def test_display_prefix_collision_expands_but_original_keys_remain(self):
        s=self.fixture()
        def digest(value):
            result=Mock();result.hexdigest.return_value='a'*8+value[-1:].decode().zfill(4)+'0'*52;return result
        with patch('dots_panel.agent_identity.hashlib.sha256',side_effect=digest):ids=profile_short_ids(s['agents'])
        self.assertEqual(set(ids),{a['id'] for a in s['agents']});self.assertTrue(all(len(value)==12 for value in ids.values()));self.assertEqual(len(set(ids.values())),6)
    def test_avatar_group_draws_three_and_remainder(self):
        view=Dashboard.__new__(Dashboard);view.font='sans';view.muted='gray';canvas=Mock();rows=activity_participants(self.fixture(),'goal')
        with patch('dots_panel.desktop_view.draw_portrait') as draw:view.draw_participant_group(canvas,rows,200,10,Mock())
        self.assertEqual(draw.call_count,3);self.assertEqual(canvas.create_text.call_args.kwargs['text'],'+2');self.assertEqual(draw.call_args_list[0].args[2],92);self.assertEqual(canvas.tag_bind.call_args.args[2](None),'break')
