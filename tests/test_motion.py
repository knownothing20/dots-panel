import unittest
from dots_panel.motion import Motion, blend_color


class Scheduler:
    def __init__(self):
        self.jobs = {}
        self.serial = 0
    def after(self, milliseconds, callback):
        assert milliseconds == 32
        self.serial += 1
        self.jobs[self.serial] = callback
        return self.serial
    def after_cancel(self, job):
        self.jobs.pop(job, None)
    def tick(self):
        for key, callback in tuple(self.jobs.items()):
            if key in self.jobs:
                self.jobs.pop(key)
                callback()


class Widget:
    exists = True
    def winfo_exists(self):
        return self.exists


class MotionTests(unittest.TestCase):
    def setUp(self):
        self.scheduler, self.widget = Scheduler(), Widget()
        self.motion = Motion(self.scheduler)
        self.colors = []
    def animate(self):
        self.motion.color(self.widget, '#ffffff', '#258560', self.colors.append)
    def test_bounded_five_frame_transition(self):
        self.animate()
        for _ in range(5):
            self.assertEqual(len(self.scheduler.jobs), 1)
            self.scheduler.tick()
        self.assertEqual(self.colors[-1], '#258560')
        self.assertEqual(len(self.colors), 5)
        self.assertFalse(self.motion.jobs)
        self.assertFalse(self.scheduler.jobs)
    def test_rapid_changes_replace_pending_job(self):
        for _ in range(100):
            self.animate()
        self.assertEqual(len(self.scheduler.jobs), 1)
        self.motion.cancel_all()
        self.assertFalse(self.scheduler.jobs)
    def test_reduced_motion_is_immediate(self):
        self.motion.reduced = True
        self.animate()
        self.assertEqual(self.colors, ['#258560'])
        self.assertFalse(self.scheduler.jobs)
    def test_destroyed_widget_does_not_receive_frame(self):
        self.animate()
        self.widget.exists = False
        self.scheduler.tick()
        self.assertFalse(self.colors)
        self.assertFalse(self.motion.jobs)
    def test_reduction_cancels_existing_jobs(self):
        self.animate()
        self.motion.reduced = True
        self.animate()
        self.assertFalse(self.scheduler.jobs)
        self.assertEqual(self.colors, ['#258560'])
    def test_color_endpoints(self):
        self.assertEqual(blend_color('#ffffff', '#258560', 0), '#ffffff')
        self.assertEqual(blend_color('#ffffff', '#258560', 1), '#258560')


if __name__ == '__main__':
    unittest.main()
