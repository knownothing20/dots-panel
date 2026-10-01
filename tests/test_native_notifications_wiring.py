import unittest
from pathlib import Path
from dots_panel.notifications import PauseDeadline

class NativeNotificationChecks(unittest.TestCase):
    def test_pause_budget_not_wall_time(self):
        now=[0.0];d=PauseDeadline(lambda:now[0]);d.reset();now[0]=1.2;self.assertAlmostEqual(d.left(),3.8)
        d.pause(True);now[0]=10;self.assertAlmostEqual(d.left(),3.8);d.pause(False);now[0]=12.8;self.assertAlmostEqual(d.left(),1)
        d.pause(True);d.reset();now[0]=100;self.assertEqual(d.left(),5);d.pause(False);now[0]=105;self.assertEqual(d.left(),0)
    def test_in_app_layer_and_bounded_jobs(self):
        source=Path('src/dots_panel/native_notifications.py').read_text()
        self.assertNotIn('Toplevel',source);self.assertNotIn('topmost',source);self.assertNotIn('grab_set',source);self.assertNotIn('focus_force',source)
        self.assertIn("self.cancel(key)",source);self.assertIn("self.canvas.place(relx=1.0",source)
        self.assertIn("self.root.unbind('<Configure>', self.configure_binding)",source)
        self.assertIn('self.view.motion.reduced',source)
    def test_refresh_and_navigation_hooks(self):
        source=Path('src/dots_panel/desktop_view.py').read_text()
        self.assertIn('self.notification_state.update(self.snapshot)',source)
        self.assertIn('self.notifications.observe(notification_result)',source)
        self.assertIn('self.notifications.mark_read(page)',source)
        self.assertIn('self.notifications.close()',source)

class FakeRoot:
    def __init__(self):self.jobs={};self.serial=0;self.focus=None;self.pointer=(9999,9999);self.tk=self;self._w='root'
    def after(self,delay,fn):self.serial+=1;key='j'+str(self.serial);self.jobs[key]=(delay,fn);return key
    def after_cancel(self,key):self.jobs.pop(key,None)
    def bind(self,*args,**kwargs):return 'binding'
    def unbind(self,*args):pass
    def winfo_pointerxy(self):return self.pointer
    def focus_get(self):return self.focus
    def winfo_width(self):return 1260
    def call(self,*args):pass

class FakeWidget:
    def __init__(self,parent,**options):self.root=parent if isinstance(parent,FakeRoot) else parent.root;self.options=options;self.exists=True;self.mapped=False;self.tk=self.root;self._w='widget';self.position={}
    def bind(self,*args,**kwargs):pass
    def configure(self,**options):self.options.update(options)
    def place(self,**options):self.position=options;self.mapped=True
    def place_forget(self):self.mapped=False
    def winfo_exists(self):return self.exists
    def winfo_ismapped(self):return self.mapped
    def winfo_rootx(self):return 0
    def winfo_rooty(self):return 0
    def winfo_width(self):return self.position.get('width',510)
    def winfo_height(self):return self.position.get('height',170)
    def focus_set(self):
        if self.mapped:self.root.focus=self
    def destroy(self):self.exists=False
    def delete(self,*args):pass
    def create_oval(self,*args,**kwargs):pass
    def create_arc(self,*args,**kwargs):pass
    def create_text(self,*args,**kwargs):pass

class NativeNotificationControllerTests(unittest.TestCase):
    def make(self):
        from types import SimpleNamespace
        from dots_panel.notifications import NotificationState
        from dots_panel.native_notifications import NativeNotifications
        root=FakeRoot();tk=SimpleNamespace(Canvas=FakeWidget,Button=FakeWidget,TclError=RuntimeError)
        view=SimpleNamespace(root=root,tk=tk,bg='#fff',fg='#244A42',accent='#258560',font='sans',language='en',motion=SimpleNamespace(reduced=True),nav_buttons={p:FakeWidget(root) for p in ['conversations','agents','schedules','about']},t=lambda x:x,round_shape=lambda *args:None,cut_text=lambda text,*args:text,render_page=lambda:None)
        view.page_scroll=FakeWidget(root);view.page_scroll.place(width=700,height=500)
        state=NotificationState();state.initialized=True;state.cards=[{'id':'r','task_id':'t','title':'Synthetic','agent':'Example','participants':1}];state.unread['conversations']['r']='t'
        return NativeNotifications(view,state),root,view
    def test_collapse_keeps_unread_and_reopen_does_not_duplicate(self):
        ui,root,view=self.make();ui.expand();self.assertTrue(ui.expanded);self.assertIn('dwell',ui.jobs)
        ui.collapse();self.assertFalse(ui.expanded);self.assertEqual(ui.state.counts()['conversations'],1);self.assertEqual(len(ui.state.cards),1)
        ui.expand();self.assertEqual(len(ui.state.cards),1);ui.mark_read('conversations');self.assertFalse(ui.canvas.mapped);ui.close();self.assertFalse(root.jobs)
    def test_hover_and_visible_focus_pause_and_resume(self):
        ui,root,view=self.make();ui.expand();root.pointer=(30,30);ui.sync_pause();self.assertTrue(ui.deadline.paused);self.assertNotIn('dwell',ui.jobs)
        root.pointer=(9999,9999);root.focus=ui.controls['progress'];ui.sync_pause();self.assertTrue(ui.deadline.paused)
        root.focus=None;ui.sync_pause();self.assertFalse(ui.deadline.paused);self.assertIn('dwell',ui.jobs)
        # An invisible capsule cannot keep the expanded card paused forever.
        root.focus=ui.controls['capsule'];ui.sync_pause();self.assertFalse(ui.deadline.paused);ui.close()
    def test_progress_opens_task_and_removes_only_matching_cards(self):
        ui,root,view=self.make();ui.state.cards.append({'id':'r2','task_id':'other','title':'Other','agent':'Other','participants':1});ui.state.unread['conversations']['r2']='other';ui.expand();ui.open_task();self.assertEqual(view.selected_task,'t');self.assertEqual(len(ui.state.cards),1);self.assertEqual(ui.state.cards[0]['task_id'],'other');ui.close()
    def test_duplicate_observe_does_not_reset_dwell(self):
        ui,root,view=self.make();ui.expand();before=ui.deadline.started;ui.observe({'changed':set(),'cards':[]});self.assertEqual(ui.deadline.started,before);ui.close()

    def test_keyboard_capsule_expansion_moves_focus_to_visible_action(self):
        ui,root,view=self.make();ui.draw();ui.controls['capsule'].focus_set();self.assertIs(root.focus,ui.controls['capsule'])
        ui.controls['capsule'].options['command']();job=ui.jobs['expand_focus'];_,fn=root.jobs.pop(job);fn();self.assertIs(root.focus,ui.controls['progress']);self.assertTrue(ui.controls['progress'].winfo_ismapped());self.assertTrue(ui.deadline.paused)
        root.focus=view.page_scroll;ui.sync_pause();self.assertFalse(ui.deadline.paused);self.assertIn('dwell',ui.jobs);ui.close()
    def test_last_progress_transfers_focus_to_detail(self):
        ui,root,view=self.make();ui.expand(from_capsule=True);ui.open_task();job=ui.jobs['detail_focus'];_,fn=root.jobs.pop(job);fn();self.assertIs(root.focus,view.page_scroll);self.assertFalse(ui.canvas.mapped);ui.close()
    def test_automatic_notification_never_takes_external_focus(self):
        ui,root,view=self.make();root.focus=view.page_scroll;ui.observe({'changed':set(),'cards':[ui.state.cards[0]]});self.assertIs(root.focus,view.page_scroll);ui.close()

    def test_repaint_does_not_unmap_visible_capsule_or_action(self):
        ui,root,view=self.make();capsule=ui.controls['capsule'];action=ui.controls['progress'];counts={'capsule':0,'action':0}
        cap_hide=capsule.place_forget;action_hide=action.place_forget
        def hide_capsule():counts['capsule']+=1;cap_hide()
        def hide_action():counts['action']+=1;action_hide()
        capsule.place_forget=hide_capsule;action.place_forget=hide_action
        for _ in range(10):ui.draw()
        self.assertEqual(counts['capsule'],0)
        ui.expand();self.assertEqual(counts['capsule'],1)
        for _ in range(10):ui.draw()
        self.assertEqual(counts['action'],0);ui.close()

class EventRoot(FakeRoot):
    """Deterministic event loop with delayed geometry mapping and focus events."""
    def __init__(self):super().__init__();self.now=0;self.callbacks={}
    def after(self,delay,fn):self.serial+=1;key='j'+str(self.serial);self.jobs[key]=(self.now+delay,fn);return key
    def bind(self,sequence,fn,**kwargs):self.callbacks[sequence]=fn;return 'binding'
    def advance(self,ms):
        stop=self.now+ms;iterations=0
        while self.jobs:
            key,(when,fn)=min(self.jobs.items(),key=lambda row:(row[1][0],row[0]))
            if when>stop:break
            self.jobs.pop(key);self.now=when;fn();iterations+=1
            if iterations>10000:raise AssertionError('Event loop did not settle')
        self.now=stop
    def set_focus(self,widget):
        old=self.focus
        if old is widget:return
        self.focus=widget
        if isinstance(old,EventWidget):old.emit('<FocusOut>')
        if isinstance(widget,EventWidget):widget.emit('<FocusIn>')

class EventWidget(FakeWidget):
    def __init__(self,parent,**options):super().__init__(parent,**options);self.managed=False;self.callbacks={};self.unmaps=0;self.pressed=False;self.unmapped_focus_attempts=0
    def bind(self,sequence,fn,**kwargs):self.callbacks.setdefault(sequence,[]).append(fn)
    def emit(self,sequence):
        from types import SimpleNamespace
        for fn in self.callbacks.get(sequence,[]):self.root.after(0,lambda fn=fn:fn(SimpleNamespace(widget=self)))
    def place(self,**options):
        self.position=options
        if not self.managed:
            self.managed=True
            def mapped():
                if self.managed and self.exists:self.mapped=True;self.emit('<Map>')
            self.root.after(1,mapped)
    def place_forget(self):
        if self.managed:
            self.unmaps+=1;self.managed=False;self.mapped=False;self.pressed=False;self.emit('<Unmap>')
            if self.root.focus is self:self.root.set_focus(None)
    def focus_set(self):
        if self.mapped:self.root.set_focus(self)
        else:self.unmapped_focus_attempts+=1
    def space_activate(self):
        # A class binding may defer invocation; unmapping cancels that gesture.
        self.pressed=True
        def invoke():
            if self.pressed and self.mapped:self.pressed=False;self.options['command']()
        self.root.after(100,invoke)

class NativeAsyncFocusTests(unittest.TestCase):
    def make(self,root):
        from types import SimpleNamespace
        from dots_panel.notifications import NotificationState
        from dots_panel.native_notifications import NativeNotifications
        tk=SimpleNamespace(Canvas=EventWidget,Button=EventWidget,TclError=RuntimeError)
        view=SimpleNamespace(root=root,tk=tk,bg='#fff',fg='#244A42',accent='#258560',font='sans',language='en',motion=SimpleNamespace(reduced=False),nav_buttons={p:EventWidget(root) for p in ['conversations','agents','schedules','about']},t=lambda x:x,round_shape=lambda *args:None,cut_text=lambda text,*args:text,render_page=lambda:None)
        view.page_scroll=EventWidget(root);view.page_scroll.place(width=700,height=500)
        state=NotificationState();state.initialized=True;state.cards=[{'id':'r','task_id':'t','title':'Synthetic','agent':'Example','participants':1}];state.unread['conversations']['r']='t'
        return NativeNotifications(view,state),view
    def test_space_reopen_survives_resize_map_focus_timing_and_dwell(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        root=EventRoot()
        with patch('dots_panel.native_notifications.time.monotonic',side_effect=lambda:root.now/1000):
            ui,view=self.make(root);root.advance(2);capsule=ui.controls['capsule'];capsule.focus_set();root.advance(1)
            capsule.space_activate();root.after(20,lambda:ui.on_resize(SimpleNamespace(widget=root)))
            root.advance(500)
            self.assertTrue(ui.expanded);self.assertEqual(ui.progress,1);self.assertEqual(ui.canvas.winfo_width(),510)
            self.assertIs(root.focus,ui.controls['progress']);self.assertTrue(ui.controls['progress'].mapped);self.assertTrue(ui.deadline.paused)
            self.assertEqual(capsule.unmaps,1);self.assertEqual(ui.controls['progress'].unmaps,0);self.assertEqual(ui.controls['progress'].unmapped_focus_attempts,0)
            root.advance(6000);self.assertTrue(ui.expanded)
            view.page_scroll.focus_set();root.advance(5500);self.assertFalse(ui.expanded);self.assertEqual(ui.progress,0);self.assertEqual(ui.canvas.winfo_width(),232);self.assertEqual(ui.state.counts()['conversations'],1)
            ui.close();root.advance(100);self.assertFalse(root.jobs)
    def test_repeated_capsule_reopen_keeps_animation_callbacks_bounded(self):
        from unittest.mock import patch
        root=EventRoot()
        with patch('dots_panel.native_notifications.time.monotonic',side_effect=lambda:root.now/1000):
            ui,view=self.make(root);root.advance(2)
            for _ in range(5):
                ui.controls['capsule'].focus_set();ui.controls['capsule'].options['command']();root.advance(400)
                self.assertTrue(ui.expanded);self.assertEqual(ui.progress,1);self.assertIs(root.focus,ui.controls['progress']);self.assertLessEqual(len(ui.jobs),2)
                ui.collapse();root.advance(400);self.assertFalse(ui.expanded);self.assertEqual(ui.progress,0);self.assertIs(root.focus,ui.controls['capsule'])
            ui.close();root.advance(100);self.assertFalse(root.jobs)

    def test_reduced_motion_collapse_waits_for_capsule_mapping(self):
        from unittest.mock import patch
        root=EventRoot()
        with patch('dots_panel.native_notifications.time.monotonic',side_effect=lambda:root.now/1000):
            ui,view=self.make(root);view.motion.reduced=True;root.advance(2)
            ui.controls['capsule'].focus_set();ui.expand(from_capsule=True);root.advance(40)
            self.assertIs(root.focus,ui.controls['progress']);self.assertTrue(ui.deadline.paused)
            ui.collapse();root.advance(40)
            self.assertFalse(ui.expanded);self.assertEqual(ui.progress,0);self.assertTrue(ui.controls['capsule'].mapped)
            self.assertIs(root.focus,ui.controls['capsule']);self.assertEqual(ui.controls['capsule'].unmapped_focus_attempts,0)
            # A rapid reopen cancels the pending collapsed-focus handoff.
            ui.expand(from_capsule=True);root.advance(40);ui.collapse();ui.expand(from_capsule=True);root.advance(60)
            self.assertTrue(ui.expanded);self.assertIs(root.focus,ui.controls['progress']);self.assertNotIn('focus_capsule',ui.jobs)
            ui.close();root.advance(100);self.assertFalse(root.jobs)
