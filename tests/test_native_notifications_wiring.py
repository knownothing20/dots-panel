import unittest
from pathlib import Path
from dots_panel.notifications import PauseDeadline

class NativeNotificationChecks(unittest.TestCase):
    def test_pause_budget_not_wall_time(self):
        now=[0.0];d=PauseDeadline(lambda:now[0]);d.reset();now[0]=1.2;self.assertAlmostEqual(d.left(),3.8);d.pause(True);now[0]=10;self.assertAlmostEqual(d.left(),3.8);d.pause(False);now[0]=12.8;self.assertAlmostEqual(d.left(),1)
    def test_in_app_layer_bounded_jobs_and_no_capsule(self):
        source=Path('src/dots_panel/native_notifications.py').read_text()
        for forbidden in ['Toplevel','topmost','grab_set','focus_force',"controls['capsule']"]:self.assertNotIn(forbidden,source)
        self.assertIn("self.cancel(key)",source);self.assertIn('self.canvas.place(relx=1.0',source);self.assertIn('self.root.unbind(sequence, binding)',source)
        self.assertIn('self.view.motion.reduced',source);self.assertIn("draw_portrait(self.canvas,card.get('agent_record')",source)
    def test_refresh_navigation_and_identity_glue(self):
        source=Path('src/dots_panel/desktop_view.py').read_text()
        for hook in ['self.notification_state.update(self.snapshot)','self.notifications.observe(notification_result)','self.notifications.mark_read(page)','self.notifications.close()']:self.assertIn(hook,source)

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
    def create_polygon(self,*args,**kwargs):pass
    def create_line(self,*args,**kwargs):pass

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



def make_view(root, widget, reduced=True):
    from types import SimpleNamespace
    from dots_panel.notifications import NotificationState
    from dots_panel.native_notifications import NativeNotifications
    tk=SimpleNamespace(Canvas=widget,Button=widget,TclError=RuntimeError)
    view=SimpleNamespace(root=root,tk=tk,bg='#fff',fg='#244A42',accent='#258560',font='sans',language='en',motion=SimpleNamespace(reduced=reduced),nav_buttons={p:widget(root) for p in ['conversations','agents','schedules','about']},t=lambda x:x,round_shape=lambda *args:None,cut_text=lambda text,*args:text,render_page=lambda:None)
    view.page_scroll=widget(root);view.page_scroll.place(width=700,height=500)
    state=NotificationState();state.initialized=True;state.cards=[{'id':'r','task_id':'t','title':'Synthetic','agent':'Example','participants':1,'agent_record':{'id':'a','name':'Example','portrait':'bloom-mint'}}];state.unread['conversations']['r']='t'
    return NativeNotifications(view,state),view

class NativeNotificationControllerTests(unittest.TestCase):
    def make(self):
        root=FakeRoot();ui,view=make_view(root,FakeWidget);return ui,root,view
    def test_initial_queue_is_hidden_and_close_preserves_unread(self):
        ui,root,view=self.make();self.assertFalse(ui.canvas.mapped);self.assertNotIn('capsule',ui.controls)
        ui.expand();self.assertTrue(ui.expanded);ui.collapse();self.assertFalse(ui.canvas.mapped);self.assertEqual(ui.state.counts()['conversations'],1)
        ui.observe({'changed':set(),'cards':[],'content_changed':True});self.assertFalse(ui.canvas.mapped);ui.close();self.assertFalse(root.jobs)
    def test_mouse_focus_is_not_keyboard_pause_or_outline(self):
        ui,root,view=self.make();ui.expand();root.focus=ui.controls['more'];ui.pointer_input();ui.sync_pause();self.assertFalse(ui.deadline.paused)
        self.assertTrue(all(w.options['highlightthickness']==0 for w in ui.controls.values()))
        root.focus=ui.controls['progress'];ui.keyboard_input();ui.sync_pause();self.assertTrue(ui.deadline.paused)
        self.assertTrue(all(w.options['highlightthickness']==1 for w in ui.controls.values()))
        ui.pointer_input();ui.sync_pause();self.assertFalse(ui.deadline.paused);ui.close()
    def test_hover_pause_and_leave_resume(self):
        ui,root,view=self.make();ui.expand();root.pointer=(30,30);ui.sync_pause();self.assertTrue(ui.deadline.paused)
        root.pointer=(9999,9999);ui.sync_pause();self.assertFalse(ui.deadline.paused);ui.close()
    def test_keyboard_progress_focuses_detail_mouse_progress_does_not(self):
        for keyboard in (False,True):
            ui,root,view=self.make();ui.expand();root.focus=ui.controls['progress'];ui.input_mode='keyboard' if keyboard else 'pointer';ui.open_task();_,fn=root.jobs.pop(ui.jobs['detail_focus']);fn()
            self.assertEqual(view.selected_task,'t');self.assertFalse(ui.canvas.mapped)
            self.assertEqual(root.focus is view.page_scroll,keyboard);ui.close()
    def test_auto_notification_never_takes_focus_and_poll_does_not_reset(self):
        ui,root,view=self.make();root.focus=view.page_scroll;ui.observe({'changed':set(),'cards':[ui.state.cards[0]]});self.assertIs(root.focus,view.page_scroll);started=ui.deadline.started
        ui.observe({'changed':set(),'cards':[]});self.assertEqual(ui.deadline.started,started);ui.close()
    def test_three_unread_categories_use_identical_dots(self):
        ui,root,view=self.make()
        for p in ('conversations','agents','schedules'):ui.state.unread[p]['x']=True
        ui.badges()
        for p in ('conversations','agents','schedules'):
            label=view.nav_buttons[p].options['text'];self.assertTrue(label.endswith('  ●'));self.assertFalse(any(c.isdigit() for c in label));self.assertNotIn('◷',label)
        ui.mark_read('agents');self.assertFalse(view.nav_buttons['agents'].options['text'].endswith('●'));self.assertEqual(ui.state.counts()['conversations'],2);ui.close()
    def test_notification_uses_shared_portrait_and_keeps_widgets_mapped(self):
        from unittest.mock import patch
        ui,root,view=self.make()
        with patch('dots_panel.native_notifications.draw_portrait') as draw:
            ui.expand();self.assertEqual(draw.call_args.args[1],ui.state.cards[0]['agent_record'])
        action=ui.controls['progress'];count=[0];original=action.place_forget
        def hide():count[0]+=1;original()
        action.place_forget=hide
        for _ in range(10):ui.draw()
        self.assertEqual(count[0],0);ui.close()

class NativeAsyncInputTests(unittest.TestCase):
    def test_mouse_focus_does_not_pin_after_leave_and_full_hide_reappears_for_new_event(self):
        from unittest.mock import patch
        root=EventRoot()
        with patch('dots_panel.native_notifications.time.monotonic',side_effect=lambda:root.now/1000):
            ui,view=make_view(root,EventWidget,False);root.advance(2);view.page_scroll.focus_set();ui.expand();root.advance(400)
            self.assertIs(root.focus,view.page_scroll);ui.pointer_input();ui.controls['progress'].focus_set();root.advance(6000)
            self.assertFalse(ui.expanded);self.assertEqual(ui.progress,0);self.assertFalse(ui.canvas.mapped);self.assertEqual(ui.state.counts()['conversations'],1)
            ui.observe({'changed':set(),'cards':[],'content_changed':True});root.advance(100);self.assertFalse(ui.canvas.mapped)
            ui.state.cards.insert(0,{'id':'new','task_id':'new','title':'New','agent':'Example','participants':1});ui.observe({'changed':{'conversations'},'cards':[ui.state.cards[0]]});root.advance(400)
            self.assertTrue(ui.expanded);self.assertTrue(ui.canvas.mapped);ui.close();root.advance(100);self.assertFalse(root.jobs)
    def test_keyboard_focus_pauses_and_blur_resumes_without_unmap_churn(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        root=EventRoot()
        with patch('dots_panel.native_notifications.time.monotonic',side_effect=lambda:root.now/1000):
            ui,view=make_view(root,EventWidget,False);root.advance(2);ui.expand();root.advance(400);ui.keyboard_input();ui.controls['progress'].focus_set();root.advance(40)
            self.assertTrue(ui.deadline.paused);root.after(20,lambda:ui.on_resize(SimpleNamespace(widget=root)));root.advance(6000)
            self.assertTrue(ui.expanded);self.assertEqual(ui.controls['progress'].unmaps,0)
            view.page_scroll.focus_set();root.advance(5500);self.assertFalse(ui.canvas.mapped);self.assertFalse(ui.expanded);ui.close();root.advance(100);self.assertFalse(root.jobs)
    def test_keyboard_escape_restores_external_focus_for_both_motion_modes(self):
        from unittest.mock import patch
        for reduced in (False,True):
            root=EventRoot()
            with patch('dots_panel.native_notifications.time.monotonic',side_effect=lambda:root.now/1000):
                ui,view=make_view(root,EventWidget,reduced);root.advance(2);view.page_scroll.focus_set();ui.expand();root.advance(400);ui.keyboard_input();ui.controls['close'].focus_set();root.advance(40);ui.escape();root.advance(400)
                self.assertIs(root.focus,view.page_scroll);self.assertFalse(ui.canvas.mapped);self.assertEqual(ui.state.counts()['conversations'],1);ui.close();root.advance(100);self.assertFalse(root.jobs)
    def test_space_progress_after_configure_and_keyboard_focus(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        root=EventRoot()
        with patch('dots_panel.native_notifications.time.monotonic',side_effect=lambda:root.now/1000):
            ui,view=make_view(root,EventWidget,False);root.advance(2);ui.expand();root.advance(400);ui.keyboard_input();ui.controls['progress'].focus_set();ui.controls['progress'].space_activate();root.after(20,lambda:ui.on_resize(SimpleNamespace(widget=root)));root.advance(300)
            self.assertEqual(view.selected_task,'t');self.assertIs(root.focus,view.page_scroll);self.assertFalse(ui.canvas.mapped);ui.close();root.advance(100);self.assertFalse(root.jobs)

class NativeFailedOpenPreservesUnreadTests(unittest.TestCase):
    def test_renderer_failure_does_not_acknowledge(self):
        ui,root,view=NativeNotificationControllerTests().make()
        def fail():raise RuntimeError('Synthetic render failure')
        view.render_page=fail
        ui.expand();ui.open_task()
        self.assertEqual(ui.state.counts()['conversations'],1)
        self.assertIn('kept unread',ui.open_error)
        ui.close()

    def test_requirement_must_return_true_and_be_visible(self):
        ui,root,view=NativeNotificationControllerTests().make()
        ui.state.cards[0].update(id='requirement:q',kind='requirement',requirement_id='q')
        ui.state.unread['conversations']={'requirement:q':'t'}
        view.open_requirement=lambda _:False
        ui.expand();ui.open_task();self.assertEqual(ui.state.counts()['conversations'],1)
        view.open_requirement=lambda _:True
        ui.open_task();self.assertEqual(ui.state.counts()['conversations'],0)
        ui.close()
