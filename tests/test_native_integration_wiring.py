"""New integration checks that call native renderers instead of checking presence alone."""
from unittest import TestCase
from unittest.mock import Mock
from dots_panel.desktop_view import Dashboard, PAGE_NAMES

class NativeIntegrationWiringTests(TestCase):
    def viewer(self):
        view=Dashboard.__new__(Dashboard)
        view.motion=Mock()
        view.tk=Mock();view.root=Mock();view.root.winfo_children.return_value=[]
        view.t=lambda value,**kwargs:value
        view.label=Mock(return_value=Mock());view.button=Mock(return_value=Mock());view.filter_chip=Mock(return_value=Mock())
        view.bg='white';view.fg='black';view.muted='gray';view.accent='green';view.panel='white';view.tint='white'
        view.language='zh';view.language_choice='zh';view.snapshot={};view.render_page=Mock()
        return view
    def test_shell_has_live_global_manual_refresh(self):
        view=self.viewer();view.refresh=Mock();view.build_shell()
        self.assertTrue(any(call.args[1]=='↻ 刷新' and call.args[2] is view.refresh for call in view.filter_chip.call_args_list))
        self.assertEqual(PAGE_NAMES['about'],'关于与版本')
    def test_overview_omits_attention_renderer(self):
        view=self.viewer();view.workspace_toolbar=Mock();area=Mock();view.scroll_area=Mock(return_value=area)
        view.render_attention=Mock();view.rows=[];view.workspace_filter='all';view.search_query=Mock();view.search_query.get.return_value=''
        view.card=Mock(return_value=(Mock(),Mock()));view.resource_card=Mock(return_value=Mock());view.schedules_summary_card=Mock(return_value=Mock())
        view.render_overview();view.render_attention.assert_not_called()
    def test_home_removal_preserves_waiting_lifecycle(self):
        from dots_panel.desktop_view import task_rows
        snapshot={'tasks':[{'id':'task','name':'Synthetic','project':'Test','latest_status':'waiting_user'}],'runs':[{'id':'run','task_id':'task','status':'waiting_user','started':1,'updated':1,'lifecycle_reason':'Review scope','next_step':'Decide'}]}
        row=task_rows(snapshot, now=2)[0]
        self.assertEqual(row['status'],'waiting_user')
        self.assertEqual(row['run']['lifecycle_reason'],'Review scope')
        self.assertEqual(row['run']['next_step'],'Decide')
        self.assertFalse(hasattr(Dashboard,'render_attention'))
    def test_health_shows_actual_last_successful_sample(self):
        view=self.viewer();view.health=Mock();view.read_error=False;view.preference_error=False;view.last_successful_refresh=1
        view.update_health();label=view.health.configure.call_args.kwargs['text'];self.assertIn('每 5 秒 · 最近刷新',label)
        view.read_error=True;view.update_health();self.assertIn('刷新失败',view.health.configure.call_args.kwargs['text'])
    def test_software_details_expand_without_starting_services(self):
        view=self.viewer();view.scroll_area=Mock(return_value=Mock());view.compact_row=Mock(return_value=Mock())
        view.snapshot={'software':[{'id':'panel','name':'Panel','kind':'dots-panel','description':'Description','available':True,'version':'0.2.0','controls':['close_current_viewer']}]}
        view.expanded_software={'panel'};view.render_software()
        labels=[str(call.args[1]) for call in view.label.call_args_list]
        self.assertTrue(any('简介: Description' in label for label in labels));self.assertTrue(any('类型: dots-panel' in label for label in labels))
        self.assertTrue(any(call.args[2]==view.close_viewer for call in view.filter_chip.call_args_list))
        view.toggle_registry_detail('software','panel');self.assertEqual(view.expanded_software,set());view.render_page.assert_called()
    def test_schedule_expansion_shows_registry_boundary(self):
        view=self.viewer();view.scroll_area=Mock(return_value=Mock());view.compact_row=Mock(return_value=Mock())
        view.snapshot={'schedules':[{'id':'schedule','name':'Schedule','project':'Example','source':'manual','state':'disconnected','next_run':None,'updated':1}]}
        view.expanded_schedules={'schedule'};view.render_schedules()
        labels=[str(call.args[1]) for call in view.label.call_args_list]
        self.assertTrue(any('来源: manual' in label for label in labels));self.assertTrue(any('登记不会创建、启动或恢复' in label for label in labels))
    def test_close_viewer_cancel_does_not_close(self):
        from unittest.mock import patch
        view=self.viewer()
        with patch('tkinter.messagebox.askyesno',return_value=False):view.close_viewer()
        view.root.destroy.assert_not_called()
    def test_activity_rows_render_recorded_owner(self):
        view=self.viewer();view.workspace_toolbar=Mock();view.scroll_area=Mock(return_value=Mock());view.compact_row=Mock(return_value=Mock());view.workspace_filter='all';view.search_query=Mock();view.search_query.get.return_value=''
        view.snapshot={'agents':[{'id':'owner','name':'Example Owner','status':'idle','observed_at':1}],'agent_assignments':[{'agent_id':'owner','task_id':'task'}]}
        view.rows=[{'id':'task','status':'pending','warning':'','values':('Task','Project','Pending','Testing','—','Stamp')}]
        view.render_conversation_list();summary=view.compact_row.call_args.args[2];self.assertIn('面板编号 194b0635',summary);self.assertIn('空闲',summary)
    def test_overview_canvas_draws_recorded_owner(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        view=self.viewer();view.live_updates=[];view.font='sans';view.surface_layers=Mock();view.round_shape=Mock();view.pill=Mock();view.cut_text=lambda value,*args:value
        view.snapshot={'agents':[{'id':'owner','name':'Example Owner','status':'idle','observed_at':1}],'agent_assignments':[{'agent_id':'owner','task_id':'task'}],'activity':[]}
        row={'id':'task','status':'pending','run':None,'warning':'','values':('Task','Project','Pending','Testing','—','Stamp')}
        view.airy_task_card(Mock(),row,0);canvas=view.tk.Canvas.return_value
        draw=next(call.args[1] for call in canvas.bind.call_args_list if call.args[0]=='<Configure>')
        with patch('tkinter.font.Font') as font:
            font.return_value.measure.return_value=40;draw(SimpleNamespace(width=500))
        texts=[call.kwargs.get('text','') for call in canvas.create_text.call_args_list];self.assertTrue(any('面板编号 194b0635' in text and '空闲' in text for text in texts))
    def test_image_preview_geometry_fits_landscape_and_portrait(self):
        from dots_panel.desktop_view import image_preview_geometry
        for image in ((1672,941),(941,1672),(100,3000)):
            for screen in ((1280,900),(1920,1080),(640,480)):
                width,height,factor=image_preview_geometry(*image,*screen)
                self.assertLess(width,screen[0]);self.assertLess(height,screen[1]);self.assertGreaterEqual(factor,1)
                self.assertLessEqual(image[0]/factor,width-35);self.assertLessEqual(image[1]/factor,height-100)
    def test_image_preview_invalid_geometry_rejected(self):
        from dots_panel.desktop_view import image_preview_geometry
        with self.assertRaises(ValueError):image_preview_geometry(0,100,1280,900)
