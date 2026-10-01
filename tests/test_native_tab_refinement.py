"""Synthetic native layout QA, only on an explicitly available test desktop."""
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from dots_panel.app import Store, Metrics
from dots_panel.desktop_view import Dashboard, ReadOnlyStore, PAGE_NAMES


def seed(store):
    if store.snapshot()['tasks']:
        return
    for index in range(6):
        key='synthetic-'+str(index)
        store.register(key,['合成任务 · 界面检查','合成任务 · 视频制作','合成任务 · 内容整理'][index%3], 'Synthetic QA')
        run=store.start(key,'最早的启动说明；应位于较新记录之后')
        store.progress_update(run,'核对卡片层级与时间线','已检查真实样式结构','验证窄窗口与滚动位置','Synthetic test fixture',240 if index==0 else None,576 if index==0 else None,'frames' if index==0 else '')
        if index==0:
            store.agent_register('synthetic-worker','测试执行者')
            store.agent_observe('synthetic-worker','running',datetime.now(timezone.utc).isoformat(),'Synthetic UI QA observation')
            store.agent_run_assign(run,'synthetic-worker','testing')
    for index in range(2):
        key='synthetic-schedule-'+str(index)
        store.schedule_register(key,'合成每日任务' if index else '合成每小时检查','Synthetic QA')
        store.schedule_platform_import(key,{'schema_version':'dots-panel.platform-schedule.v1','platform':'dot','task_id':'synthetic-platform-'+str(index),'title':'Synthetic task','enabled':True,'timezone':'Asia/Shanghai','timing_mode':'exact_schedule','schedule':('BEGIN:VEVENT\nDTSTART;TZID=Asia/Shanghai:20261002T080000\nRRULE:FREQ=DAILY;BYHOUR=8;BYMINUTE=0;BYSECOND=0\nEND:VEVENT' if index else 'BEGIN:VEVENT\nDTSTART:20261001T000000Z\nRRULE:FREQ=HOURLY\nEND:VEVENT'),'last_run_at':None,'next_run_at':None,'observed_at':datetime.now(timezone.utc).isoformat()})


@unittest.skipUnless(os.environ.get('DISPLAY'),'explicit native test display required')
class NativeTabRefinementTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from tkinter import ttk
        self.tk=tk;self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/'data');seed(self.store)
        self.root=tk.Tk();self.view=Dashboard(self.root,ReadOnlyStore(self.store.directory),Metrics(self.store.directory),tk,ttk,'zh')
        self.root.attributes('-zoomed',False)
    def tearDown(self):
        for job in self.root.tk.call('after','info'):self.root.after_cancel(job)
        self.root.destroy()
    def settle(self,width=1260):
        self.root.geometry(f'{width}x850')
        for _ in range(12):self.root.update_idletasks();self.root.update()
    def test_all_tabs_keep_content_at_top_and_readable(self):
        for page in PAGE_NAMES:
            self.view.navigate(page);self.settle()
            if hasattr(self.view,'page_scroll'):
                self.assertGreaterEqual(self.view.page_scroll.canvasy(0),-1)
                self.assertLessEqual(self.view.page_scroll.canvasy(0),1)
    def test_short_schedule_collapse_does_not_float_content(self):
        self.view.navigate('schedules');self.settle();self.view.toggle_registry_detail('schedules','synthetic-schedule-0');self.settle()
        self.view.page_scroll.yview_moveto(.8)
        self.view.toggle_registry_detail('schedules','synthetic-schedule-0');self.settle()
        self.assertAlmostEqual(self.view.page_scroll.canvasy(0),0,delta=1)
    def test_toolbar_wide_single_row_narrow_wrap_and_progress(self):
        self.view.navigate('conversations');self.settle(1260)
        self.assertEqual(int(self.view.search_entry.master.grid_info()['row']),0)
        self.settle(760);self.assertEqual(int(self.view.search_entry.master.grid_info()['row']),1)
        self.view.open_task('synthetic-0');self.settle(1260)
        self.assertEqual(self.view.selected_task,'synthetic-0')
        self.view.refresh();self.settle();self.assertEqual(self.view.selected_task,'synthetic-0')

if __name__=='__main__':unittest.main()
