"""Synthetic, no-display UI regressions for explicit collaborative event authors."""
import copy
import inspect
import unittest
from unittest.mock import Mock, patch
from dots_panel.desktop_view import (Dashboard, collaboration_actor, collaboration_scope,
                                    collaboration_mode, collaboration_records)

class CollaborativeUiTests(unittest.TestCase):
    def fixture(self):
        attribution={'agent_id':'a','actor_name':'旧昵称','actor_name_en':'Old name','actor_short_id':'aaaabbbb','actor_display_id':'a','portrait':'leaf-sky','color_key':'aabbccdd','work_type':'review','assignment_id':'ep1'}
        return {'tasks':[{'id':'p','name':'Project','activity_kind':'project','collaboration_mode':'team','mode_source':'explicit'},{'id':'c','name':'Child','parent_task_id':'p'},{'id':'x','name':'Elsewhere'}],
                'agents':[{'id':'a','name':'Current name','name_en':'Current English','portrait':'bloom-mint','panel_short_id':'newid'}],
                'agent_assignments':[{'task_id':'p','agent_id':'a','work_type':'development'}],
                'runs':[{'id':'r','task_id':'p','started':1,'status':'running'},{'id':'rc','task_id':'c','started':2,'status':'running'}],
                'activity':[{'id':1,'task_id':'p','created':3,'message':'Author unrecorded','stage':'implementation'},
                            {'id':2,'task_id':'c','created':4,'message':'Real attributed work','stage':'review','attribution':attribution}],
                'events':[{'id':3,'run_id':'rc','created':4,'message':'Real attributed work','attribution':{**attribution,'agent_id':'b','actor_short_id':'bbbbbbbb'}}]}
    def test_author_snapshot_role_avatar_and_short_id_never_use_current_owner(self):
        state=self.fixture();before=copy.deepcopy(state)
        known=collaboration_actor(state['activity'][1],state,'en')
        self.assertEqual((known['label'],known['role'],known['short_id'],known['agent']['portrait']),('Old name','Review','aaaabbbb','leaf-sky'))
        self.assertFalse(collaboration_actor(state['activity'][0],state)['known'])
        self.assertEqual(state,before)
    def test_missing_short_id_does_not_fall_back_to_current_profile(self):
        state=self.fixture();del state['activity'][1]['attribution']['actor_short_id']
        self.assertEqual(collaboration_actor(state['activity'][1],state,'en')['short_id'],'ID unrecorded')
    def test_project_scope_is_explicit_and_unknown_history_can_be_filtered(self):
        state=self.fixture();self.assertEqual(collaboration_scope(state,'p'),{'p','c'})
        self.assertEqual(collaboration_scope(state,'p',False),{'p'})
        self.assertEqual([r['message'] for r in collaboration_records(state,'p',{'agent':'unattributed'})],['Author unrecorded'])
        rows=collaboration_records(state,'p',{'task':'c','role':'review'});self.assertEqual(len(rows),2)
        self.assertEqual(len(collaboration_records(state,'p',{'agent':'a'})),1)
        self.assertEqual(collaboration_records(state,'p',{'task':'x'}),[])
    def test_identical_text_by_two_recorded_authors_is_not_deduplicated(self):
        state=self.fixture();self.assertEqual(len(collaboration_records(state,'p')),3)
    def test_mode_never_inferred_from_participants_and_tint_is_stable(self):
        state=self.fixture();self.assertIn('Mode not recorded',collaboration_mode({},'en'));self.assertNotIn('Team',collaboration_mode({},'en'))
        row=state['activity'][1];old=collaboration_actor(row,state)['color'];row['attribution']['actor_name']='Renamed'
        self.assertEqual(collaboration_actor(row,state)['color'],old)
    def test_header_collapses_with_hysteresis_without_rebuilding_page(self):
        view=Dashboard.__new__(Dashboard);view.page='conversations';view.selected_task='p';view.root=Mock();view.root.focus_get.return_value=None;view.page_scroll=Mock();view.detail_header_secondary=Mock();view.conversation_header_compact=False;view.detail_meta=True
        view.page_scroll.canvasy.return_value=70;view.update_conversation_header();view.detail_header_secondary.pack_forget.assert_called_once()
        view.page_scroll.canvasy.return_value=20;view.update_conversation_header();view.detail_header_secondary.pack.assert_not_called()
        view.page_scroll.canvasy.return_value=0;view.update_conversation_header();view.detail_header_secondary.pack.assert_called_once()
    def test_detail_default_does_not_render_participant_wall_or_metadata(self):
        view=Dashboard.__new__(Dashboard);view.tk=Mock();view.tk.Frame.return_value.winfo_children.return_value=[];view.ttk=Mock();view.root=Mock();view.content=Mock();view.language='en';view.timezone='UTC';view.font='Sans';view.bg=view.panel=view.tint='white';view.fg='black';view.accent='green';view.muted='gray';view.selected_task='p';view.detail_tab='files';view.detail_meta=False;view.live_updates=[];view.snapshot=self.fixture();view.rows=[{'id':'p','values':['Project','','Running','','','Stamp'],'run':{'status':'running'}}]
        view.label=Mock();view.filter_chip=Mock();view.scroll_area=Mock();view.render_task_files=Mock();view.render_task_participants=Mock();view.render_progress_detail=Mock()
        view.render_conversation();view.render_task_participants.assert_not_called();view.render_progress_detail.assert_not_called();view.render_task_files.assert_called_once()
    def test_rendered_stream_uses_scoped_read_and_event_portrait(self):
        view=Dashboard.__new__(Dashboard);view.tk=Mock();view.tk.Frame.return_value.winfo_children.return_value=[];view.ttk=Mock();view.root=Mock();view.content=Mock();view.language='en';view.timezone='UTC';view.font='Sans';view.bg=view.panel=view.tint='white';view.fg='black';view.accent='green';view.muted='gray';view.selected_task='p';view.detail_tab='timeline';view.detail_meta=False;view.live_updates=[];view.snapshot=self.fixture();view.rows=[{'id':'p','values':['Project','','Running','','','Stamp'],'run':{'status':'running'}}]
        view.label=Mock();view.filter_chip=Mock();view.scroll_area=Mock();view.card=Mock(return_value=(Mock(),Mock()));view.detail_paragraph=Mock();view.render_conversation_filters=Mock();view.button=Mock();view.store=Mock()
        event={**view.snapshot['activity'][1],'kind':'activity','key':'activity:2'}
        view.store.collaboration_timeline.return_value={'rows':[event],'total':1,'limit':100,'offset':0,'has_more':False}
        with patch('dots_panel.desktop_view.draw_portrait') as draw:view.render_conversation()
        self.assertEqual(draw.call_args.args[1]['portrait'],'leaf-sky');self.assertEqual(draw.call_args.args[1]['name'],'旧昵称')
        view.store.collaboration_timeline.assert_called_once_with('p',include_children=True,agent_id=None,work_type=None,child_task_id=None,limit=100,offset=0)
        self.assertTrue(any(call.args[1]=='Old name' for call in view.label.call_args_list))
    def test_scroll_and_keyboard_guards_are_preserved(self):
        self.assertIn('pending_conversation_anchor',inspect.getsource(Dashboard.scroll_area))
        self.assertIn('conversation_focus',inspect.getsource(Dashboard.refresh))
        self.assertIn('combo.bind',inspect.getsource(Dashboard.render_conversation_filters))

if __name__=='__main__':unittest.main()
