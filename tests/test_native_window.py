"""No-display Tk/WM event-order tests; no live desktop or system configuration."""
from types import SimpleNamespace
import unittest
from dots_panel.native_window import NativeWindow


class TkError(Exception):
    pass


class Root:
    def __init__(self, supported=True, state_supported=False):
        self.mapped = False
        self.zoomed = False
        self.supported = supported
        self.state_supported = state_supported
        self.bindings = {}
        self.jobs = {}
        self.counter = 0
        self.now = 0
        self.writes = []
        self.requested_geometry = ''
        self.screen = (1364, 1024)
    def geometry(self, value):
        self.requested_geometry = value
        self.writes.append(('geometry', value))
    def minsize(self, *value):self.minimum = value
    def maxsize(self):return (1344, 974)
    def resizable(self, *value):self.resize = value
    def winfo_screenwidth(self):return self.screen[0]
    def winfo_screenheight(self):return self.screen[1]
    def winfo_vrootwidth(self):return self.screen[0]
    def winfo_vrootheight(self):return self.screen[1]
    def winfo_ismapped(self):return self.mapped
    def winfo_geometry(self):return '1344x930+10+32' if self.zoomed else self.requested_geometry+'+92+120'
    def bind(self, event, callback, add=None):self.bindings[event] = callback
    def event(self, event, widget=None):self.bindings[event](SimpleNamespace(widget=self if widget is None else widget))
    def after(self, delay, callback):
        self.counter += 1
        self.jobs[self.counter] = (self.now+delay, callback)
        return self.counter
    def after_idle(self, callback):return self.after(0, callback)
    def after_cancel(self, job):self.jobs.pop(job, None)
    def advance(self, milliseconds=0):
        target = self.now + milliseconds
        for _ in range(100):
            ready = [(when, job) for job,(when, _) in self.jobs.items() if when <= target]
            if not ready:break
            when, job = min(ready)
            self.now = when
            _, callback = self.jobs.pop(job)
            callback()
        else:raise AssertionError('Unbounded loop')
        self.now = target
    def attributes(self, name, *values):
        if not self.supported:raise TkError('unsupported')
        if values:
            self.writes.append((name, values[0], self.mapped))
            # WM acknowledgment happens later, never synchronously.
            self.after(40, lambda:self.ack(values[0]))
        else:return int(self.zoomed)
    def state(self, *values):
        if values:
            if not self.state_supported:raise TkError('unsupported')
            self.writes.append(('state', values[0], self.mapped))
            self.after(40, lambda:self.ack(values[0] == 'zoomed'))
        else:return 'zoomed' if self.zoomed else 'normal'
    def ack(self, zoomed):
        self.zoomed = zoomed
        self.event('<Configure>')


class NativeWindowTests(unittest.TestCase):
    def make(self, **kwargs):
        root = Root(**kwargs)
        reports = []
        window = NativeWindow(root, TkError, reports.append)
        return root, window, reports
    def map(self, root):
        root.mapped = True
        root.event('<Map>')
    def requests(self, root):
        return [entry for entry in root.writes if entry[0] in ('-zoomed', 'state')]
    def test_startup_requests_only_after_root_is_mapped(self):
        root, window, reports = self.make()
        self.assertEqual(self.requests(root), [])
        root.event('<Map>', object());root.advance()
        self.assertEqual(self.requests(root), [])
        self.map(root);self.assertEqual(self.requests(root), [])
        root.advance(50)
        self.assertEqual(self.requests(root), [('-zoomed', True, True)])
        self.assertTrue(window.maximized())
        root.advance(700);self.assertTrue(reports[0]['maximized'])
    def test_user_system_restore_is_never_remaximized_or_warned(self):
        root, window, reports = self.make();self.map(root);root.advance(50)
        root.ack(False);root.advance(2000)
        self.assertFalse(root.zoomed)
        self.assertEqual(len(self.requests(root)), 1)
        self.assertFalse(window.request_unconfirmed)
        # Further Map/Configure events, including remapping, only observe state.
        for _ in range(4):root.event('<Map>');root.event('<Configure>');root.advance(1000)
        self.assertEqual(len(self.requests(root)), 1)
    def test_explicit_restore_cancels_pending_startup_and_confirmation(self):
        root, window, reports = self.make();self.map(root);window.restore();root.advance(1000)
        self.assertEqual(self.requests(root), [('-zoomed', False, True)])
        self.assertFalse(root.zoomed);self.assertFalse(window.request_unconfirmed)
    def test_delayed_mapping_checks_are_bounded(self):
        root, window, reports = self.make();root.event('<Map>');root.advance(1000)
        self.assertEqual(self.requests(root), []);self.assertFalse(root.jobs)
        self.assertEqual(window.startup_checks, 3)
    def test_mapping_transient_event_retries_before_request(self):
        root, window, reports = self.make();root.event('<Map>');root.advance()
        root.mapped=True;root.advance(150)
        self.assertEqual(self.requests(root), [('-zoomed', True, True)])
    def test_unsupported_uses_native_state_fallback(self):
        root, window, reports = self.make(supported=False, state_supported=True)
        self.map(root);root.advance(1000)
        self.assertEqual(self.requests(root), [('state', 'zoomed', True)])
        self.assertTrue(root.zoomed)
        window.toggle();root.advance(50)
        self.assertEqual(self.requests(root)[-1], ('state', 'normal', True))
        self.assertFalse(root.zoomed)
    def test_no_native_support_never_guesses_workarea_or_fullscreen(self):
        root, window, reports = self.make(supported=False);self.map(root);root.advance(1000)
        self.assertTrue(window.request_unconfirmed)
        self.assertEqual(root.writes, [('geometry', '1180x812')])
        self.assertEqual(root.resize, (True, True))
        self.assertEqual(reports[0]['maximum_hint'], (1344, 974))
    def test_native_request_ignored_no_geometry_fallback(self):
        root, window, reports = self.make()
        original = root.attributes
        def ignored(name, *values):
            if values:root.writes.append((name, values[0], root.mapped))
            else:return original(name)
        root.attributes = ignored;self.map(root);root.advance(1000)
        self.assertTrue(window.request_unconfirmed)
        self.assertEqual(root.writes, [('geometry', '1180x812'), ('-zoomed', True, True)])
        self.assertFalse(root.jobs)
    def test_app_toggle_restores_and_maximizes_once_each(self):
        root, window, reports = self.make();self.map(root);root.advance(1000)
        window.toggle();root.advance(1000);self.assertFalse(window.maximized())
        window.toggle();root.advance(1000);self.assertTrue(window.maximized())
        self.assertEqual(len(self.requests(root)), 3)
    def test_destroy_cancels_all_queued_work(self):
        root, window, reports = self.make();self.map(root);root.advance()
        root.event('<Destroy>');root.advance(1000)
        self.assertTrue(window.closed);self.assertFalse(window.jobs)
        self.assertFalse(reports)


if __name__ == '__main__':unittest.main()
