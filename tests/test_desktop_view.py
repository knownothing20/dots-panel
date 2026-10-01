"""Recovered native regression cases from visible Sep 30 edit records."""
import sqlite3
import os
import json
import tempfile
import unittest
from pathlib import Path

from dots_panel.app import Store
from dots_panel.desktop_view import (
    ReadOnlyStore, choose_font, duration, pipeline_counts, size, task_rows,
    load_language, save_language, resolve_language, translate, schedule_summary,
    timeline_records, workspace_rows, timestamp_label, percent, scroll_thumb,
    scroll_drag_fraction, Dashboard, display_signature, PAGE_NAMES,
)


class NativeViewTests(unittest.TestCase):
    def test_read_only_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            store.register("example", "Example", "Sample")
            viewer = ReadOnlyStore(directory)
            self.assertEqual(viewer.snapshot()["tasks"][0]["id"], "example")
            with viewer.connect() as db:
                with self.assertRaises(sqlite3.OperationalError):
                    db.execute("DELETE FROM tasks")
            self.assertEqual(len(store.snapshot()["tasks"]), 1)

    def test_readonly_connection_closes_after_use_and_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            Store(directory)
            viewer = ReadOnlyStore(directory)
            with viewer.connect() as db:
                self.assertEqual(db.execute("SELECT 1").fetchone()[0], 1)
            with self.assertRaises(sqlite3.ProgrammingError):
                db.execute("SELECT 1")
            with self.assertRaises(RuntimeError):
                with viewer.connect() as failed_db:
                    raise RuntimeError("Example failure")
            with self.assertRaises(sqlite3.ProgrammingError):
                failed_db.execute("SELECT 1")
            for _ in range(50):
                self.assertEqual(viewer.snapshot()["tasks"], [])

    def test_missing_database_creates_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "absent"
            with self.assertRaises(FileNotFoundError):
                ReadOnlyStore(target)
            self.assertFalse(target.exists())

    def test_elapsed_terminal_and_stale(self):
        snapshot = {"tasks": [{"id": "one", "name": "Task", "project": "Project"}],
                    "runs": [{"task_id": "one", "started": 100, "updated": 120, "finished": 130,
                              "status": "succeeded", "stale": False}], "activity": []}
        row = task_rows(snapshot, 200)[0]
        self.assertEqual(row["values"][4], "30 秒")
        snapshot["runs"][0].update(status="running", stale=True, finished=None, tracking_mode="heartbeat")
        row = task_rows(snapshot, 200)[0]
        self.assertEqual(row["status"], "running")
        self.assertIn("心跳过期", row["warning"])
        self.assertEqual(row["values"][2], "进行中")

    def test_stage_counts_latest_only(self):
        records = [{"project": "Sample", "task_id": "a", "stage": "test", "created": i, "state": state}
                   for i, state in enumerate(("planned", "in_progress", "verified"))]
        self.assertEqual(pipeline_counts({"activity": records}), {"planned": 0, "in_progress": 0, "verified": 1})

    def test_pending_and_formatters(self):
        row = task_rows({"tasks": [{"id": "one", "name": "Task", "project": "Project"}]}, 200)[0]
        self.assertEqual(row["status"], "pending")
        self.assertEqual(size(None), "不可用")
        self.assertEqual(duration(-10), "0 秒")
        self.assertEqual(duration(3601), "1 小时 00 分")

    def test_cjk_font_preferred(self):
        self.assertEqual(choose_font(["DejaVu Sans", "noto sans cjk sc"]), "noto sans cjk sc")
        self.assertEqual(choose_font(["DejaVu Sans", "Noto Serif CJK SC"]), "Noto Serif CJK SC")

    def test_language_detection_and_source_text(self):
        self.assertEqual(resolve_language("auto", {"LANG": "zh_CN.UTF-8"}), "zh")
        self.assertEqual(resolve_language("auto", {"LC_ALL": "en_US", "LANG": "zh_CN"}), "en")
        self.assertEqual(resolve_language("zh", {"LANG": "en_US"}), "zh")
        self.assertEqual(translate("任务", "en"), "Task")
        self.assertEqual(translate("Original {message}", "en"), "Original {message}")
        row = task_rows({"tasks": [{"id": "one", "name": "任务原文", "project": "项目原文"}]}, 0, "en")[0]
        self.assertEqual(row["values"][:3], ("任务原文", "项目原文", "Pending"))
        self.assertEqual(duration(70, "en"), "1m 10s")

    def test_local_language_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(load_language(directory), "auto")
            save_language(directory, "en")
            self.assertEqual(load_language(directory), "en")
            config = Path(directory) / "config"
            self.assertEqual(config.stat().st_mode & 0o777, 0o700)
            self.assertEqual((config / "ui.json").stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads((config / "ui.json").read_text()), {"language": "en"})
            with self.assertRaises(ValueError):
                save_language(directory, "invalid")

    def test_language_symlink_refusal(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "config").mkdir()
            target = base / "untouched.json"
            target.write_text('{"language":"zh"}')
            (base / "config/ui.json").symlink_to(target)
            self.assertEqual(load_language(directory), "auto")
            with self.assertRaises(ValueError):
                save_language(directory, "en")
            self.assertEqual(target.read_text(), '{"language":"zh"}')
            (base / "config/ui.json").unlink()
            (base / "config").rmdir()
            (base / "elsewhere").mkdir()
            (base / "config").symlink_to(base / "elsewhere", target_is_directory=True)
            with self.assertRaises(OSError):
                save_language(directory, "en")
            self.assertFalse((base / "elsewhere/ui.json").exists())

    def test_manual_stale_is_unconfirmed_not_failure(self):
        snapshot = {"tasks": [{"id": "one", "name": "Task", "project": "Project"}],
                    "runs": [{"task_id": "one", "started": 100, "updated": 110,
                              "status": "running", "stale": True, "tracking_mode": "manual"}]}
        row = task_rows(snapshot, 300)[0]
        self.assertEqual(row["status"], "running")
        self.assertEqual(row["values"][2], "进行中")
        self.assertEqual(row["warning"], "进度更新较久，执行状态待确认")
        self.assertNotIn("心跳", row["values"][2])

    def test_schedule_metadata_does_not_claim_execution(self):
        self.assertEqual(schedule_summary({"state": "disconnected", "next_run": None}), ("未接入", "下次运行未知"))
        self.assertEqual(schedule_summary({"state": "disconnected"}, "en"), ("Disconnected", "Next run unknown"))

    def test_timeline_filters_tasks_and_preserves_messages(self):
        snapshot = {"runs": [{"id": "r1", "task_id": "a"}, {"id": "r2", "task_id": "b"}],
                    "activity": [{"task_id": "a", "stage": "Original stage", "created": 1, "message": "Original message"},
                                 {"task_id": "b", "stage": "Other", "created": 3, "message": "Other"}],
                    "events": [{"run_id": "r1", "created": 2, "message": "Event"}, {"run_id": "r2", "created": 4, "message": "Other event"}]}
        records = timeline_records(snapshot, "a")
        self.assertEqual([row["message"] for row in records], ["Event", "Original message"])
        self.assertEqual(records[1]["title"], "Original stage")

    def test_workspace_filters_preserve_all_lifecycles(self):
        rows = [{"status": status} for status in ("pending", "running", "succeeded", "cancelled", "failed")]
        self.assertEqual(workspace_rows(rows), rows)
        for row in rows:
            self.assertEqual(workspace_rows(rows, row["status"]), [row])
        self.assertIn("UTC", timestamp_label(0))

    def test_older_lifecycle_is_not_marked_pending(self):
        rows = task_rows({"tasks": [{"id": "old", "name": "Old task", "project": "Sample", "latest_status": "succeeded"}]}, 200)
        self.assertEqual(rows[0]["status"], "succeeded")
        self.assertEqual(rows[0]["values"][2], "已完成")

    def test_resource_percent_requires_measured_total(self):
        self.assertIsNone(percent(1, None))
        self.assertIsNone(percent(1, 0))
        self.assertEqual(percent(2, 8), 25)
        self.assertEqual(percent(9, 8), 100)

    def test_search_uses_real_task_name_and_project(self):
        rows = [{"status": "running", "values": ("Example Task", "Research")},
                {"status": "succeeded", "values": ("Other", "Sample")}]
        self.assertEqual(workspace_rows(rows, "all", "EXAMPLE"), [rows[0]])
        self.assertEqual(workspace_rows(rows, "running", "research"), [rows[0]])
        self.assertEqual(workspace_rows(rows, "succeeded", "research"), [])

    def test_scrollbar_geometry_and_drag_bounds(self):
        top, bottom = scroll_thumb(0, .2, 208)
        self.assertEqual((top, bottom), (4, 44))
        self.assertEqual(scroll_drag_fraction(4, 0, 0, .2, 208), 0)
        self.assertAlmostEqual(scroll_drag_fraction(164, 0, 0, .2, 208), .8)
        self.assertEqual(scroll_drag_fraction(-100, 0, 0, .2, 208), 0)
        self.assertAlmostEqual(scroll_drag_fraction(10000, 0, 0, .2, 208), .8)
        self.assertEqual(scroll_drag_fraction(100, 0, 0, 1, 208), 0)
        self.assertLessEqual(scroll_thumb(.5, .6, 20)[1], 16)

    def test_mixed_script_timeline_keeps_complete_source(self):
        message = "A 风格四页与详情已完成。Mixed Latin and 中文 remain intact.\n保留换行。\n"
        snapshot = {"activity": [{"task_id": "sample", "stage": "UI", "created": 1, "message": message}]}
        self.assertEqual(timeline_records(snapshot, "sample")[0]["message"], message)

    def test_paragraph_widget_keeps_mixed_text_without_rewriting(self):
        from types import SimpleNamespace
        class FakeText:
            def __init__(self, parent, **settings):
                self.settings, self.source = settings, None
            def insert(self, position, source):
                self.source = source
            def configure(self, **settings):
                self.settings.update(settings)
            def pack(self, **settings):
                pass
            def bind(self, sequence, callback):
                pass
        viewer = Dashboard.__new__(Dashboard)
        viewer.tk = SimpleNamespace(Text=FakeText)
        viewer.panel, viewer.fg, viewer.font = "white", "black", "Example"
        source = "A 风格四页与详情已完成。Mixed Latin 与中文。\n第二行。\n"
        paragraph = viewer.detail_paragraph(None, source)
        self.assertEqual(paragraph.source, source)
        self.assertEqual(paragraph.settings["wrap"], "char")
        self.assertEqual(paragraph.settings["state"], "disabled")

    def test_activity_labels_do_not_claim_real_conversation_sync(self):
        self.assertEqual(PAGE_NAMES["conversations"], "活动")
        self.assertEqual(translate(PAGE_NAMES["conversations"], "en"), "Activities")
        self.assertIn("no separate execution session", translate("已登记活动与工作记录；尚未绑定独立执行会话", "en"))

    def test_end_home_cancel_restore_and_use_correct_endpoints(self):
        from types import SimpleNamespace
        calls = []
        viewer = Dashboard.__new__(Dashboard)
        viewer.page_scroll = SimpleNamespace(winfo_exists=lambda: True, cancel_restore=lambda: calls.append("cancel"), yview_moveto=lambda point: calls.append(point))
        widget = SimpleNamespace(winfo_class=lambda: "Canvas")
        self.assertEqual(viewer.scroll_key(SimpleNamespace(widget=widget, keysym="End")), "break")
        self.assertEqual(calls, ["cancel", 1.0])
        calls.clear()
        viewer.scroll_key(SimpleNamespace(widget=widget, keysym="Home"))
        self.assertEqual(calls, ["cancel", 0.0])

    def test_unchanged_poll_keeps_existing_widgets(self):
        from types import SimpleNamespace
        import copy
        viewer = Dashboard.__new__(Dashboard)
        viewer.snapshot = {"tasks": [], "runs": [], "software": [{"id": "sample", "verified_at": 1}]}
        updated = copy.deepcopy(viewer.snapshot)
        updated["software"][0]["verified_at"] = 2
        viewer.store = SimpleNamespace(snapshot=lambda: updated)
        viewer.metrics = SimpleNamespace(collect=lambda: {})
        viewer.page, viewer.selected_task, viewer.language, viewer.workspace_filter = "software", None, "zh", "all"
        viewer.search_query = SimpleNamespace(get=lambda: "")
        viewer.last_render_signature = viewer.view_signature()
        viewer.scroll_dragging = False
        calls = []
        viewer.live_updates = [lambda: calls.append("live")]
        viewer.render_page = lambda: calls.append("rebuild")
        viewer.update_health = lambda: None
        viewer.root = SimpleNamespace(after=lambda milliseconds, callback: 1)
        viewer.refresh()
        self.assertEqual(calls, ["live"])

    def test_refresh_signature_ignores_age_ticks_but_tracks_real_changes(self):
        original = {"runs": [{"id": "run", "status": "running", "updated": 1, "progress_updated": 1, "stale": False}],
                    "software": [{"id": "app", "available": True, "verified_at": 1}]}
        import copy
        tick = copy.deepcopy(original)
        tick["runs"][0].update(updated=2, progress_updated=2)
        tick["software"][0]["verified_at"] = 2
        self.assertEqual(display_signature(original), display_signature(tick))
        tick["runs"][0]["stale"] = True
        self.assertNotEqual(display_signature(original), display_signature(tick))
        tick["runs"][0]["stale"] = False
        tick["runs"][0]["status"] = "succeeded"
        self.assertNotEqual(display_signature(original), display_signature(tick))


if __name__ == "__main__":
    unittest.main()
