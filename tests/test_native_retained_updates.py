"""Headless stateful widget tests for non-destructive background updates."""
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from dots_panel.desktop_view import Dashboard,RetainedCanvas,collaboration_actor,PAGE_NAMES

class Widget:
    def __init__(self,parent=None,**options):
        self.master=parent;self.options=dict(options);self.children=[];self.exists=True;self.bindings={};self.configurations=[];self.managed=False;self.fraction=(0,1);self.deleted=0
        if isinstance(parent,Widget):parent.children.append(self)
    def pack(self,**kwargs):self.managed=True
    def pack_forget(self):self.managed=False
    def place(self,**kwargs):self.managed=True
    def place_forget(self):self.managed=False
    def grid(self,**kwargs):self.managed=True
    def configure(self,**kwargs):self.options.update(kwargs);self.configurations.append(kwargs)
    config=configure
    def cget(self,key):return self.options.get(key,'white' if key=='bg' else 150)
    def bind(self,key,callback,**kwargs):self.bindings[key]=callback
    def destroy(self):self.exists=False;self.deleted+=1
    def winfo_exists(self):return self.exists
    def winfo_children(self):return [c for c in self.children if c.exists]
    def winfo_width(self):return 800
    def winfo_height(self):return 600
    def winfo_reqheight(self):return 1000
    def winfo_y(self):return 0
    def winfo_manager(self):return 'pack' if self.managed else ''
    def yview(self):return self.fraction
    def yview_moveto(self,value):self.fraction=(max(0,value-.2),value)
    def canvasy(self,value):return self.fraction[0]*1000
    def focus_set(self):pass
    def insert(self,*args):self.source=args[-1]
    def count(self,*args):return (1,)
    def grid_columnconfigure(self,*args,**kwargs):pass
    columnconfigure=grid_columnconfigure

class Canvas(Widget):
    def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self.items={};self.serial=0;self.item_changes=[];self.item_deletions=[]
    def create(self,kind,coords,options):
        self.serial+=1;self.items[self.serial]=[kind,coords,dict(options)];return self.serial
    def __getattr__(self,name):
        if name.startswith('create_'):return lambda *args,**kwargs:self.create(name,args,kwargs)
        if name in ('tag_bind','tag_raise','addtag_withtag'):return lambda *args,**kwargs:None
        raise AttributeError(name)
    def delete(self,key):
        self.item_deletions.append(key)
        if key=='all':self.items.clear()
        else:self.items.pop(key,None)
    def coords(self,key,*args):self.items[key][1]=args
    def itemconfigure(self,key,**kwargs):self.items[key][2].update(kwargs);self.item_changes.append((key,kwargs))
    def find_all(self):return tuple(self.items)

class RetainedUpdateTests(unittest.TestCase):
    def view(self):
        v=Dashboard.__new__(Dashboard);v.root=Mock();v.root.focus_get.return_value=None;v.root.after_idle=Mock(return_value='idle');v.tk=SimpleNamespace(Frame=Widget,Canvas=Canvas,Label=Widget,Text=Widget,Button=Widget);v.ttk=Mock();v.content=Widget();v.language='en';v.timezone='UTC';v.font='sans';v.bg=v.panel=v.tint='white';v.fg='black';v.accent='green';v.muted='gray';v.live_updates=[];v.output_buttons={};v.filter_chip=lambda parent,text,action,selected=False:Widget(parent,text=text,command=action);v.button=lambda parent,text,action,primary=False:Widget(parent,text=text,command=action);v.render_page=Mock();v.cut_text=lambda text,*args:text;v.surface_layers=Mock();return v
    def test_canvas_retains_item_and_embedded_window_identity(self):
        canvas=Canvas();button=Widget()
        def paint(text):
            with RetainedCanvas(canvas) as c:
                c.delete('all');c.create_text(10,10,text=text);c.create_window(20,20,window=button)
        paint('Running');ids=tuple(canvas.items);paint('Running')
        self.assertEqual(tuple(canvas.items),ids);self.assertEqual(canvas.item_changes,[]);self.assertEqual(canvas.item_deletions,[])
        paint('Done');self.assertEqual(tuple(canvas.items),ids);self.assertEqual(canvas.item_changes,[(ids[0],{'text':'Done'})]);self.assertEqual(button.deleted,0)
    def test_four_identical_polls_never_rebuild_any_page(self):
        for page in PAGE_NAMES:
            v=self.view();v.page=page;v.selected_task=None;v.workspace_filter='all';v.search_query=SimpleNamespace(get=lambda:'');v.snapshot={'tasks':[],'runs':[]};v.store=SimpleNamespace(snapshot=lambda:copy.deepcopy(v.snapshot));v.metrics=SimpleNamespace(collect=lambda:{});v.update_health=Mock();v.scroll_dragging=False;v.last_render_signature=v.view_signature();local=Mock();v.live_updates=[local]
            for _ in range(4):v.refresh()
            v.render_page.assert_not_called();self.assertEqual(local.call_count,4,page)
    def test_each_secondary_page_ignores_unrelated_activity_changes(self):
        for page in ('software','schedules','rules','about','settings'):
            v=self.view();v.page=page;v.selected_task=None;v.workspace_filter='all';v.search_query=SimpleNamespace(get=lambda:'');v.snapshot={'activity':[{'message':'one'}]};before=v.view_signature();v.snapshot['activity'].append({'message':'two'});self.assertEqual(v.view_signature(),before,page)
    def test_changed_page_uses_local_handler_not_full_render(self):
        v=self.view();v.page='overview';v.selected_task=None;v.workspace_filter='all';v.search_query=SimpleNamespace(get=lambda:'');v.snapshot={'tasks':[]};v.last_render_signature=v.view_signature();v.store=SimpleNamespace(snapshot=lambda:{'tasks':[],'activity':[{'id':1}]});v.metrics=SimpleNamespace(collect=lambda:{});v.scroll_dragging=False;v.update_health=Mock();v.background_refresh=Mock();v.live_updates=[v.background_refresh]
        v.refresh();v.render_page.assert_not_called();v.background_refresh.assert_called_once()
    def test_resources_update_existing_items_only(self):
        v=self.view();v.metric_values={'cpu_percent':10,'memory_total':100,'memory_available':50,'disk_used':25,'disk_total':100};card=v.resource_card(Widget());card.bindings['<Configure>'](SimpleNamespace(width=600));ids=tuple(card.items);deleted=list(card.item_deletions)
        v.metric_values={**v.metric_values,'cpu_percent':22};v.live_updates[0]()
        self.assertEqual(tuple(card.items),ids);self.assertEqual(card.item_deletions,deleted);self.assertTrue(any(options.get('text')=='22%' for _,options in card.item_changes))
        changes=len(card.item_changes);v.live_updates[0]();self.assertEqual(len(card.item_changes),changes)
    def test_registry_status_only_keeps_card_and_controls(self):
        v=self.view();grid=Widget();grid.card_items=[];grid.reflow_cards=Mock();v.card_grid=lambda *args,**kwargs:grid;boxes=[]
        def card(parent,title,summary,status):
            box=Widget();box.surface=Widget();box.title_label=Widget(text=title);box.summary_label=Widget(text=summary);box.status_label=Widget(text=status);boxes.append(box);return box
        v.compact_row=card;rows=[{'id':'a','status':'running'}]
        reconcile=v.keyed_registry(Widget(),lambda:rows,lambda r:{'title':'same','summary':'same','status':r['status'],'details':[('evidence','same')],'actions':[('details','Details',lambda:None)]})
        first=boxes[0];controls=list(first.children);rows[0]['status']='done';reconcile()
        self.assertEqual(len(boxes),1);self.assertEqual(first.status_label.options['text'],'done');self.assertEqual(first.title_label.configurations,[]);self.assertEqual(first.summary_label.configurations,[]);self.assertEqual(first.surface.deleted,0);self.assertEqual(first.children,controls)
    def test_anonymous_is_fixed_neutral_without_invented_role(self):
        actor=collaboration_actor({'attribution':None},{'agents':[{'id':'owner'}]},'en');self.assertEqual(actor['label'],'Anonymous');self.assertEqual(actor['role'],'');self.assertFalse(actor['known']);self.assertIsNone(actor['agent'])
    def test_timeline_keeps_old_widget_and_buffers_off_bottom(self):
        v=self.view();v.selected_task='task';v.page='conversations';v.detail_tab='timeline';v.detail_meta=False
        v.snapshot={'tasks':[{'id':'task','name':'Task'}],'runs':[{'id':'r','task_id':'task','status':'running','started':1}]};v.rows=[{'id':'task','values':['Task','','Running','','','Stamp'],'run':{'status':'running'}}]
        v.page_scroll=Canvas();area=Widget();v.scroll_area=lambda:area;v.render_conversation_filters=Mock();v.store=Mock();v.card=lambda parent,*args,**kwargs:(Canvas(parent),Widget(parent));v.detail_paragraph=lambda parent,message:Widget(parent,text=message)
        old={'id':1,'key':'activity:1','kind':'activity','task_id':'task','created':1,'stage':'implementation','message':'old','attribution':None}
        data=lambda rows:{'rows':rows,'total':len(rows),'limit':100,'offset':0,'has_more':False}
        v.store.collaboration_timeline.return_value=data([old]);v.render_conversation();first=v.conversation_anchors['activity:1']
        new={**old,'id':2,'key':'activity:2','created':2,'message':'new'};v.store.collaboration_timeline.return_value=data([new,old]);v.page_scroll.fraction=(.8,1);v.background_refresh()
        self.assertIs(v.conversation_anchors['activity:1'],first);self.assertEqual(first.deleted,0);self.assertIn('activity:2',v.conversation_anchors)
        third={**old,'id':3,'key':'activity:3','created':3,'message':'third'};v.store.collaboration_timeline.return_value=data([third,new,old]);v.page_scroll.fraction=(.2,.5);v.background_refresh()
        self.assertNotIn('activity:3',v.conversation_anchors);self.assertIs(v.conversation_anchors['activity:1'],first);v.render_page.assert_not_called()
        hint=next(w for w in v.content.children if 'new records' in str(w.options.get('text','')));self.assertTrue(hint.managed);hint.options['command']();self.assertIn('activity:3',v.conversation_anchors);self.assertFalse(hint.managed)

if __name__=='__main__':unittest.main()
