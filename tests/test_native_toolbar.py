"""Folded type selector and informational recovery disclosure behavior."""
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock
from dots_panel.desktop_view import Dashboard
from test_language_popup import Widget


class NativeToolbarTests(TestCase):
    def view(self, language='zh'):
        v=Dashboard.__new__(Dashboard);v.root=SimpleNamespace(winfo_screenwidth=lambda:1400,winfo_screenheight=lambda:900)
        v.type_filter_button=Widget();v.more_filter_button=Widget();v.workspace_filter='unfinished';v.collaboration_mode_filter='all';v.rows=[]
        v.bg,v.panel,v.accent,v.tint,v.fg,v.font='#fff','#fff','#080','#efe','#222','sans';v.t=lambda x:x;v.round_shape=Mock();v.render_page=Mock();v.language=language
        buttons=[]
        def button(*args,**kwargs):
            item=Widget(*args,**kwargs);buttons.append(item);return item
        v.tk=SimpleNamespace(Toplevel=Widget,Canvas=Widget,Frame=Widget,Button=button,TclError=RuntimeError)
        return v,buttons
    def test_type_menu_defaults_folded_then_keyboard_selection(self):
        for language in ('zh','en'):
            v,buttons=self.view(language);v.open_filter_menu('type');popup=v.filter_popup
            self.assertEqual(len(buttons),4);self.assertTrue(v.filter_menu_open)
            self.assertLess(popup.winfo_height(),220)
            popup.mapped=True;popup.run_jobs();self.assertTrue(popup.grabbed)
            buttons[0].bindings['<End>'](None);buttons[-1].bindings['<Return>'](None)
            self.assertEqual(v.collaboration_mode_filter,'project')
            self.assertEqual(v.workspace_filter,'unfinished')
            self.assertFalse(v.filter_menu_open);v.render_page.assert_called_once()
            self.assertGreater(v.type_filter_button.focuses,0)
    def test_cancel_does_not_rebuild_page_or_change_filter(self):
        v,buttons=self.view();v.collaboration_mode_filter='team';v.open_filter_menu('type')
        popup=v.filter_popup;popup.bindings['<Escape>'](None)
        self.assertEqual(v.collaboration_mode_filter,'team');v.render_page.assert_not_called()
        self.assertFalse(popup.jobs);self.assertFalse(popup.exists)
    def test_recovery_notice_collapsed_until_explicit_action(self):
        v,buttons=self.view();v.snapshot={'recovery':{'notice_zh':'真实恢复边界说明','notice_en':'Recovery provenance'}};v.page='overview';v.selected_task=None
        v.recovery_banner=Widget();v.recovery_info_button=Widget();v.content=Widget();v.patch_caption=Mock()
        v.update_recovery_notice()
        self.assertEqual(v.recovery_banner.cget('text'),'真实恢复边界说明')
        self.assertNotIn('pack',v.recovery_banner.settings)
        self.assertIn('pack',v.recovery_info_button.settings)
        v.toggle_recovery_info();self.assertIn('pack',v.recovery_banner.settings)
        v.toggle_recovery_info();self.assertNotIn('pack',v.recovery_banner.settings)
        v.render_page.assert_not_called()
    def test_notice_refresh_preserves_open_state_and_detail_is_minimal(self):
        v,buttons=self.view('en');v.snapshot={'recovery':{'notice_en':'Recovery provenance'}};v.page='overview';v.selected_task=None
        v.recovery_banner=Widget();v.recovery_info_button=Widget();v.content=Widget();v.patch_caption=Mock();v.recovery_info_expanded=True
        v.update_recovery_notice();self.assertIn('pack',v.recovery_banner.settings)
        for _ in range(4):v.update_recovery_notice()
        self.assertTrue(v.recovery_info_expanded)
        v.page='conversations';v.selected_task='task';v.update_recovery_notice()
        self.assertNotIn('pack',v.recovery_banner.settings);self.assertNotIn('pack',v.recovery_info_button.settings)
        v.selected_task=None;v.update_recovery_notice();self.assertIn('pack',v.recovery_banner.settings)
        v.snapshot={};v.update_recovery_notice();self.assertNotIn('pack',v.recovery_info_button.settings)
        v.render_page.assert_not_called()
