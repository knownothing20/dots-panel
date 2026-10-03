"""Synthetic view contracts; no real DATA, processes, network or desktop control."""
import copy
import unittest
from unittest.mock import Mock,patch
from pathlib import Path
from dots_panel.companion_sources import companion_snapshot, scheduler_is_bundled, skill_is_bundled
from dots_panel.native_requirement_bookmarks import requirement_records,requirement_work,requirement_owner,requirement_status
from dots_panel.desktop_view import Dashboard,timeline_records,collaboration_actor,PAGE_NAMES,memory_bytes
import test_native_retained_updates as retained
from test_native_retained_updates import Widget,Canvas

class CompanionSourceTests(unittest.TestCase):
    def test_skill_only_exact_origin(self):
        for name in ('Panel task skill','X resolver','Book Radar','Personal cloud rules'):
            self.assertFalse(skill_is_bundled({'name':name,'source':{'origin':'personal'}}))
            self.assertTrue(skill_is_bundled({'name':name,'source':{'origin':'project_bundled'}}))
    def test_scheduler_latest_verified_exact_reference_only(self):
        schedule={'name':'Fixed panel backup','platform_observation':{'task_id':'synthetic-fixed','enabled':False}}
        rows=[{'id':1,'component':'scheduler_configuration','status':'verified','reference':'synthetic-fixed','observed_at':1}]
        self.assertTrue(scheduler_is_bundled(schedule,rows))
        self.assertFalse(scheduler_is_bundled({**schedule,'platform_observation':{'task_id':'other','enabled':True}},rows))
        self.assertFalse(scheduler_is_bundled(schedule,rows+[{'id':2,'component':'scheduler_configuration','status':'unknown','reference':'synthetic-fixed','observed_at':2}]))
        self.assertFalse(scheduler_is_bundled(schedule,[{**rows[0],'reference':''}]))
        self.assertFalse(scheduler_is_bundled({'name':schedule['name']},rows))
    def test_snapshot_does_not_mutate_or_badge_independent_skills(self):
        state={'rules':{'skills':[{'id':'a','source':{'origin':'project_bundled'}},{'id':'b','source':{'origin':'independent'}}]},'schedules':[{'id':'s','platform_observation':{'task_id':'actual'}}],'about':{'doctor':{'observations':{'scheduler_configuration':{'status':'verified','reference':'actual','observed_at':1}}}}}
        before=copy.deepcopy(state);self.assertEqual(companion_snapshot(state),{'project_rules':True,'skills':['a'],'schedules':['s']});self.assertEqual(state,before)

class RequirementViewTests(unittest.TestCase):
    def card(self):
        return {'id':'q','task_id':'t','summary':'Original literal <script>','observed_at':2,'status':'received','owner':{'status':'assignment_unconfirmed'},'history':[],'status_history':[{'id':1,'status':'received','observed_at':2,'evidence':'Receipt only'}]}
    def test_source_time_and_terminal_history_are_unchanged(self):
        card=self.card();state={'requirements':[card],'tasks':[{'id':'t'}],'runs':[],'activity':[{'id':1,'task_id':'t','stage':'progress','created':3,'message':'New work'}]}
        records=timeline_records(state,'t');self.assertEqual([r['kind'] for r in records],['activity','requirement'])
        self.assertEqual(records[1]['created'],2);self.assertEqual(records[1]['message'],card['summary'])
        card['status']='completed';self.assertEqual(len(requirement_records(state,{'t'})),1);self.assertEqual(requirement_records(state,{'other'}),[])
    def test_unconfirmed_owner_and_receipt_do_not_invent_execution(self):
        card=self.card();self.assertEqual(requirement_owner(card,'en'),'Owner unconfirmed');self.assertEqual(requirement_work(card),'')
        card['current_step']='Explicit linked action';self.assertEqual(requirement_work(card),'Explicit linked action')
        card['owner']={'status':'confirmed','name':'Sprout','name_en':'Sprout EN'};self.assertEqual(requirement_owner(card,'en'),'Sprout EN')
        self.assertEqual(requirement_status('pending_acceptance','en'),'Pending acceptance')
    def test_system_author_distinct_from_unknown_and_agent(self):
        self.assertEqual(collaboration_actor({'role':'system'},{},'en')['label'],'System record')
        self.assertEqual(collaboration_actor({},{},'en')['label'],'Historical author unknown')
        self.assertFalse(collaboration_actor({'role':'system'},{},'en')['known'])
    def test_retained_requirement_controls_and_history_update_in_place(self):
        view=retained.RetainedUpdateTests().view();view.card=lambda parent,*a,**k:(Canvas(parent),Widget(parent));card=self.card();area=Widget()
        surface=view.requirement_message(area,{'kind':'requirement','requirement':card,'created':2})
        button=surface.requirement_button;button.options['command']()
        self.assertIn('q',view.expanded_requirements)
        updated={**card,'status':'blocked','history':[{'id':1,'kind':'receipt','status':'received','observed_at':2,'evidence':'Receipt only'},{'id':2,'kind':'state','status':'blocked','observed_at':3,'evidence':'Waiting for evidence'}]}
        surface.refresh_requirement(updated);self.assertIs(surface.requirement_button,button);self.assertEqual(button.deleted,0);self.assertIn('q',view.expanded_requirements)
        texts=[c.options.get('text') for c in area.children[-1].children if 'text' in c.options]
        self.assertTrue(any('Blocked' in str(text) for text in texts))
    def test_bundled_title_has_actual_heading_parent(self):
        view=retained.RetainedUpdateTests().view();box=Widget();box.title_label=Widget(box,text='Long bundled title remains visible');box.summary_label=Widget(box);box.bounded_title=False
        original=box.title_label;badge=view.attach_bundled_badge(box)
        self.assertEqual(original.deleted,1);self.assertEqual(box.title_label.cget('text'),'Long bundled title remains visible');self.assertIsNot(box.title_label.master,box);self.assertIs(badge.master,box.title_label.master)
        self.assertTrue(box.title_label.own_title_wrap)
    def test_small_rss_never_rounds_to_zero_gib(self):
        self.assertEqual(memory_bytes(8*2**20),'8.0 MiB');self.assertEqual(memory_bytes(32*2**20),'32.0 MiB');self.assertEqual(memory_bytes(128),'128 B');self.assertEqual(memory_bytes(None,'en'),'Unknown')
    def test_pages_default_and_readonly_ui_contract(self):
        self.assertIn('memory',PAGE_NAMES);self.assertIn('reset',PAGE_NAMES)
        source=Path('src/dots_panel/desktop_view.py').read_text();self.assertIn('self.workspace_filter = "unfinished"',source)
        self.assertIn('height=28',source);self.assertIn("font=(self.font,-12,'bold')",source);self.assertIn("'#d5ecdd'",source);self.assertIn("'#24543c'",source)
        self.assertIn('title.own_title_wrap=True',source);self.assertIn("if getattr(child,'own_title_wrap',False):continue",source)
        self.assertIn("'known_original_run_id'",source)
    def test_bookmark_geometry_allocates_no_fixed_column(self):
        source=Path('src/dots_panel/native_requirement_bookmarks.py').read_text()
        self.assertIn('self.frame.place(relx=1',source);self.assertNotIn('self.frame.pack(',source);self.assertNotIn('self.frame.grid(',source)
        self.assertIn("card.get('status') not in TERMINAL",source)
