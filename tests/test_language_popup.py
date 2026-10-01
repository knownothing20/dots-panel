"""Explicitly reconstructed recovery tests/fake; not the lost original test file.

Contract comes from the retained open_filter_menu fragment and its retained tests.
No Tk window, desktop interaction, or GUI process is created by this fake.
"""
import re
from types import SimpleNamespace
import unittest
from dots_panel.desktop_view import Dashboard


class Widget:
    def __init__(self, *args, **kwargs):
        self.parent = args[0] if args else None
        self.settings = dict(kwargs)
        self.exists = True
        self.mapped = False
        self.jobs = {}
        self.bindings = {}
        self.grabbed = False
        self.focuses = 0
        self.children = []
        self._job_counter = 0
        self._item_counter = 0
        self._x, self._y = 100, 70
        self._width, self._height = kwargs.get('width', 180), kwargs.get('height', 34)
        if isinstance(self.parent, Widget):
            self.parent.children.append(self)

    def overrideredirect(self, value):
        self.settings['overrideredirect'] = value

    def transient(self, parent):
        self.settings['transient'] = parent

    def configure(self, **kwargs):
        self.settings.update(kwargs)

    config = configure

    def cget(self, name):
        return self.settings.get(name)

    def geometry(self, value):
        match = re.fullmatch(r'(\d+)x(\d+)\+(-?\d+)\+(-?\d+)', value)
        if match:
            self._width, self._height, self._x, self._y = map(int, match.groups())
        self.settings['geometry'] = value

    def pack(self, **kwargs):
        self.settings['pack'] = kwargs

    def pack_forget(self):
        self.settings.pop('pack', None)

    def create_window(self, *args, **kwargs):
        self._item_counter += 1
        return self._item_counter

    def create_polygon(self, *args, **kwargs):
        self._item_counter += 1
        return self._item_counter

    def bind(self, sequence, callback, **kwargs):
        self.bindings[sequence] = callback

    def after(self, milliseconds, callback):
        self._job_counter += 1
        key = f'job-{self._job_counter}'
        self.jobs[key] = callback
        return key

    def after_cancel(self, job):
        self.jobs.pop(job, None)

    def run_jobs(self):
        # Run one event-loop batch. Unmapped focus retry stays pending for next batch.
        queued = list(self.jobs.items())
        for key, callback in queued:
            if key in self.jobs:
                self.jobs.pop(key)
                callback()

    def winfo_exists(self):
        return self.exists

    def winfo_viewable(self):
        return self.exists and self.mapped

    def winfo_rootx(self):
        return self._x

    def winfo_rooty(self):
        return self._y

    def winfo_width(self):
        return self._width

    def winfo_height(self):
        return self._height

    def winfo_children(self):
        return list(self.children)

    def grab_set(self):
        self.grabbed = True

    def grab_release(self):
        self.grabbed = False

    def focus_force(self):
        self.focuses += 1
        callback = self.bindings.get('<FocusIn>')
        if callback:
            callback(SimpleNamespace(widget=self))

    focus_set = focus_force

    def destroy(self):
        self.exists = False
        self.grabbed = False
        self.jobs.clear()


class LanguagePopupRecoveryTests(unittest.TestCase):
    def make_viewer(self):
        viewer = Dashboard.__new__(Dashboard)
        viewer.root = SimpleNamespace(winfo_screenwidth=lambda: 1400, winfo_screenheight=lambda: 900)
        viewer.locale_selector = Widget()
        viewer.language_choice = 'auto'
        viewer.bg, viewer.panel, viewer.accent, viewer.tint, viewer.fg, viewer.font = '#fff', '#fff', '#080', '#efe', '#222', 'sans'
        viewer.t = lambda value: value
        viewer.round_shape = lambda *args: None
        choices = []
        viewer.change_language = lambda choice=None: choices.append(choice)
        buttons = []
        def button(*args, **kwargs):
            result = Widget(*args, **kwargs)
            buttons.append(result)
            return result
        viewer.tk = SimpleNamespace(Toplevel=Widget, Canvas=Widget, Frame=Widget, Button=button, TclError=RuntimeError)
        return viewer, buttons, choices

    def test_focus_waits_for_mapping_and_keyboard_chooses_english(self):
        viewer, buttons, choices = self.make_viewer()
        self.assertEqual(viewer.open_language_menu(), 'break')
        popup = viewer.language_popup
        self.assertEqual(len(buttons), 3)
        popup.run_jobs()
        self.assertFalse(popup.grabbed)
        self.assertTrue(popup.jobs)
        popup.mapped = True
        popup.run_jobs()
        self.assertTrue(popup.grabbed)
        self.assertEqual(buttons[0].bindings['<End>'](None), 'break')
        self.assertEqual(buttons[-1].bindings['<Return>'](None), 'break')
        self.assertEqual(choices, ['en'])
        self.assertFalse(popup.exists)
        self.assertFalse(popup.jobs)
        self.assertGreater(viewer.locale_selector.focuses, 0)

    def test_escape_preserves_choice_and_cancels_pending_focus(self):
        viewer, buttons, choices = self.make_viewer()
        viewer.open_language_menu()
        popup = viewer.language_popup
        self.assertTrue(popup.jobs)
        self.assertEqual(popup.bindings['<Escape>'](None), 'break')
        self.assertEqual(choices, [])
        self.assertFalse(popup.jobs)
        self.assertFalse(popup.exists)

    def test_outside_click_dismisses_without_changing_language(self):
        viewer, buttons, choices = self.make_viewer()
        viewer.open_language_menu()
        popup = viewer.language_popup
        popup.bindings['<Button-1>'](SimpleNamespace(x_root=-100, y_root=-100))
        self.assertFalse(popup.exists)
        self.assertEqual(choices, [])


if __name__ == '__main__':
    unittest.main()
