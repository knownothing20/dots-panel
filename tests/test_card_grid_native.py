"""Native layout integration; runs on an existing permitted desktop, skips headless."""
import os
import tempfile
import unittest
from pathlib import Path

from dots_panel.app import Store, Metrics
from dots_panel.desktop_view import Dashboard, ReadOnlyStore

@unittest.skipUnless(os.environ.get('DISPLAY'), 'existing desktop required')
class NativeCardGridTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from tkinter import ttk
        self.tk = tk
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name)/'data')
        for index in range(7):
            self.store.agent_register('agent-'+str(index), 'Synthetic agent '+str(index))
        self.root = tk.Tk()
        self.viewer = Dashboard(self.root, ReadOnlyStore(self.store.directory), Metrics(self.store.directory), tk, ttk, 'en')
        self.root.attributes('-zoomed', False)
        self.viewer.navigate('agents')
    def tearDown(self):
        for job in self.root.tk.call("after", "info"):
            self.root.after_cancel(job)
        self.root.destroy()
        self.temp.cleanup()
    def settle(self, width):
        self.root.geometry(str(width)+'x850')
        for _ in range(8):
            self.root.update_idletasks(); self.root.update()
    def grids(self, widget=None):
        widget = widget or self.root
        found = [widget] if hasattr(widget, 'card_items') else []
        for child in widget.winfo_children():
            found.extend(self.grids(child))
        return found
    def test_responsive_columns_and_real_card_containment(self):
        for width, columns in ((1260,3),(1000,2),(760,1)):
            self.settle(width)
            grid = self.grids()[0]
            self.assertEqual(grid.card_columns, columns)
            self.assertEqual(len(grid.card_items), 7)
            for surface in grid.card_items:
                body = next(w for w in surface.winfo_children() if isinstance(w,self.tk.Frame))
                self.assertLessEqual(body.winfo_y()+body.winfo_height(), surface.winfo_height())
                for label in body.winfo_children():
                    self.assertLessEqual(label.winfo_y()+label.winfo_height(),body.winfo_height())
    def test_keyboard_details_and_refresh_keep_selection(self):
        self.settle(1260)
        surface = self.grids()[0].card_items[0]
        surface.focus_force(); surface.event_generate('<Return>'); self.root.update()
        self.assertEqual(self.viewer.selected_agent,'agent-0')
        self.viewer.refresh(); self.root.update()
        self.assertEqual(self.viewer.selected_agent,'agent-0')
        self.viewer.open_agent(None); self.settle(1000)
        self.assertEqual(self.grids()[0].card_columns,2)

if __name__ == '__main__': unittest.main()
