"""Local metrics and an opt-in task ledger. Python standard library only."""
import argparse
from .doctor import install_doctor, COMPONENTS, OBSERVATION_STATES
from . import VERSION
import errno
import hashlib
from datetime import datetime, timezone
from contextlib import contextmanager
import math
import sys
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sqlite3
import stat
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
import uuid

ROOT = Path(__file__).resolve().parents[2]
STATUSES = ("succeeded", "failed", "cancelled")
OPEN_STATUSES = ("running", "waiting_user", "waiting_external", "paused", "awaiting_review")
LIFECYCLE_STATUSES = OPEN_STATUSES + STATUSES
# A terminal run is immutable; continuation uses a new run on the same activity.
ALLOWED_TRANSITIONS = {state: frozenset(LIFECYCLE_STATUSES) - {state} for state in OPEN_STATUSES}
ARTIFACT_DESIGNATIONS = ("draft", "final")
DELIVERY_STATUSES = ("sent", "accepted", "user_open_confirmed")
VERIFICATION_STATUSES = ("passed", "failed", "untested")
OBSERVED_STATUSES = ("created", "running", "completed", "failed", "interrupted", "unknown")
BINDING_SOURCES = ("cloud_thread", "codex_thread")
ENVIRONMENT_KINDS = ("cloud", "desktop", "remote")


AGENT_STATUSES = ("running", "idle", "blocked", "unavailable", "unknown")

AGENT_AVATARS = ("mint", "sky", "lavender", "peach")

RELEASE_STATUSES = ("unknown", "unpublished", "published")

SYNC_STATUSES = ("unknown", "unpublished", "matched", "different", "local_changes")

INSTALL_NOTES = [
    {"zh": "紧凑活动、Agent、计划和软件视图；支持中英切换", "en": "Compact activity, agent, schedule and software views with Chinese/English UI"},
    {"zh": "私有任务文件归档及受控图片、纯文本预览", "en": "Private task output archives with bounded image and plain-text previews"},
    {"zh": "仅显式登记状态与发布信息；不自动发现、更新或发布", "en": "Explicitly recorded status and release observations; no automatic discovery, updating or publishing"},
]

def verified_repository_url(value):
    if not isinstance(value, str) or not re.fullmatch(r"https://github\.com/[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}/?", value):
        raise ValueError("Use the verified HTTPS GitHub owner/repository URL without credentials, query or fragment")
    return value.rstrip("/")

SKILL_ORIGINS = ("unknown", "project_bundled", "personal", "independent")

SKILL_PUBLICATIONS = ("unknown", "pending", "published", "not_applicable")

def skill_origin_label(value, language="zh"):
    labels = {"unknown": ("来源未标记", "Origin unspecified"), "project_bundled": ("项目配套", "Project bundled"), "personal": ("个人规则", "Personal rules"), "independent": ("独立 Skill", "Independent Skill")}
    return labels.get(value, labels["unknown"])[language == "en"]

def skill_publication_label(value, language="zh"):
    labels = {"unknown": ("发布未核验", "Publication unverified"), "pending": ("待发布", "Pending publication"), "published": ("已核验发布", "Publication checked"), "not_applicable": ("不随项目发布", "Not bundled for publication")}
    return labels.get(value, labels["unknown"])[language == "en"]

ARTIFACT_KINDS = ("report", "image", "document", "data", "other")

ARTIFACT_SUFFIXES = (".txt", ".md", ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".csv", ".json", ".xlsx", ".docx", ".pptx", ".zip", ".html")

MAX_ARTIFACT_BYTES = 32 * 1024 * 1024

LIBRARY_XATTRS = ("user.library-file-id", "user.library-file-version")

def artifact_kind_label(value, language="zh"):
    labels = {"report": ("报告", "Report"), "image": ("图片", "Image"), "document": ("文档", "Document"), "data": ("数据", "Data"), "other": ("其他", "Other")}
    return labels.get(value, labels["other"])[1 if language == "en" else 0]

WORK_TYPES = {
    "unspecified": ("未注明", "Unspecified"),
    "development": ("编程开发", "Development"),
    "research": ("资料搜集", "Research"),
    "testing": ("测试验证", "Testing"),
    "review": ("审查核对", "Review"),
    "writing": ("内容写作", "Writing"),
    "coordination": ("任务协调", "Coordination"),
}

def agent_text(agent, field, language="zh"):
    """Use human-configured English only; otherwise preserve the original."""
    return (agent.get(field + "_en") if language == "en" else None) or agent.get(field) or ""

def work_type_label(value, language="zh"):
    return WORK_TYPES.get(value, WORK_TYPES["unspecified"])[1 if language == "en" else 0]

def agent_work(snapshot, agent):
    """Ownership and lifecycle do not independently prove current work."""
    assignments = {a["task_id"]: a for a in snapshot.get("agent_assignments", []) if a.get("agent_id") == agent["id"]}
    latest = {}
    for run in snapshot.get("runs", []):
        key = run["task_id"]
        if key not in latest or (run.get("started", 0), run.get("id", "")) > (latest[key].get("started", 0), latest[key].get("id", "")):
            latest[key] = run
    result = {"current": [], "unfinished": [], "recent": []}
    for task in snapshot.get("tasks", []):
        if task["id"] not in assignments:
            continue
        assignment = assignments[task["id"]]
        status = latest.get(task["id"], {}).get("status") or task.get("latest_status") or "pending"
        row = {"task": task, "work_type": assignment.get("work_type", "unspecified"), "status": status}
        if status == "pending" or status in OPEN_STATUSES:
            result["unfinished"].append(row)
            if agent.get("status") == "running" and status == "running":
                result["current"].append(row)
        else:
            result["recent"].append(row)
    return result

def artifact_delivery_label(artifact, language="zh"):
    en = language == "en"
    designation = {"draft": ("草稿", "Draft"), "final": ("最终稿", "Final"), "unclassified": ("未指定版本", "Unclassified")}.get(artifact.get("designation"), ("未指定版本", "Unclassified"))[en]
    observed = {row["status"] for row in artifact.get("delivery_observations", []) if row.get("sha256") == artifact.get("sha256")}
    labels = [("已归档", "Archived")[en], designation]
    for status, zh, english in (("sent", "已记录发送", "Sent recorded"), ("accepted", "传输已接收", "Transport accepted"), ("user_open_confirmed", "用户打开已确认", "User open confirmed")):
        if status in observed:
            labels.append(english if en else zh)
    if not observed:
        labels.append("Delivery unverified" if en else "交付未核验")
    if "user_open_confirmed" not in observed:
        labels.append("User open unverified" if en else "用户打开未核验")
    return " · ".join(labels)

def verification_label(value, language="zh"):
    return {"passed": ("检查通过", "Checks passed"), "failed": ("检查失败", "Checks failed"), "untested": ("未测试", "Untested")}.get(value, ("未登记验证", "Verification not recorded"))[language == "en"]

def attention_items(snapshot):
    """Derived read-only queue, one latest run per visible task; no inferred needs."""
    latest = {}
    for run in snapshot.get("latest_runs", snapshot.get("runs", [])):
        old = latest.get(run["task_id"])
        if old is None or (run.get("started", 0), run.get("id", "")) > (old.get("started", 0), old.get("id", "")):
            latest[run["task_id"]] = run
    result = {"action_required": [], "external": []}
    seen = set()
    for task in snapshot.get("tasks", []):
        if task["id"] in seen:
            continue
        seen.add(task["id"])
        run = latest.get(task["id"])
        if not run:
            continue
        status = run["status"]
        group = "action_required" if status in ("waiting_user", "awaiting_review", "paused") else "external" if status == "waiting_external" else None
        if group:
            result[group].append({"task": task, "run": run})
    return result

def attention_draft(task, run, language="zh"):
    """Copyable suggestion only. Never claim that a decision was sent or accepted."""
    reason, next_step = run.get("lifecycle_reason") or "—", run.get("next_step") or "—"
    if language == "en":
        return f"Regarding task ‘{task['name']}’, please check its current status.\nRecorded reason: {reason}\nSuggested next step: {next_step}\nMy decision or additional information: [please fill in]"
    return f"关于任务“{task['name']}”，请先核对当前状态。\n记录原因：{reason}\n建议下一步：{next_step}\n我的决定或补充信息：[请填写]"

def timestamp(value):
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Timestamp requires an explicit timezone")
        value = parsed.timestamp()
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
        raise ValueError("Timestamp must be finite and non-negative")
    return float(value)


def verified_link(value):
    if not value:
        return None
    if len(value) > 2048 or any(ord(char) < 33 for char in value):
        raise ValueError("Invalid shareable link")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname not in ("chatgpt.com", "chat.openai.com", "codex.openai.com") or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("Use only an actual returned HTTPS link on the supported platform; local/deep links are not shareable here")
    return value


def open_directory(path):
    """Recovery reconstruction: walk an explicit path without following symlinks."""
    path = Path(path).absolute()
    if ".." in path.parts:
        raise ValueError("Directory path traversal is not allowed")
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def default_data_dir():
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "dots-panel"


def text(value, limit=500):
    value = str(value).strip()
    if not value or len(value) > limit or any(ord(c) < 32 and c not in "\n\t" for c in value):
        raise ValueError(f"Text must contain 1–{limit} printable characters")
    return value


def verified_skill_url(value):
    if not isinstance(value, str) or not re.fullmatch(r"https://chatgpt\.com/skills\?skill_id=[A-Za-z0-9_-]{1,100}", value):
        raise ValueError("Use a verified ChatGPT skill detail URL")
    return value


SKILL_STATUSES = ("available", "unavailable", "unknown")


SKILL_VERSIONS = ("unverified", "saved_verified")


def skill_status_label(value, language="zh"):
    labels = {"available": ("已观察可读取", "Observed readable"), "unavailable": ("已观察不可读取", "Observed unreadable"), "unknown": ("可用性未核验", "Availability unverified")}
    return labels.get(value, labels["unknown"])[language == "en"]


def skill_version_label(value, language="zh"):
    labels = {"unverified": ("版本未核验", "Version unverified"), "saved_verified": ("已核验保存内容", "Saved content checked")}
    return labels.get(value, labels["unverified"])[language == "en"]


def project_rules():
    # Packaged project guidelines only: never load assistant/private policy files.
    return json.loads(Path(__file__).with_name("project_rules.json").read_text(encoding="utf-8"))


from .recovery_support import RecoveryStoreMixin, recovery_notice


class Store(RecoveryStoreMixin):
    def __init__(self, directory):
        requested = Path(directory).expanduser().absolute()
        if any(p.is_symlink() for p in (requested, *requested.parents)):
            raise ValueError("Runtime directory must not contain symlinks")
        self.directory = requested.resolve()
        if self.directory == ROOT or ROOT in self.directory.parents:
            raise ValueError("Runtime data must be outside the source checkout")
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        for target in (self.directory, *(self.directory / folder for folder in ("config", "db", "logs", "run", "tmp"))):
            if target.is_symlink():
                raise ValueError("Runtime directories must not be symlinks")
            target.mkdir(exist_ok=True, mode=0o700)
            if target.stat().st_mode & 0o077:
                raise ValueError("Existing runtime directory has non-private permissions; owner review required")
        self.path = self.directory / "db/panel.sqlite3"
        if self.path.is_symlink():
            raise ValueError("Database must not be a symlink")
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        except FileExistsError:
            if not stat.S_ISREG(self.path.stat().st_mode) or self.path.stat().st_mode & 0o077:
                raise ValueError("Existing database has non-private permissions; owner review required")
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS rules_config (id INTEGER PRIMARY KEY CHECK(id=1), skill_url TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS user_skills (
              id TEXT PRIMARY KEY, scope TEXT NOT NULL CHECK(scope='user_installed'),
              name TEXT NOT NULL, name_en TEXT NOT NULL, purpose TEXT NOT NULL, purpose_en TEXT NOT NULL,
              when_used TEXT NOT NULL, when_used_en TEXT NOT NULL, url TEXT,
              status TEXT NOT NULL CHECK(status IN ('available','unavailable','unknown')),
              version_status TEXT NOT NULL CHECK(version_status IN ('unverified','saved_verified')),
              version_note TEXT NOT NULL, version_note_en TEXT NOT NULL,
              observed_at REAL NOT NULL, recorded_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS skill_origins (
              skill_id TEXT PRIMARY KEY REFERENCES user_skills(id), origin TEXT NOT NULL,
              repo_url TEXT, publication TEXT NOT NULL, commit_sha TEXT, observed_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS release_observation (
              id INTEGER PRIMARY KEY CHECK(id=1), repo_url TEXT NOT NULL,
              release_status TEXT NOT NULL, release_tag TEXT, remote_commit TEXT,
              sync_status TEXT NOT NULL, checked_at REAL NOT NULL, recorded_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS artifacts (
              id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id),
              relative_path TEXT NOT NULL UNIQUE, title TEXT NOT NULL, kind TEXT NOT NULL,
              size INTEGER NOT NULL, sha256 TEXT NOT NULL, created REAL NOT NULL, library_id TEXT);
            CREATE TABLE IF NOT EXISTS agents (
              id TEXT PRIMARY KEY, name TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'unknown' CHECK(status IN ('running','idle','blocked','unavailable','unknown')),
              observed_at REAL, note TEXT NOT NULL DEFAULT '',
              avatar TEXT NOT NULL CHECK(avatar IN ('mint','sky','lavender','peach')),
              created REAL NOT NULL, updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS agent_assignments (
              task_id TEXT PRIMARY KEY REFERENCES tasks(id),
              agent_id TEXT NOT NULL REFERENCES agents(id), assigned_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS installation_observations (
              id INTEGER PRIMARY KEY, component TEXT NOT NULL, status TEXT NOT NULL,
              evidence TEXT NOT NULL, observed_at REAL NOT NULL, recorded_at REAL NOT NULL,
              skill_id TEXT, reference TEXT NOT NULL, configuration_id INTEGER);
            CREATE TABLE IF NOT EXISTS artifact_designations (
              id INTEGER PRIMARY KEY, artifact_id TEXT NOT NULL REFERENCES artifacts(id),
              designation TEXT NOT NULL, evidence TEXT NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS artifact_delivery (
              id INTEGER PRIMARY KEY, artifact_id TEXT NOT NULL REFERENCES artifacts(id),
              status TEXT NOT NULL, evidence TEXT NOT NULL, observed_at REAL NOT NULL,
              recorded_at REAL NOT NULL, sha256 TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS closeout_records (
              id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
              summary TEXT NOT NULL, scope TEXT NOT NULL, verification TEXT NOT NULL,
              evidence TEXT NOT NULL, limits TEXT NOT NULL, no_artifact_reason TEXT NOT NULL,
              created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS closeout_artifacts (
              record_id TEXT NOT NULL REFERENCES closeout_records(id),
              artifact_id TEXT NOT NULL REFERENCES artifacts(id), sha256 TEXT NOT NULL,
              PRIMARY KEY(record_id,artifact_id));
            CREATE TABLE IF NOT EXISTS closeout_completions (
              record_id TEXT PRIMARY KEY REFERENCES closeout_records(id),
              run_id TEXT NOT NULL UNIQUE REFERENCES runs(id), created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS task_bindings (
              task_id TEXT PRIMARY KEY REFERENCES tasks(id), source_type TEXT NOT NULL,
              thread_id TEXT NOT NULL, environment_kind TEXT NOT NULL, environment_id TEXT,
              observed_status TEXT NOT NULL, observed_at REAL NOT NULL,
              verified_url TEXT, synced_at REAL NOT NULL, sync_mode TEXT NOT NULL DEFAULT 'manual');
            CREATE TABLE IF NOT EXISTS schedules (
              id TEXT PRIMARY KEY, name TEXT NOT NULL, project TEXT NOT NULL,
              source TEXT NOT NULL, state TEXT NOT NULL, next_run REAL,
              created REAL NOT NULL, updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS software (
              id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL,
              kind TEXT NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS activity (
              id INTEGER PRIMARY KEY, created REAL NOT NULL, project TEXT NOT NULL,
              role TEXT NOT NULL, stage TEXT NOT NULL, message TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS tasks (
              id TEXT PRIMARY KEY, name TEXT NOT NULL, project TEXT NOT NULL,
              created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS runs (
              id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id),
              status TEXT NOT NULL, started REAL NOT NULL, updated REAL NOT NULL,
              finished REAL, note TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
              created REAL NOT NULL, message TEXT NOT NULL);
            """)
            run_columns = {row[1] for row in db.execute("PRAGMA table_info(runs)")}
            for field in ("lifecycle_reason", "next_step", "lifecycle_evidence"):
                if field not in run_columns:
                    db.execute(f"ALTER TABLE runs ADD COLUMN {field} TEXT NOT NULL DEFAULT ''")
            if "closeout_required" not in run_columns:
                db.execute("ALTER TABLE runs ADD COLUMN closeout_required INTEGER NOT NULL DEFAULT 0")
            agent_columns = {row[1] for row in db.execute("PRAGMA table_info(agents)")}
            for field in ("name_en", "note_en"):
                if field not in agent_columns:
                    db.execute(f"ALTER TABLE agents ADD COLUMN {field} TEXT NOT NULL DEFAULT ''")
            assignment_columns = {row[1] for row in db.execute("PRAGMA table_info(agent_assignments)")}
            if "work_type" not in assignment_columns:
                db.execute("ALTER TABLE agent_assignments ADD COLUMN work_type TEXT NOT NULL DEFAULT 'unspecified'")
            task_columns = {row[1] for row in db.execute("PRAGMA table_info(tasks)")}
            if "tracking_mode" not in task_columns:
                db.execute("ALTER TABLE tasks ADD COLUMN tracking_mode TEXT NOT NULL DEFAULT 'manual'")
            columns = {row[1] for row in db.execute("PRAGMA table_info(activity)")}
            for name, definition in (("task_id", "TEXT"), ("state", "TEXT NOT NULL DEFAULT 'in_progress'"), ("source_event_id", "TEXT"), ("source_observed_at", "REAL"), ("ingested_at", "REAL")):
                if name not in columns:
                    db.execute(f"ALTER TABLE activity ADD COLUMN {name} {definition}")
            db.execute("CREATE INDEX IF NOT EXISTS runs_task_latest ON runs(task_id,started DESC,id DESC)")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS binding_source_thread ON task_bindings(source_type,thread_id)")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS activity_source_event ON activity(task_id,source_event_id) WHERE source_event_id IS NOT NULL")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                yield db
        finally:
            db.close()

    def register(self, key, name, project, tracking_mode="manual"):
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", key):
            raise ValueError("Task ID must use lowercase letters, digits, hyphens or underscores")
        if tracking_mode not in ("manual", "heartbeat"):
            raise ValueError("tracking_mode must be manual or heartbeat")
        with self.connect() as db:
            db.execute("INSERT INTO tasks(id,name,project,created,tracking_mode) VALUES(?,?,?,?,?)", (key, text(name, 120), text(project, 120), time.time(), tracking_mode))
        self.task_init(key)
        return key

    def start(self, task_id, note=""):
        key = uuid.uuid4().hex[:16]
        now = time.time()
        with self.connect() as db:
            db.execute("INSERT INTO runs(id,task_id,status,started,updated,finished,note,closeout_required) VALUES(?,?,?,?,?,?,?,1)", (key, task_id, "running", now, now, None, text(note) if note else ""))
        return key

    def _gate_success(self, key, from_status=None):
        with self.connect() as db:
            run = db.execute("SELECT closeout_required FROM runs WHERE id=?", (key,)).fetchone()
            if not run or not run["closeout_required"]:
                return None
            record = db.execute("SELECT id FROM closeout_records WHERE run_id=? ORDER BY created DESC,id DESC LIMIT 1", (key,)).fetchone()
            if not record:
                raise ValueError("New runs require closeout-record evidence before success")
        return self.closeout(key, record["id"], from_status=from_status)

    def update(self, key, status=None, message=None):
        if status is not None and status not in STATUSES:
            raise ValueError("Invalid terminal status")
        if status == "succeeded" and self._gate_success(key) is not None:
            return
        now = time.time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status FROM runs WHERE id=?", (key,)).fetchone()
            if not row:
                raise ValueError("Unknown run ID")
            if row["status"] not in OPEN_STATUSES:
                raise ValueError("Run already finished")
            if message is not None:
                db.execute("INSERT INTO events(run_id,created,message) VALUES(?,?,?)", (key, now, text(message, 2000)))
            db.execute("UPDATE runs SET updated=?,status=?,finished=? WHERE id=?", (now, status or row["status"], now if status else None, key))
            if status:
                # Legacy finish remains supported but must not display an obsolete
                # waiting reason as evidence for completion.
                db.execute("UPDATE runs SET lifecycle_reason='',next_step='',lifecycle_evidence='' WHERE id=?", (key,))

    def transition(self, key, status, reason, evidence, next_step="", from_status=None):
        """Record a justified lifecycle change; never control the actual executor."""
        if status not in LIFECYCLE_STATUSES:
            raise ValueError("Invalid lifecycle status")
        if from_status is not None and from_status not in LIFECYCLE_STATUSES:
            raise ValueError("Invalid expected lifecycle status")
        if not isinstance(reason, str) or not isinstance(evidence, str) or not isinstance(next_step, str):
            raise ValueError("Reason, evidence and next step must be text")
        reason, evidence = text(reason, 2000), text(evidence, 2000)
        next_step = text(next_step, 2000) if status in OPEN_STATUSES or next_step else ""
        if status == "succeeded":
            result = self._gate_success(key, from_status)
            if result is not None:
                return {**result, "record_only": True}
        now = time.time()
        with self.connect() as db:
            # Serialize validation and writing: a stale observation must not overwrite
            # a concurrent terminal transition.
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status,task_id FROM runs WHERE id=?", (key,)).fetchone()
            if not row:
                raise ValueError("Unknown run ID")
            previous = row["status"]
            if from_status is not None and previous != from_status:
                raise ValueError("Lifecycle changed; refresh before recording a transition")
            if status not in ALLOWED_TRANSITIONS.get(previous, ()):
                raise ValueError(f"Invalid lifecycle transition: {previous} -> {status}")
            db.execute("UPDATE runs SET status=?,updated=?,finished=?,lifecycle_reason=?,next_step=?,lifecycle_evidence=? WHERE id=?",
                       (status, now, now if status in STATUSES else None, reason, next_step, evidence, key))
            message = f"{previous} -> {status} | {reason} | Next: {next_step or '—'} | Evidence: {evidence}"
            db.execute("INSERT INTO events(run_id,created,message) VALUES(?,?,?)", (key, now, message))
            task = db.execute("SELECT project FROM tasks WHERE id=?", (row["task_id"],)).fetchone()
            db.execute("INSERT INTO activity(created,project,role,stage,message,task_id,state) VALUES(?,?,?,?,?,?,?)",
                       (now, task["project"], "system", "state_changed", message, row["task_id"], "in_progress"))
        return {"run_id": key, "previous_status": previous, "status": status,
                "lifecycle_reason": reason, "next_step": next_step, "lifecycle_evidence": evidence,
                "record_only": True}

    def activity(self, project, role, stage, message, task_id=None, state="in_progress"):
        if role not in ("user", "assistant", "system"):
            raise ValueError("Invalid activity role")
        if state not in ("planned", "in_progress", "verified"):
            raise ValueError("Invalid progress state")
        with self.connect() as db:
            if task_id and not db.execute("SELECT id FROM tasks WHERE id=?", (task_id,)).fetchone():
                raise ValueError("Unknown task ID")
            db.execute("INSERT INTO activity(created,project,role,stage,message,task_id,state) VALUES(?,?,?,?,?,?,?)", (time.time(), text(project, 120), role, text(stage, 60), text(message, 4000), task_id, state))

    def bind(self, task_id, source_type, thread_id, environment_kind, environment_id, observed_status, observed_at, url=None):
        if source_type not in BINDING_SOURCES or environment_kind not in ENVIRONMENT_KINDS or observed_status not in OBSERVED_STATUSES:
            raise ValueError("Unsupported binding source, environment or observed status")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}", thread_id):
            raise ValueError("Use the actual returned thread ID, not an internal task path or URL")
        environment_id = text(environment_id, 200) if environment_id else None
        observed_at, url = timestamp(observed_at), verified_link(url)
        with self.connect() as db:
            if not db.execute("SELECT id FROM tasks WHERE id=?", (task_id,)).fetchone():
                raise ValueError("Register the activity before binding it")
            duplicate = db.execute("SELECT task_id FROM task_bindings WHERE source_type=? AND thread_id=? AND task_id<>?", (source_type, thread_id, task_id)).fetchone()
            if duplicate:
                raise ValueError("This actual session is already bound to another activity; reuse that activity")
            existing = db.execute("SELECT * FROM task_bindings WHERE task_id=?", (task_id,)).fetchone()
            if existing:
                identity = (source_type, thread_id, environment_kind, environment_id)
                if identity != tuple(existing[key] for key in ("source_type", "thread_id", "environment_kind", "environment_id")):
                    raise ValueError("Activity already bound to a different session; continue its existing binding")
                if url and existing["verified_url"] and url != existing["verified_url"]:
                    raise ValueError("Existing verified link differs; refusing silent replacement")
                if observed_at >= existing["observed_at"]:
                    db.execute("UPDATE task_bindings SET observed_status=?,observed_at=?,verified_url=COALESCE(?,verified_url),synced_at=? WHERE task_id=?", (observed_status, observed_at, url, time.time(), task_id))
            else:
                db.execute("INSERT INTO task_bindings(task_id,source_type,thread_id,environment_kind,environment_id,observed_status,observed_at,verified_url,synced_at) VALUES(?,?,?,?,?,?,?,?,?)", (task_id, source_type, thread_id, environment_kind, environment_id, observed_status, observed_at, url, time.time()))
        return task_id

    def ingest(self, task_id, source_event_id, role, stage, state, message, observed_at, observed_status=None):
        if role not in ("user", "assistant", "system") or state not in ("planned", "in_progress", "verified"):
            raise ValueError("Invalid summary role or stage state")
        if observed_status is not None and observed_status not in OBSERVED_STATUSES:
            raise ValueError("Invalid observed status")
        source_event_id, stage, message = text(source_event_id, 200), text(stage, 60), text(message, 4000)
        observed_at = timestamp(observed_at)
        with self.connect() as db:
            binding = db.execute("SELECT * FROM task_bindings WHERE task_id=?", (task_id,)).fetchone()
            if not binding:
                raise ValueError("Bind an actual created session before ingesting its summaries")
            existing = db.execute("SELECT id FROM activity WHERE task_id=? AND source_event_id=?", (task_id, source_event_id)).fetchone()
            if existing:
                return {"activity_id": existing["id"], "duplicate": True}
            task = db.execute("SELECT project FROM tasks WHERE id=?", (task_id,)).fetchone()
            now = time.time()
            cursor = db.execute("INSERT OR IGNORE INTO activity(created,project,role,stage,message,task_id,state,source_event_id,source_observed_at,ingested_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (observed_at, task["project"], role, stage, message, task_id, state, source_event_id, observed_at, now))
            if cursor.rowcount == 0:
                existing = db.execute("SELECT id FROM activity WHERE task_id=? AND source_event_id=?", (task_id, source_event_id)).fetchone()
                return {"activity_id": existing["id"], "duplicate": True}
            if observed_status and observed_at >= binding["observed_at"]:
                db.execute("UPDATE task_bindings SET observed_status=?,observed_at=?,synced_at=? WHERE task_id=?", (observed_status, observed_at, now, task_id))
            else:
                db.execute("UPDATE task_bindings SET synced_at=? WHERE task_id=?", (now, task_id))
            return {"activity_id": cursor.lastrowid, "duplicate": False}

    def schedule_register(self, key, name, project, source="manual", state="disconnected", next_run=None):
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", key):
            raise ValueError("Invalid schedule ID")
        if state not in ("disconnected", "planned", "paused"):
            raise ValueError("Only disconnected, planned or paused registry states are supported")
        if next_run is not None and (not isinstance(next_run, (int, float)) or not math.isfinite(next_run) or next_run < 0):
            raise ValueError("next_run must be a finite timestamp")
        now = time.time()
        with self.connect() as db:
            db.execute("INSERT INTO schedules VALUES(?,?,?,?,?,?,?,?)", (key, text(name, 120), text(project, 120), text(source, 120), state, next_run, now, now))
        return key

    def software_register(self, key, name, description, kind):
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", key):
            raise ValueError("Invalid software ID")
        if kind not in ("dots-panel", "python", "git"):
            raise ValueError("Unsupported software kind; only read-only allowlisted detection is supported")
        with self.connect() as db:
            db.execute("INSERT INTO software VALUES(?,?,?,?,?)", (key, text(name, 120), text(description, 500), kind, time.time()))
        return key

    @contextmanager
    def task_directory(self, task_id, area="outputs", create=False):
        if not isinstance(task_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", task_id):
            raise ValueError("Invalid stable task ID")
        if area not in ("inputs", "outputs", "tmp"):
            raise ValueError("Invalid task directory area")
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone():
                raise ValueError("Unknown task ID")
        fd = open_directory(self.directory)
        try:
            for component in ("tasks", task_id, area):
                if create:
                    try:
                        os.mkdir(component, 0o700, dir_fd=fd)
                    except FileExistsError:
                        pass
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
                if os.fstat(fd).st_mode & 0o077:
                    raise ValueError("Task directories must be private")
            yield fd
        finally:
            os.close(fd)

    def task_init(self, task_id):
        for area in ("inputs", "outputs", "tmp"):
            with self.task_directory(task_id, area, create=True):
                pass
        return {"task_id": task_id, "relative_path": f"tasks/{task_id}"}

    def artifact_add(self, task_id, source, title, kind="report", slug="artifact", library_id=None):
        if kind not in ARTIFACT_KINDS or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,59}", slug):
            raise ValueError("Invalid artifact kind or safe filename slug")
        title = text(title, 160)
        if library_id is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,199}", library_id):
            raise ValueError("Invalid optional Library ID")
        source = Path(source).expanduser().absolute()
        if ".." in source.parts or source.suffix.lower() not in ARTIFACT_SUFFIXES:
            raise ValueError("Unsupported artifact path or file extension")
        self.task_init(task_id)
        parent = open_directory(source.parent)
        try:
            source_fd = os.open(source.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        finally:
            os.close(parent)
        with os.fdopen(source_fd, "rb") as original:
            info = os.fstat(original.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_ARTIFACT_BYTES:
                raise ValueError("Artifact must be a regular file of at most 32 MiB")
            attributes = {}
            if hasattr(os, "getxattr"):
                for attribute in LIBRARY_XATTRS:
                    try:
                        value = os.getxattr(original.fileno(), attribute)
                        if len(value) > 512:
                            raise ValueError("Invalid Library metadata length")
                        attributes[attribute] = value
                    except OSError as exc:
                        if exc.errno not in (errno.ENODATA, errno.ENOTSUP):
                            raise
            source_library_id = attributes.get("user.library-file-id", b"").decode("utf-8")
            if source_library_id:
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,199}", source_library_id):
                    raise ValueError("Invalid source Library ID metadata")
                if library_id and library_id != source_library_id:
                    raise ValueError("Explicit Library ID conflicts with source metadata")
                library_id = source_library_id
            if library_id:
                attributes["user.library-file-id"] = library_id.encode()
            else:
                attributes.pop("user.library-file-version", None)
            key = uuid.uuid4().hex
            name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + slug + "-" + key[:12] + source.suffix.lower()
            relative = f"tasks/{task_id}/outputs/{name}"
            with self.task_directory(task_id, create=False) as destination:
                created = False
                try:
                    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=destination)
                    created = True
                    digest, size = hashlib.sha256(), 0
                    with os.fdopen(fd, "wb") as output:
                        while True:
                            chunk = original.read(1024 * 1024)
                            if not chunk:
                                break
                            size += len(chunk)
                            if size > MAX_ARTIFACT_BYTES:
                                raise ValueError("Artifact grew beyond 32 MiB")
                            digest.update(chunk)
                            output.write(chunk)
                        output.flush()
                        for attribute, value in attributes.items():
                            os.setxattr(output.fileno(), attribute, value)
                        os.fsync(output.fileno())
                    after = os.fstat(original.fileno())
                    if (info.st_size, info.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                        raise ValueError("Source changed while copying; retry after it is finished")
                    now = time.time()
                    with self.connect() as db:
                        project = db.execute("SELECT project FROM tasks WHERE id=?", (task_id,)).fetchone()["project"]
                        db.execute("INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?)", (key, task_id, relative, title, kind, size, digest.hexdigest(), now, library_id))
                        db.execute("INSERT INTO activity(created,project,role,stage,message,task_id,state) VALUES(?,?,?,?,?,?,?)",
                                   (now, project, "system", "artifact", f"成果已归档 / Artifact archived: {title}", task_id, "verified"))
                except BaseException:
                    if created:
                        os.unlink(name, dir_fd=destination)
                    raise
        return {"id": key, "task_id": task_id, "relative_path": relative, "size": size, "sha256": digest.hexdigest()}

    def artifact_bytes(self, artifact_id, suffixes, limit):
        """Read only an explicitly registered output, with identity and content checks."""
        with self.connect() as db:
            row = db.execute("SELECT * FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
        if not row:
            raise ValueError("Unknown registered artifact")
        path = Path(row["relative_path"])
        if len(path.parts) != 4 or path.parts[:3] != ("tasks", row["task_id"], "outputs") or path.suffix not in suffixes:
            raise ValueError("This registered output type cannot be previewed")
        with self.task_directory(row["task_id"]) as directory:
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            with os.fdopen(fd, "rb") as handle:
                info = os.fstat(handle.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
                    raise ValueError("Preview exceeds its safe size limit")
                data = handle.read(limit+1)
        if len(data) > limit or len(data) != row["size"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise ValueError("Artifact differs from its registered hash")
        return data

    def artifact_text(self, artifact_id):
        data = self.artifact_bytes(artifact_id, (".txt", ".md", ".json", ".csv"), 1024*1024)
        return data.decode("utf-8", errors="replace")

    def artifact_png(self, artifact_id):
        """Bounded read for the native viewer only; never executes or opens files."""
        data = self.artifact_bytes(artifact_id, (".png",), 10*1024*1024)
        if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
            raise ValueError("Invalid PNG header")
        width, height = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
        if not (0 < width <= 4096 and 0 < height <= 4096 and width*height <= 8_000_000):
            raise ValueError("PNG dimensions exceed preview limits")
        return data

    def skill_origin(self, key, origin, publication, observed_at, repo_url=None, commit_sha=None):
        if origin not in SKILL_ORIGINS or publication not in SKILL_PUBLICATIONS:
            raise ValueError("Invalid skill origin or publication state")
        observed = timestamp(observed_at)
        if observed > time.time() + 300:
            raise ValueError("Observation cannot be in the future")
        repo = verified_repository_url(repo_url) if repo_url else None
        if origin == "project_bundled":
            if not repo or publication == "not_applicable":
                raise ValueError("Project bundled skills require a repository and publication observation")
        elif repo or commit_sha or publication not in ("unknown", "not_applicable"):
            raise ValueError("Only project bundled skills carry repository publication metadata")
        if publication == "published":
            if not isinstance(commit_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
                raise ValueError("Published observation requires a verified full commit SHA")
        elif commit_sha:
            raise ValueError("Only a published observation carries a commit")
        values = (key, origin, repo, publication, commit_sha, observed)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM user_skills WHERE id=?", (key,)).fetchone():
                raise ValueError("Register the user skill first")
            old = db.execute("SELECT * FROM skill_origins WHERE skill_id=?", (key,)).fetchone()
            if old and observed <= old["observed_at"]:
                if tuple(old) == values:
                    return {"id": key, "duplicate": True}
                raise ValueError("A changed origin requires a newer observation")
            db.execute("INSERT INTO skill_origins VALUES(?,?,?,?,?,?) ON CONFLICT(skill_id) DO UPDATE SET origin=excluded.origin,repo_url=excluded.repo_url,publication=excluded.publication,commit_sha=excluded.commit_sha,observed_at=excluded.observed_at", values)
        return {"id": key, "duplicate": False}

    def installation_observe(self, component, status, evidence, observed_at, skill_id=None, reference=""):
        if component not in COMPONENTS or status not in OBSERVATION_STATES:
            raise ValueError("Invalid installation observation component or status")
        if not isinstance(evidence, str) or not isinstance(reference, str):
            raise ValueError("Installation evidence and reference must be text")
        evidence, observed_at = text(evidence, 2000), timestamp(observed_at)
        reference = text(reference, 200) if reference else ""
        if observed_at > time.time() + 300:
            raise ValueError("Installation observation cannot be more than five minutes in the future")
        configuration_id = None
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT * FROM installation_observations WHERE component=? ORDER BY observed_at DESC,id DESC LIMIT 1", (component,)).fetchone()
            if existing and observed_at <= existing["observed_at"]:
                if observed_at == existing["observed_at"] and all(existing[key] == value for key, value in (("status",status),("evidence",evidence),("skill_id",skill_id),("reference",reference))):
                    return {"id":existing["id"],"component":component,"status":status,"record_only":True,"duplicate":True}
                raise ValueError("Installation observations require newer evidence; stale/conflicting observations rejected")
            if component.startswith("account_") and status == "verified":
                skill = db.execute("SELECT scope,status,version_status FROM user_skills WHERE id=?", (skill_id,)).fetchone()
                origin = db.execute("SELECT origin,publication FROM skill_origins WHERE skill_id=?", (skill_id,)).fetchone()
                expected = "project_bundled" if component == "account_task_skill" else "personal"
                if not skill or not origin or skill["scope"] != "user_installed" or skill["status"] != "available" or skill["version_status"] != "saved_verified" or origin["origin"] != expected:
                    raise ValueError("First register the verified user-installed Skill and its correct origin")
                if component == "account_personal_skill" and origin["publication"] != "not_applicable":
                    raise ValueError("Personal account Skill must not be bundled for publication")
            if component.startswith("scheduler_") and status == "verified":
                if not reference:
                    raise ValueError("Verified scheduler observations require an actual scheduler reference")
                if component == "scheduler_execution":
                    config = db.execute("SELECT * FROM installation_observations WHERE component='scheduler_configuration' ORDER BY observed_at DESC,id DESC LIMIT 1").fetchone()
                    if not config or config["status"] != "verified" or config["reference"] != reference or observed_at < config["observed_at"]:
                        raise ValueError("Execution evidence must match the verified scheduler configuration")
                    configuration_id = config["id"]
            cursor = db.execute("INSERT INTO installation_observations(component,status,evidence,observed_at,recorded_at,skill_id,reference,configuration_id) VALUES(?,?,?,?,?,?,?,?)",
                                (component,status,evidence,observed_at,time.time(),skill_id,reference,configuration_id))
        return {"id":cursor.lastrowid,"component":component,"status":status,"record_only":True}

    def artifact_designate(self, artifact_id, designation, evidence):
        if designation not in ARTIFACT_DESIGNATIONS:
            raise ValueError("Invalid artifact designation")
        if not isinstance(evidence, str):
            raise ValueError("Evidence must be text")
        evidence = text(evidence, 2000)
        self.artifact_bytes(artifact_id, ARTIFACT_SUFFIXES, MAX_ARTIFACT_BYTES)
        with self.connect() as db:
            cursor = db.execute("INSERT INTO artifact_designations(artifact_id,designation,evidence,created) VALUES(?,?,?,?)",
                                (artifact_id, designation, evidence, time.time()))
        return {"id": cursor.lastrowid, "artifact_id": artifact_id, "designation": designation}

    def artifact_delivery(self, artifact_id, status, evidence, observed_at):
        if status not in DELIVERY_STATUSES:
            raise ValueError("Invalid delivery observation")
        if not isinstance(evidence, str):
            raise ValueError("Evidence must be text")
        evidence, observed_at = text(evidence, 2000), timestamp(observed_at)
        if observed_at > time.time() + 300:
            raise ValueError("Delivery observation cannot be more than five minutes in the future")
        self.artifact_bytes(artifact_id, ARTIFACT_SUFFIXES, MAX_ARTIFACT_BYTES)
        with self.connect() as db:
            artifact = db.execute("SELECT sha256,created FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
            if observed_at < artifact["created"]:
                raise ValueError("Delivery observation predates this archived version")
            cursor = db.execute("INSERT INTO artifact_delivery(artifact_id,status,evidence,observed_at,recorded_at,sha256) VALUES(?,?,?,?,?,?)",
                                (artifact_id, status, evidence, observed_at, time.time(), artifact["sha256"]))
        return {"id": cursor.lastrowid, "artifact_id": artifact_id, "status": status, "record_only": True}

    def closeout_record(self, run_id, summary, scope, verification, evidence, limits, artifact_ids=(), no_artifact_reason=""):
        if verification not in VERIFICATION_STATUSES:
            raise ValueError("Invalid verification result")
        if not all(isinstance(value, str) for value in (summary, scope, evidence, limits, no_artifact_reason)):
            raise ValueError("Closeout summary, scope, evidence, limits and reason must be text")
        summary, scope, evidence, limits = (text(value, 4000) for value in (summary, scope, evidence, limits))
        artifact_ids = list(artifact_ids)
        if len(set(artifact_ids)) != len(artifact_ids):
            raise ValueError("Duplicate closeout artifact")
        if bool(artifact_ids) == bool(no_artifact_reason):
            raise ValueError("Provide artifacts or a justified no-artifact reason, exclusively")
        no_artifact_reason = text(no_artifact_reason, 2000) if no_artifact_reason else ""
        key, now = uuid.uuid4().hex, time.time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            run = db.execute("SELECT task_id,status FROM runs WHERE id=?", (run_id,)).fetchone()
            if not run or run["status"] not in OPEN_STATUSES:
                raise ValueError("Closeout records require an open run")
            files = []
            for artifact_id in artifact_ids:
                artifact = db.execute("SELECT task_id,sha256 FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
                if not artifact or artifact["task_id"] != run["task_id"]:
                    raise ValueError("Closeout artifact belongs to another task or is unknown")
                self.artifact_bytes(artifact_id, ARTIFACT_SUFFIXES, MAX_ARTIFACT_BYTES)
                files.append((key, artifact_id, artifact["sha256"]))
            db.execute("INSERT INTO closeout_records VALUES(?,?,?,?,?,?,?,?,?)",
                       (key, run_id, summary, scope, verification, evidence, limits, no_artifact_reason, now))
            db.executemany("INSERT INTO closeout_artifacts VALUES(?,?,?)", files)
            project = db.execute("SELECT project FROM tasks WHERE id=?", (run["task_id"],)).fetchone()["project"]
            db.execute("INSERT INTO activity(created,project,role,stage,message,task_id,state) VALUES(?,?,?,?,?,?,?)",
                       (now, project, "system", "closeout", "交付与验证已登记 / Closeout recorded: " + summary, run["task_id"], "in_progress"))
        return {"record_id": key, "run_id": run_id, "verification": verification, "completed": False}

    def closeout(self, run_id, record_id, from_status=None):
        """Evidence-bearing completion only; does not send, open or accept a file."""
        now = time.time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            run = db.execute("SELECT task_id,status FROM runs WHERE id=?", (run_id,)).fetchone()
            record = db.execute("SELECT * FROM closeout_records WHERE id=? AND run_id=?", (record_id, run_id)).fetchone()
            latest = db.execute("SELECT id FROM closeout_records WHERE run_id=? ORDER BY created DESC,id DESC LIMIT 1", (run_id,)).fetchone()
            if not run or run["status"] not in OPEN_STATUSES or not record:
                raise ValueError("Closeout requires an open run and its recorded evidence")
            if from_status is not None and run["status"] != from_status:
                raise ValueError("Lifecycle changed; refresh before recording a transition")
            if not latest or latest["id"] != record_id:
                raise ValueError("Closeout evidence was superseded; review the latest record")
            if record["verification"] == "failed":
                raise ValueError("Failed verification cannot close out as succeeded")
            files = db.execute("SELECT ca.artifact_id,ca.sha256,a.task_id FROM closeout_artifacts ca JOIN artifacts a ON a.id=ca.artifact_id WHERE ca.record_id=?", (record_id,)).fetchall()
            if not files and not record["no_artifact_reason"]:
                raise ValueError("Closeout requires artifacts or a no-artifact reason")
            for artifact in files:
                artifact_id = artifact["artifact_id"]
                if artifact["task_id"] != run["task_id"]:
                    raise ValueError("Closeout artifact task mismatch")
                data = self.artifact_bytes(artifact_id, ARTIFACT_SUFFIXES, MAX_ARTIFACT_BYTES)
                if hashlib.sha256(data).hexdigest() != artifact["sha256"]:
                    raise ValueError("Closeout output evidence is stale")
                designation = db.execute("SELECT designation FROM artifact_designations WHERE artifact_id=? ORDER BY created DESC,id DESC LIMIT 1", (artifact_id,)).fetchone()
                if not designation or designation["designation"] != "final":
                    raise ValueError("Closeout output must be explicitly designated final")
                delivery = db.execute("SELECT 1 FROM artifact_delivery WHERE artifact_id=? AND sha256=? AND status IN ('sent','accepted','user_open_confirmed')", (artifact_id, artifact["sha256"])).fetchone()
                if not delivery:
                    raise ValueError("Archived output has no recorded delivery evidence")
            db.execute("INSERT INTO closeout_completions VALUES(?,?,?)", (record_id, run_id, now))
            db.execute("UPDATE runs SET status='succeeded',updated=?,finished=?,lifecycle_reason=?,next_step='',lifecycle_evidence=? WHERE id=?",
                       (now, now, record["summary"], record["evidence"], run_id))
            project = db.execute("SELECT project FROM tasks WHERE id=?", (run["task_id"],)).fetchone()["project"]
            message = f"{run['status']} -> succeeded | Closeout: {record['summary']} | Verification: {record['verification']} | Limits: {record['limits']}"
            db.execute("INSERT INTO events(run_id,created,message) VALUES(?,?,?)", (run_id, now, message))
            db.execute("INSERT INTO activity(created,project,role,stage,message,task_id,state) VALUES(?,?,?,?,?,?,?)",
                       (now, project, "system", "state_changed", message, run["task_id"], "in_progress"))
        return {"run_id": run_id, "record_id": record_id, "status": "succeeded", "verification": record["verification"]}

    def rules_skill(self, url):
        url = verified_skill_url(url)
        with self.connect() as db:
            db.execute("INSERT INTO rules_config VALUES(1,?) ON CONFLICT(id) DO UPDATE SET skill_url=excluded.skill_url", (url,))
        return {"skill_url": url}

    def skill_upsert(self, key, name, purpose, when_used, observed_at, *, user_installed=False,
                     name_en="", purpose_en="", when_used_en="", url=None, status="unknown",
                     version_status="unverified", version_note="", version_note_en=""):
        """Explicit user-authored catalog only; no discovery or private instruction ingestion."""
        if user_installed is not True:
            raise ValueError("Confirm this is a user-installed, user-authored skill; internal/system skills are excluded")
        if not isinstance(key, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,99}", key):
            raise ValueError("Invalid skill ID")
        if status not in SKILL_STATUSES or version_status not in SKILL_VERSIONS:
            raise ValueError("Invalid manual skill observation")
        optional = lambda value, limit: text(value, limit) if value else ""
        values = dict(id=key, scope="user_installed", name=text(name, 120), name_en=optional(name_en, 120),
                      purpose=text(purpose, 500), purpose_en=optional(purpose_en, 500),
                      when_used=text(when_used, 500), when_used_en=optional(when_used_en, 500),
                      url=verified_skill_url(url) if url else None, status=status, version_status=version_status,
                      version_note=optional(version_note, 500), version_note_en=optional(version_note_en, 500),
                      observed_at=timestamp(observed_at))
        now = time.time()
        if values["observed_at"] > now + 300:
            raise ValueError("Skill observation cannot be more than five minutes in the future")
        if version_status == "saved_verified" and (status != "available" or not values["version_note"]):
            raise ValueError("Checking saved content requires a readable observation and a factual version note")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT * FROM user_skills WHERE id=?", (key,)).fetchone()
            if existing and values["observed_at"] <= existing["observed_at"]:
                if all(existing[k] == v for k, v in values.items()):
                    return {"id": key, "duplicate": True}
                raise ValueError("Skill updates require a newer observation; same-time conflicts are rejected")
            values["recorded_at"] = now
            columns = list(values)
            db.execute("INSERT INTO user_skills (" + ",".join(columns) + ") VALUES (" + ",".join("?" for _ in columns) + ") "
                       "ON CONFLICT(id) DO UPDATE SET " + ",".join(k + "=excluded." + k for k in columns if k != "id"), tuple(values.values()))
        return {"id": key, "duplicate": False}

    def snapshot(self, stale_seconds=120):
        now = time.time()
        with self.connect() as db:
            tasks = [dict(r) for r in db.execute("SELECT tasks.*, (SELECT status FROM runs WHERE task_id=tasks.id ORDER BY started DESC, id DESC LIMIT 1) AS latest_status FROM tasks ORDER BY created DESC LIMIT 500")]
            runs = [dict(r) for r in db.execute("SELECT * FROM runs ORDER BY started DESC,id DESC LIMIT 100")]
            # Keep the latest run for every visible task even outside the history window.
            latest_runs = [dict(r) for r in db.execute("SELECT runs.* FROM tasks JOIN runs ON runs.id=(SELECT r.id FROM runs r WHERE r.task_id=tasks.id ORDER BY r.started DESC,r.id DESC LIMIT 1) WHERE tasks.id IN (SELECT id FROM tasks ORDER BY created DESC LIMIT 500) ORDER BY tasks.created DESC,tasks.id")]
            events = [dict(r) for r in db.execute("SELECT * FROM events ORDER BY id DESC LIMIT 100")]
            activity = [dict(r) for r in db.execute("SELECT * FROM activity ORDER BY created DESC, id DESC LIMIT 100")]
            bindings = [dict(r) for r in db.execute("SELECT * FROM task_bindings ORDER BY synced_at DESC LIMIT 500")]
            schedules = [dict(r) for r in db.execute("SELECT * FROM schedules ORDER BY created DESC LIMIT 500")]
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            rules_row = db.execute("SELECT skill_url FROM rules_config WHERE id=1").fetchone() if "rules_config" in tables else None
            rules = project_rules()
            rules["skill_url"] = rules_row["skill_url"] if rules_row else None
            rules["skills"] = [dict(r) for r in db.execute("SELECT * FROM user_skills WHERE scope='user_installed' ORDER BY id")] if "user_skills" in tables else []
            origins = {r["skill_id"]: dict(r) for r in db.execute("SELECT * FROM skill_origins")} if "skill_origins" in tables else {}
            for item in rules["skills"]:
                item["source"] = origins.get(item["id"], {"origin": "unknown", "publication": "unknown"})
            release_row = db.execute("SELECT * FROM release_observation WHERE id=1").fetchone() if "release_observation" in tables else None
            release = dict(release_row) if release_row else {"repo_url": None, "release_status": "unknown", "release_tag": None, "remote_commit": None, "sync_status": "unknown", "checked_at": None}
            artifacts = [dict(r) for r in db.execute("SELECT * FROM artifacts ORDER BY created DESC,id DESC")] if "artifacts" in tables else []
            designations = [dict(r) for r in db.execute("SELECT * FROM artifact_designations ORDER BY created DESC,id DESC")] if "artifact_designations" in tables else []
            deliveries = [dict(r) for r in db.execute("SELECT * FROM artifact_delivery ORDER BY observed_at DESC,id DESC")] if "artifact_delivery" in tables else []
            closeouts = [dict(r) for r in db.execute("SELECT * FROM closeout_records ORDER BY created DESC,id DESC")] if "closeout_records" in tables else []
            closeout_files = [dict(r) for r in db.execute("SELECT * FROM closeout_artifacts")] if "closeout_artifacts" in tables else []
            completions = {r["record_id"]: r["created"] for r in db.execute("SELECT * FROM closeout_completions")} if "closeout_completions" in tables else {}
            for artifact in artifacts:
                artifact["designation"] = next((row["designation"] for row in designations if row["artifact_id"] == artifact["id"]), "unclassified")
                artifact["delivery_observations"] = [row for row in deliveries if row["artifact_id"] == artifact["id"]]
            for record in closeouts:
                record["artifacts"] = [row for row in closeout_files if row["record_id"] == record["id"]]
                record["completed_at"] = completions.get(record["id"])
            agents = [dict(r) for r in db.execute("SELECT * FROM agents ORDER BY created ASC,id ASC")]
            agent_assignments = [dict(r) for r in db.execute("SELECT * FROM agent_assignments ORDER BY assigned_at ASC,task_id ASC")]
            software = [dict(r) for r in db.execute("SELECT * FROM software ORDER BY created ASC LIMIT 100")]
        for item in software:
            kind = item["kind"]
            executable = sys.executable if kind == "python" else shutil.which("git") if kind == "git" else None
            item["available"] = (ROOT / "src/dots_panel/app.py").is_file() if kind == "dots-panel" else bool(executable and os.access(executable, os.X_OK))
            item["verified_at"] = now
            item["version"] = platform.python_version() if kind == "python" else VERSION if kind == "dots-panel" else None
            item["controls"] = ["close_current_viewer"] if kind == "dots-panel" else []
            item["running"] = None  # Availability is not evidence that a program is running.

        task_modes = {task["id"]: task.get("tracking_mode", "manual") for task in tasks}
        for run in runs + latest_runs:
            run.setdefault("closeout_required", 0)
            run["closeout"] = next((record for record in closeouts if record["run_id"] == run["id"]), None)
            for field in ("lifecycle_reason", "next_step", "lifecycle_evidence"):
                run.setdefault(field, "")
            run["tracking_mode"] = task_modes.get(run["task_id"], "manual")
            latest_summary = max((item["created"] for item in activity if item.get("task_id") == run["task_id"] and item.get("stage") not in ("assignment", "work_type")), default=run["updated"])
            run["progress_updated"] = max(run["updated"], latest_summary) if run["tracking_mode"] == "manual" else run["updated"]
            run["stale"] = run["status"] in OPEN_STATUSES and now - run["progress_updated"] > stale_seconds
        return {"recovery": recovery_notice(self.directory), "rules": rules, "about": {"installed_version": VERSION, "install_notes": INSTALL_NOTES, "release": release, "doctor": install_doctor(ROOT, self.directory)}, "artifacts": artifacts, "agents": agents, "agent_assignments": agent_assignments, "tasks": tasks, "runs": runs, "latest_runs": latest_runs, "closeouts": closeouts, "events": events, "activity": activity, "schedules": schedules, "software": software, "bindings": bindings, "stale_after_seconds": stale_seconds}



def read(path):
    try:
        return Path(path).read_text().strip()
    except (OSError, UnicodeError):
        return None


class Metrics:
    def __init__(self, disk_path):
        self.disk_path = disk_path
        self.previous = None
        self.lock = threading.Lock()

    def collect(self):
        now = time.time()
        cpu = None
        raw = read("/proc/stat")
        if raw and raw.startswith("cpu "):
            values = [int(n) for n in raw.splitlines()[0].split()[1:9]]
            sample = (sum(values), values[3] + (values[4] if len(values) > 4 else 0))
            with self.lock:
                if self.previous and sample[0] > self.previous[0]:
                    cpu = round(100 * (1 - (sample[1] - self.previous[1]) / (sample[0] - self.previous[0])), 1)
                self.previous = sample
        memory = {}
        for line in (read("/proc/meminfo") or "").splitlines():
            fields = line.split()
            if fields[0] in ("MemTotal:", "MemAvailable:"):
                memory[fields[0][:-1]] = int(fields[1]) * 1024
        disk = shutil.disk_usage(self.disk_path)
        quota = read("/sys/fs/cgroup/cpu.max")
        cpu_limit = None
        if quota:
            parts = quota.split()
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit() and int(parts[1]):
                cpu_limit = round(int(parts[0]) / int(parts[1]), 2)
        mem_limit_raw = read("/sys/fs/cgroup/memory.max")
        mem_current = read("/sys/fs/cgroup/memory.current")
        return {
            "sampled_at": now,
            "scope": "当前执行环境可见值；可能是容器宿主机视图，不代表可用配额",
            "os": platform.system(), "architecture": platform.machine(),
            "python": platform.python_version(), "visible_cpu_count": os.cpu_count(),
            "cpu_percent": cpu, "cpu_quota_cores": cpu_limit,
            "memory_total": memory.get("MemTotal"),
            "memory_available": memory.get("MemAvailable"),
            "memory_quota": int(mem_limit_raw) if mem_limit_raw and mem_limit_raw.isdigit() else None,
            "cgroup_memory_current": int(mem_current) if mem_current and mem_current.isdigit() else None,
            "disk_total": disk.total, "disk_used": disk.used, "disk_free": disk.free,
        }


def make_server(store, port=8765):
    metrics = Metrics(store.directory)
    metrics.collect()
    assets = {"/": ("index.html", "text/html; charset=utf-8"), "/style.css": ("style.css", "text/css; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/i18n.js": ("i18n.js", "text/javascript; charset=utf-8"), "/workspace.js": ("workspace.js", "text/javascript; charset=utf-8")}

    class Handler(BaseHTTPRequestHandler):
        server_version = "dots-panel"

        def log_message(self, *_):
            pass

        def send_body(self, code, body, mime="application/json; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; connect-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            expected = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            if self.headers.get("Host") not in expected or self.headers.get("Sec-Fetch-Site") == "cross-site":
                self.send_body(403, b'{"error":"Local access only"}')
                return
            path = urlsplit(self.path).path
            try:
                if path == "/api/state":
                    body = {"server_time": time.time(), "metrics": metrics.collect(), **store.snapshot()}
                    self.send_body(200, json.dumps(body, ensure_ascii=False).encode())
                elif path == "/health":
                    self.send_body(200, b'{"status":"ok"}')
                elif path in assets:
                    filename, mime = assets[path]
                    self.send_body(200, (ROOT / "web" / filename).read_bytes(), mime)
                else:
                    self.send_body(404, b'{"error":"Not found"}')
            except (OSError, sqlite3.Error):
                self.send_body(503, b'{"error":"Local data temporarily unavailable"}')

        def do_POST(self):
            self.send_body(405, b'{"error":"Read-only HTTP. Use the local CLI."}')

        do_PUT = do_DELETE = do_PATCH = do_POST

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description="Private-by-default, local-only task panel")
    parser.add_argument("--data-dir", type=Path, default=default_data_dir())
    subs = parser.add_subparsers(dest="command", required=True)
    serve = subs.add_parser("serve")
    serve.add_argument("--port", type=int, default=8765)
    register = subs.add_parser("register")
    register.add_argument("id")
    register.add_argument("--name", required=True)
    register.add_argument("--project", required=True)
    register.add_argument("--tracking-mode", choices=("manual", "heartbeat"), default="manual")
    start = subs.add_parser("start")
    start.add_argument("task_id")
    start.add_argument("--note", default="")
    for command in ("heartbeat", "log", "finish"):
        sub = subs.add_parser(command)
        sub.add_argument("run_id")
        if command == "log":
            sub.add_argument("message")
        if command == "finish":
            sub.add_argument("--status", choices=STATUSES, required=True)
    activity = subs.add_parser("activity")
    activity.add_argument("--project", required=True)
    activity.add_argument("--role", choices=("user", "assistant", "system"), required=True)
    activity.add_argument("--stage", required=True)
    activity.add_argument("message")
    activity.add_argument("--task-id")
    activity.add_argument("--state", choices=("planned", "in_progress", "verified"), default="in_progress")
    bind = subs.add_parser("bind", help="Bind an existing activity to an actually created session; metadata only")
    bind.add_argument("task_id")
    bind.add_argument("--source-type", choices=BINDING_SOURCES, required=True)
    bind.add_argument("--thread-id", required=True)
    bind.add_argument("--environment-kind", choices=ENVIRONMENT_KINDS, required=True)
    bind.add_argument("--environment-id")
    bind.add_argument("--observed-status", choices=OBSERVED_STATUSES, required=True)
    bind.add_argument("--observed-at", required=True)
    bind.add_argument("--url", help="Only an actual returned shareable HTTPS URL; never guess one")
    ingest = subs.add_parser("ingest", help="Mirror a user-visible summary once by its actual source event ID")
    ingest.add_argument("task_id")
    ingest.add_argument("message")
    ingest.add_argument("--source-event-id", required=True)
    ingest.add_argument("--role", choices=("user", "assistant", "system"), required=True)
    ingest.add_argument("--stage", required=True)
    ingest.add_argument("--state", choices=("planned", "in_progress", "verified"), required=True)
    ingest.add_argument("--observed-at", required=True)
    ingest.add_argument("--observed-status", choices=OBSERVED_STATUSES)
    schedule = subs.add_parser("schedule-register", help="Record metadata only; never creates or starts a scheduler")
    schedule.add_argument("id")
    schedule.add_argument("--name", required=True)
    schedule.add_argument("--project", required=True)
    schedule.add_argument("--source", default="manual")
    schedule.add_argument("--state", choices=("disconnected", "planned", "paused"), default="disconnected")
    schedule.add_argument("--next-run", help="Informational ISO timestamp with timezone; does not schedule execution")
    software = subs.add_parser("software-register", help="Register software for safe read-only availability detection")
    software.add_argument("id")
    software.add_argument("--name", required=True)
    software.add_argument("--description", required=True)
    software.add_argument("--kind", choices=("dots-panel", "python", "git"), required=True)
    rule_cmd = subs.add_parser("rules-skill", help="Configure the verified project skill link; does not edit permissions")
    rule_cmd.add_argument("--url", required=True)
    skill_cmd = subs.add_parser("skill-upsert", help="Register/update a private user-installed skill summary; no installation or auto-sync")
    skill_cmd.add_argument("id")
    skill_cmd.add_argument("--user-installed", action="store_true", required=True, help="Attest this is user-installed/user-authored, never internal or system")
    for field in ("name", "purpose", "when-used", "observed-at"):
        skill_cmd.add_argument("--" + field, required=True)
    for field in ("name-en", "purpose-en", "when-used-en", "version-note", "version-note-en"):
        skill_cmd.add_argument("--" + field, default="")
    skill_cmd.add_argument("--url")
    skill_cmd.add_argument("--status", choices=SKILL_STATUSES, default="unknown")
    skill_cmd.add_argument("--version-status", choices=SKILL_VERSIONS, default="unverified")
    transition = subs.add_parser("transition", help="Record lifecycle only; does not pause, resume or cancel an executor")
    transition.add_argument("run_id")
    transition.add_argument("--status", choices=LIFECYCLE_STATUSES, required=True)
    transition.add_argument("--reason", required=True)
    transition.add_argument("--evidence", required=True)
    transition.add_argument("--next-step", default="", help="Required for nonterminal states")
    transition.add_argument("--from-status", choices=LIFECYCLE_STATUSES, help="Reject if the recorded state changed")
    designate = subs.add_parser("artifact-designate", help="Record draft/final designation only")
    designate.add_argument("artifact_id")
    designate.add_argument("--designation", choices=ARTIFACT_DESIGNATIONS, required=True)
    designate.add_argument("--evidence", required=True)
    delivery = subs.add_parser("artifact-delivery", help="Record observed delivery; does not send or open a file")
    delivery.add_argument("artifact_id")
    delivery.add_argument("--status", choices=DELIVERY_STATUSES, required=True)
    delivery.add_argument("--evidence", required=True)
    delivery.add_argument("--observed-at", type=timestamp, required=True)
    close_record = subs.add_parser("closeout-record", help="Append delivery/verification evidence; does not finish the run")
    close_record.add_argument("run_id")
    for field in ("summary", "scope", "evidence", "limits"):
        close_record.add_argument("--"+field, required=True)
    close_record.add_argument("--verification", choices=VERIFICATION_STATUSES, required=True)
    close_record.add_argument("--artifact", action="append", default=[])
    close_record.add_argument("--no-artifact-reason", default="")
    close = subs.add_parser("closeout", help="Complete an open run after checking its latest evidence and delivery records")
    close.add_argument("run_id")
    close.add_argument("--record", required=True)
    subs.add_parser("doctor", help="Read-only installation checks; never initializes, installs, repairs or schedules")
    observation = subs.add_parser("installation-observe", help="Append explicit manual account/scheduler evidence; does not connect or configure it")
    observation.add_argument("--component", choices=COMPONENTS, required=True)
    observation.add_argument("--status", choices=OBSERVATION_STATES, required=True)
    observation.add_argument("--evidence", required=True)
    observation.add_argument("--observed-at", type=timestamp, required=True)
    observation.add_argument("--skill-id")
    observation.add_argument("--reference", default="")
    task_init = subs.add_parser("task-init")
    task_init.add_argument("task_id")
    artifact = subs.add_parser("artifact-add", help="Copy a finished output into the task archive and register verified metadata")
    artifact.add_argument("task_id")
    artifact.add_argument("source", type=Path)
    artifact.add_argument("--title", required=True)
    artifact.add_argument("--kind", choices=ARTIFACT_KINDS, default="report")
    artifact.add_argument("--slug", default="artifact")
    artifact.add_argument("--library-id")
    origin_cmd = subs.add_parser("skill-origin")
    origin_cmd.add_argument("id")
    origin_cmd.add_argument("--origin", choices=SKILL_ORIGINS, required=True)
    origin_cmd.add_argument("--publication", choices=SKILL_PUBLICATIONS, required=True)
    origin_cmd.add_argument("--observed-at", type=timestamp, required=True)
    origin_cmd.add_argument("--repo-url")
    origin_cmd.add_argument("--commit-sha")
    agent = subs.add_parser("agent-register", help="Record an agent profile; does not create an executor")
    agent.add_argument("id"); agent.add_argument("--name", required=True)
    agent.add_argument("--name-en", default=""); agent.add_argument("--avatar", choices=AGENT_AVATARS, default="mint")
    profile = subs.add_parser("agent-profile")
    profile.add_argument("id"); profile.add_argument("--name"); profile.add_argument("--name-en"); profile.add_argument("--avatar", choices=AGENT_AVATARS)
    observe = subs.add_parser("agent-observe")
    observe.add_argument("id"); observe.add_argument("--status", choices=AGENT_STATUSES, required=True)
    observe.add_argument("--observed-at", required=True); observe.add_argument("--note", default=""); observe.add_argument("--note-en", default="")
    assign = subs.add_parser("agent-assign")
    assign.add_argument("task_id"); assign.add_argument("agent_id")
    assign.add_argument("--replace", action="store_true"); assign.add_argument("--work-type", choices=tuple(WORK_TYPES), default="unspecified")
    release = subs.add_parser("release-observe", help="Record manual evidence only; no network or publication")
    release.add_argument("--repo-url", required=True); release.add_argument("--release-status", choices=RELEASE_STATUSES, required=True)
    release.add_argument("--sync-status", choices=SYNC_STATUSES, required=True); release.add_argument("--checked-at", required=True)
    release.add_argument("--release-tag"); release.add_argument("--remote-commit")
    subs.add_parser("status")
    args = parser.parse_args()
    try:
        if args.command == "doctor":
            print(json.dumps(install_doctor(ROOT, args.data_dir), ensure_ascii=False, indent=2))
            return
        store = Store(args.data_dir)
        if args.command == "serve":
            server = make_server(store, args.port)
            print(f"dots-panel: http://127.0.0.1:{server.server_port} (loopback only)", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
        elif args.command == "register":
            print(store.register(args.id, args.name, args.project, args.tracking_mode))
        elif args.command == "start":
            print(store.start(args.task_id, args.note))
        elif args.command == "activity":
            store.activity(args.project, args.role, args.stage, args.message, args.task_id, args.state)
        elif args.command == "bind":
            print(store.bind(args.task_id, args.source_type, args.thread_id, args.environment_kind, args.environment_id, args.observed_status, args.observed_at, args.url))
        elif args.command == "ingest":
            print(json.dumps(store.ingest(args.task_id, args.source_event_id, args.role, args.stage, args.state, args.message, args.observed_at, args.observed_status)))
        elif args.command == "schedule-register":
            next_run = None
            if args.next_run:
                parsed = datetime.fromisoformat(args.next_run.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    raise ValueError("--next-run requires an explicit timezone")
                next_run = parsed.timestamp()
            print(store.schedule_register(args.id, args.name, args.project, args.source, args.state, next_run))
        elif args.command == "software-register":
            print(store.software_register(args.id, args.name, args.description, args.kind))
        elif args.command == "rules-skill":
            print(json.dumps(store.rules_skill(args.url)))
        elif args.command == "skill-upsert":
            print(json.dumps(store.skill_upsert(args.id, args.name, args.purpose, args.when_used, args.observed_at,
                user_installed=args.user_installed, name_en=args.name_en, purpose_en=args.purpose_en,
                when_used_en=args.when_used_en, url=args.url, status=args.status,
                version_status=args.version_status, version_note=args.version_note, version_note_en=args.version_note_en)))
        elif args.command == "task-init":
            print(json.dumps(store.task_init(args.task_id)))
        elif args.command == "artifact-add":
            print(json.dumps(store.artifact_add(args.task_id, args.source, args.title, args.kind, args.slug, args.library_id)))
        elif args.command == "skill-origin":
            print(json.dumps(store.skill_origin(args.id, args.origin, args.publication, args.observed_at, args.repo_url, args.commit_sha)))
        elif args.command == "transition":
            print(json.dumps(store.transition(args.run_id, args.status, args.reason, args.evidence, args.next_step, args.from_status), ensure_ascii=False))
        elif args.command == "artifact-designate":
            print(json.dumps(store.artifact_designate(args.artifact_id, args.designation, args.evidence)))
        elif args.command == "artifact-delivery":
            print(json.dumps(store.artifact_delivery(args.artifact_id, args.status, args.evidence, args.observed_at)))
        elif args.command == "closeout-record":
            print(json.dumps(store.closeout_record(args.run_id, args.summary, args.scope, args.verification, args.evidence, args.limits, args.artifact, args.no_artifact_reason)))
        elif args.command == "closeout":
            print(json.dumps(store.closeout(args.run_id, args.record)))
        elif args.command == "installation-observe":
            print(json.dumps(store.installation_observe(args.component, args.status, args.evidence, args.observed_at, args.skill_id, args.reference)))
        elif args.command == "agent-register":
            print(store.agent_register(args.id,args.name,args.avatar,args.name_en))
        elif args.command == "agent-profile":
            print(store.agent_profile(args.id,args.name,args.avatar,args.name_en))
        elif args.command == "agent-observe":
            print(store.agent_observe(args.id,args.status,args.observed_at,args.note,args.note_en))
        elif args.command == "agent-assign":
            print(json.dumps(store.agent_assign(args.task_id,args.agent_id,args.replace,args.work_type)))
        elif args.command == "release-observe":
            print(json.dumps(store.release_observe(args.repo_url,args.release_status,args.sync_status,args.checked_at,args.release_tag,args.remote_commit)))
        elif args.command == "status":
            print(json.dumps(store.snapshot(), ensure_ascii=False, indent=2))
        else:
            store.update(args.run_id, getattr(args, "status", None), getattr(args, "message", None))
    except (ValueError, sqlite3.Error, OSError) as exc:
        parser.exit(1, f"Error: {exc}\n")
