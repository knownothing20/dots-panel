"""Synthetic proc fixtures only; these tests never sample the real /proc."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import errno
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch

from dots_panel import memory_processes as memory


class ProcessMemoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.proc = self.base / "proc"
        self.proc.mkdir()
        self.sampler = memory.ProcessMemorySampler(self.proc)

    def process(self, pid, name="synthetic", rss=12, text=None):
        directory = self.proc / str(pid)
        directory.mkdir()
        (directory / "status").write_text(
            text if text is not None else f"Name:\t{name}\nVmRSS:\t{rss} kB\n",
            encoding="utf-8",
        )
        return directory

    def assert_partition(self, sample):
        self.assertEqual(sample["visible_count"], sample["readable_count"]
                         + sample["unreadable_count"] + sample["exited_count"])
        self.assertEqual(sample["readable_count"], len(sample["rows"]))

    def test_interface_and_conversion_only_status_fields(self):
        directory = self.process(22, "example", 2048)
        (directory / "cmdline").write_text("PRIVATE_COMMAND")
        (directory / "environ").write_text("PRIVATE_ENVIRONMENT")
        self.process(3, "zero", 0)
        self.process("not-a-pid", "ignored", 50)
        self.process("１２", "unicode-digits-ignored", 99)
        sample = self.sampler.sample()
        self.assertEqual(set(sample), {"sampled_at", "attempted_at", "visible_count",
            "readable_count", "unreadable_count", "exited_count", "status", "error",
            "scope", "rows"})
        self.assertEqual(sample["scope"], "sampler_visible_processes")
        self.assertEqual(sample["status"], "ok")
        self.assertIsNone(sample["error"])
        self.assertEqual(sample["visible_count"], 2)
        self.assertEqual(sample["rows"], [
            {"pid": 3, "name": "zero", "rss_bytes": 0, "task_attribution": "unknown"},
            {"pid": 22, "name": "example", "rss_bytes": 2097152,
             "task_attribution": "unknown"},
        ])
        self.assertLessEqual(datetime.fromisoformat(sample["attempted_at"].replace("Z", "+00:00")),
                             datetime.fromisoformat(sample["sampled_at"].replace("Z", "+00:00")))
        self.assertNotIn("PRIVATE", json.dumps(sample))
        self.assert_partition(sample)

    def test_empty_root_is_valid(self):
        sample = self.sampler.sample()
        self.assertEqual(sample["status"], "ok")
        self.assertEqual(sample["rows"], [])
        self.assertIsNotNone(sample["sampled_at"])
        self.assert_partition(sample)

    def test_only_status_file_is_opened_for_processes(self):
        self.process(12)
        original_open = os.open
        calls = []
        def recording_open(path, flags, *args, **kwargs):
            calls.append(os.fspath(path))
            return original_open(path, flags, *args, **kwargs)
        # Keep the capability check referring to the patched API for this spy.
        with patch.object(memory.os, "open", side_effect=recording_open) as opened:
            with patch.object(memory.os, "supports_dir_fd", os.supports_dir_fd | {opened}):
                sample = self.sampler.sample()
        self.assertEqual(sample["status"], "ok")
        self.assertEqual(calls[-2:], ["12", "status"])
        self.assertFalse(any(path in ("cmdline", "environ") for path in calls))

    def test_missing_invalid_or_duplicate_rss_omitted_not_zero(self):
        values = ["Name: kernel\n", "Name: invalid\nVmRSS: -1 kB\n",
                  "Name: wrong-unit\nVmRSS: 5 MB\n",
                  "Name: duplicate\nVmRSS: 5 kB\nVmRSS: 6 kB\n",
                  "VmRSS: 9 kB\n", "Name: a\nName: b\nVmRSS: 8 kB\n",
                  "Name: nan\nVmRSS: NaN kB\n"]
        for pid, text in enumerate(values, start=1):
            self.process(pid, text=text)
        sample = self.sampler.sample()
        self.assertEqual(sample["status"], "partial")
        self.assertEqual(sample["rows"], [])
        self.assertEqual(sample["unreadable_count"], len(values))
        self.assertIn("Name/VmRSS", sample["error"])
        self.assert_partition(sample)

    def test_oversized_status_is_bounded_and_unreadable(self):
        self.process(1, text="Name: huge\nVmRSS: 1 kB\n" + "x" * 65536)
        sample = self.sampler.sample()
        self.assertEqual(sample["rows"], [])
        self.assertEqual(sample["unreadable_count"], 1)

    def test_malicious_name_is_literal_and_control_safe(self):
        payload = '<script>alert("x")</script>; $(danger)'
        self.process(1, payload)
        self.process(2, "escape\x1b[31m\u202e")
        sample = self.sampler.sample()
        self.assertEqual(sample["rows"][0]["name"], payload)
        self.assertEqual(sample["rows"][1]["name"], "escape\ufffd[31m\ufffd")
        self.assertTrue(all(row["task_attribution"] == "unknown" for row in sample["rows"]))

    def test_invalid_utf8_name_is_replacement_text(self):
        directory = self.process(1)
        (directory / "status").write_bytes(b"Name: bad\xff\nVmRSS: 2 kB\n")
        self.assertEqual(self.sampler.sample()["rows"][0]["name"], "bad\ufffd")

    def test_root_symlink_never_followed(self):
        self.process(1)
        linked = self.base / "linked"
        linked.symlink_to(self.proc, target_is_directory=True)
        sample = memory.ProcessMemorySampler(linked).sample()
        self.assertEqual(sample["status"], "unavailable")
        self.assertIsNone(sample["sampled_at"])
        self.assertEqual(sample["rows"], [])

    def test_intermediate_root_symlink_never_followed(self):
        self.process(1)
        linked = self.base / "linked-parent"
        linked.symlink_to(self.base, target_is_directory=True)
        sample = memory.ProcessMemorySampler(linked / "proc").sample()
        self.assertEqual(sample["status"], "unavailable")

    def test_entry_and_status_symlinks_are_unreadable(self):
        target = self.base / "outside"
        target.mkdir()
        (target / "status").write_text("Name: secret\nVmRSS: 999 kB\n")
        (self.proc / "1").symlink_to(target, target_is_directory=True)
        directory = self.proc / "2"
        directory.mkdir()
        (directory / "status").symlink_to(target / "status")
        sample = self.sampler.sample()
        self.assertEqual(sample["visible_count"], 2)
        self.assertEqual(sample["unreadable_count"], 2)
        self.assertEqual(sample["rows"], [])
        self.assertNotIn("secret", json.dumps(sample))
        self.assert_partition(sample)

    def test_symlink_replacement_after_enumeration_never_followed(self):
        directory = self.process(1)
        target = self.base / "outside"
        target.mkdir()
        (target / "status").write_text("Name: secret\nVmRSS: 999 kB\n")
        original_listdir = os.listdir
        def replace_after_listing(fd):
            entries = original_listdir(fd)
            shutil.rmtree(directory)
            directory.symlink_to(target, target_is_directory=True)
            return entries
        with patch.object(memory.os, "listdir", side_effect=replace_after_listing) as listing:
            with patch.object(memory.os, "supports_fd", os.supports_fd | {listing}):
                sample = self.sampler.sample()
        self.assertEqual(sample["unreadable_count"], 1)
        self.assertEqual(sample["rows"], [])

    def test_nonregular_entry_or_status_cannot_block(self):
        (self.proc / "1").write_text("not a directory")
        directory = self.proc / "2"
        directory.mkdir()
        os.mkfifo(directory / "status")
        sample = self.sampler.sample()
        self.assertEqual(sample["unreadable_count"], 2)
        self.assertEqual(sample["rows"], [])
        self.assert_partition(sample)

    def test_missing_status_counts_exited(self):
        (self.proc / "1").mkdir()
        sample = self.sampler.sample()
        self.assertEqual(sample["exited_count"], 1)
        self.assertEqual(sample["unreadable_count"], 0)
        self.assertEqual(sample["status"], "partial")
        self.assert_partition(sample)

    def test_disappeared_process_and_permission_error(self):
        self.process(1)
        self.process(2)
        self.process(3)
        original_read = self.sampler._read_status
        def read(fd, entry):
            if entry == "1":
                shutil.rmtree(self.proc / entry)
            if entry == "2":
                # Deterministic even when tests run as root: permission failure
                # occurs on a synthetic status read, never on a real /proc path.
                raise PermissionError(errno.EACCES, "Synthetic permission failure")
            return original_read(fd, entry)
        with patch.object(self.sampler, "_read_status", side_effect=read):
            sample = self.sampler.sample()
        self.assertEqual(sample["exited_count"], 1)
        self.assertEqual(sample["unreadable_count"], 1)
        self.assertEqual([row["pid"] for row in sample["rows"]], [3])
        self.assertEqual(sample["status"], "partial")
        self.assert_partition(sample)

    def test_root_failure_preserves_old_rows_timestamp_and_counts(self):
        self.process(1)
        first = self.sampler.sample()
        shutil.rmtree(self.proc)
        second = self.sampler.sample()
        self.assertEqual(second["status"], "stale")
        for key in ("sampled_at", "rows", "visible_count", "readable_count",
                    "unreadable_count", "exited_count"):
            self.assertEqual(second[key], first[key])
        self.assertGreaterEqual(second["attempted_at"], first["attempted_at"])
        self.assertNotIn(str(self.proc), second["error"])
        third = self.sampler.sample()
        self.assertEqual(third["sampled_at"], first["sampled_at"])
        self.proc.mkdir()
        self.process(2, "recovered", 42)
        recovered = self.sampler.sample()
        self.assertEqual(recovered["status"], "ok")
        self.assertEqual([row["pid"] for row in recovered["rows"]], [2])

    def test_enumeration_failure_preserves_partial_sample(self):
        self.process(1, text="Name: no-rss\n")
        first = self.sampler.sample()
        with patch.object(memory.os, "listdir", side_effect=PermissionError()) as listing:
            with patch.object(memory.os, "supports_fd", os.supports_fd | {listing}):
                failed = self.sampler.sample()
        self.assertEqual(failed["status"], "stale")
        self.assertEqual(failed["sampled_at"], first["sampled_at"])
        self.assertEqual(failed["unreadable_count"], 1)

    def test_unavailable_without_previous_observation(self):
        shutil.rmtree(self.proc)
        sample = self.sampler.sample()
        self.assertEqual(sample["status"], "unavailable")
        self.assertIsNone(sample["sampled_at"])
        self.assertIsNotNone(sample["attempted_at"])
        self.assert_partition(sample)

    def test_no_follow_support_fails_closed(self):
        self.process(1)
        with patch.object(memory.os, "supports_dir_fd", set()):
            sample = self.sampler.sample()
        self.assertEqual(sample["status"], "unavailable")

    def test_failed_enumeration_closes_pinned_root_descriptor(self):
        opened = []
        original_open_root = memory._open_directory_path
        def open_root(path):
            descriptor = original_open_root(path)
            opened.append(descriptor)
            return descriptor
        with patch.object(memory, "_open_directory_path", side_effect=open_root):
            with patch.object(memory.os, "listdir", side_effect=PermissionError()) as listing:
                with patch.object(memory.os, "supports_fd", os.supports_fd | {listing}):
                    sample = self.sampler.sample()
        self.assertEqual(sample["status"], "unavailable")
        self.assertEqual(len(opened), 1)
        with self.assertRaises(OSError) as error:
            os.fstat(opened[0])
        self.assertEqual(error.exception.errno, errno.EBADF)

    def test_returned_data_cannot_mutate_retained_sample(self):
        self.process(1)
        first = self.sampler.sample()
        first["rows"][0]["name"] = "changed"
        first["rows"].clear()
        shutil.rmtree(self.proc)
        stale = self.sampler.sample()
        self.assertEqual(stale["rows"][0]["name"], "synthetic")
        stale["rows"][0]["rss_bytes"] = 0
        self.assertEqual(self.sampler.sample()["rows"][0]["rss_bytes"], 12288)

    def test_sampling_is_serial_under_concurrency(self):
        self.process(1)
        first_entered = threading.Event()
        release_first = threading.Event()
        counters_lock = threading.Lock()
        active = maximum = calls = 0
        original_read = self.sampler._read_status
        def read(fd, entry):
            nonlocal active, maximum, calls
            with counters_lock:
                active += 1
                calls += 1
                this_call = calls
                maximum = max(maximum, active)
            try:
                if this_call == 1:
                    first_entered.set()
                    if not release_first.wait(5):
                        raise AssertionError("Synthetic concurrency test timed out")
                return original_read(fd, entry)
            finally:
                with counters_lock:
                    active -= 1
        with patch.object(self.sampler, "_read_status", side_effect=read):
            with ThreadPoolExecutor(max_workers=4) as pool:
                first = pool.submit(self.sampler.sample)
                self.assertTrue(first_entered.wait(5))
                others = [pool.submit(self.sampler.sample) for _ in range(3)]
                release_first.set()
                samples = [first.result(timeout=5)] + [task.result(timeout=5) for task in others]
        self.assertEqual(maximum, 1)
        self.assertEqual(calls, 4)
        self.assertTrue(all(sample["status"] == "ok" for sample in samples))
        self.assertTrue(all(sample["rows"] == samples[0]["rows"] for sample in samples))
        self.assertIsNot(samples[0]["rows"], samples[1]["rows"])


class ProcessMemorySortTests(unittest.TestCase):
    def setUp(self):
        self.rows = [{"pid": pid, "name": name, "rss_bytes": rss,
                      "task_attribution": "unknown"}
                     for pid, name, rss in ((9, "Zulu", 20), (3, "alpha", 40),
                                            (6, "Beta", 20), (1, "alpha", 5))]

    def test_rss_both_directions_and_stable_ties(self):
        self.assertEqual([row["pid"] for row in memory.sort_process_rows(self.rows)],
                         [3, 6, 9, 1])
        self.assertEqual([row["pid"] for row in memory.sort_process_rows(self.rows, "rss_asc")],
                         [1, 6, 9, 3])

    def test_pid_and_casefolded_name(self):
        self.assertEqual([row["pid"] for row in memory.sort_process_rows(self.rows, "pid")],
                         [1, 3, 6, 9])
        self.assertEqual([row["pid"] for row in memory.sort_process_rows(self.rows, "name")],
                         [1, 3, 6, 9])

    def test_sort_has_no_input_mutation_or_shared_row_dicts(self):
        original = json.dumps(self.rows)
        sorted_rows = memory.sort_process_rows(self.rows)
        self.assertEqual(json.dumps(self.rows), original)
        sorted_rows[0]["name"] = "changed"
        self.assertEqual(json.dumps(self.rows), original)

    def test_unsupported_order_rejected_even_if_empty(self):
        with self.assertRaises(ValueError):
            memory.sort_process_rows([], "total")


if __name__ == "__main__":
    unittest.main()
