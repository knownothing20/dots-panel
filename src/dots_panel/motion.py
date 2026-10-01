"""Small, bounded interaction transitions; no idle animation or external dependencies."""


def blend_color(start, end, progress):
    """Interpolate #rrggbb colors, with a gentle ease-out."""
    progress = max(0.0, min(1.0, progress))
    eased = 1 - (1 - progress) ** 2
    a = tuple(int(start[i:i+2], 16) for i in (1, 3, 5))
    b = tuple(int(end[i:i+2], 16) for i in (1, 3, 5))
    return "#" + "".join(f"{round(x+(y-x)*eased):02x}" for x, y in zip(a, b))


class Motion:
    """At most one pending callback per widget; every transition ends in 160ms.

    The owner cancels on page replacement, widget destruction and window close.
    Reduced motion applies the final state synchronously without scheduling work.
    """
    def __init__(self, scheduler, reduced=False):
        self.scheduler = scheduler
        self.reduced = reduced
        self.jobs = {}

    def cancel(self, widget):
        job = self.jobs.pop(widget, None)
        if job is not None:
            try:
                self.scheduler.after_cancel(job)
            except Exception:
                pass  # Widget/root can already have been destroyed by Tk.

    def cancel_all(self):
        for widget in tuple(self.jobs):
            self.cancel(widget)

    def color(self, widget, start, end, apply):
        self.cancel(widget)
        if self.reduced or start == end:
            apply(end)
            return
        step = 0
        def tick():
            nonlocal step
            self.jobs.pop(widget, None)
            if not widget.winfo_exists():
                return
            step += 1
            apply(blend_color(start, end, step / 5))
            if step < 5:
                self.jobs[widget] = self.scheduler.after(32, tick)
        self.jobs[widget] = self.scheduler.after(32, tick)
