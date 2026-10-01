import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from dots_panel.desktop_view import Dashboard
from dots_panel.outputs import output_main_text


def summary(count=2):
    return {'count':count,'kinds':[{'kind':'video','count':count}],'main':{'id':'a','title':'Example.mp4','filename':'registered.mp4','designation':'draft','delivery':[]}}

class OutputUiTests(unittest.TestCase):
    def view(self):
        v=Dashboard.__new__(Dashboard);v.tk=Mock();v.root=Mock();v.motion=Mock();v.language='zh';v.bg='white';v.panel='white';v.accent='green';v.muted='gray';v.fg='black';v.font='sans';v.live_updates=[]
        v.snapshot={'output_summaries':{'task':summary()}};v.label=Mock(return_value=Mock());v.filter_chip=Mock(return_value=Mock());v.render_page=Mock();return v
    def test_detail_outputs_actions_bound_to_exact_task(self):
        v=self.view();v.open_task_files=Mock();v.open_task_outputs=Mock();v.render_output_bar(Mock(),'task',detail=True)
        labels=[call.args[1] for call in v.label.call_args_list];self.assertTrue(any('成果 2' in label for label in labels));self.assertTrue(any('草稿' in label and '已归档' in label for label in labels))
        for call in v.filter_chip.call_args_list:call.args[2]()
        v.open_task_files.assert_called_once_with('task');v.open_task_outputs.assert_called_once_with('task')
    def test_zero_outputs_have_no_folder_action(self):
        v=self.view();v.snapshot={};v.render_output_bar(Mock(),'task',detail=True)
        labels=[call.args[1] for call in v.filter_chip.call_args_list];self.assertEqual(labels,['查看文件'])
    def test_file_jump_selects_existing_files_tab(self):
        v=self.view();v.open_task_files('task');self.assertEqual((v.page,v.selected_task,v.detail_tab),('conversations','task','files'));v.render_page.assert_called_once()
    def test_canvas_exposes_count_and_real_file_button(self):
        v=self.view();v.surface_layers=Mock();v.round_shape=Mock();v.pill=Mock();v.cut_text=lambda value,*args:value
        row={'id':'task','status':'pending','run':None,'warning':'','values':('Task','Project','Pending','Testing','—','Stamp')}
        v.airy_task_card(Mock(),row,0);canvas=v.tk.Canvas.return_value
        draw=next(call.args[1] for call in canvas.bind.call_args_list if call.args[0]=='<Configure>')
        with patch('tkinter.font.Font') as font:font.return_value.measure.return_value=30;draw(SimpleNamespace(width=310))
        self.assertTrue(any('成果 2' in call.kwargs.get('text','') for call in canvas.create_text.call_args_list));canvas.create_window.assert_called();self.assertIn(('task','files'),v.output_buttons)
    def test_registered_actions_support_keyboard_and_refresh_focus(self):
        source=inspect.getsource(Dashboard.filter_chip);self.assertIn('<Return>',source);self.assertIn('<space>',source)
        source=inspect.getsource(Dashboard.render_page);self.assertIn('output_focus',source);self.assertIn('output_target.focus_set()',source)
    def test_summary_never_equates_archive_to_acceptance(self):
        self.assertNotIn('验收',output_main_text(summary()));self.assertIn('Draft',output_main_text(summary(),'en'))
    def test_files_first_when_more_information_collapsed(self):
        v=self.view();v.content=Mock();v.selected_task='task';v.detail_tab='files';v.detail_meta=False
        v.rows=[{'id':'task','status':'running','values':('Task','Project','Running','Testing','—','Stamp'),'run':{'status':'running','lifecycle_reason':'LONG PRIVATE REASON','next_step':'LONG NEXT','lifecycle_evidence':'LONG EVIDENCE'}}]
        v.scroll_area=Mock(return_value=Mock());v.render_task_files=Mock();v.render_output_bar=Mock()
        v.render_conversation();v.render_task_files.assert_called_once()
        self.assertFalse(any('LONG ' in str(call.args[1]) for call in v.label.call_args_list))
