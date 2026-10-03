"""Read-only RSS observations for processes visible to this sampler.

Only ASCII-numeric entries and their ``status`` files are visited. Symlinks are
never followed, including components of ``proc_root``. No command lines,
environment variables, task ownership, process control, or RSS totals are used.

``visible_count`` counts numeric directory-entry candidates; unsafe/non-directory
candidates count as unreadable. ``readable_count`` counts usable Name + VmRSS
records and equals the number of rows. Missing/invalid VmRSS (including kernel
threads without VmRSS) is unknown: omit the row and count it as unreadable, never
invent zero. Explicit ``VmRSS: 0 kB`` is a valid zero. These counts plus
``exited_count`` partition the visible candidates. Counts and rows describe one
non-atomic observation of the sampler's process namespace, not the whole host.

Root failure retains the last completed observation, including its timestamp and
counts, with status stale and a newer attempted_at. Without one, it is unavailable
and sampled_at is None. An empty readable root is a valid ok observation.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import errno
import os
import re
import stat
import threading
import unicodedata
from typing import Literal, TypedDict

__all__ = ["ProcessMemorySampler", "sort_process_rows"]

_SCOPE = "sampler_visible_processes"
_MAX_STATUS_BYTES = 64 * 1024
_RSS = re.compile(r"[ \t]*([0-9]+)[ \t]+kB[ \t\r]*\Z", re.ASCII)
_SORT_ORDERS = ("rss_desc", "rss_asc", "pid", "name")


class ProcessMemoryRow(TypedDict):
    pid: int
    name: str
    rss_bytes: int
    task_attribution: Literal["unknown"]


class ProcessMemorySample(TypedDict):
    sampled_at: str | None
    attempted_at: str
    visible_count: int
    readable_count: int
    unreadable_count: int
    exited_count: int
    status: Literal["ok", "partial", "stale", "unavailable"]
    error: str | None
    scope: Literal["sampler_visible_processes"]
    rows: list[ProcessMemoryRow]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sort_process_rows(
    rows: list[ProcessMemoryRow], order: str = "rss_desc"
) -> list[ProcessMemoryRow]:
    """Return independent sorted rows without modifying the input.

    RSS may be descending or ascending; PID and name are ascending. Ties use
    ascending PID. Names sort by casefolded literal text, then exact text/PID.
    """
    if order not in _SORT_ORDERS:
        raise ValueError("Unsupported process-memory sort order")
    copied = [dict(row) for row in rows]
    if order == "rss_desc":
        return sorted(copied, key=lambda row: (-row["rss_bytes"], row["pid"]))
    if order == "rss_asc":
        return sorted(copied, key=lambda row: (row["rss_bytes"], row["pid"]))
    if order == "name":
        return sorted(copied, key=lambda row: (
            row["name"].casefold(), row["name"], row["pid"]
        ))
    return sorted(copied, key=lambda row: row["pid"])


def _open_directory_path(path: str) -> int:
    """Open and pin a directory without following any path-component symlink."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    current = os.open("/" if os.path.isabs(path) else ".", flags)
    try:
        for component in path.split("/"):
            if component in ("", "."):
                continue
            following = os.open(component, flags, dir_fd=current)
            os.close(current)
            current = following
        return current
    except BaseException:
        os.close(current)
        raise


def _parse_status(contents: bytes, pid: int) -> ProcessMemoryRow:
    if len(contents) > _MAX_STATUS_BYTES:
        raise ValueError("Oversized process status")
    fields: dict[str, str] = {}
    for line in contents.decode("utf-8", errors="replace").split("\n"):
        key, separator, value = line.partition(":")
        if separator and key in ("Name", "VmRSS"):
            if key in fields:
                raise ValueError("Ambiguous process status")
            fields[key] = value
    name = fields.get("Name", "").strip(" \t\r")
    match = _RSS.fullmatch(fields.get("VmRSS", ""))
    if not name or match is None:
        raise ValueError("Missing or invalid Name/VmRSS")
    rss_bytes = int(match.group(1)) * 1024
    # Markup remains literal text. Remove terminal/control/bidi-format escapes;
    # consumers must still render names as text, never HTML or executable code.
    name = "".join(
        "\ufffd" if unicodedata.category(character) in ("Cc", "Cf", "Cs")
        else character for character in name
    )[:256]
    return {"pid": pid, "name": name, "rss_bytes": rss_bytes,
            "task_attribution": "unknown"}


class ProcessMemorySampler:
    """Serial, in-memory sampler; construction performs no I/O.

    ``sample()`` returns a JSON-compatible independent snapshot. UTC timestamps
    are ISO 8601 strings ending in Z. No observations are written to disk.
    Platforms without safe descriptor-relative/no-follow support fail closed.
    """

    def __init__(self, proc_root: str | os.PathLike[str] = "/proc") -> None:
        self.proc_root = os.fspath(proc_root)
        if not isinstance(self.proc_root, str) or not self.proc_root:
            raise ValueError("Process directory must be a nonempty text path")
        self._lock = threading.Lock()
        self._last_sample: ProcessMemorySample | None = None

    def _root_failure(self, attempted_at: str) -> ProcessMemorySample:
        if self._last_sample is not None:
            result = deepcopy(self._last_sample)
            result.update(attempted_at=attempted_at, status="stale",
                          error="Process directory unavailable; retaining previous observation")
            return result
        return {"sampled_at": None, "attempted_at": attempted_at,
                "visible_count": 0, "readable_count": 0,
                "unreadable_count": 0, "exited_count": 0,
                "status": "unavailable", "error": "Process directory unavailable",
                "scope": _SCOPE, "rows": []}

    @staticmethod
    def _read_status(root_fd: int, entry: str) -> bytes:
        directory = os.open(entry, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                            | os.O_CLOEXEC, dir_fd=root_fd)
        try:
            descriptor = os.open("status", os.O_RDONLY | os.O_NOFOLLOW
                                 | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory)
            try:
                if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                    raise ValueError("Process status is not a regular file")
                with os.fdopen(descriptor, "rb", closefd=False) as handle:
                    return handle.read(_MAX_STATUS_BYTES + 1)
            finally:
                os.close(descriptor)
        finally:
            os.close(directory)

    def sample(self) -> ProcessMemorySample:
        """Collect only Name/VmRSS; root errors retain the last completed sample."""
        with self._lock:
            attempted_at = _utc_now()
            root_fd: int | None = None
            entries: list[str] | None = None
            try:
                required = ("O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC", "O_NONBLOCK")
                if (any(not hasattr(os, flag) for flag in required)
                        or os.open not in os.supports_dir_fd
                        or os.listdir not in os.supports_fd):
                    return self._root_failure(attempted_at)
                root_fd = _open_directory_path(self.proc_root)
                entries = [entry for entry in os.listdir(root_fd)
                           if entry.isascii() and entry.isdecimal()]
            except (OSError, ValueError, NotImplementedError):
                return self._root_failure(attempted_at)
            finally:
                # Successful enumeration keeps the pinned descriptor for reads.
                if root_fd is not None and entries is None:
                    os.close(root_fd)

            assert root_fd is not None and entries is not None

            rows: list[ProcessMemoryRow] = []
            unreadable = exited = invalid = 0
            try:
                for entry in entries:
                    try:
                        row = _parse_status(self._read_status(root_fd, entry), int(entry))
                    except OSError as error:
                        if error.errno in (errno.ENOENT, errno.ESRCH):
                            exited += 1
                        else:
                            unreadable += 1
                    except (ValueError, UnicodeError):
                        unreadable += 1
                        invalid += 1
                    else:
                        rows.append(row)
            finally:
                os.close(root_fd)

            errors = []
            if invalid:
                errors.append(f"{invalid} status records missing or invalid Name/VmRSS")
            if unreadable - invalid:
                errors.append(f"{unreadable - invalid} process statuses unreadable")
            if exited:
                errors.append(f"{exited} processes exited during sampling")
            result: ProcessMemorySample = {
                "sampled_at": _utc_now(), "attempted_at": attempted_at,
                "visible_count": len(entries), "readable_count": len(rows),
                "unreadable_count": unreadable, "exited_count": exited,
                "status": "partial" if errors else "ok",
                "error": "; ".join(errors) if errors else None,
                "scope": _SCOPE, "rows": sort_process_rows(rows, "pid"),
            }
            self._last_sample = result
            return deepcopy(result)
