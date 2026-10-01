"""Synthetic saved-result presentation; no network, account, or runtime data."""
from copy import deepcopy
from unittest import TestCase
from unittest.mock import Mock

from dots_panel.desktop_view import Dashboard, schedule_result_view, schedule_summary, timestamp_label


def schedule_fixture():
    return {
        "id": "synthetic-result", "name": "Synthetic Radar", "project": "Example",
        "source": "manual", "state": "disconnected", "next_run": 946684800, "updated": 200,
        "external_result": {
            "repository": "example-owner/example-repo", "ref": "main",
            "status_path": "example/status.json", "index_path": "example/index.json",
            "platform_configuration": "unverified", "sync_mode": "manual",
            "checked_at": 200, "last_good_at": 100, "fetch_error": None,
            "observation": {
                "latest": {"calendar_date": "2000-01-03", "run_id": "synthetic-attempt",
                           "collected_at": "2000-01-03T08:00:00+08:00", "status": "rejected",
                           "selected_count": 0, "stale": False},
                "index": {"generated_at": "2000-01-03T00:02:00Z", "entry_count": 2, "latest_date": "2000-01-02"},
                "evidence": {"status_sha": "a" * 40, "index_sha": "b" * 40,
                             "status_url": "https://github.com/example-owner/example-repo/blob/main/example/status.json",
                             "index_url": "https://github.com/example-owner/example-repo/blob/main/example/index.json"},
            },
        },
    }


class ScheduleResultPresentationTests(TestCase):
    def viewer(self, record, language="en", expanded=False):
        view = Dashboard.__new__(Dashboard)
        view.language = language
        view.snapshot = {"schedules": [record]}
        view.muted, view.accent = "gray", "green"
        view.scroll_area = Mock(return_value=Mock())
        view.compact_row = Mock(return_value=Mock())
        view.card_grid = Mock(return_value=Mock())
        view.label = Mock(return_value=Mock())
        view.filter_chip = Mock(return_value=Mock())
        view.render_page = Mock()
        view.expanded_schedules = {record["id"]} if expanded else set()
        return view

    def test_result_link_overrides_metadata_without_mutating_it(self):
        for language, label in (("en", "Results linked · config unverified"), ("zh", "结果已接入 · 配置未核验")):
            record = schedule_fixture()
            before = deepcopy(record)
            state, timing = schedule_summary(record, language)
            self.assertEqual(state, label)
            self.assertIn("2000-01-03", timing)
            self.assertIn("rejected", timing)
            self.assertEqual(record, before)

    def test_platform_unknown_and_all_observation_clocks_are_distinct(self):
        view = schedule_result_view(schedule_fixture(), "en")
        rows = dict(view["rows"])
        self.assertEqual(rows["Latest observed attempt date"], "2000-01-03")
        self.assertEqual(rows["Accepted index latest date"], "2000-01-02")
        self.assertEqual(rows["Source collected at"], timestamp_label("2000-01-03T08:00:00+08:00"))
        self.assertEqual(rows["Index generated at"], timestamp_label("2000-01-03T00:02:00Z"))
        self.assertEqual(rows["Last fetch check"], timestamp_label(200))
        self.assertEqual(rows["Last successful fetch"], timestamp_label(100))
        self.assertIn("platform ID, enabled state and next due are unknown", rows["Platform configuration"])
        self.assertEqual(rows["Selected count"], "0")
        self.assertEqual(rows["Index entry count"], "2")
        self.assertNotIn(timestamp_label(946684800), str(rows))

    def test_source_stale_is_tristate_not_derived_from_dates_or_count(self):
        for source, expected in ((True, "Yes"), (False, "No"), (None, "Unknown")):
            record = schedule_fixture()
            record["external_result"]["observation"]["latest"]["stale"] = source
            self.assertEqual(dict(schedule_result_view(record, "en")["rows"])["Source stale flag"], expected)
        del record["external_result"]["observation"]["latest"]["stale"]
        self.assertEqual(dict(schedule_result_view(record, "en")["rows"])["Source stale flag"], "Unknown")

    def test_fetch_failure_keeps_result_and_reports_no_snapshot_when_absent(self):
        record = schedule_fixture()
        record["external_result"]["fetch_error"] = "Synthetic fetch failure"
        result = schedule_result_view(record, "en")
        self.assertIn("Retaining last good snapshot", result["error"])
        self.assertEqual(dict(result["rows"])["Source run ID"], "synthetic-attempt")
        record["external_result"]["observation"] = None
        record["external_result"]["last_good_at"] = None
        result = schedule_result_view(record, "en")
        self.assertIn("No result snapshot", result["label"])
        self.assertIn("No successful snapshot", result["error"])
        self.assertEqual(dict(result["rows"])["Last successful fetch"], "Not recorded")
        self.assertNotIn("Source run ID", dict(result["rows"]))

    def test_missing_external_result_uses_legacy_metadata(self):
        self.assertIsNone(schedule_result_view({"external_result": None}))
        self.assertEqual(schedule_summary({"state": "disconnected"}, "en"), ("Disconnected", "Next run unknown"))

    def test_native_collapsed_error_and_bilingual_expanded_detail(self):
        for language, linked, check, stale, retention in (
            ("en", "Results linked", "Last fetch check", "Source stale flag", "Retaining last good snapshot"),
            ("zh", "结果已接入", "最近获取检查", "源过期标记", "保留上次成功快照"),
        ):
            record = schedule_fixture()
            record["external_result"]["fetch_error"] = "Synthetic fetch failure"
            view = self.viewer(record, language)
            view.render_schedules()
            self.assertIn(linked, view.compact_row.call_args.args[3])
            self.assertIn(stale, view.compact_row.call_args.args[2])
            self.assertIn("2000-01-02", view.compact_row.call_args.args[2])
            labels = [str(call.args[1]) for call in view.label.call_args_list]
            self.assertTrue(any(retention in label for label in labels))
            self.assertTrue(any("GitHub" in label for label in labels))
            self.assertFalse(any(check+":" in label for label in labels))
            view.toggle_registry_detail("schedules", record["id"])
            view.render_schedules()
            labels = [str(call.args[1]) for call in view.label.call_args_list]
            self.assertTrue(any(check+":" in label for label in labels))
            source_url = record["external_result"]["observation"]["evidence"]["status_url"]
            self.assertFalse(any(source_url in label for label in labels))
            view.toggle_registry_detail("schedule_technical", record["id"])
            view.render_schedules()
            labels = [str(call.args[1]) for call in view.label.call_args_list]
            self.assertTrue(any(source_url in label for label in labels))
            self.assertEqual(len(view.expanded_schedules), 1)
            # Source evidence remains text, with no browser-opening controls.
            self.assertGreaterEqual(len(view.filter_chip.call_args_list), 3)
            view.toggle_registry_detail("schedules", record["id"])
            self.assertEqual(view.expanded_schedules, set())
