"""One-shot, mapped Tk maximization without changing desktop/window-manager settings.

Tk's public screen/vroot/maxsize values are not an OS work-area API. Maximization
therefore remains a native WM request: no fullscreen or guessed screen rectangle
is used as a fallback, so panels and docks remain managed by the WM.
"""
import json
import sys


class NativeWindow:
    def __init__(self, root, error_type, report=None):
        self.root, self.error_type = root, error_type
        self.report = report or self._report
        self.listener = None
        self.closed = False
        self.startup_started = False
        self.startup_sent = False
        self.startup_checks = 0
        self.generation = 0
        self.acknowledged_generation = None
        self.jobs = set()
        self.configure_job = None
        self.last_state = None
        self.request_unconfirmed = False
        # These are normal/restored dimensions, never a maximized-size limit.
        width, height = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{max(1, min(1180, width-80))}x{max(1, min(812, height-120))}")
        root.minsize(min(760, max(1, width-80)), min(620, max(1, height-120)))
        root.resizable(True, True)
        root.bind('<Map>', self._mapped, add='+')
        root.bind('<Configure>', self._configured, add='+')
        root.bind('<Destroy>', self._destroyed, add='+')
        if root.winfo_ismapped():
            self._mapped(None)

    @staticmethod
    def _report(data):
        # No paths, task contents, machine identity or display address are logged.
        print('Native window: '+json.dumps(data, sort_keys=True), file=sys.stderr)

    def _later(self, delay, callback):
        if self.closed:
            return None
        holder = {}
        def run():
            self.jobs.discard(holder['id'])
            if not self.closed:
                callback()
        job = self.root.after_idle(run) if delay is None else self.root.after(delay, run)
        holder['id'] = job
        self.jobs.add(job)
        return job

    def maximized(self):
        try:
            value = self.root.attributes('-zoomed')
            return str(value).lower() in ('1', 'true')
        except self.error_type:
            try:
                return self.root.state() == 'zoomed'
            except self.error_type:
                return False

    def observe(self):
        state = self.maximized()
        if state:
            self.acknowledged_generation = self.generation
            self.request_unconfirmed = False
        self.last_state = state
        if self.listener:
            self.listener(state, self.request_unconfirmed)
        return state

    def set_listener(self, listener):
        self.listener = listener
        self.observe()

    def _mapped(self, event):
        if event is not None and event.widget is not self.root:
            return
        if self.startup_started or self.closed:
            return
        self.startup_started = True
        self._later(None, self._startup)

    def _startup(self):
        if self.startup_sent or self.closed:
            return
        if not self.root.winfo_ismapped():
            self.startup_checks += 1
            if self.startup_checks < 3:
                self._later(100, self._startup)
            return
        self.startup_sent = True
        self.maximize()

    def _configured(self, event):
        if event.widget is not self.root or self.closed:
            return
        # Observe only. Never reassert maximization after a user restore/resize.
        if self.configure_job is None:
            def observed():
                self.configure_job = None
                self.observe()
            self.configure_job = self._later(None, observed)

    def _set_zoomed(self, value):
        try:
            self.root.attributes('-zoomed', value)
            return True
        except self.error_type:
            try:
                self.root.state('zoomed' if value else 'normal')
                return True
            except self.error_type:
                return False

    def maximize(self):
        # An explicit control supersedes pending startup, including its callbacks.
        self.startup_sent = True
        self.generation += 1
        generation = self.generation
        self.request_unconfirmed = False
        supported = self._set_zoomed(True)
        if not supported:
            self.request_unconfirmed = True
        self.observe()
        # X11 requests are asynchronous. Confirm, do not keep requesting.
        self._later(700, lambda: self._confirm(generation, supported))

    def restore(self):
        self.startup_sent = True
        self.generation += 1
        self.request_unconfirmed = False
        self._set_zoomed(False)
        self.observe()

    def toggle(self):
        if self.maximized():
            self.restore()
        else:
            self.maximize()

    def _confirm(self, generation, supported):
        if generation != self.generation:
            return
        maximized = self.maximized()
        # An observed max->normal transition can be an intentional user restore.
        # It must not produce a retry or an unsupported warning.
        self.request_unconfirmed = not maximized and self.acknowledged_generation != generation
        self.observe()
        self.report(self.diagnostics(supported))

    def diagnostics(self, supported=None):
        data = {'maximized': self.maximized(), 'request_supported': supported}
        for key, method in (
            ('geometry', self.root.winfo_geometry), ('maximum_hint', self.root.maxsize),
            ('screen_width', self.root.winfo_screenwidth), ('screen_height', self.root.winfo_screenheight),
            ('virtual_width', self.root.winfo_vrootwidth), ('virtual_height', self.root.winfo_vrootheight),
        ):
            try:
                data[key] = method()
            except self.error_type:
                data[key] = None
        return data

    def _destroyed(self, event):
        if event.widget is self.root:
            self.closed = True
            for job in tuple(self.jobs):
                try:
                    self.root.after_cancel(job)
                except self.error_type:
                    pass
            self.jobs.clear()
