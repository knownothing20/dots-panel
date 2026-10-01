import copy
import unittest
from unittest.mock import Mock,patch
from dots_panel.participants import activity_participants
from dots_panel.agent_identity import profile_short_ids
from dots_panel.desktop_view import Dashboard

class ParticipantTests(unittest.TestCase):
    def fixture(self):
        return {'agents':[{'id':'p'+str(i),'name':'Person '+str(i),'portrait':'leaf-sky'} for i in range(6)],'runs':[{'id':'r','task_id':'goal'},{'id':'old','task_id':'goal'},{'id':'other','task_id':'elsewhere'}], 'agent_run_assignments':[{'run_id':'r','agent_id':'p'+str(i),'work_type':'development','assigned_at':i} for i in range(5)]+[{'run_id':'old','agent_id':'p0','work_type':'review','assigned_at':0},{'run_id':'other','agent_id':'p5','work_type':'research','assigned_at':10}]}
    def test_related_profiles_deduplicate_across_runs_and_preserve_role_records(self):
        s=self.fixture();before=copy.deepcopy(s);rows=activity_participants(s,'goal')
        self.assertEqual(len(rows),5);self.assertNotIn('p5',[r['agent']['id'] for r in rows]);self.assertEqual(len(next(r for r in rows if r['agent']['id']=='p0')['assignments']),2);self.assertEqual(s,before)
    def test_older_runs_use_joined_task_id_and_unmatched_profiles_are_not_invented(self):
        s=self.fixture();s['runs']=[];s['agent_run_assignments']=[{'run_id':'outside-window','task_id':'goal','agent_id':'p0','work_type':'writing'},{'run_id':'missing','task_id':'goal','agent_id':'unknown'}]
        self.assertEqual(len(activity_participants(s,'goal')),1)
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
