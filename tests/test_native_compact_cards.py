"""Bounded card layout and retained-refresh regressions without a desktop."""
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from dots_panel.desktop_view import Dashboard, bounded_card_lines, compact_task_excerpt
from test_native_retained_updates import Canvas, Widget


class CompactCardsTests(unittest.TestCase):
    def view(self):
        v=Dashboard.__new__(Dashboard)
        v.root=Mock();v.tk=SimpleNamespace(Canvas=Canvas,Frame=Widget);v.language='zh';v.bg='#f7f8f4';v.panel='white';v.fg='black';v.accent='green';v.muted='gray';v.font='sans';v.live_updates=[]
        v.snapshot={'activity':[]};v.surface_layers=Mock();v.pill=Mock();v.t=lambda x,**kw:x;v.output_button=lambda *args:Widget();v.open_task=Mock();v.open_task_files=Mock();v.draw_participant_group=Mock()
        v.rows=[{'id':'task','status':'running','warning':'STALE LONG EVIDENCE','values':('Long title 中英文字 '*30,'Project','进行中','Implementation','10 seconds','just now'),'run':{'id':'a'*16}}]
        return v
    def test_pixel_wrap_never_exceeds_two_lines(self):
        for text in ('中'*1000, 'A long English title '*100, 'line one\nline two\nline three'):
            result=bounded_card_lines(text,150,lambda t:len(t)*10,2)
            self.assertLessEqual(len(result.splitlines()),2)
            self.assertTrue(all(len(line)*10<=150 for line in result.splitlines()))
            self.assertTrue(result.endswith('…') or len(' '.join(text.split()))<=30)
    def test_excerpt_hides_technical_tail_without_mutating_source(self):
        raw='检查阶段已完成 libfile_abcdef0123 | Evidence: '+('raw evidence '*100)
        result=compact_task_excerpt(raw)
        self.assertEqual(result,'检查阶段已完成')
        self.assertIn('Evidence',raw)
    def test_title_then_avatar_status_then_summary_then_output(self):
        v=self.view();card=v.airy_task_card(Widget(),v.rows[0],0)
        with patch('tkinter.font.Font') as font,patch('dots_panel.desktop_view.task_progress',return_value={'current_step':'Summary text 摘要 '*80}):
            font.return_value.measure.side_effect=lambda text:len(text)*9
            card.bindings['<Configure>'](SimpleNamespace(width=370))
        texts=[(coords,options) for kind,coords,options in card.items.values() if kind=='create_text']
        title=next(item for item in texts if item[0][1]==22);summary=next(item for item in texts if item[0][1]==133)
        self.assertLessEqual(len(title[1]['text'].splitlines()),2);self.assertLessEqual(len(summary[1]['text'].splitlines()),2)
        self.assertEqual(card.options['height'],244)
        self.assertEqual(v.draw_participant_group.call_args.args[3],84)
        self.assertEqual(v.pill.call_args.args[2],85)
        self.assertEqual(v.pill.call_args.args[3],'进行中')
        self.assertEqual([coords[1] for kind,coords,_ in card.items.values() if kind=='create_window'],[208])
        self.assertNotIn('STALE',str(texts));self.assertNotIn('aaaaaaaa',str(texts))
    def test_identical_polls_and_elapsed_change_do_not_touch_canvas(self):
        v=self.view();card=v.airy_task_card(Widget(),v.rows[0],0)
        with patch('tkinter.font.Font') as font:
            font.return_value.measure.side_effect=lambda text:len(text)*9
            card.bindings['<Configure>'](SimpleNamespace(width=370))
            ids=tuple(card.items)
            for i in range(4):
                v.rows=copy.deepcopy(v.rows);v.rows[0]['values']=tuple(list(v.rows[0]['values'][:4])+[str(i)+'s','new sample'])
                card.update_live()
        self.assertEqual(tuple(card.items),ids);self.assertEqual(card.item_changes,[]);self.assertEqual(card.item_deletions,[])
    def test_status_only_changes_keep_canvas_and_file_button(self):
        v=self.view();card=v.airy_task_card(Widget(),v.rows[0],0)
        with patch('tkinter.font.Font') as font:
            font.return_value.measure.side_effect=lambda text:len(text)*9
            card.bindings['<Configure>'](SimpleNamespace(width=370))
            windows=[(key,options['window']) for key,(kind,coords,options) in card.items.items() if kind=='create_window']
            v.rows=copy.deepcopy(v.rows);v.rows[0]['status']='succeeded';card.update_live()
        self.assertEqual([(key,options['window']) for key,(kind,coords,options) in card.items.items() if kind=='create_window'],windows)
        self.assertEqual(card.item_deletions,[])
        self.assertEqual(v.pill.call_args.args[3],'已完成')


if __name__=='__main__':unittest.main()
