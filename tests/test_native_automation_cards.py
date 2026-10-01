from unittest import TestCase
from unittest.mock import Mock,patch
from types import SimpleNamespace
from dots_panel.desktop_view import Dashboard,translate,activity_summary,timeline_records
from test_native_retained_updates import Widget,Canvas

class NativeAutomationCardsTests(TestCase):
    def view(self):
        v=Dashboard.__new__(Dashboard);v.root=Mock();v.tk=SimpleNamespace(Frame=Widget,Canvas=Canvas,Label=Widget);v.font='sans';v.language='en';v.panel=v.bg='white';v.accent='green';v.fg='black';v.muted='gray';v.t=lambda text:text
        v.card=lambda parent,height:(Canvas(parent,height=height),Widget(parent));return v
    def test_collapsed_cards_equal_height_and_bound_lines(self):
        v=self.view();short=v.compact_row(Widget(),'Short','Hourly\nLatest: none','Enabled',bounded=True)
        long=v.compact_row(Widget(),'Long title '*100,'Long timing '*100+'\nLong result '*100,'Status '*100,bounded=True)
        with patch('tkinter.font.Font') as font:
            font.return_value.measure.side_effect=lambda text:len(text)*10
            for box in (short,long):box.bindings['<Configure>'](None)
            for box in (short,long):
                self.assertEqual(box.surface.options['height'],244)
                self.assertLessEqual(len(box.title_label.cget('text').splitlines()),2)
                self.assertEqual(len(box.summary_label.cget('text').splitlines()),2)
                self.assertEqual(len(box.status_label.cget('text').splitlines()),1)
            old=long.title_label;long.set_caption('title','Updated title '*100)
            self.assertIs(long.title_label,old);self.assertLessEqual(len(long.title_label.cget('text').splitlines()),2)
            long.set_expanded(True);self.assertTrue(long.surface.auto_fit);v.root.after_idle.assert_called()
            long.set_expanded(False);self.assertFalse(long.surface.auto_fit);self.assertEqual(long.surface.options['height'],244)
    def test_current_ui_copy_and_history_are_separate(self):
        for zh,en in [('任务','Tasks'),('自动化','Automations'),('尚未登记自动化','No automations registered yet'),('查看任务 →','View tasks →'),('查看计划 →','View automations →')]:
            self.assertEqual(translate(zh,'en'),en)
        self.assertEqual(translate('另有 {count} 个任务，可在任务页查看','en',count=6),'6 more tasks in Tasks')
        message='历史活动：定时任务运行说明。 Activities / Schedules original text'
        snapshot={'activity':[{'id':1,'task_id':'t','message':message,'created':1,'stage':'progress'}]}
        self.assertEqual(activity_summary(snapshot,'t'),message)
        self.assertEqual(timeline_records(snapshot,'t')[0]['message'],message)
