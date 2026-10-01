import inspect
import unittest
from types import SimpleNamespace
from dots_panel.desktop_view import Dashboard, workspace_rows, UNFINISHED_STATUSES
from test_language_popup import Widget


class StatusFilterTests(unittest.TestCase):
    def test_aggregate_never_changes_card_states(self):
        statuses = list(UNFINISHED_STATUSES) + ['succeeded','failed','cancelled']
        rows = [{'status':s, 'values':('Alpha','Project')} for s in statuses]
        self.assertEqual({r['status'] for r in workspace_rows(rows,'unfinished')},UNFINISHED_STATUSES)
        self.assertEqual(len(workspace_rows(rows,'all')),9)
        for status in statuses:
            self.assertEqual([r['status'] for r in workspace_rows(rows,status)],[status])
        self.assertEqual(workspace_rows(rows,'unfinished','missing'),[])
        self.assertEqual(len(workspace_rows(rows,'unfinished','ALPHA')),6)

    def test_one_row_primary_filters(self):
        source=inspect.getsource(Dashboard.workspace_toolbar)
        self.assertNotIn('index//5',source)
        self.assertIn('"unfinished"',source)
        self.assertIn('button.pack(side="left"',source)
        self.assertIn('self.workspace_filter not in self.filter_buttons',source)
        self.assertIn('filter_menu_open',inspect.getsource(Dashboard.refresh))

    def test_more_popup_keyboard_selection_and_dismissal(self):
        viewer=Dashboard.__new__(Dashboard)
        viewer.root=SimpleNamespace(winfo_screenwidth=lambda:1400,winfo_screenheight=lambda:900)
        viewer.more_filter_button=Widget()
        viewer.workspace_filter='all'
        viewer.rows=[]
        viewer.bg,viewer.panel,viewer.accent,viewer.tint,viewer.fg,viewer.font='#fff','#fff','#080','#efe','#222','sans'
        viewer.t=lambda s:s
        viewer.round_shape=lambda *args:None
        renders=[]
        viewer.render_page=lambda:renders.append(True)
        buttons=[]
        def button(*args,**kwargs):
            result=Widget(*args,**kwargs);buttons.append(result);return result
        viewer.tk=SimpleNamespace(Toplevel=Widget,Canvas=Widget,Frame=Widget,Button=button,TclError=RuntimeError)
        viewer.open_filter_menu()
        popup=viewer.filter_popup
        self.assertTrue(viewer.filter_menu_open)
        self.assertEqual(len(buttons),9)
        popup.mapped=True;popup.run_jobs()
        self.assertTrue(popup.grabbed)
        self.assertEqual(buttons[0].bindings['<End>'](None),'break')
        self.assertEqual(buttons[-1].bindings['<Return>'](None),'break')
        self.assertEqual(viewer.workspace_filter,'failed')
        self.assertFalse(viewer.filter_menu_open)
        self.assertFalse(popup.exists)
        self.assertTrue(renders)
        viewer.open_filter_menu();popup=viewer.filter_popup
        self.assertEqual(popup.bindings['<Escape>'](None),'break')
        self.assertEqual(viewer.workspace_filter,'failed')
        self.assertFalse(popup.jobs)
        self.assertGreater(viewer.more_filter_button.focuses,0)

if __name__=='__main__':unittest.main()
