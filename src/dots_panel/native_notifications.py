"""App-contained, transient notifications. No top-level windows or networking."""
import math
import time
from .agent_identity import draw_portrait
from .notifications import PauseDeadline


class NativeNotifications:
    def __init__(self, view, state):
        self.view, self.state, self.root, self.tk = view, state, view.root, view.tk
        self.expanded = False
        self.progress = 0.0
        self.jobs = {}
        self.deadline = PauseDeadline(time.monotonic)
        self.input_mode = 'pointer'
        self.return_focus = None
        self.canvas = self.tk.Canvas(self.root, bg=view.bg, bd=0, highlightthickness=0)
        self.controls = {}
        self.visible_controls = set()
        for name, command in [('close', self.collapse), ('progress', self.open_task), ('more', self.next_card)]:
            button = self.tk.Button(self.canvas, command=command, bd=0, relief='flat', cursor='hand2', takefocus=1,
                                    font=(view.font, -14, 'bold'), highlightthickness=0, highlightcolor=view.accent,
                                    highlightbackground='#FBFCF6', bg='#FBFCF6', fg=view.fg, activebackground='#E1EDD9')
            self.controls[name] = button
            for sequence in ('<Enter>', '<Leave>', '<FocusIn>', '<FocusOut>'):
                button.bind(sequence, self.check_interaction, add='+')
            button.bind('<ButtonPress>', self.pointer_input, add='+')
            button.bind('<KeyPress>', self.keyboard_input, add='+')
            button.bind('<Escape>', self.escape)
        for sequence in ('<Enter>', '<Leave>', '<FocusIn>', '<FocusOut>'):
            self.canvas.bind(sequence, self.check_interaction, add='+')
        self.root_bindings = {
            '<Configure>': self.root.bind('<Configure>', self.on_resize, add='+'),
            '<ButtonPress>': self.root.bind('<ButtonPress>', self.pointer_input, add='+'),
            '<KeyPress>': self.root.bind('<KeyPress>', self.keyboard_input, add='+'),
        }
        self.draw()
        self.badges()

    def later(self, key, delay, callback):
        self.cancel(key)
        def run():
            self.jobs.pop(key, None)
            if self.canvas.winfo_exists():
                callback()
        self.jobs[key] = self.root.after(delay, run)

    def cancel(self, key):
        job = self.jobs.pop(key, None)
        if job is not None:
            try:
                self.root.after_cancel(job)
            except self.tk.TclError:
                pass

    def close(self):
        for key in tuple(self.jobs):
            self.cancel(key)
        try:
            for sequence, binding in self.root_bindings.items():
                self.root.unbind(sequence, binding)
            self.canvas.destroy()
        except self.tk.TclError:
            pass

    def on_resize(self, event):
        if event.widget == self.root and (self.expanded or self.progress > 0):
            self.later('resize', 40, self.draw)

    def pointer_input(self, event=None):
        self.input_mode = 'pointer'
        self.focus_style()
        self.check_interaction()

    def keyboard_input(self, event=None):
        self.input_mode = 'keyboard'
        self.focus_style()
        self.check_interaction()

    def focus_style(self):
        for button in self.controls.values():
            button.configure(highlightthickness=1 if self.input_mode == 'keyboard' else 0)

    def check_interaction(self, event=None):
        if self.expanded:
            self.later('interaction', 35, self.sync_pause)

    def sync_pause(self):
        if not self.expanded:
            return
        x, y = self.root.winfo_pointerxy()
        hovered = (self.canvas.winfo_rootx() <= x < self.canvas.winfo_rootx()+self.canvas.winfo_width()
                   and self.canvas.winfo_rooty() <= y < self.canvas.winfo_rooty()+self.canvas.winfo_height())
        focus = self.root.focus_get()
        focused = self.input_mode == 'keyboard' and focus in self.controls.values() and focus.winfo_ismapped()
        self.deadline.pause(hovered or focused)
        self.arm()

    def arm(self):
        self.cancel('dwell')
        if self.expanded and not self.deadline.paused:
            self.later('dwell', max(1, int(self.deadline.left()*1000)), self.collapse)

    def observe(self, result):
        self.badges(result['changed'])
        if result['cards']:
            self.expand()
        elif result.get('content_changed'):
            self.draw()  # A hidden notification must remain hidden on metadata refresh.
        elif not self.state.cards:
            self.expanded = False
            self.progress = 0.0
            self.cancel('dwell')
            self.cancel('animate')
            self.draw()

    def mark_read(self, page, task_id=None):
        self.state.clear(page, task_id)
        self.badges()
        if not self.state.cards:
            self.expanded = False
            self.progress = 0.0
            self.cancel('dwell')
            self.cancel('animate')
        self.draw()

    def expand(self):
        self.cancel('return_focus')
        if not self.state.cards:
            return
        focus = self.root.focus_get()
        if focus not in self.controls.values():
            self.return_focus = focus
        self.expanded = True
        self.deadline.reset()
        self.animate(1.0)
        self.sync_pause()

    def collapse(self):
        keyboard_close = self.input_mode == 'keyboard' and self.root.focus_get() in self.controls.values()
        self.expanded = False
        self.cancel('dwell')
        self.cancel('interaction')
        self.animate(0.0)
        if keyboard_close:
            self.later('return_focus', 280 if not self.view.motion.reduced else 0, self.restore_external_focus)

    def restore_external_focus(self):
        if self.expanded:
            return
        target = self.return_focus
        if target is None or not target.winfo_exists() or not target.winfo_ismapped():
            target = getattr(self.view, 'page_scroll', None) or getattr(self.view, 'page_title', None)
        if target is not None and target.winfo_exists() and target.winfo_ismapped():
            target.focus_set()

    def escape(self, event=None):
        self.keyboard_input(event)
        self.collapse()
        return 'break'

    def next_card(self):
        if len(self.state.cards) > 1:
            self.state.cards.append(self.state.cards.pop(0))
            self.deadline.reset()
            self.draw()
            self.sync_pause()

    def open_task(self):
        if not self.state.cards:
            return
        keyboard = self.input_mode == 'keyboard'
        task_id = self.state.cards[0]['task_id']
        self.mark_read('conversations', task_id)
        self.view.page, self.view.selected_task, self.view.detail_scroll = 'conversations', task_id, 0.0
        self.view.render_page()
        def complete_action():
            if keyboard:
                target = getattr(self.view, 'page_scroll', None) or getattr(self.view, 'page_title', None)
                if target is not None and target.winfo_exists() and target.winfo_ismapped():
                    target.focus_set()
            if self.expanded:
                self.deadline.reset()
                self.sync_pause()
        self.later('detail_focus', 40, complete_action)

    def animate(self, target):
        self.cancel('animate')
        start = self.progress
        if self.view.motion.reduced:
            self.progress = target
            self.draw()
            return
        began = time.monotonic()
        def tick():
            value = min(1.0, (time.monotonic()-began)/.26)
            self.progress = start+(target-start)*(1-(1-value)**3)
            self.draw()
            if value < 1:
                self.later('animate', 16, tick)
            elif self.expanded:
                self.sync_pause()
        tick()

    def badges(self, changed=()):
        counts = self.state.counts()
        for page, button in self.view.nav_buttons.items():
            if page not in counts:
                continue
            base = self.view.t({'conversations':'活动','agents':'Agent','schedules':'定时任务','about':'关于与版本'}[page])
            marker = ('  NEW' if page == 'about' else '  ●') if counts[page] else ''
            button.configure(text=base+marker)
            if not counts[page]:
                self.cancel('badge:'+page)
                button.configure(font=(self.view.font,-16,'bold'))
            if page in changed and page!='about' and not self.view.motion.reduced:
                self.animate_badge(page, button, base, marker)

    def animate_badge(self, page, button, base, marker):
        self.cancel('badge:'+page)
        began=time.monotonic()
        def tick():
            value=min(1.0,(time.monotonic()-began)/.36)
            button.configure(font=(self.view.font,-round(16+math.sin(value*math.pi)*1.4),'bold'))
            if value<1:self.later('badge:'+page,32,tick)
            else:button.configure(font=(self.view.font,-16,'bold'),text=base+marker)
        tick()

    def show_controls(self, names):
        """Keep mapped controls stable during animation and focus events."""
        names=set(names)
        for name in self.visible_controls-names:
            self.controls[name].place_forget()
        self.visible_controls=names

    def draw(self):
        if not self.state.cards or (not self.expanded and self.progress <= 0):
            self.canvas.place_forget()
            self.show_controls(())
            return
        view=self.view
        full=min(510,max(330,self.root.winfo_width()-230))
        p=self.progress
        width=round(156+(full-156)*p)
        height=round(38+132*p)
        self.canvas.place(relx=1.0,x=-18,y=18,anchor='ne',width=width,height=height)
        self.canvas.tk.call('raise',self.canvas._w)
        self.canvas.delete('all')
        shape=lambda x,y,w,h,c,r=20:view.round_shape(self.canvas,x,y,w,h,c,r)
        if p>.68 and len(self.state.cards)>1:
            shape(18,23,width-36,height-24,'#CEDCC5');shape(11,15,width-22,height-23,'#E1EAD9')
        shape(5,12,width-10,height-18,'#E2E8DD');shape(4,8,width-8,height-20,'#D0DCCA')
        shape(3,4,width-6,height-21,'#FFFDF7');shape(6,5,width-12,2,'#FFFFFF',1)
        if p<.68:
            self.show_controls(())
            return  # Only a brief shrinking surface, never a persistent capsule.
        self.show_controls(('close','progress','more') if len(self.state.cards)>1 else ('close','progress'))
        card=self.state.cards[0]
        draw_portrait(self.canvas,card.get('agent_record') or {'avatar':card.get('avatar','mint')},19,31,56)
        en=view.language=='en'
        def text(x,y,value,size=14,color='#244A42',bold=False):
            self.canvas.create_text(x,y,text=value,anchor='nw',fill=color,font=(view.font,-size,'bold' if bold else 'normal'))
        text(89,18,'Task assigned' if en else '新的任务已分派',12,'#6C8D6D',True)
        text(89,40,view.cut_text(card['title'],width-122,17,True),17,bold=True)
        person=card.get('agent_record') or {}
        agent=(person.get('name_en') if en else None) or card['agent']
        agent += f' +{card["participants"]-1}' if card['participants']>1 else ''
        text(89,69,view.cut_text(('Assigned: ' if en else '已登记分派 · ')+agent,width-250,12),12,'#718770')
        self.controls['close'].configure(text='×',font=(view.font,-18),bg='#FFFDF7')
        self.controls['close'].place(x=width-37,y=10,width=26,height=25)
        self.controls['progress'].configure(text='View progress →' if en else '查看进度 →',bg='#244A42',fg='white',activebackground='#365D47',activeforeground='white')
        self.controls['progress'].place(x=width-157,y=67,width=133,height=35)
        if len(self.state.cards)>1:
            text(21,122,'Stacked notifications' if en else '通知已合并叠放',11,'#8C9B83')
            self.controls['more'].configure(text=(f'+{len(self.state.cards)-1} more · next' if en else f'另有 {len(self.state.cards)-1} 条 · 下一条'),bg='#ECF2E4',font=(view.font,-12))
            self.controls['more'].place(x=width-188,y=114,width=164,height=27)
        else:
            text(22,125,'Hides after 5s · hover / keyboard focus to pause' if en else '约 5 秒后隐藏 · 悬停 / 键盘焦点暂停',11,'#8C9B83')
