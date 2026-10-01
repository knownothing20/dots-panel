"""Asynchronous body sizing and cross-detail scroll ownership regressions."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from test_native_retained_updates import Widget,Canvas
import test_native_retained_updates as retained
from dots_panel.desktop_view import Dashboard

class Frame(Widget):
    def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self.requested=1;self.actual=1
    def winfo_reqheight(self):return self.requested
    def winfo_height(self):return self.actual

class ScrollCanvas(Canvas):
    def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self.moved=[];self.embedded_height=1;self.viewport=600;self.mapped=True
    def winfo_height(self):return self.viewport
    def winfo_ismapped(self):return self.mapped
    def bbox(self,item):return (0,0,800,self.embedded_height) if self.embedded_height is not None else None
    def yview_moveto(self,value):self.moved.append(value);self.fraction=(value,min(1,value+.2))

class ScrollMountTests(unittest.TestCase):
    def view(self):
        v=Dashboard.__new__(Dashboard);v.root=Mock();v.root.after.return_value='job';v.tk=SimpleNamespace(Frame=Frame,Canvas=ScrollCanvas);v.content=Widget();v.bg='white';v.page='conversations';v.selected_task='task-A';v.scroll_positions={};v.make_scrollbar=lambda *args:Widget();return v
    def test_region_tracks_canvas_window_bounds_not_frame_geometry(self):
        v=self.view();body=v.scroll_area();canvas=v.page_scroll
        canvas.cancel_restore();canvas.follow_tail=True
        for requested,actual,bounds in ((6000,1300,1300),(1300,6000,1300),(2600,2600,2600),(600,600,600)):
            body.requested=requested;body.actual=actual;canvas.embedded_height=bounds;body.bindings['<Configure>'](None)
            self.assertEqual(canvas.options['scrollregion'][3],max(600,bounds))
            self.assertAlmostEqual(canvas.moved[-1],max(0,(bounds-600)/bounds))
            self.assertLess(canvas.moved[-1],1)
            self.assertLessEqual(canvas.moved[-1]*max(600,bounds),max(0,bounds-600))
    def test_tail_and_delayed_restore_use_window_bounds_after_frame_unmaps(self):
        v=self.view();body=v.scroll_area();canvas=v.page_scroll
        body.requested=18016;body.actual=23344;canvas.embedded_height=18016;canvas.viewport=690
        canvas.follow_tail=True
        # Geometry can change without a body Configure event while the frame
        # is outside the viewport. Both delayed paths must resync the region.
        restore=v.root.after.call_args.args[1]
        restore()
        self.assertEqual(canvas.options['scrollregion'][3],18016)
        self.assertAlmostEqual(canvas.moved[-1]*18016,17326)
        self.assertLessEqual(canvas.moved[-1]*18016,17326)
        canvas.embedded_height=14000
        canvas.follow_end()
        self.assertEqual(canvas.options['scrollregion'][3],14000)
        self.assertAlmostEqual(canvas.moved[-1]*14000,13310)
        self.assertLess(canvas.moved[-1]*14000,canvas.embedded_height)
    def test_missing_window_bounds_stays_at_top_until_mapped(self):
        v=self.view();body=v.scroll_area();canvas=v.page_scroll
        body.requested=body.actual=6000;canvas.embedded_height=None
        canvas.follow_end()
        self.assertEqual(canvas.options['scrollregion'][3],600)
        self.assertEqual(canvas.moved[-1],0)
    def test_saved_anchor_is_clamped_to_the_same_window_extent(self):
        v=self.view();body=v.scroll_area();canvas=v.page_scroll
        body.requested=18016;body.actual=23344;canvas.embedded_height=18016;canvas.viewport=690
        anchor=Widget();anchor.winfo_y=lambda:23000
        v.pending_conversation_anchor=('record',0);v.conversation_anchors={'record':anchor}
        v.root.after.call_args.args[1]()
        self.assertEqual(canvas.options['scrollregion'][3],18016)
        self.assertLessEqual(canvas.moved[-1]*18016,17326)
        self.assertIsNone(v.pending_conversation_anchor)
    def test_one_pixel_viewport_cancels_pending_jump_and_later_starts_at_top(self):
        v=self.view();body=v.scroll_area();canvas=v.page_scroll
        body.requested=body.actual=16309;canvas.embedded_height=16309
        restore=v.root.after.call_args.args[1]
        canvas.viewport=1;canvas.mapped=False;canvas.follow_tail=True
        before=len(canvas.moved);restore();canvas.follow_end()
        self.assertEqual(len(canvas.moved),before)
        self.assertFalse(canvas.follow_tail)
        canvas.viewport=690;canvas.mapped=True;body.bindings['<Configure>'](None)
        self.assertEqual(canvas.moved[-1],0)
        restore()
        self.assertEqual(canvas.moved[-1],0,'Cancelled restore must not jump after mapping')
    def test_old_task_follow_callback_cannot_scroll_new_task(self):
        v=self.view();old_body=v.scroll_area();old=v.page_scroll;old_body.requested=6000;old_body.actual=6000;old.embedded_height=6000
        follow=old.follow_end;restore=v.root.after.call_args.args[1]
        v.selected_task='task-B';body=v.scroll_area();new=v.page_scroll;body.requested=1800;body.actual=1800;new.embedded_height=1800;body.bindings['<Configure>'](None)
        old_count=len(old.moved);new_count=len(new.moved);follow();restore()
        self.assertEqual(len(old.moved),old_count);self.assertEqual(len(new.moved),new_count)
        new.follow_end();self.assertAlmostEqual(new.moved[-1],2/3)
    def test_switch_from_many_authored_rows_to_unattributed_mounts_all_records(self):
        v=retained.RetainedUpdateTests().view();v.page='conversations';v.detail_tab='timeline';v.detail_meta=False
        v.scroll_area=lambda:Widget();v.page_scroll=Canvas();v.render_conversation_filters=Mock();v.card=lambda parent,*args,**kwargs:(Canvas(parent),Widget(parent));v.detail_paragraph=lambda parent,message:Widget(parent,text=message)
        v.store=Mock()
        for key,count,actor in [('task-A',100,{'actor_name':'Known','actor_short_id':'1234','work_type':'review','portrait':'bloom-mint','color_key':1}),('task-B',13,None)]:
            v.selected_task=key;v.snapshot={'tasks':[{'id':key,'name':key}],'runs':[]};v.rows=[{'id':key,'values':[key,'','Running','','','Stamp'],'run':None}]
            rows=[{'id':i,'key':f'{key}:activity:{i}','kind':'activity','task_id':key,'created':i,'stage':'progress','message':'Existing record '+str(i),'attribution':actor} for i in range(count)]
            v.store.collaboration_timeline.return_value={'rows':rows,'total':count,'limit':100,'offset':0,'has_more':False}
            v.render_conversation();self.assertEqual(len(v.conversation_anchors),count)
            self.assertFalse(v.page_scroll.follow_tail,'First render starts at the top')
            self.assertTrue(all(widget.exists and widget.managed for widget in v.conversation_anchors.values()))
            self.assertTrue(all(key in identity for identity in v.conversation_anchors))

if __name__=='__main__':unittest.main()
