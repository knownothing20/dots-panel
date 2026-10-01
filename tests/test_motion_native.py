"""Real Tk interaction checks, skipped when no permitted desktop is attached."""
import os
import tempfile
import unittest
from pathlib import Path
from dots_panel.app import Store, Metrics
from dots_panel.desktop_view import Dashboard, ReadOnlyStore

@unittest.skipUnless(os.environ.get('DISPLAY'), 'existing desktop required')
class NativeMotionTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from tkinter import ttk
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name)/'data')
        self.root = tk.Tk()
        self.viewer = Dashboard(self.root, ReadOnlyStore(self.store.directory), Metrics(self.store.directory), tk, ttk, 'en')
        self.root.update()
    def tearDown(self):
        self.viewer.motion.cancel_all()
        for job in self.root.tk.call('after','info'):
            self.root.after_cancel(job)
        self.root.destroy()
        self.temp.cleanup()
    def test_rapid_hover_page_refresh_and_focus(self):
        self.viewer.motion.cancel_all()
        chip = self.viewer.refresh_button
        for _ in range(50):
            chip.event_generate('<Enter>');chip.event_generate('<Leave>')
        self.assertLessEqual(len(self.viewer.motion.jobs),1)
        chip.focus_force()
        self.root.update_idletasks()
        self.assertEqual(int(chip.cget('highlightthickness')),1)
        self.viewer.navigate('settings')
        self.assertFalse(self.viewer.motion.jobs)
        self.viewer.refresh()
        self.assertFalse(self.viewer.motion.jobs)
    def test_reduced_motion_settings_and_rebuild(self):
        self.viewer.navigate('settings')
        self.viewer.motion_preference.set(True)
        self.viewer.change_motion()
        self.assertTrue(self.viewer.motion.reduced)
        self.viewer.refresh_button.event_generate('<Enter>')
        self.assertFalse(self.viewer.motion.jobs)
        self.viewer.motion_preference.set(False)
        self.viewer.change_motion()
        self.assertFalse(self.viewer.motion.reduced)

if __name__ == '__main__': unittest.main()
