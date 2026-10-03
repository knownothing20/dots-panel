"""Read-only requirement presentation and independent right-edge bookmarks."""
TERMINAL = frozenset(('completed', 'cancelled'))
LABELS = {'received': ('已接收','Received'), 'in_progress': ('进行中','In progress'), 'blocked': ('受阻','Blocked'), 'pending_acceptance': ('待验收','Pending acceptance'), 'completed': ('已完成','Completed'), 'cancelled': ('已取消','Cancelled')}


def requirement_status(value, language='zh'):
    return LABELS.get(value, (value or '未知', value or 'Unknown'))[language == 'en']


def requirement_owner(card, language='zh'):
    owner = card.get('owner') or {}
    if owner.get('status') != 'confirmed':
        return 'Owner unconfirmed' if language == 'en' else '负责人待确认'
    return (owner.get('name_en') if language == 'en' else owner.get('name')) or owner.get('name') or ('Unknown' if language == 'en' else '未知')


def requirement_work(card):
    """Only an explicit linked current-step or latest state evidence, never a heartbeat."""
    states = card.get('status_history') or []
    latest = max(states, key=lambda row: (row.get('observed_at', 0), row.get('id', 0)), default={})
    return card.get('current_step') or latest.get('next_step') or (latest.get('evidence') if latest.get('status') in ('in_progress','blocked') else '') or ''


def requirement_records(snapshot, task_ids):
    return [{'id': card['id'], 'source_id': card['id'], 'key': 'requirement:'+card['id'], 'kind': 'requirement',
             'task_id': card['task_id'], 'created': card.get('observed_at', card.get('created', 0)), 'title': '需求',
             'message': card.get('summary', ''), 'requirement_id': card['id'], 'requirement': card}
            for card in snapshot.get('requirements', []) if card.get('task_id') in task_ids]


class NativeRequirementBookmarks:
    """Places horizontal pills over unused edge space without allocating a content column."""
    def __init__(self, view):
        self.view = view
        self.frame = view.tk.Frame(view.content, bg=view.bg, bd=0)
        self.buttons = {}
        self.cards = []
        self.more = self.pill('',self.show_all)
        self.more.bind('<FocusIn>',self.expand)
        self.expanded = False
        self.frame.bind('<Enter>', self.expand)
        self.frame.bind('<Leave>', self.retract)
        self.frame.bind('<FocusIn>', self.expand)
        self.frame.bind('<Escape>', self.retract)
        self.resize_binding = view.content.bind('<Configure>', self.resize, add='+')
        self.update()

    def pill(self,caption,command):
        view=self.view
        canvas=view.tk.Canvas(self.frame,width=206,height=30,bg=view.bg,highlightthickness=1,highlightbackground=view.bg,highlightcolor=view.accent,bd=0,takefocus=1,cursor='hand2')
        view.round_shape(canvas,0,0,206,30,'#dcece2',radius=14)
        canvas.caption_text=view.cut_text(caption,186,12,True)
        canvas.caption_item=canvas.create_text(10,15,text=canvas.caption_text,anchor='w',font=(view.font,-12,'bold'),fill='#24543c')
        for sequence in ('<Button-1>','<Return>','<space>'):canvas.bind(sequence,lambda event:command())
        return canvas

    def close(self):
        if self.resize_binding:
            try:self.view.content.unbind('<Configure>',self.resize_binding)
            except Exception:pass
            self.resize_binding=None
        if self.frame.winfo_exists():self.frame.destroy()

    def update(self):
        view = self.view
        ids={view.selected_task}
        task=next((t for t in view.snapshot.get('tasks',[]) if t['id']==view.selected_task),{})
        if task.get('activity_kind')=='project':ids.update(t['id'] for t in view.snapshot.get('tasks',[]) if t.get('parent_task_id')==view.selected_task)
        cards = [card for card in view.snapshot.get('requirements', []) if card.get('task_id') in ids and card.get('status') not in TERMINAL]
        self.cards = cards
        ids = {row['id'] for row in cards}
        for key in list(self.buttons):
            if key not in ids:
                self.buttons.pop(key).destroy()
        for index, card in enumerate(cards):
            key = card['id']
            caption = f"{index+1} · {card.get('summary', '')[:22]}"
            if key not in self.buttons:
                button = self.pill(caption,lambda key=key:view.try_open_requirement(key))
                button.pack(anchor='e', pady=3)
                button.bind('<FocusIn>', self.expand)
                button.bind('<Escape>', self.retract)
                self.buttons[key] = button
            view.patch_caption(self.buttons[key],view.cut_text(caption,186,12,True))
        self.resize()

    def expand(self, event=None):
        self.expanded = True
        self.resize()

    def retract(self, event=None):
        self.expanded = False
        self.resize()

    def show_all(self):
        self.view.requirement_list_open=True
        self.view.scroll_positions[self.view.viewport_key()]=0
        self.view.render_page()
        self.view.page_scroll.yview_moveto(0)

    def resize(self, event=None):
        if not self.frame.winfo_exists():return
        if not self.cards:
            self.frame.place_forget()
            return
        available=max(70,self.view.content.winfo_height()-170)
        slots=max(1,int(available//36)-1)
        for index,card in enumerate(self.cards):
            button=self.buttons[card['id']]
            if index<slots:button.pack(anchor='e',pady=3)
            else:button.pack_forget()
        hidden=max(0,len(self.cards)-slots)
        if hidden:
            self.view.patch_caption(self.more,('All requirements' if self.view.language=='en' else '全部需求')+' · '+str(len(self.cards)));self.more.pack(anchor='e',pady=3)
        else:self.more.pack_forget()
        width = self.view.content.winfo_width()
        shown = 214 if width >= 950 or self.expanded else 28
        self.frame.place(relx=1, x=214-shown-14, y=78, anchor='ne', width=214, height=min(len(self.cards)*36,available))
        self.frame.tk.call('raise', self.frame._w)


class NativeRequirementPopover:
    """Read-only preview overlay: never navigates or scrolls the underlying timeline."""
    def __init__(self, view):
        self.view = view
        self.return_focus = view.root.focus_get()
        self.requirement_id = None
        self.surface = None
        self.frame = view.tk.Frame(view.content, bg='#edf5e9', bd=1, relief='solid', highlightthickness=1, highlightbackground='#abc69f')
        header = view.tk.Frame(self.frame, bg='#edf5e9');header.pack(fill='x',padx=12,pady=(10,6))
        self.title = view.label(header,'Requirement preview' if view.language=='en' else '需求详情',15,'#42643d',True,bg='#edf5e9',raw=True)
        self.title.pack(side='left',fill='x',expand=True)
        self.close_button = view.tk.Button(header,text='Close ×' if view.language=='en' else '关闭 ×',command=self.close,bd=0,bg='#dcece2',fg='#24543c',font=(view.font,-12,'bold'),takefocus=1,padx=10,pady=6)
        self.close_button.pack(side='right',padx=(8,0))
        holder = view.tk.Frame(self.frame,bg='#edf5e9');holder.pack(fill='both',expand=True)
        self.canvas = view.tk.Canvas(holder,bg='#edf5e9',bd=0,highlightthickness=0,takefocus=1)
        self.scrollbar = view.ttk.Scrollbar(holder,orient='vertical',command=self.canvas.yview)
        self.scrollbar.pack(side='right',fill='y');self.canvas.pack(side='left',fill='both',expand=True)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.body = view.tk.Frame(self.canvas,bg='#edf5e9')
        self.window = self.canvas.create_window(0,0,anchor='nw',window=self.body)
        self.body.bind('<Configure>',self.layout)
        self.canvas.bind('<Configure>',self.layout)
        self.resize_binding = view.content.bind('<Configure>',self.resize,add='+')
        self.resize()

    def owns(self, widget):
        return widget is self.frame or widget is not None and str(widget).startswith(str(self.frame)+'.')

    def visible(self):
        return bool(self.frame.winfo_exists() and self.frame.winfo_ismapped() and self.surface and self.surface.winfo_ismapped())

    def resize(self, event=None):
        if not self.frame.winfo_exists():return
        width=max(250,min(560,self.view.content.winfo_width()-32))
        height=max(200,min(560,self.view.content.winfo_height()-64))
        self.frame.place(relx=1,x=-16,y=48,anchor='ne',width=width,height=height)
        self.frame.tk.call('raise',self.frame._w)

    def layout(self, event=None):
        if not self.frame.winfo_exists():return
        self.canvas.itemconfigure(self.window,width=max(100,self.canvas.winfo_width()))
        bounds=self.canvas.bbox(self.window)
        if bounds:self.canvas.configure(scrollregion=bounds)

    def show(self, card):
        if self.requirement_id != card['id']:
            if self.surface is not None:self.surface.destroy()
            self.requirement_id=card['id']
            self.surface=self.view.requirement_message(self.body,{'kind':'requirement','created':card.get('observed_at'),'requirement':card})
            self.surface.pack(fill='x',expand=True)
            self.canvas.yview_moveto(0)
        else:self.surface.refresh_requirement(card)
        self.resize();self.view.root.update_idletasks();self.layout()
        self.close_button.focus_set()
        return self.visible()

    def update(self):
        if not self.frame.winfo_exists():return
        card=next((q for q in self.view.snapshot.get('requirements',[]) if q['id']==self.requirement_id),None)
        if card is not None and self.surface is not None:
            self.surface.refresh_requirement(card)
            self.layout()

    def close(self, restore_focus=True):
        if self.resize_binding:
            try:self.view.content.unbind('<Configure>',self.resize_binding)
            except Exception:pass
            self.resize_binding=None
        if self.frame.winfo_exists():self.frame.destroy()
        if getattr(self.view,'requirement_popover',None) is self:self.view.requirement_popover=None
        if restore_focus and self.return_focus is not None:
            try:
                if self.return_focus.winfo_exists():self.return_focus.focus_set()
            except Exception:pass
