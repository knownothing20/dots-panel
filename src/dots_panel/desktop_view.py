"""Native read-only panel: retained source plus documented recovery integration.

See docs/restoration.md for restoration provenance and boundaries.
Task database access is read-only; only UI language preferences are written.
"""
import argparse
from .outputs import TaskFolderOpener, task_output_summary, output_summary_text, output_main_text
import base64
from .doctor import doctor_rows
from .notifications import NotificationState
from .native_notifications import NativeNotifications
from .native_window import NativeWindow
from .progress import task_progress, current_run, task_meaningful_updated, agent_observation
from .agent_identity import draw_portrait, identity_label, source_label
from .participants import activity_participants, profile_reference
from .app import artifact_delivery_label, verification_label, attention_items, attention_draft, artifact_kind_label, VERSION, verified_repository_url, verified_link, skill_origin_label, skill_publication_label
from contextlib import contextmanager
import json
import hashlib
import os
from pathlib import Path
import sqlite3
import stat
import uuid
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    LOADED_SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
except OSError:
    LOADED_SOURCE_SHA256 = 'unavailable'

DEFAULT_TIMEZONE = "Asia/Shanghai"
COMMON_TIMEZONES = ("Asia/Shanghai", "UTC", "America/Los_Angeles", "America/New_York", "Europe/London", "Europe/Paris", "Asia/Tokyo", "Asia/Singapore", "Australia/Sydney")

def validate_timezone(value):
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ValueError("Invalid IANA timezone")
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("Unsupported IANA timezone: " + value) from exc
    return value

from .motion import Motion
from .exit_region import label as exit_region_label
from .backup_status import presentation as backup_presentation

from .app import (Metrics, Store, ROOT, default_data_dir, agent_text, agent_work, work_type_label,
                  verified_skill_url, skill_status_label, skill_version_label)

STATUS = {"waiting_user": "等待用户", "waiting_external": "等待外部结果", "paused": "已暂停记录", "awaiting_review": "等待验收", "running": "进行中", "succeeded": "已完成", "failed": "失败", "cancelled": "已取消", "pending": "待开始"}
STATES = {"unknown": "历史状态未保留","planned": "计划", "in_progress": "进行中", "verified": "已验证"}
PAGE_NAMES = {"overview": "概览", "conversations": "任务", "schedules": "自动化", "software": "软件", "rules": "规则", "about": "关于与版本", "settings": "设置"}
EN = {"设置": "Settings", "语言": "Language", "显示时区": "Display timezone", "应用时区": "Apply timezone", "默认北京时间；支持 IANA 时区。仅调整显示，不改变系统时间或任务调度。": "Beijing time by default; supports IANA timezones. Display only; system time and automation timing stay unchanged.", "设置保存在本机": "Settings are saved locally", "无效或不支持的 IANA 时区": "Invalid or unsupported IANA timezone", "未保存偏好；当前仅本次有效": "Preferences not saved; applied for this session only","已登记任务与工作记录；执行会话绑定情况见详情": "Registered tasks and work records; see details for execution-session bindings","关于与版本": "About & version", "↻ 刷新": "↻ Refresh", "每 5 秒 · 最近刷新": "Every 5s · Last refreshed", "尚未刷新": "Not refreshed yet","历史状态未保留": "Historical state unavailable", "recovered_summary": "Recovered summary","等待用户": "Waiting for user", "等待外部结果": "Waiting for external result", "已暂停记录": "Recorded as paused", "等待验收": "Awaiting review",

    "进行中 / 已完成 · {count} 个任务": "Running / done · {count} tasks",
    "容器配额 {quota}": "Container quota: {quota}",
    "工作进展": "Work progress", "最新进展": "Overview", "全部记录": "All records",
    "语言仅本次生效；无法保存偏好": "Language applies this session; preference could not be saved",
    "Dots Panel · 任务与资源看板": "Dots Panel · Tasks & Resources",
    "  /  本地任务观测台": "  /  Local task dashboard", "正在读取本地数据": "Reading local data",
    "任务数据只读  ·  每 5 秒刷新  ·  仅语言偏好保存在本机": "Task data is read-only · Refreshes every 5s · Only language preference is saved locally",
    "CPU 使用率": "CPU usage", "内存": "Memory", "磁盘": "Disk", "任务状态": "Task status",
    "等待采样": "Waiting for sample", "采样中": "Sampling", "任务流水线": "Task pipeline",
    "任务": "Task", "项目": "Project", "状态": "Status", "最新阶段": "Latest stage",
    "运行时长": "Elapsed", "最后心跳": "Last heartbeat", "最新工作摘要与事件": "Latest work summaries & events",
    "进行中": "Running", "已完成": "Succeeded", "失败": "Failed", "已取消": "Cancelled",
    "无近期运行": "No recent run", "计划": "Planned", "已验证": "Verified", "记录": "Recorded",
    " · 心跳过期": " · Stale", "不可用": "Unavailable", "未知": "unknown",
    "可见 {cores} 核 · 配额 {quota} 核": "{cores} visible cores · {quota} quota cores",
    "容器用量 / 容器配额": "Container usage / quota", "可见可用量 · 总量 {total}": "Visible available · {total} total",
    "可用空间 · 总量 {total}": "Free space · {total} total", "{running} 进行中 / {done} 完成": "{running} running / {done} done",
    "已登记 {count} 个任务 · 按最近运行统计": "{count} registered tasks · Latest run per task",
    "机器指标：": "Metrics: ", "当前执行环境可见值；可能是容器宿主机视图，不代表可用配额": "Visible environment metrics; host values may differ from container quotas",
    "当前执行环境可见值": "Values visible to this environment",
    "任务流水线     计划 {planned}  →  进行中 {active}  →  已验证 {verified} 个阶段": "Pipeline     {planned} planned  →  {active} in progress  →  {verified} verified stages",
    "● 本地数据 · ": "● Local data · ", "● 读取失败 · 保留上次结果，5 秒后重试": "● Read failed · Showing last result; retrying in 5s",
    "运行事件": "Run event", "当前任务：": "Selected task: ", "启动说明：": "Start note: ",
    "尚无显式记录的工作摘要。请通过本地 CLI 登记任务、运行事件和阶段进度；此视图不会读取会话或自动发现任务。": "No explicitly recorded summaries yet. Register tasks, events and stage progress using the local CLI. This view does not read sessions or discover tasks automatically.",
    "说明": "Description", "最后更新": "Last update", "最后更新：": "Last update: ",
    "进度更新较久，执行状态待确认": "Progress update is old; execution unconfirmed", "更新较久，待确认": "Old update; unconfirmed",
    "概览": "Overview", "任务": "Tasks", "自动化": "Automations", "软件": "Software",
    "你的本地工作空间": "Your local workspace", "资源、工作与计划，一目了然": "Resources, work and plans at a glance",
    "已登记任务与工作记录；尚未绑定独立执行会话": "Registered tasks and work records; no separate execution session is linked",
    "只展示已登记计划；此面板不会执行自动化": "Registered plans only; this panel does not execute automations",
    "本地软件登记与检测；不会运行任意命令": "Local software registry and checks; no arbitrary commands",
    "本地优先": "Local first", "工作中": "Active work", "查看任务 →": "View tasks →",
    "查看计划 →": "View automations →", "没有进行中的已登记任务": "No registered task is currently running",
    "尚未登记任务": "No tasks registered yet", "尚未登记自动化": "No automations registered yet",
    "尚未登记其他软件": "No other software registered yet", "未接入": "Disconnected", "已暂停": "Paused",
    "下次运行未知": "Next run unknown", "计划时间": "Planned time", "来源": "Source", "计划数量": "Registered plans",
    "未接入调度器": "No scheduler connected", "此页仅显示元数据，不代表任务已安排或会运行": "Metadata only; a listed plan is not confirmation of scheduling or execution",
    "全部任务": "All tasks", "打开所选任务": "Open selected task",
    "双击任务或按 Enter 打开记录；Esc 返回列表": "Double-click a task or press Enter to open; Esc returns to the list",
    "← 返回列表": "← Back to list", "工作时间线": "Work timeline", "暂无工作记录": "No work records yet",
    "任务进展记录；尚未绑定独立执行会话": "Task progress records; no separate execution session is linked",
    "此窗口正在运行": "This viewer is running", "本地任务与资源看板": "Local task and resource dashboard",
    "关闭此窗口": "Close this viewer", "确认关闭此窗口？": "Close this viewer?",
    "只关闭当前看板窗口，不会停止任务、自动化或其他服务。可从桌面启动器重新打开。": "Only this viewer will close. Tasks, automations and other services will keep their current state. Reopen it from the desktop launcher.",
    "可用": "Available", "未检测到": "Not detected", "未验证": "Not verified", "最近检测": "Last checked", "版本": "Version",
    "此处未提供进程控制": "Process controls are not available here", "数据来自显式登记；不读取内部会话": "Explicitly registered data only; internal sessions are not read",
    "可见指标可能来自宿主机；配额以容器值为准": "Visible metrics may reflect the host; use container quota values",
    "近期运行：{running} 进行中 · {done} 完成": "Latest runs: {running} active · {done} done",
    "已登记 {count} 个计划": "{count} registered plans", "刷新失败，保留上次数据": "Refresh failed; retaining the last data",
    "每 5 秒刷新": "Refreshes every 5s", "最近 100 条工作记录": "Up to 100 recent work records", "本机时间": "Local time", "未保存语言偏好": "Language preference was not saved",
    "心跳跟踪": "Heartbeat tracking", "手动记录": "Manual record", "已登记的软件": "Registered software", "资源使用情况": "Resource usage",
    "可见指标；内存优先使用容器配额": "Visible metrics; memory uses quota when available", "工作区": "Workspace", "全部": "All", "待开始": "Pending", "心跳过期": "Heartbeat stale",
    "该状态暂无任务": "No tasks with this status", "另有 {count} 个任务，可在任务页查看": "{count} more tasks in Tasks",
}

EN.update({"任务":"Tasks","自动化":"Automations","等待用户": "Waiting for user", "等待外部": "Waiting externally", "待验收": "Awaiting review", "规则": "Rules", "关于": "About"})


def bounded_card_lines(text, width, measure, limit=2):
    """Pixel-bounded, deterministic excerpts; full content stays in task detail."""
    remaining = ' '.join(str(text or '').split())
    lines = []
    width = max(1, width)
    for index in range(limit):
        if not remaining:
            break
        if measure(remaining) <= width:
            lines.append(remaining)
            break
        suffix = '…' if index == limit-1 else ''
        low, high = 0, len(remaining)
        while low < high:
            middle = (low+high+1)//2
            if measure(remaining[:middle]+suffix) <= width:
                low = middle
            else:
                high = middle-1
        cut = max(1, low)
        if not suffix:
            word = remaining.rfind(' ', 0, cut+1)
            if word >= cut//2:
                cut = word
        lines.append(remaining[:cut].rstrip()+suffix)
        remaining = remaining[cut:].lstrip()
    return '\n'.join(lines)


def compact_task_excerpt(text):
    """Keep technical evidence out of overview/list excerpts, not out of storage."""
    import re
    text = re.split(r'(?i)\s*(?:\|\s*)?(?:Evidence|Next|验证依据|状态依据|下一步)\s*[:：]', str(text or ''), maxsplit=1)[0]
    text = re.sub(r'\b(?:libfile_[a-zA-Z0-9_]+|[0-9a-f]{16,64})\b', '', text)
    return ' '.join(text.split())


def image_preview_geometry(width, height, screen_width, screen_height):
    """Bound an image preview to the current screen using lossless Tk subsampling."""
    import math
    if min(width,height,screen_width,screen_height) <= 0:
        raise ValueError("Image and screen dimensions must be positive")
    window_width = min(1100, max(1, screen_width-80))
    window_height = min(850, max(1, screen_height-100))
    available_width, available_height = max(1,window_width-35),max(1,window_height-100)
    factor = max(1, math.ceil(width/available_width), math.ceil(height/available_height))
    return window_width, window_height, factor


def popup_position(x, y, anchor_width, anchor_height, width, height, screen_width, screen_height):
    """Reconstructed bounded placement for the retained popover fragment."""
    left = max(0, min(x+anchor_width-width, screen_width-width))
    top = y+anchor_height+5
    if top+height > screen_height:
        top = max(0, y-height-5)
    return left, max(0, min(top, screen_height-height))


def agent_status_label(value, language="zh"):
    labels = {"running": ("已观察运行", "Observed running"), "idle": ("空闲", "Idle"), "blocked": ("受阻", "Blocked"), "unavailable": ("不可用", "Unavailable"), "unknown": ("状态未知", "Status unknown")}
    return labels.get(value, labels["unknown"])[language == "en"]


def participant_caption(progress, language='zh'):
    if progress['assigned_participants']:
        return 'Assigned participant: ' if language == 'en' else '已分派参与者：'
    return 'Owner: ' if language == 'en' else '负责人：'


def participant_observation(agent, snapshot, language='zh', now=None, timezone=DEFAULT_TIMEZONE):
    observation = agent_observation(agent, snapshot, now)
    label = agent_status_label(observation['status'], language)
    if observation['known'] and not observation['recent']:
        label += ' · Older; current state unconfirmed' if language == 'en' else ' · 较早，当前待核对'
    if observation['known']:
        label += ' · ' + observation_label(agent['observed_at'], language, timezone)
    return label


def run_participant_names(snapshot, run_id, language='zh'):
    links = {a['agent_id']:a for a in snapshot.get('agent_run_assignments', []) if a['run_id'] == run_id}
    return ', '.join(profile_reference(a,language)+' · '+work_type_label(links[a['id']].get('work_type'),language) for a in snapshot.get('agents', []) if a['id'] in links)


def observation_label(value, language="zh", timezone=DEFAULT_TIMEZONE):
    if not isinstance(value, (int, float)):
        return "观察时间未知" if language != "en" else "Observation time unknown"
    return ("最后观察：" if language != "en" else "Last observed: ")+timestamp_label(value, timezone)


def resolve_language(choice="auto", environ=None):
    if choice in ("zh", "en"):
        return choice
    environ = os.environ if environ is None else environ
    locale_name = next((environ.get(key) for key in ("LC_ALL", "LC_MESSAGES", "LANG") if environ.get(key)), "en")
    return "zh" if locale_name.lower().startswith("zh") else "en"


def translate(value, language="zh", **variables):
    return (EN.get(value, value) if language == "en" else value).format(**variables) if variables else (EN.get(value, value) if language == "en" else value)


def load_preferences(directory):
    config = Path(directory) / "config"
    try:
        if config.is_symlink():
            return {}
        parent = os.open(config, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fd = os.open("ui.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            with os.fdopen(fd, "r", encoding="utf-8") as handle:
                if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                    return {}
                content = json.loads(handle.read(4097))
                return content if isinstance(content, dict) else {}
        finally:
            os.close(parent)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError, UnicodeError):
        return {"_read_error": True}


def load_language(directory):
    value = load_preferences(directory).get("language")
    return value if value in ("auto", "zh", "en") else "auto"

def save_language(directory, language):
    save_preferences(directory, language=language)

def save_preferences(directory, language=None, timezone=None, reduced_motion=None):
    content = load_preferences(directory)
    if content.pop("_read_error", False):
        raise ValueError("Cannot safely read existing preferences")
    if reduced_motion is not None:
        if not isinstance(reduced_motion, bool):
            raise ValueError("Invalid reduced-motion preference")
        content["reduced_motion"] = reduced_motion
    language = language if language is not None else content.get("language", "auto")
    if timezone is not None:
        content["timezone"] = validate_timezone(timezone)
    if language not in ("auto", "zh", "en"):
        raise ValueError("Invalid UI language")
    directory = Path(directory).expanduser().resolve()
    if directory == ROOT or ROOT in directory.parents:
        raise ValueError("UI preferences must remain outside the source checkout")
    config = directory / "config"
    config.mkdir(mode=0o700, exist_ok=True)
    parent = os.open(config, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = ".ui-" + uuid.uuid4().hex + ".tmp"
    try:
        os.fchmod(parent, 0o700)
        try:
            existing = os.stat("ui.json", dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISREG(existing.st_mode):
                raise ValueError("Refusing a non-regular UI preference file")
        except FileNotFoundError:
            pass
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            content["language"] = language
            json.dump(content, handle)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, "ui.json", src_dir_fd=parent, dst_dir_fd=parent)
    finally:
        try:
            os.unlink(temporary, dir_fd=parent)
        except FileNotFoundError:
            pass
        os.close(parent)


class ReadOnlyStore(Store):
    def __init__(self, directory):
        self.directory = Path(directory).expanduser().resolve()
        self.path = self.directory / "db/panel.sqlite3"
        if not self.path.is_file():
            raise FileNotFoundError("No local task database; initialize it with the panel CLI first")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=1)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            with db:
                yield db
        finally:
            db.close()


def duration(seconds, language="zh"):
    seconds = max(0, int(seconds or 0))
    if language == "en":
        if seconds < 60:
            return f"{seconds}s"
        if seconds < 3600:
            return f"{seconds // 60}m {seconds % 60:02d}s"
        return f"{seconds // 3600}h {seconds % 3600 // 60:02d}m"
    if seconds < 60:
        return f"{seconds} 秒"
    if seconds < 3600:
        return f"{seconds // 60} 分 {seconds % 60:02d} 秒"
    return f"{seconds // 3600} 小时 {seconds % 3600 // 60:02d} 分"


def size(value, language="zh"):
    if value is None:
        return translate("不可用", language)
    return f"{value / (1024 ** 3):.1f} GiB"


STAGES = {"progress": ("工作进展", "Work progress"),"recovered_summary": ("恢复摘要", "Recovered summary"),"planned": ("规划", "Planning"), "implementation": ("实现", "Implementation"),
          "testing": ("测试", "Testing"), "review": ("审查", "Review"), "delivered": ("交付", "Delivery"),
          "artifact": ("成果归档", "Artifact archived"), "assignment": ("负责人变更", "Owner assignment"), "work_type": ("任务类型更新", "Task type update"), "state_changed": ("状态变更", "State changed"), "closeout": ("交付与验证", "Delivery & verification")}


def stage_label(stage, language="zh"):
    return STAGES.get(stage, (stage, stage))[1 if language == "en" else 0]


def activity_summary(snapshot, task_id, language="zh"):
    records = [item for item in snapshot.get("activity", []) if item.get("task_id") == task_id and item.get("stage") not in ("assignment", "work_type")]
    latest = max(records, key=lambda item: (item["created"], item.get("id", 0)), default=None)
    return latest["message"] if latest else ("No work progress recorded" if language == "en" else "尚无工作进展摘要")


def assigned_agent(snapshot, task_id):
    # Recovery reconstruction of simple owner lookup; original body not retained.
    assignment=next((item for item in snapshot.get("agent_assignments",[]) if item["task_id"]==task_id),None)
    return next((item for item in snapshot.get("agents",[]) if assignment and item["id"]==assignment["agent_id"]),None)


def binding_summary(snapshot, task_id, language="zh", timezone=DEFAULT_TIMEZONE):
    # Recovery reconstruction; uses retained safe URL validator, never invents a link.
    en=language=="en"
    item=next((row for row in snapshot.get("bindings",[]) if row["task_id"]==task_id),None)
    if not item:return {"title":"Platform chat: not linked" if en else "平台独立聊天：未绑定","lines":[],"url":None}
    try:url=verified_link(item.get("verified_url")) if item.get("verified_url") else None
    except ValueError:url=None
    return {"title":"Session binding recorded" if en else "已登记会话绑定","lines":[str(item.get("observed_status","unknown")),timestamp_label(item["observed_at"], timezone),"Manual observation; not live" if en else "手动观察，非实时连接"],"url":url}


def task_rows(snapshot, now, language="zh"):
    rows = []
    for task in snapshot.get("tasks", []):
        run = current_run(snapshot, task["id"], now)
        activities = [a for a in snapshot.get("activity", []) if a.get("task_id") == task["id"] and a.get("stage") not in ("assignment", "work_type", "heartbeat")]
        activity = max(activities, key=lambda a: a["created"], default=None)
        status = run["status"] if run else (task.get("latest_status") or "pending")
        label = translate(STATUS.get(status, status), language)
        warning = ""
        if run and run.get("stale"):
            if run.get("tracking_mode", task.get("tracking_mode", "manual")) == "heartbeat":
                warning = translate("心跳过期", language)
            else:
                warning = translate("进度更新较久，执行状态待确认", language)
        elapsed = duration((run.get("finished") or now) - run["started"], language) if run else "—"
        updated = duration(now - run.get("progress_updated", run["updated"]), language) + (" ago" if language == "en" else "前") if run else "—"
        rows.append({"id": task["id"], "run": run, "status": status, "warning": warning,
                     "values": (task["name"], task["project"], label, stage_label(activity["stage"], language) if activity else "—", elapsed, updated)})
    priority = lambda status: 0 if status == "running" else 2 if status in {"succeeded", "cancelled", "failed"} else 1
    return sorted(rows, key=lambda row: (priority(row["status"]), -task_meaningful_updated(snapshot, row["id"]), row["id"]))


def pipeline_counts(snapshot):
    latest = {}
    for item in sorted(snapshot.get("activity", []), key=lambda a: a["created"]):
        if item.get("stage") in ("assignment", "work_type", "state_changed", "closeout", "recovered_summary"):
            continue
        latest[(item["project"], item.get("task_id"), item["stage"])] = item.get("state", "in_progress")
    return {state: sum(value == state for value in latest.values()) for state in ("planned", "in_progress", "verified")}


def choose_font(families):
    available = {name.casefold(): name for name in families}
    for name in ("Noto Sans CJK SC", "Noto Sans SC", "WenQuanYi Zen Hei", "WenQuanYi Micro Hei", "Microsoft YaHei", "PingFang SC", "Noto Sans CJK TC", "Noto Sans CJK JP", "Noto Serif CJK SC"):
        if name.casefold() in available:
            return available[name.casefold()]
    return next((name for name in families if "cjk" in name.casefold()), "sans-serif")


def schedule_summary(schedule, language="zh", timezone=DEFAULT_TIMEZONE):
    platform = schedule_platform_view(schedule, language, timezone)
    if platform:
        return platform["label"], platform["compact"]
    result = schedule_result_view(schedule, language, timezone)
    if result:
        return result["label"], result["error"] or result["compact"][0]
    states = {"disconnected": "未接入", "planned": "计划", "paused": "已暂停"}
    state = translate(states.get(schedule.get("state"), "未知"), language)
    when = schedule.get("next_run")
    timing = (translate("计划时间", language) + ": " + timestamp_label(when, timezone)) if isinstance(when, (int, float)) else translate("下次运行未知", language)
    return state, timing


def schedule_platform_view(schedule, language="zh", timezone=DEFAULT_TIMEZONE):
    item = schedule.get("platform_observation")
    if not item:
        return None
    text = lambda zh, en: en if language == "en" else zh
    unknown = text("未知", "Unknown")
    enabled = text("已启用", "Enabled") if item.get("enabled") is True else text("已停用", "Disabled") if item.get("enabled") is False else unknown
    rows = [(text("平台", "Platform"), item.get("platform") or unknown), (text("平台任务 ID", "Platform task ID"), item.get("task_id") or unknown), (text("已观察启用状态", "Observed enabled state"), enabled), (text("调度时区", "Schedule timezone"), item.get("timezone") or unknown), (text("计划", "Schedule"), item.get("schedule") or unknown), (text("定时方式", "Timing mode"), item.get("timing_mode") or unknown), (text("上次运行", "Last run"), timestamp_label(item["last_run_at"], timezone) if item.get("last_run_at") else unknown), (text("下次运行", "Next run"), timestamp_label(item["next_run_at"], timezone) if item.get("next_run_at") else unknown), (text("平台观察时间", "Platform observed at"), timestamp_label(item.get("observed_at"), timezone)), (text("首次定时执行", "First scheduled execution"), text("尚未核验", "Not yet verified"))]
    rule = str(item.get("schedule") or "")
    parts = dict(part.split("=", 1) for line in rule.splitlines() if line.startswith("RRULE:") for part in line[6:].split(";") if "=" in part)
    compact = text("已记录计划；展开查看", "Recorded schedule; expand for details")
    if parts.get("FREQ") == "HOURLY" and parts.get("INTERVAL", "1") == "1":
        compact = text("每小时", "Every hour")
    elif parts.get("FREQ") == "DAILY" and parts.get("INTERVAL", "1") == "1" and parts.get("BYHOUR", "").isdigit() and parts.get("BYMINUTE", "0").isdigit():
        compact = text("每天 ", "Daily ") + f"{int(parts['BYHOUR']):02d}:{int(parts.get('BYMINUTE', '0')):02d}"
    return {"label": text("平台观察 · ", "Platform observed · ")+enabled, "compact": compact+" · "+(item.get("timezone") or unknown), "rows": rows}


def schedule_result_view(schedule, language="zh", timezone=DEFAULT_TIMEZONE):
    """Present saved evidence without inferring platform settings or source freshness."""
    result = schedule.get("external_result")
    if not result:
        return None
    en = language == "en"
    text = lambda zh, english: english if en else zh
    unknown = text("未知", "Unknown")
    value = lambda item: unknown if item is None or item == "" else str(item)
    checked = lambda item: timestamp_label(item, timezone) if isinstance(item, (int, float)) else text("尚无记录", "Not recorded")
    observation = result.get("observation")
    latest = (observation or {}).get("latest") or {}
    index = (observation or {}).get("index") or {}
    evidence = (observation or {}).get("evidence") or {}
    stale = text("是", "Yes") if latest.get("stale") is True else text("否", "No") if latest.get("stale") is False else unknown
    platform = schedule_platform_view(schedule, language, timezone)
    label = (text("结果已接入 · 平台配置已观察", "Results linked · platform config observed") if observation else text("暂无结果快照 · 平台配置已观察", "No result snapshot · platform config observed")) if platform else (text("结果已接入 · 配置未核验", "Results linked · config unverified") if observation else text("暂无结果快照 · 配置未核验", "No result snapshot · config unverified"))
    compact = [
        f"{text('最近观察尝试', 'Latest observed attempt')}: {value(latest.get('calendar_date'))} · {value(latest.get('status'))} · {text('入选数', 'Selected')}: {value(latest.get('selected_count'))}",
        f"{text('源过期标记', 'Source stale flag')}: {stale} · {text('已接受索引最新日期', 'Accepted index latest date')}: {value(index.get('latest_date'))}",
    ] if observation else [text("尚无可用的外部结果快照", "No usable external result snapshot")]
    error = ""
    if result.get("fetch_error"):
        retention = text("保留上次成功快照", "Retaining last good snapshot") if observation else text("尚无成功快照", "No successful snapshot")
        error = f"{text('获取失败', 'Fetch failed')}: {result['fetch_error']} · {retention}"
    rows = [
        (text("平台配置", "Platform configuration"), text("未核验；平台 ID、启用状态、下次执行时间均未知", "Unverified; platform ID, enabled state and next due are unknown")),
        (text("同步方式", "Sync mode"), text("手动结果快照；非实时连接", "Manual result snapshot; not a live connection")),
        (text("最近获取检查", "Last fetch check"), checked(result.get("checked_at"))),
        (text("最近成功获取", "Last successful fetch"), checked(result.get("last_good_at"))),
    ]
    if platform:
        rows[0] = (text("平台配置", "Platform configuration"), text("有人工观察快照；不代表实时状态或首次定时运行成功", "Manual snapshot available; not live status or proof of first scheduled execution"))
    if observation:
        rows.extend([
            (text("最近观察尝试日期", "Latest observed attempt date"), value(latest.get("calendar_date"))),
            (text("源运行编号", "Source run ID"), value(latest.get("run_id"))),
            (text("源采集时间", "Source collected at"), timestamp_label(latest.get("collected_at"), timezone)),
            (text("源结果状态", "Source result status"), value(latest.get("status"))),
            (text("入选数", "Selected count"), value(latest.get("selected_count"))),
            (text("源过期标记", "Source stale flag"), stale),
            (text("已接受索引最新日期", "Accepted index latest date"), value(index.get("latest_date"))),
            (text("索引生成时间", "Index generated at"), timestamp_label(index.get("generated_at"), timezone)),
            (text("索引条目数", "Index entry count"), value(index.get("entry_count"))),
        ])
    rows.extend([
        (text("结果仓库", "Result repository"), value(result.get("repository"))),
        (text("来源版本", "Source ref"), value(result.get("ref"))),
        (text("状态文件", "Status path"), value(result.get("status_path"))),
        (text("索引文件", "Index path"), value(result.get("index_path"))),
    ])
    if platform:
        rows[0] = (text("平台配置", "Platform configuration"), text("有人工观察快照；不代表实时状态或首次定时运行成功", "Manual snapshot available; not live status or proof of first scheduled execution"))
    if observation:
        rows.extend([
            ("Status blob SHA", value(evidence.get("status_sha"))), ("Index blob SHA", value(evidence.get("index_sha"))),
            (text("状态来源 URL", "Status source URL"), value(evidence.get("status_url"))),
            (text("索引来源 URL", "Index source URL"), value(evidence.get("index_url"))),
        ])
    return {"label": label, "compact": compact, "error": error, "rows": rows}


def timeline_records(snapshot, task_id):
    """One newest-first stream, including every run's original start note."""
    runs = {row["id"]: row for field in ("runs", "latest_runs", "current_runs", "open_runs") for row in snapshot.get(field, []) if row["task_id"] == task_id}
    records = []
    for item in snapshot.get("activity", []):
        if item.get("task_id") == task_id:
            records.append({"created": item["created"], "title": item["stage"], "state": item.get("state"), "message": item["message"], "kind": "activity", "source_id": str(item.get("id", "")), "key": "activity:"+str(item.get("id", "")), "task_id": task_id, "attribution": item.get("attribution"), "run_id": item.get("run_id")} )
    mirrored = {(row["created"], row["message"]) for row in records if not row.get("attribution")}
    for item in snapshot.get("events", []):
        if item["run_id"] in runs and (item.get("attribution") or (item["created"], item["message"]) not in mirrored):
            records.append({"created": item["created"], "title": "运行事件", "state": None, "message": item["message"], "kind": "event", "source_id": str(item.get("id", "")), "key": "event:"+str(item.get("id", "")), "task_id": task_id, "attribution": item.get("attribution"), "run_id": item.get("run_id")})
    for item in runs.values():
        if item.get("note"):
            records.append({"created": item["started"], "title": "启动说明：", "state": None, "message": item["note"], "kind": "note", "source_id": str(item["id"]), "key": "note:"+str(item["id"]), "task_id": task_id, "attribution": None, "run_id": item["id"]})
    order = {"activity": 0, "event": 1, "note": 2}
    return sorted(records, key=lambda row: (-row["created"], order[row["kind"]], row["source_id"], row["message"]))



COLLABORATION_COLORS = ('#eef5ef','#edf3fa','#f8f0e8','#f1eef8','#f8edf1','#eef5f5')


def collaboration_scope(snapshot, task_id, include_children=True):
    task = next((t for t in snapshot.get('tasks', []) if t['id'] == task_id), {})
    ids = {task_id}
    if include_children and task.get('activity_kind') == 'project':
        ids.update(t['id'] for t in snapshot.get('tasks', []) if t.get('parent_task_id') == task_id)
    return ids


def collaboration_participants(snapshot, task_id):
    merged = {}
    for key in sorted(collaboration_scope(snapshot, task_id)):
        for row in activity_participants(snapshot, key):
            if row['agent']['id'] not in merged:
                merged[row['agent']['id']] = {**row, 'assignments': list(row['assignments'])}
            else:
                merged[row['agent']['id']]['assignments'].extend(row['assignments'])
    return list(merged.values())


def collaboration_mode(task, language='zh'):
    en = language == 'en'
    parts = [('Project' if en else '项目') if task.get('activity_kind') == 'project' else ('Task' if en else '任务'),
             ('Team' if en else '团队') if task.get('collaboration_mode') == 'team' else ('Single' if en else '单人')]
    if task.get('mode_source') != 'explicit':
        parts[1]='Mode not recorded' if en else '协作方式未登记' 
    return ' · '.join(parts)


def collaboration_actor(record, snapshot, language='zh'):
    attribution = record.get('attribution') or {}
    if not attribution.get('agent_id'):
        return {'known': False, 'label': 'Anonymous' if language == 'en' else '匿名',
                'role': '', 'color': '#f3f4ef', 'agent': None, 'id': 'unattributed'}
    key = attribution.get('color_key', '')
    if len(key) != 8 or any(c not in '0123456789abcdefABCDEF' for c in key):
        key = '00000000'
    agent = {'id': attribution['agent_id'], 'name': attribution.get('actor_name', ''), 'name_en': attribution.get('actor_name_en', ''),
             'portrait': attribution.get('portrait', ''), 'panel_short_id': attribution.get('actor_short_id') or ('ID unrecorded' if language == 'en' else '编号未记录')}
    return {'known': True, 'label': agent_text(agent, 'name', language) or agent['panel_short_id'], 'short_id': agent['panel_short_id'],
            'role': work_type_label(attribution.get('work_type', 'unspecified'), language), 'color': COLLABORATION_COLORS[int(key, 16) % len(COLLABORATION_COLORS)],
            'agent': agent, 'id': agent['id'], 'assignment_id': attribution.get('assignment_id')}


def collaboration_records(snapshot, task_id, filters=None):
    filters = filters or {}
    ids = collaboration_scope(snapshot, task_id, filters.get('include_children', True))
    records = [r for key in sorted(ids) for r in timeline_records(snapshot, key)]
    return sorted([r for r in records if (not filters.get('task') or r.get('task_id') == filters['task'])
                   and (not filters.get('agent') or (r.get('attribution') or {}).get('agent_id', 'unattributed') == filters['agent'])
                   and (not filters.get('role') or (r.get('attribution') or {}).get('work_type', 'unattributed') == filters['role'])],
                  key=lambda r: (-r['created'], r['kind'], r['source_id']))


class RetainedCanvas:
    """Patch a deterministic drawing without deleting unchanged items or windows."""
    def __init__(self, canvas):
        self.canvas=canvas
        self.items=getattr(canvas,'retained_items',None)
        if not isinstance(self.items,dict):self.items={}
        canvas.retained_items=self.items
        self.used=set();self.index=0
    def __enter__(self):return self
    def __exit__(self,*args):
        for key in list(self.items):
            if key not in self.used:
                self.canvas.delete(self.items.pop(key)['id'])
    def delete(self,*tags):
        if tags==('all',):return
        self.canvas.delete(*tags)
    def __getattr__(self,name):
        if not name.startswith('create_'):return getattr(self.canvas,name)
        def create(*coords,**options):
            key=('window',str(options.get('window'))) if name=='create_window' else ('item',self.index)
            self.index+=1;self.used.add(key);previous=self.items.get(key)
            if previous is None or previous['method']!=name:
                if previous:self.canvas.delete(previous['id'])
                item=getattr(self.canvas,name)(*coords,**options)
                self.items[key]={'id':item,'method':name,'coords':coords,'options':dict(options)}
            else:
                item=previous['id']
                if previous['coords']!=coords:self.canvas.coords(item,*coords);previous['coords']=coords
                changed={key:value for key,value in options.items() if previous['options'].get(key)!=value}
                if changed:self.canvas.itemconfigure(item,**changed)
                previous['options']=dict(options)
            return item
        return create

def scroll_extent(content_height, viewport_height, fraction=0):
    """Keep short pages top-aligned; never allow a negative Canvas origin."""
    height = max(1, content_height, viewport_height)
    maximum = max(0, height-max(1, viewport_height))/height
    return height, max(0.0, min(float(fraction), maximum))


UNFINISHED_STATUSES = frozenset(("pending", "running", "waiting_user", "waiting_external", "paused", "awaiting_review"))


def workspace_rows(rows, status="all", query=""):
    query = query.casefold().strip()
    return [row for row in rows if (status == "all" or row["status"] == status or (status == "unfinished" and row["status"] in UNFINISHED_STATUSES)) and (not query or query in " ".join(row["values"][:2]).casefold())]


def percent(used, total):
    if used is None or total is None or total <= 0:
        return None
    return max(0, min(100, used / total * 100))


def timestamp_label(value, timezone=DEFAULT_TIMEZONE):
    if value is None:
        return "—"
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return value + " [timezone unknown]"
            value = parsed.timestamp()
        except ValueError:
            return value
    local = datetime.fromtimestamp(value, ZoneInfo(validate_timezone(timezone)))
    offset = local.strftime("%z")
    offset = offset[:3] + ":" + offset[3:]
    return local.strftime("%Y-%m-%d %H:%M:%S") + f" {timezone} (UTC{offset})"


def scroll_thumb(first, last, height):
    track = max(0, height-8)
    visible = max(0, min(1, last-first))
    length = min(track, max(32, track*visible))
    start = 4 + (max(0, min(first, 1-visible))/(1-visible)*(track-length) if visible < 1 else 0)
    return start, start+length


def scroll_drag_fraction(pointer, offset, first, last, height):
    visible = max(0, min(1, last-first))
    top, bottom = scroll_thumb(first, last, height)
    travel = max(0, height-8-(bottom-top))
    if travel <= 0 or visible >= 1:
        return 0.0
    return max(0, min(1, (pointer-4-offset)/travel))*(1-visible)


def display_signature(snapshot):
    ignored = {"sampled_at", "verified_at", "updated", "progress_updated"}
    def stable(value):
        if isinstance(value, dict):
            return {key: stable(item) for key, item in value.items() if key not in ignored}
        if isinstance(value, list):
            return [stable(item) for item in value]
        return value
    return json.dumps(stable(snapshot), sort_keys=True, ensure_ascii=False)


class Dashboard:
    timezone = DEFAULT_TIMEZONE
    timezone_error = False
    def __init__(self, root, store, metrics, tk, ttk, language="auto"):
        self.root, self.store, self.metrics, self.tk, self.ttk = root, store, metrics, tk, ttk
        self.language_choice, self.language = language, resolve_language(language)
        prefs = load_preferences(store.directory)
        self.timezone = DEFAULT_TIMEZONE
        self.timezone_error = bool(prefs.get("_read_error"))
        try:
            self.timezone = validate_timezone(prefs.get("timezone", DEFAULT_TIMEZONE))
        except ValueError:
            self.timezone_error = True
        self.motion = Motion(root, reduced=prefs.get("reduced_motion") is True)
        root.bind("<Destroy>", lambda event: self.motion.cancel_all() if event.widget is root else None, add="+")
        self.snapshot, self.metric_values, self.rows = {}, {}, []
        self.notification_state = NotificationState()
        self.notifications = None
        root.bind("<Destroy>", lambda event: self.notifications.close() if event.widget is root and self.notifications is not None else None, add="+")
        self.page, self.selected_task, self.timer = "overview", None, None
        self.workspace_filter = "all"
        self.search_query = tk.StringVar(root, value="")
        self.scroll_positions = {}
        self.scroll_dragging = False
        self.live_updates = []
        self.last_render_signature = None
        self.preference_error, self.read_error = False, False
        self.detail_scroll = 0.0
        self.bg, self.panel, self.fg, self.muted = "#f7f8f4", "#ffffff", "#24322b", "#657368"
        self.accent, self.tint = "#258560", "#e3f1e8"
        import tkinter.font as font
        self.font = choose_font(font.families(root))
        root.configure(bg=self.bg)
        self.window_state = NativeWindow(root, tk.TclError)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("Treeview", background=self.panel, foreground=self.fg, fieldbackground=self.panel, rowheight=45, borderwidth=0, font=(self.font, -17))
        style.configure("Treeview.Heading", background="#edf2ed", foreground=self.muted, font=(self.font, -15, "bold"), relief="flat")
        style.map("Treeview", background=[("selected", self.tint)], foreground=[("selected", self.fg)])
        root.bind("<Escape>", self.go_back)
        root.bind("<MouseWheel>", self.mousewheel)
        root.bind("<Button-4>", self.mousewheel)
        root.bind("<Button-5>", self.mousewheel)
        for key in ("Home", "End", "Prior", "Next"):
            root.bind(f"<{key}>", self.scroll_key)
        for index, page in enumerate(PAGE_NAMES, 1):
            root.bind(f"<Control-Key-{index}>", lambda event, destination=page: self.navigate(destination))
        self.metrics.collect()
        self.build_shell()
        self.refresh()

    def stamp(self, value):
        return timestamp_label(value, getattr(self, "timezone", DEFAULT_TIMEZONE))

    def t(self, value, **variables):
        return translate(value, self.language, **variables)

    def label(self, parent, text, pixels=17, color=None, bold=False, bg=None, wrap=0, raw=False):
        return self.tk.Label(parent, text=text if raw else self.t(text), bg=bg or parent.cget("bg"), fg=color or self.fg, font=(self.font, -pixels, "bold" if bold else "normal"), anchor="w", justify="left", wraplength=wrap)

    def button(self, parent, text, command, primary=False):
        button = self.tk.Button(parent, text=self.t(text), command=command, font=(self.font, -16, "bold"), bg=self.accent if primary else self.tint, fg="white" if primary else self.accent, activebackground="#d4e8dc", activeforeground=self.fg, relief="flat", bd=0, padx=16, pady=10, cursor="hand2", highlightthickness=1, highlightbackground=parent.cget("bg"), highlightcolor=self.accent)
        normal = {"color": button.cget("bg")}
        def enter(event):
            if button not in self.motion.jobs:
                normal["color"] = button.cget("bg")
            self.motion.color(button, normal["color"], "#1c7452" if primary else "#d3e8d9", lambda color: button.configure(bg=color))
        def leave(event):
            base = next((self.tint if name == self.page else "#eaf2e9" for name, item in getattr(self, "nav_buttons", {}).items() if item is button), normal["color"])
            self.motion.color(button, button.cget("bg"), base, lambda color: button.configure(bg=color))
        button.bind("<Enter>", enter)
        button.bind("<Leave>", leave)
        button.bind("<Destroy>", lambda event: self.motion.cancel(button), add="+")
        return button

    def card(self, parent, height=130, fill=None):
        canvas = self.tk.Canvas(parent, height=height, bg=self.bg, highlightthickness=0, bd=0)
        inner = self.tk.Frame(canvas, bg=fill or self.panel)
        window = canvas.create_window(20, 17, window=inner, anchor="nw")
        def redraw(event):
            for shape in canvas.find_all():
                if shape != window:
                    canvas.delete(shape)
            self.surface_layers(canvas, event.width, event.height, fill=fill)
            canvas.tag_raise(window)
            canvas.itemconfigure(window, width=max(20, event.width-40), height=0 if getattr(canvas, "auto_fit", False) else max(20, event.height-39))
        canvas.bind("<Configure>", redraw)
        return canvas, inner

    def build_shell(self):
        if getattr(self, "notifications", None) is not None:
            self.notifications.close()
            self.notifications = None
        self.motion.cancel_all()
        for widget in self.root.winfo_children():
            widget.destroy()
        self.root.title(self.t("Dots Panel · 任务与资源看板"))
        shell = self.tk.Frame(self.root, bg=self.bg)
        shell.pack(fill="both", expand=True)
        sidebar = self.tk.Frame(shell, bg="#eaf2e9", width=190)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        self.label(sidebar, "● dots-panel", 19, self.accent, True).pack(anchor="w", padx=18, pady=(26, 4))
        self.label(sidebar, "本地优先", 14, self.muted).pack(anchor="w", padx=24, pady=(0, 30))
        self.nav_buttons = {}
        for index, (page, title) in enumerate(PAGE_NAMES.items(), 1):
            button = self.button(sidebar, title, lambda destination=page: self.navigate(destination))
            button.configure(anchor="w", padx=18, bg="#eaf2e9", fg=self.fg)
            button.pack(fill="x", padx=12, pady=4)
            self.nav_buttons[page] = button
        self.label(sidebar, "v" + VERSION + "  ·  Ctrl 1–7", 13, self.muted).pack(side="bottom", anchor="w", padx=22, pady=22)
        if getattr(self, "window_state", None) is not None:
            window_hint = self.label(sidebar, "", 11, self.muted, wrap=150, raw=True)
            window_control = self.button(sidebar, "", self.window_state.toggle)
            window_control.configure(font=(self.font, -14), pady=6)
            window_control.pack(side="bottom", fill="x", padx=16, pady=(0, 5))
            def update_window_control(maximized, unconfirmed):
                caption = (("Restore window" if maximized else "Maximize window") if self.language == "en"
                           else ("还原窗口" if maximized else "最大化窗口"))
                if window_control.cget('text') != caption:
                    window_control.configure(text=caption)
                if unconfirmed:
                    window_hint.configure(text="Window manager did not confirm maximization" if self.language == "en" else "窗口管理器尚未确认最大化")
                    window_hint.pack(side="bottom", padx=18, pady=(0, 4))
                else:
                    window_hint.pack_forget()
            self.window_state.set_listener(update_window_control)
        main = self.tk.Frame(shell, bg=self.bg)
        main.pack(side="left", fill="both", expand=True, padx=25, pady=22)
        top = self.tk.Frame(main, bg=self.bg)
        top.pack(fill="x")
        self.page_title = self.label(top, "概览", 29, bold=True)
        self.page_title.pack(side="left")
        self.refresh_button = self.filter_chip(top, self.t("↻ 刷新"), self.refresh)
        self.refresh_button.pack(side="right", padx=(10, 0), pady=5)
        self.health = self.label(top, "正在读取本地数据", 13, self.muted, wrap=430)
        self.health.pack(side="right")
        self.shell_top = top
        top.bind("<Configure>", lambda event: self.health.configure(wraplength=max(160, event.width-250)))
        self.subtitle = self.label(main, "", 15, self.muted)
        self.subtitle.pack(anchor="w", pady=(5, 13))
        self.recovery_banner = self.label(main, "", 12, "#946a25", raw=True, wrap=900)
        self.recovery_info_button = self.filter_chip(top, "ⓘ Data note ⌄" if self.language == "en" else "ⓘ 数据说明 ⌄", self.toggle_recovery_info)
        self.recovery_notice_text = None
        self.recovery_info_visible = False
        self.recovery_body_visible = False
        self.content = self.tk.Frame(main, bg=self.bg)
        self.content.pack(fill="both", expand=True)
        self.footer = self.label(main, "数据来自显式登记；不读取内部会话", 13, self.muted)
        self.footer.pack(anchor="w", pady=(10, 0))
        self.render_page()
        if hasattr(self, "notification_state"):
            self.notifications = NativeNotifications(self, self.notification_state)

    def render_settings(self):
        area = self.scroll_area()
        language_card, language_box = self.card(area, 150)
        language_card.pack(fill="x", pady=(0, 14))
        self.label(language_box, "语言", 20, bold=True).pack(anchor="w", pady=(0, 12))
        self.locale_selector = self.filter_chip(language_box, {"auto": "Auto", "zh": "中文", "en": "English"}[self.language_choice]+" ⌄", self.open_language_menu)
        self.locale_selector.pack(anchor="w")
        self.locale_selector.bind("<Down>", lambda event: self.open_language_menu())
        self.fit_card(language_card, language_box)

        timezone_card, timezone_box = self.card(area, 270)
        timezone_card.pack(fill="x", pady=(0, 14))
        self.label(timezone_box, "显示时区", 20, bold=True).pack(anchor="w", pady=(0, 12))
        self.timezone_input = self.tk.StringVar(self.root, value=self.timezone)
        style = self.ttk.Style(self.root)
        style.configure("Settings.TCombobox", padding=(12, 9), fieldbackground="#f3f7f0", background="#e5eee1", foreground=self.fg, arrowcolor=self.accent, bordercolor="#d5e2d2", lightcolor="#d5e2d2", darkcolor="#d5e2d2", borderwidth=1, arrowsize=16)
        style.map("Settings.TCombobox", bordercolor=[("focus", self.accent)])
        selector = self.ttk.Combobox(timezone_box, style="Settings.TCombobox", textvariable=self.timezone_input, values=COMMON_TIMEZONES, width=26, font=(self.font, -17))
        selector.pack(anchor="w", pady=(0, 12))
        selector.bind("<Return>", lambda event: self.change_timezone())
        self.button(timezone_box, "应用时区", self.change_timezone).pack(anchor="w", pady=(0, 8))
        self.settings_error = self.label(timezone_box, "无效或不支持的 IANA 时区" if self.timezone_error else "", 15, "#9c611c")
        if self.timezone_error:
            self.settings_error.pack(anchor="w")
        self.label(timezone_box, self.stamp(time.time()), 15, self.accent, raw=True).pack(anchor="w", pady=(4, 8))
        self.label(timezone_box, "默认北京时间；支持 IANA 时区。仅调整显示，不改变系统时间或任务调度。", 15, self.muted, wrap=660).pack(anchor="w")
        region = self.snapshot.get("exit_region")
        region_info = exit_region_label(region, self.language)
        if region:
            region_info += " · ipwho.is · " + self.stamp(region["checked_at"])
        region_label=self.label(timezone_box,region_info,15,self.muted,raw=True,wrap=660)
        region_label.pack(anchor='w',pady=(10,0))
        last_region=[region_info]
        self.fit_card(timezone_card, timezone_box)

        refresh_backup = self.backup_card(area)

        motion_card, motion_box = self.card(area, 150)
        motion_card.pack(fill="x", pady=(0, 14))
        self.motion_preference = self.tk.BooleanVar(self.root, value=self.motion.reduced)
        self.motion_checkbox = self.tk.Checkbutton(motion_box, text="Reduce motion" if self.language == "en" else "减少动效", variable=self.motion_preference, command=self.change_motion, bg=self.panel, activebackground=self.panel, fg=self.fg, selectcolor=self.panel, font=(self.font, -17), highlightcolor=self.accent, highlightthickness=1, highlightbackground=self.panel, padx=4, pady=8)
        self.motion_checkbox.pack(anchor="w", pady=(0, 6))
        self.label(motion_box, "Short hover feedback only. This native app uses this local preference." if self.language == "en" else "仅保留短暂的悬停反馈；原生窗口使用此本机偏好。", 15, self.muted, raw=True, wrap=660).pack(anchor="w")
        self.fit_card(motion_card, motion_box)
        def wrap_settings(event):
            for child in event.widget.winfo_children():
                if isinstance(child, self.tk.Label):
                    child.configure(wraplength=max(100, event.width-8))
        for box in (language_box, timezone_box, motion_box):
            box.bind("<Configure>", wrap_settings, add="+")
        self.label(area, "设置保存在本机", 14, self.muted).pack(anchor="w", pady=(0, 12))
        def refresh_settings():
            region=self.snapshot.get('exit_region');info=exit_region_label(region,self.language)
            if region:info+=' · ipwho.is · '+self.stamp(region['checked_at'])
            if info!=last_region[0]:region_label.configure(text=info);last_region[0]=info
            refresh_backup()
        self.background_refresh=refresh_settings

    def backup_card(self, parent, compact=False):
        """Patch only changed backup labels; keep the page, focus and scroll intact."""
        card, box = self.card(parent, 150 if compact else 400)
        card.pack(fill='x', pady=(0, 14))
        en = self.language == 'en'
        self.label(box, 'Backup & recovery' if en else '备份与恢复', 19, bold=True, raw=True).pack(anchor='w', pady=(0, 8))
        status = self.label(box, '', 15, self.accent, raw=True, wrap=760)
        status.pack(anchor='w', pady=(0, 7))
        watch_status = self.label(box, '', 14, self.muted, raw=True, wrap=760)
        watch_status.pack(anchor='w', pady=(0, 7))
        details = self.tk.Frame(box, bg=self.panel)
        details.pack(fill='x')
        update_rows = self.keyed_labels(details)
        note = self.label(box, '', 13, self.muted, raw=True, wrap=760)
        note.pack(anchor='w', pady=(7, 0))
        if compact:
            self.filter_chip(box, 'View backup details →' if en else '查看备份详情 →', lambda: self.navigate('settings')).pack(anchor='w', pady=(9, 0))
        else:
            def copy_location():
                value = self.snapshot.get('backup') or {}
                location = (value.get('destination') or {}).get('path')
                if location:
                    self.root.clipboard_clear()
                    self.root.clipboard_append(location)
            self.filter_chip(box, 'Copy Library path' if en else '复制 Library 路径', copy_location).pack(anchor='w', pady=(9, 0))
        saved = {}
        def refresh_backup():
            value = backup_presentation(self.snapshot.get('backup'), self.language, self.stamp)
            if saved.get('title') != value['compact']:
                warning = (self.snapshot.get('backup') or {}).get('status') in ('failed', 'unavailable', 'unverified', 'stale', 'pending')
                status.configure(text=value['compact'], fg='#9c611c' if warning else self.accent)
                saved['title'] = value['compact']
            if saved.get('watch') != value['watch_compact']:
                watch_status.configure(text=value['watch_compact'])
                saved['watch'] = value['watch_compact']
            rows = [] if compact else [(key, title + ' · ' + text) for key, title, text in value['rows']]
            update_rows(rows)
            caption = ('Local historical evidence; remote state is not queried live.' if en else '本机历史回执；未实时查询远端状态。') if compact else value['note']
            if saved.get('note') != caption:
                note.configure(text=caption)
                saved['note'] = caption
        def wrap(event):
            width = max(140, event.width - 10)
            status.configure(wraplength=width)
            watch_status.configure(wraplength=width)
            note.configure(wraplength=width)
            for child in details.winfo_children():
                child.configure(wraplength=width)
        box.bind('<Configure>', wrap, add='+')
        refresh_backup()
        self.fit_card(card, box)
        return refresh_backup

    def change_motion(self):
        self.motion.reduced = self.motion_preference.get()
        self.motion.cancel_all()
        try:
            save_preferences(self.store.directory, reduced_motion=self.motion.reduced)
            self.preference_error = False
        except (OSError, ValueError):
            self.preference_error = True
        self.build_shell()
        self.update_health()
        self.motion_checkbox.focus_set()

    def change_timezone(self):
        try:
            value = validate_timezone(self.timezone_input.get().strip())
        except ValueError:
            self.settings_error.configure(text=self.t("无效或不支持的 IANA 时区"))
            self.settings_error.pack(anchor="w")
            return
        try:
            save_preferences(self.store.directory, timezone=value)
            self.preference_error = False
        except (OSError, ValueError):
            self.preference_error = True
        self.timezone, self.timezone_error = value, False
        self.render_page()
        self.update_health()

    def open_language_menu(self):
        if getattr(self, "language_popup", None) is not None:
            try:
                self.language_popup.destroy()
            except self.tk.TclError:
                pass
        popup = self.tk.Toplevel(self.root)
        self.language_popup = popup
        popup.overrideredirect(True)
        popup.transient(self.root)
        popup.configure(bg=self.bg)
        width, height = 174, 146
        x, y = popup_position(self.locale_selector.winfo_rootx(), self.locale_selector.winfo_rooty(),
            self.locale_selector.winfo_width(), self.locale_selector.winfo_height(), width, height,
            self.root.winfo_screenwidth(), self.root.winfo_screenheight())
        popup.geometry(f"{width}x{height}+{x}+{y}")
        surface = self.tk.Canvas(popup, width=width, height=height, bg=self.bg, bd=0, highlightthickness=0)
        surface.pack(fill="both", expand=True)
        self.round_shape(surface, 4, 5, width-4, height-5, "#e7ece4", 12)
        self.round_shape(surface, 2, 3, width-5, height-6, "#dde7dc", 12)
        self.round_shape(surface, 0, 0, width-5, height-6, "#d6e4d8", 12)
        self.round_shape(surface, 1, 1, width-7, height-8, self.panel, 11)
        panel = self.tk.Frame(surface, bg=self.panel)
        surface.create_window(7, 7, window=panel, anchor="nw", width=width-19, height=height-20)
        options = [("auto", "Auto"), ("zh", "中文"), ("en", "English")]
        buttons, position = [], [next((i for i, pair in enumerate(options) if pair[0] == self.language_choice), 0)]
        focus_job = {"id": None}
        def close(event=None):
            if focus_job["id"] is not None:
                popup.after_cancel(focus_job["id"])
                focus_job["id"] = None
            if popup.winfo_exists():
                popup.grab_release()
                popup.destroy()
            self.language_popup = None
            if self.locale_selector.winfo_exists():
                self.locale_selector.focus_set()
            return "break"
        def choose(choice):
            close()
            self.change_language(choice=choice)
            return "break"
        for choice, label in options:
            button = self.tk.Button(panel, text=("✓  " if choice == self.language_choice else "    ")+label,
                anchor="w", command=lambda value=choice: choose(value), font=(self.font, -14),
                bg=self.tint if choice == self.language_choice else self.panel, fg=self.accent if choice == self.language_choice else self.fg,
                activebackground=self.tint, relief="flat", bd=0, padx=11, pady=8, highlightthickness=1, highlightbackground=self.panel, highlightcolor=self.accent)
            button.pack(fill="x", pady=1)
            buttons.append(button)
        def move(delta):
            position[0] = (position[0]+delta) % len(buttons)
            buttons[position[0]].focus_force()
            return "break"
        bindings = {
            "<Down>": lambda event: move(1), "<Up>": lambda event: move(-1),
            "<Home>": lambda event: move(-position[0]), "<End>": lambda event: move(len(buttons)-1-position[0]),
            "<Return>": lambda event: choose(options[position[0]][0]),
            "<space>": lambda event: choose(options[position[0]][0]),
            "<Escape>": close, "<Tab>": close,
        }
        # Child widget bindings run before Tk's Button class bindings. Returning
        # break prevents one keypress from moving twice or invoking a stale row.
        for target in (popup, *buttons):
            for sequence, callback in bindings.items():
                target.bind(sequence, callback)
        for index, button in enumerate(buttons):
            button.bind("<FocusIn>", lambda event, index=index: position.__setitem__(0, index))
        popup.bind("<Button-1>", lambda event: close() if not (popup.winfo_rootx() <= event.x_root < popup.winfo_rootx()+popup.winfo_width() and popup.winfo_rooty() <= event.y_root < popup.winfo_rooty()+popup.winfo_height()) else None)
        def focus_when_mapped():
            focus_job["id"] = None
            if self.language_popup is not popup or not popup.winfo_exists():
                return
            if not popup.winfo_viewable():
                focus_job["id"] = popup.after(20, focus_when_mapped)
                return
            popup.grab_set()
            popup.focus_force()
            buttons[position[0]].focus_force()
        # An override-redirect window is not guaranteed to be mapped when
        # constructed, particularly after rebuilding the shell for a locale.
        focus_job["id"] = popup.after(30, focus_when_mapped)
        return "break"

    def change_language(self, event=None, choice=None):
        choice = choice or self.language_choice
        try:
            save_language(self.store.directory, choice)
            self.preference_error = False
        except (OSError, ValueError):
            self.preference_error = True
        if hasattr(self, "page_scroll") and self.page_scroll.winfo_exists():
            self.scroll_positions[getattr(self, "rendered_page_key", self.viewport_key())] = self.page_scroll.yview()[0]
        self.language_choice, self.language = choice, resolve_language(choice)
        self.rows = task_rows(self.snapshot, time.time(), self.language)
        self.build_shell()
        self.update_health()

    def navigate(self, page):
        self.page, self.selected_task, self.detail_scroll = page, None, 0.0
        self.render_page()
        if getattr(self, "notifications", None) is not None:
            self.notifications.mark_read(page)

    def go_back(self, event=None):
        if self.page == "conversations" and self.selected_task:
            self.selected_task, self.detail_scroll = None, 0.0
            self.render_page()

    def refresh(self):
        if getattr(self, "timer", None) is not None:
            self.root.after_cancel(self.timer)
            self.timer = None
        try:
            self.snapshot = self.store.snapshot()
            notification_result = self.notification_state.update(self.snapshot) if hasattr(self, "notification_state") else None
            self.metric_values = self.metrics.collect()
            self.rows = task_rows(self.snapshot, time.time(), self.language)
            self.last_successful_refresh = time.time()
            self.read_error = False
            conversation_widgets = getattr(self,"conversation_filter_widgets",{})
            conversation_focus = bool(conversation_widgets) and self.root.focus_get() in conversation_widgets.values()
            if not self.scroll_dragging and not getattr(self, "filter_menu_open", False) and not conversation_focus:
                changed = self.view_signature() != self.last_render_signature
                handler = getattr(self,'background_refresh',None)
                if changed and callable(handler):
                    handler()
                    self.last_render_signature=self.view_signature()
                elif changed:
                    self.render_page()
                for update in list(self.live_updates):
                    if not (changed and update is handler):update()
            if notification_result is not None and getattr(self, "notifications", None) is not None:
                self.notifications.observe(notification_result)
        except (OSError, sqlite3.Error, ValueError, KeyError):
            self.read_error = True
        self.update_recovery_notice()
        self.update_health()
        self.timer = self.root.after(5000, self.refresh)

    def toggle_recovery_info(self):
        self.recovery_info_expanded = not getattr(self,'recovery_info_expanded',False)
        self.update_recovery_notice()

    def update_recovery_notice(self):
        if getattr(self,'recovery_banner',None) is None:
            return
        recovery=self.snapshot.get('recovery') or {}
        notice=recovery.get('notice_en' if self.language=='en' else 'notice_zh','')
        if notice != getattr(self,'recovery_notice_text',None):
            self.recovery_banner.configure(text=notice)
            self.recovery_notice_text=notice
        if getattr(self,'recovery_info_button',None) is None:
            return
        visible=bool(notice) and not (self.page=='conversations' and bool(self.selected_task))
        expanded=bool(getattr(self,'recovery_info_expanded',False))
        caption=('ⓘ Data note' if self.language=='en' else 'ⓘ 数据说明')+(' ⌃' if expanded else ' ⌄')
        self.patch_caption(self.recovery_info_button,caption)
        if visible != getattr(self,'recovery_info_visible',False):
            if visible:self.recovery_info_button.pack(side='right',padx=(0,8),pady=5)
            else:self.recovery_info_button.pack_forget()
            self.recovery_info_visible=visible
        body_visible=visible and expanded
        if body_visible != getattr(self,'recovery_body_visible',False):
            if body_visible:self.recovery_banner.pack(anchor='w',fill='x',pady=(0,8),before=self.content)
            else:self.recovery_banner.pack_forget()
            self.recovery_body_visible=body_visible

    def update_health(self):
        if self.read_error:
            message = self.t("刷新失败，保留上次数据")
        elif self.preference_error:
            message = self.t("未保存偏好；当前仅本次有效")
        elif self.timezone_error:
            message = self.t("无效或不支持的 IANA 时区")
        else:
            last = getattr(self, "last_successful_refresh", None)
            stamp = datetime.fromtimestamp(last, ZoneInfo(self.timezone)).strftime("%Y-%m-%d %H:%M:%S") if last is not None else self.t("尚未刷新")
            message = self.t("每 5 秒 · 最近刷新") + " " + stamp + " · " + exit_region_label(self.snapshot.get("exit_region"), self.language)
        self.health.configure(text=message, fg="#9c611c" if self.read_error or self.preference_error else self.accent)

    def render_page(self):
        self.motion.cancel_all()
        self.pending_conversation_anchor = None
        anchor_key=(self.page,self.selected_task,getattr(self,'detail_tab','timeline'),json.dumps(getattr(self,'conversation_filters',{}),sort_keys=True),getattr(self,'conversation_offset',0))
        if getattr(self,'conversation_anchor_key',None)==anchor_key and hasattr(self,'page_scroll') and self.page_scroll.winfo_exists():
            top=self.page_scroll.canvasy(0)
            if top>0:
                for key,widget in getattr(self,'conversation_anchors',{}).items():
                    if widget.winfo_exists() and widget.winfo_y()+widget.winfo_height()>top:
                        self.pending_conversation_anchor=(key,widget.winfo_y()-top);break
        self.conversation_anchor_key=anchor_key
        focused = self.root.focus_get()
        output_focus = next((key for key, widget in getattr(self, "output_buttons", {}).items() if widget == focused), None)
        self.output_buttons = {}
        filter_focus = next((key for key, widget in getattr(self, "filter_buttons", {}).items() if widget == focused), None)
        more_focus = focused is not None and focused == getattr(self, "more_filter_button", None)
        had_search_focus = hasattr(self, "search_entry") and self.root.focus_get() == self.search_entry
        if hasattr(self, "page_scroll") and self.page_scroll.winfo_exists():
            self.scroll_positions[getattr(self, "rendered_page_key", self.viewport_key())] = self.page_scroll.yview()[0]
        old_selection = ()
        if hasattr(self, "task_tree") and self.task_tree.winfo_exists():
            old_selection = self.task_tree.selection()
        if hasattr(self, "timeline") and self.timeline.winfo_exists():
            self.detail_scroll = self.timeline.yview()[0]
        self.cancel_viewport_restore()
        self.live_updates = []
        self.background_refresh = None
        for widget in self.content.winfo_children():
            widget.destroy()
        detail_only = self.page == 'conversations' and bool(self.selected_task)
        if hasattr(self,'shell_top'):
            if detail_only:
                self.shell_top.pack_forget();self.subtitle.pack_forget()
            else:
                self.shell_top.pack(fill='x',before=self.content)
                self.subtitle.pack(anchor='w',pady=(5,13),before=self.content)
            self.update_recovery_notice()
        self.page_title.configure(text=self.t("工作区" if self.page == "overview" else PAGE_NAMES[self.page]))
        subtitles = {"overview": "资源、工作与计划，一目了然", "conversations": "已登记任务与工作记录；执行会话绑定情况见详情", "schedules": "只展示已登记计划；此面板不会执行自动化", "software": "本地软件登记与检测；不会运行任意命令"}
        self.subtitle.configure(text=self.t(subtitles.get(self.page, "")))
        if self.page == 'schedules':self.subtitle.pack_forget()
        for name, button in self.nav_buttons.items():
            button.configure(bg=self.tint if name == self.page else "#eaf2e9", fg=self.accent if name == self.page else self.fg)
        if self.page == "overview":
            self.render_overview()
        elif self.page == "conversations":
            if self.selected_task:
                self.render_conversation()
            else:
                self.render_conversation_list(old_selection)
        elif self.page == "schedules":
            self.render_schedules()
        elif self.page == "software":
            self.render_software()
        elif self.page == "rules":
            self.render_rules()
        elif self.page == "settings":
            self.render_settings()
        elif self.page == "about":
            self.render_about()
        if getattr(self, "notifications", None) is not None:
            self.notifications.badges()
            self.notifications.canvas.tk.call("raise", self.notifications.canvas._w)
        self.rendered_page_key = self.viewport_key()
        self.last_render_signature = self.view_signature()
        focus_target = getattr(self, "more_filter_button", None) if more_focus else getattr(self, "filter_buttons", {}).get(filter_focus)
        if focus_target is not None and focus_target.winfo_exists():
            focus_target.focus_set()
        output_target = getattr(self,"output_buttons",{}).get(output_focus)
        if output_target is not None and output_target.winfo_exists():
            output_target.focus_set()
        if had_search_focus and hasattr(self, "search_entry") and self.search_entry.winfo_exists():
            self.search_entry.focus_set()
            self.search_entry.icursor("end")

    def round_shape(self, canvas, x, y, width, height, fill, radius=14):
        return canvas.create_polygon(x+radius, y, x+width-radius, y, x+width, y, x+width, y+radius, x+width, y+height-radius, x+width, y+height, x+width-radius, y+height, x+radius, y+height, x, y+height, x, y+height-radius, x, y+radius, x, y, smooth=True, fill=fill, outline="")

    def filter_chip(self, parent, text, command, selected=False):
        import tkinter.font as font
        width = font.Font(root=self.root, family=self.font, size=-14).measure(text) + 26
        canvas = self.tk.Canvas(parent, width=width, height=34, bg=self.bg, bd=0, highlightthickness=0, cursor="hand2", takefocus=1)
        normal = self.accent if selected else "#e9eee8"
        shape = self.round_shape(canvas, 0, 0, width, 34, normal, 17)
        canvas.configure(highlightthickness=1, highlightbackground=self.bg, highlightcolor=self.accent)
        def feedback(active):
            target = ("#1b7351" if selected else "#dcecdf") if active else normal
            self.motion.color(canvas, canvas.itemcget(shape, "fill"), target, lambda color: canvas.itemconfigure(shape, fill=color))
        canvas.bind("<Enter>", lambda event: feedback(True))
        canvas.bind("<Leave>", lambda event: feedback(False))
        canvas.bind("<Destroy>", lambda event: self.motion.cancel(canvas), add="+")
        canvas.caption_text=text
        canvas.caption_item=canvas.create_text(width/2, 17, text=text, fill="white" if selected else self.muted, font=(self.font, -14, "bold" if selected else "normal"))
        canvas.bind("<Button-1>", lambda event: command())
        canvas.bind("<Return>", lambda event: command())
        canvas.bind("<space>", lambda event: command())
        return canvas

    def patch_caption(self,widget,text):
        if getattr(widget,'caption_text',None)==text:return
        widget.caption_text=text
        item=getattr(widget,'caption_item',None)
        if item is not None:
            widget.itemconfigure(item,text=text)
        else:widget.configure(text=text)

    def keyed_labels(self,parent):
        labels={};previous={}
        def reconcile(rows):
            wanted=[key for key,_ in rows]
            for key in list(labels):
                if key not in wanted:labels.pop(key).destroy();previous.pop(key,None)
            for key,text in rows:
                if key not in labels:
                    labels[key]=self.label(parent,text,14,self.muted,raw=True,wrap=800);labels[key].pack(anchor='w',fill='x',pady=3)
                elif previous[key]!=text:labels[key].configure(text=text)
                previous[key]=text
        return reconcile

    def keyed_registry(self,parent,records,model,minimum=330,maximum=3,bounded=False):
        grid=self.card_grid(parent,minimum=minimum,maximum=maximum);cards={};previous={}
        empty=self.label(parent,'暂无记录' if self.language=='zh' else 'No records',15,self.muted,raw=True)
        def reconcile():
            values=records();wanted=[str(row.get('id',row.get('name',''))) for row in values]
            for key in list(cards):
                if key not in wanted:cards.pop(key)['box'].surface.destroy();previous.pop(key,None)
            for row,key in zip(values,wanted):
                value=model(row)
                if key not in cards:
                    box=self.compact_row(grid,value['title'],value.get('summary',''),value.get('status',''),**({'bounded':True} if bounded else {}))
                    details=self.tk.Frame(box,bg=self.panel);details.pack(fill='x',pady=(4,0))
                    actions=self.tk.Frame(box,bg=self.panel);actions.pack(fill='x',pady=(5,0))
                    cards[key]={'box':box,'details':self.keyed_labels(details),'actions':actions,'buttons':{},'callbacks':{}}
                item=cards[key];old=previous.get(key,{})
                for field,widget in (('title',item['box'].title_label),('summary',item['box'].summary_label),('status',item['box'].status_label)):
                    if field in old and old.get(field)!=value.get(field) and widget is not None:
                        if bounded:item['box'].set_caption(field,value.get(field,''))
                        else:widget.configure(text=value.get(field,''))
                item['details'](value.get('details',[]))
                if bounded:item['box'].set_expanded(bool(value.get('details')))
                actions=value.get('actions',[]);action_keys=[entry[0] for entry in actions]
                for action in list(item['buttons']):
                    if action not in action_keys:item['buttons'].pop(action).destroy();item['callbacks'].pop(action,None)
                for action,label,callback in actions:
                    item['callbacks'][action]=callback
                    if action not in item['buttons']:
                        button=self.filter_chip(item['actions'],label,lambda item=item,action=action:item['callbacks'][action]());button.pack(side='left',padx=(0,7));item['buttons'][action]=button
                    else:self.patch_caption(item['buttons'][action],label)
                previous[key]=value
            ordered=[cards[key]['box'].surface for key in wanted]
            if grid.card_items!=ordered:grid.card_items=ordered;grid.reflow_cards()
            if wanted:empty.pack_forget()
            else:empty.pack(anchor='w',pady=12)
        reconcile()
        self.background_refresh=reconcile
        if not hasattr(self,"live_updates"):self.live_updates=[]
        self.live_updates.append(reconcile)
        return reconcile

    def set_workspace_filter(self, status):
        self.workspace_filter = status
        if not getattr(self, "filter_menu_open", False):
            self.render_page()
            button = getattr(self, "filter_buttons", {}).get(status, getattr(self, "more_filter_button", None))
            if button is not None and button.winfo_exists():
                button.focus_set()

    def open_filter_menu(self, kind="status"):
        if getattr(self, "filter_popup", None) is not None:
            try:
                self.filter_popup.destroy()
            except self.tk.TclError:
                pass
        popup = self.tk.Toplevel(self.root)
        self.filter_popup = popup
        self.filter_menu_open = True
        popup.overrideredirect(True)
        popup.transient(self.root)
        popup.configure(bg=self.bg)
        type_menu = kind == 'type'
        anchor_name = 'type_filter_button' if type_menu else 'more_filter_button'
        anchor = getattr(self,anchor_name)
        selected = getattr(self,'collaboration_mode_filter','all') if type_menu else self.workspace_filter
        width, height = (224,190) if type_menu else (292,410)
        x, y = popup_position(anchor.winfo_rootx(), anchor.winfo_rooty(),
            anchor.winfo_width(), anchor.winfo_height(), width, height,
            self.root.winfo_screenwidth(), self.root.winfo_screenheight())
        popup.geometry(f"{width}x{height}+{x}+{y}")
        surface = self.tk.Canvas(popup, width=width, height=height, bg=self.bg, bd=0, highlightthickness=0)
        surface.pack(fill="both", expand=True)
        self.round_shape(surface, 4, 5, width-4, height-5, "#e7ece4", 12)
        self.round_shape(surface, 2, 3, width-5, height-6, "#dde7dc", 12)
        self.round_shape(surface, 0, 0, width-5, height-6, "#d6e4d8", 12)
        self.round_shape(surface, 1, 1, width-7, height-8, self.panel, 11)
        panel = self.tk.Frame(surface, bg=self.panel)
        surface.create_window(7, 7, window=panel, anchor="nw", width=width-19, height=height-20)
        options = [(status, self.t(STATUS[status]) + f"  {len(workspace_rows(self.rows, status))}") for status in ("pending", "running", "waiting_user", "waiting_external", "paused", "awaiting_review", "succeeded", "cancelled", "failed")]
        if type_menu:
            options=[('all','All types' if self.language=='en' else '全部类型'),('single','Single' if self.language=='en' else '单人'),('team','Team' if self.language=='en' else '团队'),('project','Project' if self.language=='en' else '项目')]
        buttons, position = [], [next((i for i, pair in enumerate(options) if pair[0] == selected), 0)]
        focus_job = {"id": None}
        def close(event=None, apply=False):
            if focus_job["id"] is not None:
                popup.after_cancel(focus_job["id"])
                focus_job["id"] = None
            if popup.winfo_exists():
                popup.grab_release()
                popup.destroy()
            self.filter_popup = None
            self.filter_menu_open = False
            if apply:self.render_page()
            trigger=getattr(self,anchor_name,None)
            if trigger is not None and trigger.winfo_exists():
                trigger.focus_set()
            return "break"
        def choose(choice):
            if type_menu:self.collaboration_mode_filter=choice
            else:self.workspace_filter=choice
            close(apply=True)
            return "break"
        for choice, label in options:
            button = self.tk.Button(panel, text=("✓  " if choice == selected else "    ")+label,
                anchor="w", command=lambda value=choice: choose(value), font=(self.font, -14),
                bg=self.tint if choice == selected else self.panel, fg=self.accent if choice == selected else self.fg,
                activebackground=self.tint, relief="flat", bd=0, padx=11, pady=8, highlightthickness=1, highlightbackground=self.panel, highlightcolor=self.accent)
            button.pack(fill="x", pady=1)
            buttons.append(button)
        def move(delta):
            position[0] = (position[0]+delta) % len(buttons)
            buttons[position[0]].focus_force()
            return "break"
        bindings = {
            "<Down>": lambda event: move(1), "<Up>": lambda event: move(-1),
            "<Home>": lambda event: move(-position[0]), "<End>": lambda event: move(len(buttons)-1-position[0]),
            "<Return>": lambda event: choose(options[position[0]][0]),
            "<space>": lambda event: choose(options[position[0]][0]),
            "<Escape>": close, "<Tab>": close,
        }
        # Child widget bindings run before Tk's Button class bindings. Returning
        # break prevents one keypress from moving twice or invoking a stale row.
        for target in (popup, *buttons):
            for sequence, callback in bindings.items():
                target.bind(sequence, callback)
        for index, button in enumerate(buttons):
            button.bind("<FocusIn>", lambda event, index=index: position.__setitem__(0, index))
        popup.bind("<Button-1>", lambda event: close() if not (popup.winfo_rootx() <= event.x_root < popup.winfo_rootx()+popup.winfo_width() and popup.winfo_rooty() <= event.y_root < popup.winfo_rooty()+popup.winfo_height()) else None)
        def focus_when_mapped():
            focus_job["id"] = None
            if self.filter_popup is not popup or not popup.winfo_exists():
                return
            if not popup.winfo_viewable():
                focus_job["id"] = popup.after(20, focus_when_mapped)
                return
            popup.grab_set()
            popup.focus_force()
            buttons[position[0]].focus_force()
        # An override-redirect window is not guaranteed to be mapped when
        # constructed, particularly after rebuilding the shell for a locale.
        focus_job["id"] = popup.after(30, focus_when_mapped)
        return "break"

    def output_button(self, parent, text, command, task_id, action="files"):
        button = self.filter_chip(parent, text, command)
        if not hasattr(self,"output_buttons"):
            self.output_buttons = {}
        self.output_buttons[(task_id,action)] = button
        return button

    def open_task_files(self, task_id):
        if getattr(self,"selected_task",None) != task_id:self.detail_meta=False
        self.detail_tab = "files"
        self.show_attention_advice = False
        self.page, self.selected_task, self.detail_scroll = "conversations", task_id, 0.0
        self.render_page()

    def open_task_outputs(self, task_id):
        from tkinter import messagebox
        try:
            if not hasattr(self, "folder_opener"):
                self.folder_opener = TaskFolderOpener()
                self.root.bind("<Destroy>", lambda event: self.folder_opener.close() if event.widget is self.root else None, add="+")
            process = self.folder_opener.open(self.store, task_id)
            def check_launch():
                if process.poll() not in (None, 0):
                    messagebox.showerror("Folder unavailable" if self.language == "en" else "无法打开文件夹", "The cloud desktop file manager could not open this registered task folder." if self.language == "en" else "云桌面文件管理器未能打开该任务的成果文件夹。", parent=self.root)
            self.root.after(400, check_launch)
        except (OSError, ValueError, sqlite3.Error):
            messagebox.showerror("Folder unavailable" if self.language == "en" else "无法打开文件夹", "Only an unchanged registered task output folder can be opened on the cloud desktop." if self.language == "en" else "只能在云桌面打开经过核验、未被替换的任务成果文件夹。", parent=self.root)

    def render_output_bar(self, parent, task_id, detail=False):
        summary = task_output_summary(self.snapshot, task_id)
        en = self.language == "en"
        if not detail and not summary.get("count") and getattr(parent, "detail_link", None) is not None:
            parent.detail_link.configure(text="Open details › · No outputs" if en else "查看详情 › · 暂无成果")
            return parent
        box = self.tk.Frame(parent, bg=parent.cget("bg"))
        box.pack(fill="x", pady=(4, 3))
        if detail and not summary.get("count"):
            self.label(box, "No registered outputs" if en else "尚无已登记成果", 12, self.muted, raw=True).pack(side="left", padx=(0, 12))
            self.output_button(box, "View files" if en else "查看文件", lambda key=task_id:self.open_task_files(key), task_id).pack(side="left")
            return box
        self.label(box, output_summary_text(summary, self.language) if detail else (("Outputs · " if en else "成果 · ")+str(summary.get("count",0))), 13, self.accent, True, raw=True, wrap=780).pack(anchor="w", fill="x")
        if summary.get("main"):
            main = self.label(box, output_main_text(summary, self.language), 12, self.muted, raw=True, wrap=780)
            main.pack(anchor="w", fill="x", pady=(2, 3))
            box.bind("<Configure>", lambda event: main.configure(wraplength=max(120,event.width-10)), add="+")
        actions = self.tk.Frame(box, bg=box.cget("bg"))
        actions.pack(anchor="w", pady=(3,0))
        if summary.get("count") or detail:
            self.output_button(actions, "View files" if en else "查看文件", lambda key=task_id:self.open_task_files(key), task_id).pack(side="left", padx=(0,6))
        if detail and summary.get("count"):
            self.output_button(actions, "Open output folder" if en else "打开成果文件夹", lambda key=task_id:self.open_task_outputs(key), task_id, "folder").pack(side="left")
        if detail:
            self.label(box, "Registered files only · archiving does not imply delivery or acceptance" if en else "仅显示已登记文件 · 归档不等于发送或验收", 11, self.muted, raw=True, wrap=780).pack(anchor="w", pady=(3,0))
        return box

    def open_task(self, task_id, advice=False):
        if getattr(self,"selected_task",None) != task_id:self.detail_meta=False
        self.show_attention_advice = advice
        self.page, self.selected_task, self.detail_scroll = "conversations", task_id, 0.0
        self.render_page()

    def surface_layers(self, canvas, width, height, fill=None, border="#e7ece5", radius=19):
        fill = fill or self.panel
        self.round_shape(canvas, 2, 6, max(1, width-4), max(1, height-7), "#e4e9e2", radius)
        self.round_shape(canvas, 1, 3, max(1, width-2), max(1, height-7), "#edf0e9", radius)
        self.round_shape(canvas, 0, 0, width, max(1, height-7), border, radius)
        self.round_shape(canvas, 1, 1, max(1, width-2), max(1, height-9), fill, radius-1)

    def cut_text(self, text, width, pixels=15, bold=False):
        import tkinter.font as font
        face = font.Font(root=self.root, family=self.font, size=-pixels, weight="bold" if bold else "normal")
        original = str(text).replace("\n", " ")
        value = original
        while value and face.measure(value) > width:
            value = value[:-2]
        return value + "…" if value != original else value

    def pill(self, canvas, x, y, text, color="#258560", background="#e5f5eb"):
        import tkinter.font as font
        width = font.Font(root=self.root, family=self.font, size=-13).measure(text) + 26
        self.round_shape(canvas, x, y, width, 27, background, 13)
        canvas.create_text(x+width/2, y+13, text=text, fill=color, font=(self.font, -13))
        return width

    def make_scrollbar(self, parent, target):
        bar = self.tk.Canvas(parent, width=18, bg=self.bg, bd=0, highlightthickness=0, takefocus=1)
        state = {"first": 0.0, "last": 1.0, "hover": False, "drag": None}
        def draw(event=None):
            bar.delete("all")
            first, last = state["first"], state["last"]
            if last-first >= .999:
                return
            top, bottom = scroll_thumb(first, last, bar.winfo_height())
            active = state["hover"] or state["drag"] is not None or self.root.focus_get() == bar
            width = 7 if active else 5
            x = (18-width)/2
            self.round_shape(bar, x, top, width, max(width, bottom-top), "#a8c0ae" if active else "#d6e2d5", width/2)
        def update(first, last):
            state["first"], state["last"] = float(first), float(last)
            draw()
            if callable(getattr(target,"on_scroll",None)):
                target.on_scroll(first,last)
        def hover(inside):
            state["hover"] = inside
            draw()
        def press(event):
            self.cancel_viewport_restore(target)
            bar.focus_set()
            top, bottom = scroll_thumb(state["first"], state["last"], bar.winfo_height())
            if state["last"]-state["first"] >= .999:
                return "break"
            if top <= event.y <= bottom:
                state["drag"] = event.y-top
                self.scroll_dragging = True
            else:
                target.yview_scroll(-1 if event.y < top else 1, "pages")
            draw()
            return "break"
        def drag(event):
            if state["drag"] is not None:
                fraction = scroll_drag_fraction(event.y, state["drag"], state["first"], state["last"], bar.winfo_height())
                target.yview_moveto(fraction)
            return "break"
        def release(event):
            state["drag"] = None
            self.scroll_dragging = False
            draw()
            return "break"
        def key(event):
            self.cancel_viewport_restore(target)
            keys = {"Up": (-1, "units"), "Down": (1, "units"), "Prior": (-1, "pages"), "Next": (1, "pages")}
            if event.keysym in keys:
                target.yview_scroll(*keys[event.keysym])
            elif event.keysym == "Home":
                target.yview_moveto(0)
            elif event.keysym == "End":
                target.yview_moveto(1)
            return "break"
        bar.bind("<Configure>", draw)
        bar.bind("<Enter>", lambda event: hover(True))
        bar.bind("<Leave>", lambda event: hover(False))
        bar.bind("<FocusIn>", draw)
        bar.bind("<FocusOut>", draw)
        bar.bind("<Button-1>", press)
        bar.bind("<B1-Motion>", drag)
        bar.bind("<ButtonRelease-1>", release)
        for name in ("Up", "Down", "Prior", "Next", "Home", "End"):
            bar.bind(f"<{name}>", key)
            target.bind(f"<{name}>", key)
        target.configure(yscrollcommand=update)
        return bar

    def detail_paragraph(self, parent, source):
        text = self.tk.Text(parent, wrap="char", relief="flat", bd=0, bg=parent.cget("bg") if parent is not None else self.panel, fg=self.fg, font=(self.font, -16), width=1, height=1, padx=0, pady=0, highlightthickness=0, spacing1=0, spacing2=0, spacing3=0, takefocus=1)
        text.insert("1.0", source)
        text.configure(state="disabled")
        text.pack(fill="x", anchor="w")
        def route_scroll(event):
            self.mousewheel(event)
            return "break"
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            text.bind(sequence, route_scroll)
        def key_scroll(event):
            if hasattr(self, "page_scroll") and self.page_scroll.winfo_exists():
                self.cancel_viewport_restore()
                if event.keysym == "Home":
                    self.page_scroll.yview_moveto(0)
                elif event.keysym == "End":
                    self.page_scroll.yview_moveto(1)
                else:
                    self.page_scroll.yview_scroll(-1 if event.keysym == "Prior" else 1, "pages")
            return "break"
        for sequence in ("Prior", "Next", "Home", "End"):
            text.bind(f"<{sequence}>", key_scroll)
        return text

    def cancel_viewport_restore(self, target=None):
        target = target or getattr(self, "page_scroll", None)
        if target is not None and hasattr(target, "cancel_restore"):
            target.cancel_restore()

    def scroll_key(self, event):
        if event.widget.winfo_class() in ("Entry", "TEntry", "TCombobox"):
            return
        target = getattr(self, "page_scroll", None)
        if target is not None and target.winfo_exists():
            self.cancel_viewport_restore(target)
            if event.keysym == "End":
                target.yview_moveto(1.0)
            elif event.keysym == "Home":
                target.yview_moveto(0.0)
            else:
                target.yview_scroll(-1 if event.keysym == "Prior" else 1, "pages")
        return "break"

    def view_signature(self):
        now = time.time()
        fresh = tuple(sorted((agent['id'],agent.get('status')) for agent in self.snapshot.get('agents',[]) if agent_observation(agent,self.snapshot,now)['recent']))
        fields={'software':('software',),'schedules':('schedules',),'rules':('rules',),'about':('about',),'settings':('exit_region','backup')}.get(self.page)
        visible={key:self.snapshot.get(key) for key in fields} if fields else self.snapshot
        return (self.page,self.selected_task,self.language,self.workspace_filter,self.search_query.get(),fresh if fields is None else (),display_signature(visible))

    def viewport_key(self):
        return (self.page,self.selected_task)

    def scroll_area(self):
        holder = self.tk.Frame(self.content, bg=self.bg)
        holder.pack(fill="both", expand=True)
        canvas = self.tk.Canvas(holder, bg=self.bg, bd=0, highlightthickness=0)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar = self.make_scrollbar(holder, canvas)
        scrollbar.pack(side="right", fill="y")
        body = self.tk.Frame(canvas, bg=self.bg)
        item = canvas.create_window(0, 0, anchor="nw", window=body)
        self.page_scroll = canvas
        key = self.viewport_key()
        position = self.scroll_positions.get(key, 0)
        restore = {"pending": True, "job": None}
        def viewport_ready():
            return canvas.winfo_width() > 1 and canvas.winfo_height() > 1 and canvas.winfo_ismapped()
        def cancel():
            canvas.follow_tail=False
            restore["pending"] = False
            if restore["job"] is not None:
                self.root.after_cancel(restore["job"])
                restore["job"] = None
        canvas.cancel_restore = cancel
        def sync_extent(fraction=0):
            # Canvas bounds remain current even when an offscreen frame keeps
            # an older mapped height. Use one geometry for region and scrolling.
            bounds = canvas.bbox(item)
            height, fraction = scroll_extent(bounds[3] if bounds else 1, canvas.winfo_height(), fraction)
            canvas.configure(scrollregion=(0, 0, max(1, canvas.winfo_width()), height))
            return height, fraction
        def follow_end():
            if self.page_scroll is not canvas or not canvas.winfo_exists():return
            if not viewport_ready():
                cancel()
                return
            _, fraction = sync_extent(1)
            canvas.yview_moveto(fraction)
        canvas.follow_end=follow_end
        def layout_diagnostic():
            if self.page_scroll is not canvas or not canvas.winfo_exists():return
            print('Native layout: '+json.dumps({'viewport':[canvas.winfo_width(),canvas.winfo_height()],
                'source_sha256':LOADED_SOURCE_SHA256,'layout_revision':'mapped-viewport-top-v1',
                'canvas_mapped':bool(canvas.winfo_ismapped()),
                'content_actual':[self.content.winfo_width(),self.content.winfo_height()],
                'content_children':[[w.winfo_x(),w.winfo_y(),w.winfo_width(),w.winfo_height(),bool(w.winfo_ismapped())] for w in self.content.winfo_children()[:6]],
                'body_children':[[w.winfo_x(),w.winfo_y(),w.winfo_width(),w.winfo_height(),bool(w.winfo_ismapped())] for w in body.winfo_children()[:6]],
                'body_requested':body.winfo_reqheight(),'body_actual':body.winfo_height(),
                'window_bbox':canvas.bbox(item),'scrollregion':str(canvas.cget('scrollregion')),
                'yview':canvas.yview(),'origin_y':canvas.canvasy(0),
                'mounted_records':len(getattr(self,'conversation_anchors',{}))}),file=sys.stderr)
        canvas.layout_diagnostic=layout_diagnostic
        def finish_restore():
            restore["job"] = None
            if restore["pending"] and self.page_scroll is canvas and canvas.winfo_exists():
                if not viewport_ready():
                    cancel()
                    return
                restore["pending"] = False
                height, fraction = sync_extent(position)
                anchor=getattr(self,'pending_conversation_anchor',None)
                if anchor:
                    widget=getattr(self,'conversation_anchors',{}).get(anchor[0])
                    if widget is not None and widget.winfo_exists():
                        _, fraction = scroll_extent(height, canvas.winfo_height(), (widget.winfo_y()-anchor[1])/height)
                    self.pending_conversation_anchor=None
                if getattr(canvas,'follow_tail',False):
                    _, fraction = scroll_extent(height, canvas.winfo_height(), 1)
                canvas.yview_moveto(fraction)
        def layout(event=None):
            if not canvas.winfo_exists():
                return
            if not viewport_ready():
                if restore['job'] is not None:cancel()
                return
            height, fraction = sync_extent(canvas.yview()[0])
            if height <= canvas.winfo_height():
                canvas.yview_moveto(0)
            elif not restore['pending'] and getattr(canvas,'follow_tail',False):
                _, fraction = scroll_extent(height, canvas.winfo_height(), 1)
                canvas.yview_moveto(fraction)
            if restore["pending"]:
                if restore["job"] is not None:
                    self.root.after_cancel(restore["job"])
                restore["job"] = self.root.after(60, finish_restore)
        body.bind("<Configure>", layout)
        def resize(event):
            canvas.itemconfigure(item, width=event.width)
            layout()
        canvas.bind("<Configure>", resize)
        layout()
        return body

    def mousewheel(self, event):
        if hasattr(self, "page_scroll") and self.page_scroll.winfo_exists():
            self.cancel_viewport_restore()
            units = -1 if getattr(event, "num", 0) == 4 else 1 if getattr(event, "num", 0) == 5 else (-1 if event.delta > 0 else 1)
            self.page_scroll.yview_scroll(units * 2, "units")

    def workspace_toolbar(self):
        bar = self.tk.Frame(self.content, bg=self.bg)
        bar.pack(fill="x", pady=(0, 16))
        filters = self.tk.Frame(bar, bg=self.bg)
        filters.grid(row=0, column=0, sticky="w")
        bar.grid_columnconfigure(0, weight=1)
        self.filter_buttons = {}
        for status, label in (("all", self.t("全部")), ("unfinished", "Unfinished" if self.language == "en" else "未完成"), ("succeeded", "Completed" if self.language == "en" else "已完成")):
            count = len(workspace_rows(self.rows, status))
            button = self.filter_chip(filters, f"{label} {count}", lambda value=status: self.set_workspace_filter(value), self.workspace_filter == status)
            button.pack(side="left", padx=(0, 6))
            self.filter_buttons[status] = button
        if self.page == 'conversations':
            mode=getattr(self,'collaboration_mode_filter','all')
            labels={'all':('全部','All'),'single':('单人','Single'),'team':('团队','Team'),'project':('项目','Project')}
            caption=('Type · ' if self.language=='en' else '类型 · ')+labels.get(mode,labels['all'])[self.language=='en']+' ⌄'
            self.type_filter_button=self.filter_chip(filters,caption,lambda:self.open_filter_menu('type'),mode!='all')
            self.type_filter_button.pack(side='left',padx=(0,6))
            self.type_filter_button.bind('<Down>',lambda event:self.open_filter_menu('type'))
        exact = self.workspace_filter not in self.filter_buttons
        more = (self.t(STATUS.get(self.workspace_filter, "未知")) + f" {len(workspace_rows(self.rows, self.workspace_filter))}" if exact else ("More filters" if self.language == "en" else "更多筛选")) + " ⌄"
        self.more_filter_button = self.filter_chip(filters, more, self.open_filter_menu, exact)
        self.more_filter_button.pack(side="left")
        self.more_filter_button.bind("<Down>", lambda event: self.open_filter_menu())
        def refresh_counts():
            for status,label in (('all',self.t('全部')),('unfinished','Unfinished' if self.language=='en' else '未完成'),('succeeded','Completed' if self.language=='en' else '已完成')):
                self.patch_caption(self.filter_buttons[status],label+' '+str(len(workspace_rows(self.rows,status))))
        self.live_updates.append(refresh_counts)
        if self.page != "conversations":
            return
        search = self.tk.Canvas(bar, width=170, height=34, bg=self.bg, bd=0, highlightthickness=0)
        search.grid(row=0, column=1, sticky="e", padx=(10, 0))
        def toolbar_layout(event):
            narrow = event.width < max(620, filters.winfo_reqwidth()+190)
            search.grid_configure(row=1 if narrow else 0, column=0 if narrow else 1, sticky="e", pady=(8, 0) if narrow else 0)
        bar.bind("<Configure>", toolbar_layout)
        self.round_shape(search, 0, 0, 170, 34, "#e4eae2", 14)
        self.round_shape(search, 1, 1, 168, 32, "#ffffff", 13)
        search.create_text(16, 17, text="⌕", fill=self.muted, font=(self.font, -23))
        self.search_entry = self.tk.Entry(search, textvariable=self.search_query, bd=0, relief="flat", bg="white", fg=self.fg, insertbackground=self.accent, font=(self.font, -14), width=13)
        search.create_window(30, 17, window=self.search_entry, anchor="w", width=129)
        self.search_entry.bind("<Return>", lambda event: self.render_page())
        search.bind("<Button-1>", lambda event: self.search_entry.focus_set())

    def airy_task_card(self, parent, row, index):
        # One bounded presentation shared by overview and task list.
        card = self.tk.Canvas(parent, height=244, bg=self.bg, bd=0, highlightthickness=0, cursor="hand2", takefocus=1)
        if hasattr(parent, "card_items"):
            parent.card_items.append(card)
            parent.reflow_cards()
        else:
            card.grid(row=index//2, column=index%2, sticky="nsew", padx=(0 if index%2 == 0 else 13, 0), pady=(0, 12))
            parent.grid_columnconfigure(index%2, weight=1, uniform="task_cards")
        output_button = self.output_button(card, "View files" if self.language == "en" else "查看文件", lambda key=row["id"]:self.open_task_files(key), row["id"])
        painted = {'signature': None}
        def model(value):
            title,summary,status=self.activity_row_summary(value)
            return {'title':title,'summary':summary,'status':status,'lifecycle':value['status'],
                    'count':task_output_summary(self.snapshot,value['id']).get('count',0),
                    'people':activity_participants(self.snapshot,value['id'])}
        def draw(event):
            import tkinter.font as font
            data=model(row)
            with RetainedCanvas(card) as paint:
                painted['signature'] = display_signature(data)
                width = event.width
                paint.delete("all")
                active = data['lifecycle'] == "running"
                self.surface_layers(paint, width, 244, "#f3fcf6" if active else self.panel, "#cfe9d7" if active else "#e7ece5")
                people=data['people'];group_width=28+(min(3,len(people))-1)*24+(32 if len(people)>3 else 0) if people else 0
                status_font=font.Font(root=self.root,family=self.font,size=-13)
                pill_text=bounded_card_lines(data['status'],max(20,width-40-group_width-(12 if people else 0)-26),status_font.measure,1)
                pill_width=status_font.measure(pill_text)+26
                pill_colors={"running":("#24845b","#e5f5eb"),"succeeded":("#24845b","#e5f5eb"),"failed":("#b4554a","#fbe8e4")}
                pill_fg,pill_bg=pill_colors.get(data['lifecycle'],("#8c712e","#fff3d9"))
                self.pill(paint,20+group_width+12 if people else 20,85,pill_text,pill_fg,pill_bg)
                self.draw_participant_group(paint,people,20+group_width,84,lambda key=row['id']:self.open_task(key))
                title_font=font.Font(root=self.root,family=self.font,size=-18,weight='bold')
                body_font=font.Font(root=self.root,family=self.font,size=-14)
                title=bounded_card_lines(data['title'],max(20,width-40),title_font.measure,2)
                summary=bounded_card_lines(data['summary'],max(20,width-40),body_font.measure,2)
                paint.create_text(20,22,text=title,anchor='nw',fill=self.fg,font=(self.font,-18,'bold'))
                paint.create_text(20,133,text=summary,anchor='nw',fill=self.muted,font=(self.font,-14))
                paint.create_line(20,183,width-20,183,fill='#e4eee5' if active else '#edf0ea')
                count=("Files " if self.language=='en' else "成果 ")+str(data['count'])
                paint.create_text(20,208,text=count,anchor='w',fill=self.accent,font=(self.font,-12,'bold'))
                if output_button is not None:
                    paint.create_window(width-20,208,window=output_button,anchor='e')
        card.bind("<Configure>", draw)
        def update_live():
            latest_row = next((item for item in self.rows if item["id"] == row["id"]), None)
            if latest_row and card.winfo_exists() and display_signature(model(latest_row)) != painted['signature']:
                row.update(latest_row)
                from types import SimpleNamespace
                draw(SimpleNamespace(width=card.winfo_width()))
        card.update_live=update_live
        self.live_updates.append(update_live)
        card.bind("<Button-1>", lambda event: self.open_task(row["id"]))
        card.bind("<Return>", lambda event: self.open_task(row["id"]))
        card.bind("<space>", lambda event: self.open_task(row["id"]))
        card.bind("<FocusIn>",lambda event:card.configure(highlightthickness=2,highlightcolor=self.accent))
        card.bind("<FocusOut>",lambda event:card.configure(highlightthickness=0))
        return card

    def resource_card(self, parent):
        card = self.tk.Canvas(parent, height=181, bg=self.bg, bd=0, highlightthickness=0)
        nodes = []
        painted = {'values': None}
        def values():
            metrics = self.metric_values
            memory = percent(metrics.get('cgroup_memory_current'), metrics.get('memory_quota'))
            if memory is None and metrics.get('memory_total') and metrics.get('memory_available') is not None:
                memory = percent(metrics['memory_total']-metrics['memory_available'], metrics['memory_total'])
            return [("CPU",metrics.get('cpu_percent'),'#54bd84'),(self.t('内存'),memory,'#6b9de8'),(self.t('磁盘'),percent(metrics.get('disk_used'),metrics.get('disk_total')),'#e7a64b')]
        def arc_options(value):
            return {'extent':-max(.01,min(99.99,value))*3.6 if value is not None else 0,'state':'normal' if value is not None else 'hidden'}
        def draw(event):
            width=event.width;current=values();painted['values']=current;nodes.clear()
            card.delete('all')
            self.surface_layers(card,width,181)
            card.create_text(19,26,text=self.t('资源使用情况'),anchor='w',fill=self.fg,font=(self.font,-17,'bold'))
            for index,(title,value,color) in enumerate(current):
                center,y,radius=width*(index+.5)/3,88,31
                card.create_oval(center-radius,y-radius,center+radius,y+radius,outline='#edf0ec',width=6)
                arc=card.create_arc(center-radius,y-radius,center+radius,y+radius,start=90,style='arc',outline=color,width=6,**arc_options(value))
                label=card.create_text(center,y,text=f'{value:.0f}%' if value is not None else '—',fill=self.fg,font=(self.font,-18,'bold'))
                nodes.append((arc,label))
                card.create_text(center,135,text=title,fill=self.muted,font=(self.font,-13))
            card.create_text(19,159,text=self.cut_text(self.t('可见指标；内存优先使用容器配额'),width-38,11),anchor='w',fill=self.muted,font=(self.font,-11))
        def update_live():
            current=values()
            if not card.winfo_exists() or not nodes or current==painted['values']:return
            for index,(_,value,_) in enumerate(current):
                if painted['values'][index][1]==value:continue
                arc,label=nodes[index]
                card.itemconfigure(arc,**arc_options(value))
                card.itemconfigure(label,text=f'{value:.0f}%' if value is not None else '—')
            painted['values']=current
        card.bind('<Configure>',draw)
        self.live_updates.append(update_live)
        return card

    def schedules_summary_card(self, parent):
        card = self.tk.Canvas(parent, height=181, bg=self.bg, bd=0, highlightthickness=0, cursor="hand2", takefocus=1)
        records = self.snapshot.get("schedules", [])
        def draw(event):
            with RetainedCanvas(card) as paint:
                width = event.width
                paint.delete("all")
                self.surface_layers(paint, width, 181)
                paint.create_text(19, 26, text=self.t("自动化"), anchor="w", fill=self.fg, font=(self.font, -17, "bold"))
                paint.create_text(width-22, 26, text=self.t("全部"), anchor="e", fill=self.accent, font=(self.font, -13))
                for index, record in enumerate(records[:2]):
                    y = 68 + index*54
                    paint.create_oval(20, y-12, 46, y+14, fill="#e2f7e9", outline="")
                    paint.create_oval(27, y-5, 39, y+7, outline=self.accent, width=2)
                    paint.create_line(33, y-2, 33, y+2, 36, y+2, fill=self.accent)
                    paint.create_text(57, y-3, text=self.cut_text(record["name"], width-95, 15, True), anchor="w", fill=self.fg, font=(self.font, -15, "bold"))
                    state, timing = schedule_summary(record, self.language, self.timezone)
                    paint.create_text(57, y+19, text=self.cut_text(state+" · "+timing, width-80, 12), anchor="w", fill=self.muted, font=(self.font, -12))
                if not records:
                    paint.create_text(20, 76, text=self.t("尚未登记自动化"), anchor="w", fill=self.muted, font=(self.font, -15))
                boundary = "Recorded observations · not live scheduling" if self.language == "en" else "已记录观察 · 非实时调度状态"
                paint.create_text(20, 157, text=boundary, anchor="w", fill=self.muted, font=(self.font, -11))
        card.bind("<Configure>", draw)
        card.bind("<Button-1>", lambda event: self.navigate("schedules"))
        card.bind("<Return>", lambda event: self.navigate("schedules"))
        def update_live():
            nonlocal records
            updated=self.snapshot.get('schedules',[])
            if display_signature(updated)==display_signature(records) or not card.winfo_exists():return
            records=updated
            from types import SimpleNamespace
            draw(SimpleNamespace(width=card.winfo_width()))
        self.live_updates.append(update_live)
        return card

    def render_overview(self):
        self.workspace_toolbar()
        area=self.scroll_area();grid=self.card_grid(area,minimum=370,maximum=2)
        cards={}
        empty=self.label(area,'该状态暂无任务',18,self.muted)
        more=self.label(area,'',13,self.accent);more.bind('<Button-1>',lambda event:self.navigate('conversations'))
        bottom=self.tk.Frame(area,bg=self.bg);bottom.pack(fill='x',pady=(3,0))
        bottom.grid_columnconfigure(0,weight=1,uniform='summary');bottom.grid_columnconfigure(1,weight=1,uniform='summary')
        self.resource_card(bottom).grid(row=0,column=0,sticky='nsew')
        self.schedules_summary_card(bottom).grid(row=0,column=1,sticky='nsew',padx=(13,0))
        def reconcile():
            filtered=workspace_rows(self.rows,self.workspace_filter,self.search_query.get());wanted=[row['id'] for row in filtered[:4]]
            for key in list(cards):
                if key not in wanted:
                    card=cards.pop(key)
                    if getattr(card,'update_live',None) in self.live_updates:self.live_updates.remove(card.update_live)
                    card.destroy()
            for index,row in enumerate(filtered[:4]):
                if row['id'] not in cards:cards[row['id']]=self.airy_task_card(grid,row,index)
            ordered=[cards[key] for key in wanted]
            if grid.card_items!=ordered:grid.card_items=ordered;grid.reflow_cards()
            if not filtered:empty.pack(anchor='w',pady=20,before=bottom)
            else:empty.pack_forget()
            if len(filtered)>4:
                more.configure(text=self.t('另有 {count} 个任务，可在任务页查看',count=len(filtered)-4));more.pack(anchor='w',pady=(0,10),before=bottom)
            else:more.pack_forget()
        refresh_backup = self.backup_card(area, compact=True)
        self.live_updates.append(refresh_backup)
        reconcile();self.background_refresh=reconcile


    def set_detail_tab(self, tab):
        self.detail_tab = tab
        self.render_page()

    def toggle_detail_meta(self):
        self.detail_meta = not self.detail_meta
        self.render_page()

    def render_progress_detail(self, parent, task_id, progress=None):
        progress = progress or task_progress(self.snapshot, task_id)
        if not progress["current_step"]:
            return
        en = self.language == "en"
        surface, box = self.card(parent, 170)
        surface.pack(fill="x", pady=(0, 14))
        active = progress["active_participants"]
        status = ("Task-level update · run attribution not recorded" if en else "任务级近况 · 未登记所属运行") if progress.get("scope") == "task" else (("● Recently observed working" if en else "● 最近观察到正在执行") if active else ("Latest recorded step · execution unconfirmed" if en else "最近记录步骤 · 执行状态待确认"))
        self.label(box, status, 13, self.accent if active else self.muted, raw=True).pack(anchor="w")
        if progress['assigned_participants']:
            names = run_participant_names(self.snapshot, progress['current_run_id'], self.language)
            self.label(box, ("Assigned: " if en else "已分派：") + names + (" · Run " if en else " · 运行 ") + progress['current_run_id'], 12, self.muted, raw=True, wrap=800).pack(anchor="w", fill="x", pady=(4, 0))
        step = progress["current_step"].split("\n", 1)[0]
        self.label(box, step, 17, self.fg, True, raw=True, wrap=800).pack(anchor="w", fill="x", pady=(7, 5))
        if len(progress.get("unpaused_runs", [])) > 1:
            self.label(box, ("Unfinished runs: " if en else "未完成运行：")+str(len(progress["unpaused_runs"])), 13, self.muted, raw=True).pack(anchor="w", pady=(4,0))
        if progress["counts"]:
            count = progress["counts"]
            self.label(box, f"{count['completed']:g} / {count['total']:g} {count['unit']}" + (" · measured" if en else " · 实测记录"), 16, self.accent, raw=True).pack(anchor="w")
        latest = progress.get("latest") or {}
        if latest.get("next_step"):
            self.label(box, ("Next: " if en else "下一步：")+latest["next_step"], 14, self.muted, raw=True, wrap=800).pack(anchor="w", pady=(4, 0))
        if progress["updated_at"] is not None:
            self.label(box, ("Meaningful update: " if en else "进展记录：")+self.stamp(progress["updated_at"]), 12, self.muted, raw=True).pack(anchor="w", pady=(5, 0))
        expanded = task_id in getattr(self, "expanded_progress", set())
        self.filter_chip(box, ("Hide steps ⌃" if en else "收起步骤 ⌃") if expanded else ("Recent steps ⌄" if en else "最近步骤 ⌄"), lambda: self.toggle_registry_detail("progress", task_id)).pack(anchor="w", pady=(7, 0))
        if expanded:
            if len(progress.get("open_runs", [])) > 1:
                for run in progress["open_runs"]:
                    caption = self.t(STATUS.get(run["status"], run["status"]))+" · "+(run.get("note") or run["id"])
                    caption += " · " + ("Run " if en else "运行 ") + run["id"] + " · " + (run_participant_names(self.snapshot, run["id"], self.language) or ("Unassigned" if en else "未分配"))
                    self.label(box, caption, 13, self.muted, raw=True, wrap=800).pack(anchor="w", fill="x", pady=(5,0))
            entries = progress["steps"] or progress["milestones"]
            for entry in entries:
                message = entry.get("current_step") or entry.get("message", "")
                if entry.get("result"):
                    message += "\n"+entry["result"]
                self.label(box, self.stamp(entry["created"])+"\n"+message, 14, self.muted, raw=True, wrap=800).pack(anchor="w", fill="x", pady=(8, 0))
        def wrap(event):
            for child in box.winfo_children():
                if isinstance(child, self.tk.Label):
                    child.configure(wraplength=max(100,event.width))
        box.bind("<Configure>", wrap, add="+")
        self.fit_card(surface, box)

    def render_conversation(self):
        row = next((row for row in self.rows if row["id"] == self.selected_task), None)
        if not row:
            self.selected_task = None
            self.render_page()
            return
        en = self.language == "en"
        task = next((task for task in self.snapshot.get('tasks', []) if task['id'] == self.selected_task), {})
        header = self.tk.Frame(self.content, bg=self.bg)
        header.pack(fill="x", pady=(3, 5))
        titleline = self.tk.Frame(header, bg=self.bg)
        titleline.pack(fill="x")
        self.filter_chip(titleline, "←", self.go_back).pack(side="left", padx=(0, 8))
        title = self.label(titleline, row["values"][0], 20, bold=True, raw=True)
        title.pack(side="left", fill="x", expand=True)
        self.detail_title_label=title
        files = [item for item in self.snapshot.get("artifacts", []) if item["task_id"] == self.selected_task]
        self.filter_chip(titleline, "More ⌃" if en and getattr(self,'detail_meta',False) else "更多 ⌃" if getattr(self,'detail_meta',False) else "More ⌄" if en else "更多 ⌄", self.toggle_detail_meta).pack(side="right", padx=(6,0))
        self.output_button(titleline, ("← Conversation" if en else "← 会话") if getattr(self,"detail_tab","timeline")=="files" else ("Files" if en else "成果")+f" · {task_output_summary(self.snapshot,self.selected_task).get('count',0)}", lambda: self.set_detail_tab('timeline' if getattr(self,'detail_tab','timeline')=='files' else 'files'), self.selected_task).pack(side="right", padx=(6,0))
        participants = collaboration_participants(self.snapshot,self.selected_task)
        if True:
            group = self.tk.Canvas(titleline, width=min(3,len(participants))*24+12+(30 if len(participants)>3 else 0), height=34, bg=self.bg, bd=0, highlightthickness=1, highlightbackground=self.bg, highlightcolor=self.accent, takefocus=1)
            group.pack(side='right',padx=(7,0));self.detail_avatar_group=group
            def show_participants(event=None):
                self.detail_meta=True;self.render_page();return 'break'
            group.bind('<Return>',show_participants);group.bind('<space>',show_participants)
            group.bind('<Configure>',lambda event:self.draw_participant_group(group,participants,event.width,3,show_participants))
        self.detail_status_label=self.label(titleline,row['values'][2],12,self.accent,raw=True)
        self.detail_status_label.pack(side='right',padx=6)
        def fit_title(event):
            title.configure(text=self.cut_text(row['values'][0],max(40,event.width),20,True))
        title.bind('<Configure>',fit_title)
        secondary = self.tk.Frame(header, bg=self.bg)
        if getattr(self,'detail_meta',False):secondary.pack(fill='x',pady=(5,0))
        self.detail_header_secondary = secondary
        self.conversation_header_compact = False
        self.label(secondary,collaboration_mode(task,self.language),12,self.muted,raw=True).pack(side='left')
        if getattr(self,'detail_meta',False):self.filter_chip(secondary,'Conversation' if en else '协作会话',lambda:self.set_detail_tab('timeline'),getattr(self,'detail_tab','timeline')=='timeline').pack(side='right')
        progress = task_progress(self.snapshot, self.selected_task)
        agent = progress["lead"]["agent"]
        closeout = (row.get("run") or {}).get("closeout")
        def header_refresh():
            current=next((value for value in self.rows if value['id']==self.selected_task),None)
            if current:
                if current['values'][0]!=row['values'][0]:title.configure(text=current['values'][0])
                if current['values'][2]!=row['values'][2]:self.detail_status_label.configure(text=current['values'][2])
                row.update(current)
            people=collaboration_participants(self.snapshot,self.selected_task)
            if display_signature(people)!=display_signature(participants):
                participants[:]=people;width=min(3,len(people))*24+12+(30 if len(people)>3 else 0)
                group.configure(width=width);group.delete('participant-group');self.draw_participant_group(group,people,width,3,show_participants)
            button=self.output_buttons.get((self.selected_task,'files'))
            if button is not None:
                label=('← Conversation' if en else '← 会话') if getattr(self,'detail_tab','timeline')=='files' else ('Files' if en else '成果')+' · '+str(task_output_summary(self.snapshot,self.selected_task).get('count',0))
                self.patch_caption(button,label)
        self.live_updates.append(header_refresh)
        area = self.scroll_area()
        if hasattr(self, "page_scroll"):
            self.page_scroll.on_scroll = self.update_conversation_header
        if getattr(self,'detail_meta',False):
            owner = profile_reference(agent,self.language) if agent else ('Unassigned' if en else '未分配')
            self.label(area,owner+' · '+participant_observation(agent,self.snapshot,self.language,timezone=self.timezone),12,self.muted,raw=True,wrap=800).pack(anchor='w',pady=(6,3))
            self.render_output_bar(area,self.selected_task,detail=True)
            self.render_task_participants(area,self.selected_task)
            self.render_progress_detail(area,self.selected_task,progress)
        lifecycle = row.get("run") or {}
        if getattr(self, "detail_tab", "timeline") == "files" and not getattr(self, "detail_meta", False):
            self.render_task_files(area, files)
            return
        if closeout and getattr(self, "detail_meta", False):
            self.label(area, "Final deliverables & verification" if en else "最终产出与验证", 16, self.fg, True, raw=True).pack(anchor="w", pady=(0, 6))
            state_note = ("Completion gate checked" if en else "已通过完成门槛") if closeout.get("completed_at") else ("Recorded; completion gate not yet checked" if en else "已登记；尚未通过完成门槛")
            self.label(area, state_note + " · " + verification_label(closeout["verification"], self.language), 12, self.muted, raw=True).pack(anchor="w")
            for field, zh, english in (("summary", "交付摘要", "Summary"), ("scope", "检查范围", "Scope"), ("evidence", "验证依据", "Evidence"), ("limits", "剩余限制 / 未测部分", "Limits / untested areas"), ("no_artifact_reason", "无文件产出的理由", "No-artifact reason")):
                if closeout.get(field):
                    self.label(area, (english if en else zh) + ": " + closeout[field], 12, self.muted, raw=True, wrap=800).pack(anchor="w", pady=(3, 2))
            for item in closeout.get("artifacts", []):
                artifact = next((file for file in self.snapshot.get("artifacts", []) if file["id"] == item["artifact_id"]), None)
                if artifact:
                    self.label(area, artifact["title"] + " · " + artifact_delivery_label(artifact, self.language), 12, self.muted, raw=True, wrap=800).pack(anchor="w", pady=3)
            self.filter_chip(area, "View files" if en else "查看文件", lambda: self.set_detail_tab("files")).pack(anchor="w", pady=(4, 12))
        elif lifecycle.get("status") == "succeeded" and getattr(self, "detail_meta", False):
            self.label(area, "Legacy completion; no evidence gate record" if en else "历史完成记录；未登记完成门槛依据", 12, self.muted, raw=True).pack(anchor="w", pady=(0, 8))
        if getattr(self, "detail_meta", False):
            for field, zh, english in (("lifecycle_reason", "状态原因", "Reason"), ("next_step", "下一步", "Next step"), ("lifecycle_evidence", "状态依据", "Evidence")):
                if lifecycle.get(field):
                    self.label(area, (english if en else zh) + ": " + lifecycle[field], 13, self.fg, raw=True, wrap=800).pack(anchor="w", pady=(0, 7))
            if lifecycle.get("lifecycle_reason"):
                self.label(area, "Recorded lifecycle only; does not control the executor" if en else "仅登记任务状态，不会控制执行者", 12, self.muted, raw=True, wrap=800).pack(anchor="w", pady=(0, 12))
        if getattr(self, "show_attention_advice", False) and lifecycle.get("status") in ("waiting_user", "awaiting_review", "paused"):
            task = next(item for item in self.snapshot["tasks"] if item["id"] == self.selected_task)
            self.label(area, "Copy into chat after filling in your decision; nothing has been sent" if en else "填写决定后可复制到聊天；此处没有发送任何消息", 12, self.muted, raw=True, wrap=800).pack(anchor="w", pady=(0, 6))
            draft = self.detail_paragraph(area, attention_draft(task, lifecycle, self.language))
            draft.configure(height=7)
            # Restore Text's own scrolling so a long copyable draft stays accessible.
            for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>", "<Prior>", "<Next>", "<Home>", "<End>"):
                draft.unbind(sequence)
            draft.focus_set()
            draft.bind("<Tab>", lambda event: (draft.tk_focusNext().focus_set(), "break")[-1])
            draft.bind("<Shift-Tab>", lambda event: (draft.tk_focusPrev().focus_set(), "break")[-1])
        if getattr(self, "detail_meta", False):
            binding = binding_summary(self.snapshot, self.selected_task, self.language, self.timezone)
            self.label(area, binding["title"] + " · " + " ".join(binding["lines"]), 12, self.muted, raw=True, wrap=800).pack(anchor="w", pady=(0, 10))
            if agent and agent_text(agent, "note", self.language):
                self.label(area, agent_text(agent, "note", self.language), 12, self.muted, raw=True, wrap=800).pack(anchor="w", pady=(0, 10))
            if binding["url"]:
                def open_session(url=binding["url"]):
                    import webbrowser
                    webbrowser.open(url)
                self.filter_chip(area, "Open original session" if en else "打开原会话", open_session).pack(anchor="w", pady=(0, 10))
        if getattr(self, "detail_tab", "timeline") == "files":
            self.render_task_files(area, files)
            return
        self.render_conversation_filters(area,task)
        stream=self.tk.Frame(area,bg=self.bg);stream.pack(fill='x')
        notice=self.label(area,'',12,self.muted,raw=True,wrap=800)
        paging=self.tk.Frame(area,bg=self.bg);paging.pack(fill='x',pady=(6,10))
        previous=self.button(paging,'Previous' if en else '上一页',lambda:self.change_conversation_filter(offset=max(0,getattr(self,'conversation_offset',0)-100)))
        previous.pack(side='left')
        page_label=self.label(paging,'',12,self.muted,raw=True);page_label.pack(side='left',padx=12)
        following=self.button(paging,'Next' if en else '下一页',lambda:self.change_conversation_filter(offset=getattr(self,'conversation_offset',0)+100))
        following.pack(side='left')
        new_items=self.button(self.content,'',lambda:apply_pending())
        mounted={};models={};pending={'data':None,'job':None};last_query={'signature':None}
        self.conversation_anchors=mounted
        def read_records():
            filters=getattr(self,'conversation_filters',{});offset=getattr(self,'conversation_offset',0)
            try:
                data=self.store.collaboration_timeline(self.selected_task,include_children=task.get('activity_kind')=='project',agent_id=filters.get('agent') or None,work_type=filters.get('role') or None,child_task_id=filters.get('task') or None,limit=100,offset=offset)
                rows=[{**r,'title':r.get('stage') or ('运行事件' if r['kind']=='event' else '记录'),'state':r.get('state'),'source_id':str(r['id'])} for r in data['rows']]
                data={**data,'rows':rows,'error':False}
            except (AttributeError,OSError,sqlite3.Error,ValueError):
                rows=collaboration_records(self.snapshot,self.selected_task,filters)
                data={'rows':rows,'total':len(rows),'offset':0,'limit':100,'has_more':False,'error':True}
            data['rows']=sorted(data['rows'],key=lambda r:(r['created'],r['kind'],r['source_id']))
            return data
        def apply(data,follow=False):
            wanted=[r.get('key') or r['kind']+':'+r['source_id'] for r in data['rows']]
            for key in list(mounted):
                if key not in wanted:mounted.pop(key).destroy();models.pop(key,None)
            previous_widget=None
            for record,key in zip(data['rows'],wanted):
                signature=display_signature(record)
                if key not in mounted or models.get(key)!=signature:
                    if key in mounted:mounted.pop(key).destroy()
                    mounted[key]=self.conversation_message(stream,record,task);models[key]=signature
                    options={'fill':'x','pady':(0,12)}
                    if previous_widget is not None:options['after']=previous_widget
                    elif stream.winfo_children():
                        other=next((w for w in stream.winfo_children() if w is not mounted[key]),None)
                        if other is not None:options['before']=other
                    mounted[key].pack(**options)
                previous_widget=mounted[key]
            if data['error']:
                notice.configure(text='Snapshot only; full history unavailable' if en else '仅快照窗口；完整记录读取失败');notice.pack(anchor='w',pady=6,before=paging)
            elif not wanted:
                notice.configure(text='No matching records' if en else '没有符合筛选的记录');notice.pack(anchor='w',pady=6,before=paging)
            else:notice.pack_forget()
            previous.configure(state='normal' if data['offset'] else 'disabled');following.configure(state='normal' if data['has_more'] else 'disabled')
            page_label.configure(text=f"{data['offset']+min(1,len(wanted))}–{data['offset']+len(wanted)} / {data['total']}")
            if data['total']>data['limit']:paging.pack(fill='x',pady=(6,10))
            else:paging.pack_forget()
            pending['data']=None;new_items.place_forget()
            if follow and hasattr(self,'page_scroll'):
                self.page_scroll.follow_tail=True
                canvas=self.page_scroll
                self.root.after_idle(lambda:canvas.follow_end() if self.page_scroll is canvas and canvas.winfo_exists() and hasattr(canvas,'follow_end') else None)
        def apply_pending():
            if pending['data'] is not None:apply(pending['data'],True)
        def background():
            current=next((item for item in self.rows if item['id']==self.selected_task),None)
            if current:
                if current['values'][0]!=row['values'][0]:title.configure(text=current['values'][0])
                if current['values'][2]!=row['values'][2]:self.detail_status_label.configure(text=current['values'][2])
                row.update(current)
            people=collaboration_participants(self.snapshot,self.selected_task)
            if display_signature(people)!=display_signature(participants):
                participants[:]=people;width=min(3,len(people))*24+12+(30 if len(people)>3 else 0)
                group.configure(width=width);group.delete('participant-group');self.draw_participant_group(group,people,width,3,show_participants)
            data=read_records();signature=display_signature(data)
            if signature==last_query['signature']:return
            last_query['signature']=signature
            at_bottom=not mounted or (hasattr(self,'page_scroll') and self.page_scroll.yview()[1]>=.98)
            if at_bottom:apply(data,True)
            else:
                pending['data']=data;count=sum((r.get('key') or r['kind']+':'+r['source_id']) not in mounted for r in data['rows'])
                new_items.configure(text=(f'{count} new records ↓' if en else f'{count} 条新记录 ↓') if count else ('Records updated ↓' if en else '记录已更新 ↓'))
                new_items.place(relx=1,rely=1,anchor='se',x=-26,y=-12)
        initial=read_records();last_query['signature']=display_signature(initial);apply(initial)
        if hasattr(self,'page_scroll'):
            self.page_scroll.follow_tail=False
            def scroll_update(first,last):
                self.update_conversation_header(first,last)
                if float(last)>=.98 and pending['data'] is not None and pending['job'] is None:
                    def follow_pending():pending['job']=None;apply_pending()
                    pending['job']=self.root.after_idle(follow_pending)
            self.page_scroll.on_scroll=scroll_update
        self.background_refresh=background
        if getattr(self,'layout_diagnostics',False) and hasattr(self.page_scroll,'layout_diagnostic'):
            canvas=self.page_scroll
            self.root.after(700,canvas.layout_diagnostic)


    def conversation_message(self,area,record,task):
        actor = collaboration_actor(record,self.snapshot,self.language)
        surface, inner = self.card(area, 150, fill=actor['color'])
        heading = self.tk.Frame(inner,bg=actor['color']);heading.pack(fill='x')
        portrait = self.tk.Canvas(heading,width=36,height=36,bg=actor['color'],highlightthickness=0,bd=0);portrait.pack(side='left',padx=(0,10))
        if actor['known']:
            draw_portrait(portrait,actor['agent'],0,0,36)
        else:
            portrait.create_oval(0,0,36,36,fill='#e5e8e4',outline='')
            portrait.create_oval(13,7,23,17,fill='#87948b',outline='')
            portrait.create_arc(8,17,28,37,start=0,extent=180,fill='#87948b',outline='')
        authorline = self.tk.Frame(heading,bg=actor['color']);authorline.pack(side='left',fill='x',expand=True)
        self.label(authorline,actor['label'],14,self.fg,True,raw=True).pack(anchor='w')
        if actor.get('short_id') or actor['role']:
            self.label(authorline,((actor.get('short_id')+' · ') if actor.get('short_id') else '')+actor['role'],11,self.muted,raw=True).pack(anchor='w')
        self.label(heading,self.stamp(record['created']),11,self.muted,raw=True).pack(side='right')
        title = self.t(record["title"]) if record["kind"] in ("event", "note") else stage_label(record["title"], self.language)
        if record.get("state"):
            title += "  ·  " + self.t(STATES.get(record["state"], record["state"]))
        if task.get('activity_kind')=='project':
            title += ' · '+next((t['name'] for t in self.snapshot.get('tasks',[]) if t['id']==record.get('task_id')),record.get('task_id',''))
        self.label(inner,title,12,self.muted,raw=True).pack(anchor='w',pady=(8,6))
        paragraph = self.detail_paragraph(inner, record["message"])
        pending = {"id": None}
        def fit_paragraph(event=None, paragraph=paragraph, frame=inner, card=surface, pending=pending):
            if pending["id"] is not None:
                return
            def measure():
                pending["id"] = None
                if not paragraph.winfo_exists():
                    return
                count = paragraph.count("1.0", "end-1c", "displaylines")
                lines = (count[0] if count else 0)+1
                if int(paragraph.cget("height")) != lines:
                    paragraph.configure(height=lines)
                def resize_card():
                    if frame.winfo_exists():
                        wanted = frame.winfo_reqheight()+39
                        if abs(int(card.cget("height"))-wanted) > 2:
                            card.configure(height=wanted)
                self.root.after_idle(resize_card)
            pending["id"] = self.root.after_idle(measure)
        paragraph.bind("<Configure>", fit_paragraph, add="+")
        return surface

    def update_conversation_header(self, first=None, last=None):
        secondary = getattr(self,'detail_header_secondary',None)
        if self.page != 'conversations' or not self.selected_task or secondary is None or not secondary.winfo_exists():
            return
        if not getattr(self,'detail_meta',False):return
        top = self.page_scroll.canvasy(0)
        compact = getattr(self,'conversation_header_compact',False)
        wanted = top > (8 if compact else 64)
        focused = self.root.focus_get()
        if wanted and focused is not None and (focused is secondary or str(focused).startswith(str(secondary)+'.')):
            return
        if wanted != compact:
            self.conversation_header_compact = wanted
            if wanted:secondary.pack_forget()
            else:secondary.pack(fill='x',pady=(5,0))

    def change_conversation_filter(self, key=None, value=None, offset=0):
        if not hasattr(self,'conversation_filters'):self.conversation_filters={}
        if key:self.conversation_filters[key]=value
        self.conversation_offset=offset
        self.scroll_positions[self.viewport_key()]=0
        self.render_page()
        widget=getattr(self,'conversation_filter_widgets',{}).get(key)
        if widget is not None:self.root.after_idle(widget.focus_set)

    def render_conversation_filters(self, area, task):
        if getattr(self,'conversation_task',None)!=self.selected_task:
            self.conversation_task=self.selected_task;self.conversation_filters={};self.conversation_offset=0
        en=self.language=='en';scope=collaboration_scope(self.snapshot,self.selected_task)
        agents={};roles=set()
        for episode in self.snapshot.get('assignment_episodes',[]):
            if episode.get('task_id') in scope:
                agent=next((a for a in self.snapshot.get('agents',[]) if a['id']==episode['agent_id']),None)
                if agent:agents[agent['id']]=agent
                roles.add(episode.get('work_type','unspecified'))
        for record in collaboration_records(self.snapshot,self.selected_task):
            actor=collaboration_actor(record,self.snapshot,self.language)
            if actor['known']:
                agents[actor['id']]=actor['agent'];roles.add((record.get('attribution') or {}).get('work_type','unspecified'))
        strip=self.tk.Frame(area,bg=self.bg);strip.pack(fill='x',pady=(3,6))
        bar=self.tk.Frame(area,bg=self.tint)
        def toggle():
            if bar.winfo_manager():bar.pack_forget()
            else:bar.pack(fill='x',pady=(0,8),after=strip)
        self.filter_chip(strip,'Filters ⌄' if en else '筛选 ⌄',toggle).pack(side='left')
        for key,value in self.conversation_filters.items():
            if value:
                label=('Anonymous' if en else '匿名') if value=='unattributed' and key=='agent' else work_type_label(value,self.language) if key=='role' else agent_text(agents[value],'name',self.language) if key=='agent' and value in agents else next((t['name'] for t in self.snapshot.get('tasks',[]) if t['id']==value),value)
                self.filter_chip(strip,label+' ×',lambda key=key:self.change_conversation_filter(key,'')).pack(side='left',padx=(6,0))
        style=self.ttk.Style(self.root)
        style.configure('Conversation.TCombobox',padding=(9,7),fieldbackground='#f8fbf6',background=self.tint,foreground=self.fg,arrowcolor=self.accent,bordercolor='#cfdfd0',arrowsize=14)
        style.map('Conversation.TCombobox',fieldbackground=[('readonly','#f8fbf6')],foreground=[('readonly',self.fg)])
        fields=[('agent','Author' if en else '作者',[('', 'All authors' if en else '所有作者'),('unattributed','Anonymous' if en else '匿名')]+[(key,agent_text(agent,'name',self.language)+' · '+profile_reference(agent,self.language)) for key,agent in sorted(agents.items())]),
                ('role','Role at event' if en else '事件时职责',[('', 'All roles' if en else '所有职责'),('unattributed','Unrecorded' if en else '未记录')]+[(role,work_type_label(role,self.language)) for role in sorted(roles)])]
        if task.get('activity_kind')=='project':
            fields.append(('task','Task' if en else '任务',[('', 'Whole project' if en else '整个项目')]+[(t['id'],t['name']) for t in self.snapshot.get('tasks',[]) if t['id'] in scope]))
        self.conversation_filter_widgets={}
        for column,(key,label,options) in enumerate(fields):
            frame=self.tk.Frame(bar,bg=self.bg);frame.grid(row=0,column=column,sticky='ew',padx=(0,10));bar.grid_columnconfigure(column,weight=1)
            self.label(frame,label,11,self.muted,raw=True).pack(anchor='w',pady=(0,3))
            combo=self.ttk.Combobox(frame,style='Conversation.TCombobox',state='readonly',values=[label for _,label in options],width=18)
            combo.pack(fill='x');combo.current(next((i for i,(value,_) in enumerate(options) if value==self.conversation_filters.get(key,'')),0))
            combo.bind('<<ComboboxSelected>>',lambda event,key=key,options=options,combo=combo:self.change_conversation_filter(key,options[combo.current()][0]))
            self.conversation_filter_widgets[key]=combo


    def render_task_files(self,area,files):
        en=self.language=='en';task_id=self.selected_task
        self.label(area,'Registered outputs only · private task folder' if en else '只列已登记正式产出 · 私有任务文件夹',12,self.muted,raw=True).pack(anchor='w',pady=(2,12))
        def model(artifact):
            summary=artifact_kind_label(artifact['kind'],self.language)+f" · {artifact['size']:,} B · "+self.stamp(artifact['created'])
            details=[('path',artifact['relative_path']),('checksum','SHA-256 · '+artifact['sha256'][:20]+'…')];actions=[]
            if artifact['relative_path'].endswith('.png'):actions.append(('preview','Preview PNG' if en else '预览 PNG',lambda key=artifact['id']:self.preview_artifact(key)))
            elif Path(artifact['relative_path']).suffix in ('.txt','.md','.json','.csv'):actions.append(('preview','Read text' if en else '阅读文本',lambda key=artifact['id']:self.preview_text_artifact(key)))
            elif artifact['kind']=='video':details.append(('boundary','Video metadata only; open the output folder to use the file. No automatic playback.' if en else '视频仅登记元数据；可从成果文件夹使用文件，不会自动播放。'))
            else:details.append(('boundary','Metadata only; view the delivered attachment separately' if en else '仅显示登记信息；请查看另行交付的附件'))
            return {'title':artifact['title'],'summary':summary,'status':artifact_delivery_label(artifact,self.language),'details':details,'actions':actions}
        self.keyed_registry(area,lambda:[a for a in self.snapshot.get('artifacts',[]) if a['task_id']==task_id],model,minimum=700,maximum=1)

    def preview_text_artifact(self, key):
        en = self.language == "en"
        window = self.tk.Toplevel(self.root)
        window.title("Read-only text" if en else "只读文本")
        window.geometry("900x650")
        window.configure(bg=self.bg)
        try:
            content = self.store.artifact_text(key)
            holder = self.tk.Frame(window, bg=self.panel)
            holder.pack(fill="both", expand=True, padx=15, pady=15)
            view = self.tk.Text(holder, wrap="word", bg=self.panel, fg=self.fg, relief="flat", padx=15, pady=15, font=(self.font,-15))
            view.insert("1.0", content)
            view.configure(state="disabled")
            view.pack(side="left", fill="both", expand=True)
            scrollbar = self.make_scrollbar(holder, view)
            scrollbar.pack(side="right", fill="y")
        except (ValueError, OSError, sqlite3.Error, self.tk.TclError):
            self.label(window, "Preview unavailable: missing, changed, or over 1 MiB" if en else "无法阅读：文件缺失、发生变更或超过 1 MiB", 14, self.muted, raw=True).pack(padx=20, pady=20)

    def preview_artifact(self, key):
        # Reconstructed bounded fit/scroll preview; original tail was not retained.
        en = self.language == "en"
        window = self.tk.Toplevel(self.root)
        window.title("PNG preview" if en else "PNG 预览")
        window.configure(bg=self.bg)
        try:
            data = self.store.artifact_png(key)
            photo = self.tk.PhotoImage(data=base64.b64encode(data))
            screen_width,screen_height=window.winfo_screenwidth(),window.winfo_screenheight()
            width,height,factor=image_preview_geometry(photo.width(),photo.height(),screen_width,screen_height)
            window.geometry(f"{width}x{height}+{max(0,(screen_width-width)//2)}+{max(0,(screen_height-height)//2)}")
            window.original_image = photo
            toolbar=self.tk.Frame(window,bg=self.bg);toolbar.pack(fill="x",padx=10,pady=8)
            body=self.tk.Frame(window,bg=self.bg);body.pack(fill="both",expand=True,padx=10,pady=(0,10))
            canvas=self.tk.Canvas(body,bg=self.panel,highlightthickness=0)
            vertical=self.tk.Scrollbar(body,orient="vertical",command=canvas.yview)
            horizontal=self.tk.Scrollbar(body,orient="horizontal",command=canvas.xview)
            canvas.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
            body.grid_columnconfigure(0,weight=1);body.grid_rowconfigure(0,weight=1)
            canvas.grid(row=0,column=0,sticky="nsew");vertical.grid(row=0,column=1,sticky="ns");horizontal.grid(row=1,column=0,sticky="ew")
            def display(original=False):
                window.image=photo if original else photo.subsample(factor,factor)
                canvas.delete("all");canvas.create_image(0,0,image=window.image,anchor="nw")
                canvas.configure(scrollregion=(0,0,window.image.width(),window.image.height()))
                canvas.xview_moveto(0);canvas.yview_moveto(0)
            self.filter_chip(toolbar,"Fit" if en else "适应窗口",lambda:display(False)).pack(side="left",padx=(0,6))
            self.filter_chip(toolbar,"100%",lambda:display(True)).pack(side="left",padx=(0,6))
            self.label(toolbar,f"{photo.width()} × {photo.height()} px",12,self.muted,raw=True).pack(side="left",padx=8)
            self.filter_chip(toolbar,"Close" if en else "关闭",window.destroy).pack(side="right")
            window.bind("<Escape>",lambda event:window.destroy())
            display()
        except (ValueError,OSError,sqlite3.Error,self.tk.TclError):
            self.label(window,"Preview unavailable" if en else "无法预览",14,self.muted,raw=True).pack(padx=20,pady=20)

    def fit_card(self, surface, body):
        surface.auto_fit = True
        # Follow natural body height, including labels that rewrap on resize.
        def fit(event=None):
            if body.winfo_exists() and surface.winfo_exists():
                surface.configure(height=body.winfo_reqheight()+48)
        body.bind("<Configure>",fit,add="+")
        self.root.after_idle(fit)




    def card_grid(self, parent, minimum=300, maximum=3):
        """Responsive equal-width cards; resizing does not rebuild or lose focus."""
        grid = self.tk.Frame(parent, bg=self.bg)
        grid.pack(fill="x", anchor="n")
        grid.card_items = []
        grid.card_columns = 0
        def layout(event=None):
            # Reconciliation can destroy a card before its replacement is built.
            # The new card requests layout immediately, so drop dead slots first.
            grid.card_items = [child for child in grid.card_items if child.winfo_exists()]
            width = event.width if event is not None else grid.winfo_width()
            columns = max(1, min(maximum, (max(1, width)+14)//(minimum+14)))
            if columns != grid.card_columns:
                for col in range(maximum):
                    grid.columnconfigure(col, weight=1 if col < columns else 0, uniform="cards" if col < columns else "")
                grid.card_columns = columns
            for index, child in enumerate(grid.card_items):
                child.grid(row=index//columns, column=index%columns, sticky="new", padx=(0, 14 if index%columns < columns-1 else 0), pady=(0, 14))
        grid.reflow_cards = layout
        grid.bind("<Configure>", layout)
        return grid

    def draw_participant_group(self, canvas, rows, right, top, command=None):
        if not rows:return
        count=min(3,len(rows));width=28+(count-1)*24+(32 if len(rows)>3 else 0);left=right-width
        tag='participant-group'
        class TaggedCanvas:
            def __getattr__(self, name):
                fn=getattr(canvas,name)
                return lambda *args,**kwargs:fn(*args,**dict(kwargs,tags=tag))
        for index,row in enumerate(rows[:3]):draw_portrait(TaggedCanvas(),row['agent'],left+index*24,top,28)
        if len(rows)>3:canvas.create_text(right-13,top+14,text='+'+str(len(rows)-3),font=(self.font,-11),fill=self.muted,tags=tag)
        if command:
            def open_group(event):
                command()
                return 'break'
            canvas.tag_bind(tag,'<Button-1>',open_group)

    def render_task_participants(self, area, task_id):
        rows=collaboration_participants(self.snapshot,task_id)
        if not rows:return
        en=self.language=='en'
        self.label(area,('Current round participants · ' if en else '当前轮次参与者 · ')+str(len(rows)),16,self.fg,True,raw=True).pack(anchor='w',pady=(0,8))
        for row in rows:
            agent=row['agent'];roles=list(dict.fromkeys(work_type_label(a['work_type'],self.language) for a in row['assignments']))
            line=self.tk.Frame(area,bg=self.bg);line.pack(fill='x',pady=3)
            portrait=self.tk.Canvas(line,width=26,height=26,bg=self.bg,bd=0,highlightthickness=0);portrait.pack(side='left',padx=(0,8));draw_portrait(portrait,agent,0,0,26)
            self.label(line,profile_reference(agent,self.language)+' · '+agent_text(agent,'name',self.language)+' · '+' / '.join(roles),12,self.muted,raw=True,wrap=750).pack(side='left')
            self.label(area,source_label(agent,self.language)+(' · Identity checked at ' if en else ' · 身份核验时间 ')+timestamp_label(agent.get('identity_observed_at'),self.timezone)+' · '+participant_observation(agent,self.snapshot,self.language,timezone=self.timezone),11,self.muted,raw=True,wrap=750).pack(anchor='w',padx=(34,0))

    def compact_row(self, parent, title, summary, status="", command=None, avatar=None, participants=None, bounded=False):
        surface, box = self.card(parent, 244 if bounded else 170)
        if hasattr(parent, "card_items"):
            parent.card_items.append(surface)
            parent.reflow_cards()
        else:
            surface.pack(fill="x", pady=(0, 8))
        box.surface=surface
        box.status_label=None;box.participant_group=None
        if participants is not None:
            top=self.tk.Frame(box,bg=self.panel);top.pack(fill='x',pady=(0,8))
            box.status_label=self.label(top,status,12,self.accent,raw=True);box.status_label.pack(side='right')
            width=min(3,len(participants))*24+10+(32 if len(participants)>3 else 0)
            group=self.tk.Canvas(top,width=width,height=32,bg=self.panel,highlightthickness=0)
            group.pack(side='right',padx=(0,10));self.draw_participant_group(group,participants,width,0,command);box.participant_group=group
        if status and not avatar and participants is None and not bounded:
            box.status_label=self.label(box,status,14,self.accent,raw=True);box.status_label.pack(anchor="w",fill="x",pady=(0,8))
        if avatar:
            header = self.tk.Frame(box, bg=self.panel)
            header.pack(fill="x")
            badge = self.tk.Canvas(header, width=56, height=56, bg=self.panel, highlightthickness=0)
            badge.pack(side="left", padx=(0, 12), anchor="n")
            draw_portrait(badge, avatar if isinstance(avatar, dict) else {'avatar': avatar})
            words = self.tk.Frame(header, bg=self.panel)
            words.pack(side="left", fill="x", expand=True)
            self.label(words, title, 20, self.fg, True, raw=True).pack(anchor="w", fill="x")
            if status:
                self.label(words, status, 12, self.accent, raw=True).pack(anchor="w", fill="x", pady=(4, 0))
        else:
            box.title_label=self.label(box,title,20,self.fg,True,raw=True);box.title_label.pack(anchor="w",fill="x")
        if bounded:
            box.title_label.configure(height=2,anchor='nw')
            box.status_label=self.label(box,status,12,self.accent,raw=True);box.status_label.pack(anchor='w',fill='x',pady=(7,0))
        box.summary_label=self.label(box,summary,14 if bounded else 15,self.muted,raw=True);box.summary_label.pack(anchor="w",fill="x",pady=(9,0))
        if bounded:box.summary_label.configure(height=2,anchor='nw')
        if command:
            box.detail_link = self.label(box, "Open details  ›" if self.language == "en" else "查看详情  ›", 14, self.accent, raw=True)
            box.detail_link.pack(anchor="w", pady=(9, 0))
            def descendants(widget):
                return [widget] + [item for child in widget.winfo_children() for item in descendants(child)]
            for widget in (surface, *descendants(box)):
                widget.configure(cursor="hand2")
                widget.bind("<Button-1>", lambda event, action=command: action())
            surface.configure(takefocus=1, highlightcolor=self.accent)
            surface.bind("<Return>", lambda event: command())
            surface.bind("<space>", lambda event: command())
            surface.bind("<FocusIn>", lambda event: surface.configure(highlightthickness=2))
            surface.bind("<FocusOut>", lambda event: surface.configure(highlightthickness=0))
        def wrap_children(event=None):
            width = max(40, box.winfo_width())
            def walk(widget):
                for child in widget.winfo_children():
                    if isinstance(child, self.tk.Label):
                        child.configure(wraplength=max(40, width-68) if child.master is not box else width)
                    else:
                        walk(child)
            walk(box)
        if bounded:
            source={'title':title,'summary':summary,'status':status}
            def fit_bounded(event=None):
                import tkinter.font as font
                width=max(20,box.winfo_width())
                for field,widget,pixels,lines in [('title',box.title_label,20,2),('status',box.status_label,12,1),('summary',box.summary_label,14,2)]:
                    measure=font.Font(root=self.root,family=self.font,size=-pixels,weight='bold' if field=='title' else 'normal').measure
                    value=source[field]
                    if field=='summary':value='\n'.join(bounded_card_lines(line,width,measure,1) for line in value.splitlines()[:2])
                    else:value=bounded_card_lines(value,width,measure,lines)
                    if widget.cget('text')!=value:widget.configure(text=value,wraplength=0)
                if surface.auto_fit:surface.configure(height=max(244,box.winfo_reqheight()+48))
            def set_caption(field,value):source[field]=value;fit_bounded()
            def set_expanded(value):
                if surface.auto_fit==value:return
                surface.auto_fit=value
                if not value:surface.configure(height=244)
                else:self.root.after_idle(fit_bounded)
            surface.auto_fit=False;box.set_caption=set_caption;box.set_expanded=set_expanded
            box.bind('<Configure>',fit_bounded,add='+')
        else:
            box.bind("<Configure>", wrap_children, add="+")
            self.fit_card(surface, box)
        return box

    def activity_row_summary(self,row):
        progress = task_progress(self.snapshot,row['id'])
        text = progress['current_step'] or (row.get('run') or {}).get('lifecycle_reason') or activity_summary(self.snapshot,row['id'],self.language)
        summary = compact_task_excerpt(text)
        status = self.t(STATUS.get(row['status'],row['status']))
        return row['values'][0],summary,status

    def render_conversation_list(self, selection=()):
        self.workspace_toolbar();area=self.scroll_area()
        grid=self.card_grid(area,minimum=370,maximum=2);cards={};empty=self.label(area,'该状态暂无任务',16,self.muted)
        def reconcile():
            mode=getattr(self,'collaboration_mode_filter','all');tasks={t['id']:t for t in self.snapshot.get('tasks',[])}
            rows=[r for r in workspace_rows(self.rows,self.workspace_filter,self.search_query.get()) if mode=='all' or (tasks.get(r['id'],{}).get('activity_kind')=='project' if mode=='project' else tasks.get(r['id'],{}).get('collaboration_mode','single')==mode)]
            wanted=[row['id'] for row in rows]
            for key in list(cards):
                if key not in wanted:cards.pop(key).destroy()
            for index,row in enumerate(rows):
                if row['id'] not in cards:
                    cards[row['id']]=self.airy_task_card(grid,row,index)
            ordered=[cards[key] for key in wanted]
            if grid.card_items!=ordered:grid.card_items=ordered;grid.reflow_cards()
            if rows:empty.pack_forget()
            else:empty.pack(anchor='w',pady=20)
        reconcile();self.background_refresh=reconcile

    def toggle_registry_detail(self, kind, key):
        attribute = "expanded_" + kind
        expanded = set(getattr(self, attribute, set()))
        if key in expanded:
            expanded.remove(key)
        else:
            expanded.add(key)
        setattr(self, attribute, expanded)
        self.render_page()

    def render_schedules(self):
        area=self.scroll_area();en=self.language=='en'
        info=self.tk.Frame(area,bg=self.bg)
        def toggle_info():
            self.automation_info_expanded=not getattr(self,'automation_info_expanded',False)
            if self.automation_info_expanded:info.pack(fill='x',pady=(0,10),before=grid_holder)
            else:info.pack_forget()
            self.patch_caption(info_button,('ⓘ Automation notes' if en else 'ⓘ 自动化说明')+(' ⌃' if self.automation_info_expanded else ' ⌄'))
        info_button=self.filter_chip(area,('ⓘ Automation notes' if en else 'ⓘ 自动化说明')+(' ⌃' if getattr(self,'automation_info_expanded',False) else ' ⌄'),toggle_info)
        info_button.pack(anchor='w',pady=(0,10))
        self.label(info,'Recorded observations only; local refresh does not run automations or poll GitHub. Platform configuration and result snapshots are independently observed.' if en else '只读登记快照；本地刷新不会运行自动化，也不会查询 GitHub。平台配置与结果快照分别记录观察。',13,self.muted,raw=True,wrap=800).pack(anchor='w',fill='x')
        grid_holder=self.tk.Frame(area,bg=self.bg);grid_holder.pack(fill='x')
        if getattr(self,'automation_info_expanded',False):info.pack(fill='x',pady=(0,10),before=grid_holder)
        def model(record):
            state,timing=schedule_summary(record,self.language,self.timezone);result=schedule_result_view(record,self.language,self.timezone);platform=schedule_platform_view(record,self.language,self.timezone)
            if result:
                schedule_line=platform['compact'] if platform else ('Schedule not verified' if en else '计划未核验')
                latest=((record.get('external_result') or {}).get('observation') or {}).get('latest') or {}
                result_line=' · '.join(str(value) for value in (latest.get('calendar_date'),latest.get('status')) if value is not None) or ('No result snapshot' if en else '尚无结果快照')
                if result['error']:result_line=('Check failed · ' if en else '检查失败 · ')+result_line
            else:
                schedule_line=timing;result_line='No result snapshot' if en else '尚无结果快照'
            timing=schedule_line+'\n'+(('Latest: ' if en else '最近记录：')+result_line)
            key=record['id'];expanded=key in getattr(self,'expanded_schedules',set());details=[]
            actions=[('details',('Less ⌃' if en else '收起 ⌃') if expanded else ('Details ⌄' if en else '详情 ⌄'),lambda key=key:self.toggle_registry_detail('schedules',key))]
            if expanded:
                if result and result['error']:details.append(('error',result['error']))
                technical_labels={'平台任务 ID','Platform task ID','计划','Schedule','源运行编号','Source run ID','状态文件','Status path','索引文件','Index path','Status blob SHA','Index blob SHA','状态来源 URL','Status source URL','索引来源 URL','Index path','Index source URL'}
                technical=[]
                for i,(label,value) in enumerate((platform['rows'] if platform else [])+(result['rows'] if result else [])):
                    target=technical if label in technical_labels else details;target.append(('evidence:'+str(i),label+': '+str(value)))
                if technical:
                    opened=key in getattr(self,'expanded_schedule_technical',set());actions.append(('technical',('Hide technical ⌃' if en else '收起技术信息 ⌃') if opened else ('Technical details ⌄' if en else '技术信息 ⌄'),lambda key=key:self.toggle_registry_detail('schedule_technical',key)))
                    if opened:details+=technical
                for field,label,value in [('project','Project' if en else '项目',record.get('project')),('source','Source' if en else '来源',record.get('source')),('state','Registered state' if en else '登记状态',record.get('state')),('next','Planned time (unverified)' if en else '登记计划时间（未核验）',self.stamp(record.get('next_run')) if record.get('next_run') else '—'),('updated','Last recorded update' if en else '最近登记更新',self.stamp(record.get('updated')) if record.get('updated') else '—')]:details.append((field,label+': '+str(value or '—')))
                details.append(('boundary','Registration does not create, start or resume a scheduler' if en else '登记不会创建、启动或恢复任何定时器'))
            return {'title':record['name'],'summary':timing,'status':state,'details':details,'actions':actions}
        self.keyed_registry(grid_holder,lambda:self.snapshot.get('schedules',[]),model,minimum=370,maximum=2,bounded=True)

    def render_software(self):
        area=self.scroll_area();en=self.language=='en'
        def records():
            rows=list(self.snapshot.get('software',[]))
            if not any(row.get('kind')=='dots-panel' for row in rows):rows.insert(0,{'id':'current-viewer','name':'dots-panel','description':self.t('此窗口正在运行'),'kind':'dots-panel','version':VERSION,'available':True,'controls':['close_current_viewer']})
            return rows
        def model(record):
            key=record.get('id',record['name']);available=record.get('available');state=self.t('可用' if available is True else '未检测到' if available is False else '未验证');expanded=key in getattr(self,'expanded_software',set())
            actions=[('details',('Less ⌃' if en else '收起 ⌃') if expanded else ('Details ⌄' if en else '详情 ⌄'),lambda key=key:self.toggle_registry_detail('software',key))];details=[]
            if expanded:
                for field,label,value in [('description','Description' if en else '简介',record.get('description')),('kind','Kind' if en else '类型',record.get('kind')),('available','Availability' if en else '可用性',state),('version','Version' if en else '版本',record.get('version')),('checked','Checked' if en else '检测时间',observation_label(record.get('verified_at'),self.language,self.timezone))]:details.append((field,label+': '+str(value or '—')))
                details.append(('boundary','Detected availability is not proof of a running service' if en else '检测到可用不代表服务正在运行'))
                if 'close_current_viewer' in record.get('controls',[]) and record.get('kind')=='dots-panel':actions.append(('close',self.t('关闭此窗口'),self.close_viewer))
                else:details.append(('controls','No launch/stop controls are connected' if en else '未接入启动或停止控制'))
            return {'title':record['name'],'summary':str(record.get('version') or '—'),'status':state,'details':details,'actions':actions}
        self.keyed_registry(area,records,model,minimum=285,maximum=3)

    def render_install_doctor(self,area,report):
        en=self.language=='en';section=self.tk.Frame(area,bg=self.panel,padx=12,pady=10);section.pack(fill='x',pady=(0,12))
        self.label(section,'Installation checks · read-only' if en else '安装自检 · 只读',16,self.fg,True,raw=True).pack(anchor='w')
        summary=self.label(section,'',14,self.muted,raw=True);summary.pack(anchor='w',pady=(4,5))
        facts=self.tk.Frame(section,bg=self.panel);facts.pack(fill='x');update_facts=self.keyed_labels(facts)
        def toggle():self.doctor_expanded=not getattr(self,'doctor_expanded',False);self.render_page()
        self.filter_chip(section,('Less ⌃' if en else '收起 ⌃') if getattr(self,'doctor_expanded',False) else ('Local check details ⌄' if en else '本机检查详情 ⌄'),toggle).pack(anchor='w',pady=(6,3))
        details=self.tk.Frame(section,bg=self.panel);details.pack(fill='x');update_details=self.keyed_labels(details)
        self.label(section,'No account scan, installation or scheduling; source availability does not verify account setup' if en else '不扫描账户、不安装、不创建定时器；源码可用不等于账户已配置',11,self.muted,raw=True,wrap=800).pack(anchor='w',pady=(5,0))
        saved={}
        def refresh(report):
            local,manual=doctor_rows(report,self.language);passed=sum(row['status']=='ok' for row in report.get('checks',[]))
            caption=(f'Local checks: {passed}/{len(local)} OK · permission probes only' if en else f'本机检查：{passed}/{len(local)} 通过 · 仅探测权限') if local else ('No diagnostics available' if en else '尚未运行检查')
            if caption!=saved.get('summary'):summary.configure(text=caption);saved['summary']=caption
            update_facts([(title,title+' · '+value) for title,value in manual])
            rows=[]
            if getattr(self,'doctor_expanded',False):
                rows=[(title,title+' · '+value) for title,value in local]
                for component,observation in report.get('observations',{}).items():
                    if observation.get('evidence'):rows.append(('evidence:'+component,self.stamp(observation['observed_at'])+' · '+observation['evidence']))
            update_details(rows)
        refresh(report);return refresh

    def render_about(self):
        area=self.scroll_area();en=self.language=='en';values={};value_labels={}
        labels={'unknown':('未核验','Not checked'),'unpublished':('未发布','Unpublished'),'published':('已发布','Published'),'matched':('已核验一致','Verified matching'),'different':('已核验不同','Verified different'),'local_changes':('有本地更改','Local changes')}
        titles=[('installed','Installed version' if en else '当前安装版本'),('release','Published release' if en else '已发布版本'),('sync','Source synchronization' if en else '源码同步状态'),('commit','Verified remote commit' if en else '已核验远端提交'),('checked','Last checked' if en else '最近核验')]
        for key,title in titles:
            row=self.tk.Frame(area,bg=self.panel,highlightthickness=1,highlightbackground='#e3ebe1',padx=13,pady=11);row.pack(fill='x',pady=(0,6))
            self.label(row,title,15,self.muted,raw=True).pack(side='left',padx=(0,25));value_labels[key]=self.label(row,'',15,self.fg,raw=True,wrap=620);value_labels[key].pack(side='left',fill='x',expand=True)
            row.bind('<Configure>',lambda event,label=value_labels[key]:label.configure(wraplength=max(150,event.width-200)))
        link_state={'url':None}
        def open_repository():
            if link_state['url']:
                import webbrowser
                webbrowser.open(link_state['url'])
        link=self.filter_chip(area,'GitHub project ↗' if en else 'GitHub 项目 ↗',open_repository);link.pack(anchor='w',pady=(7,4))
        link_label=self.label(area,'',14,self.muted,raw=True);link_label.pack(anchor='w',pady=(0,9))
        refresh_doctor=self.render_install_doctor(area,self.snapshot.get('about',{}).get('doctor',{}))
        self.label(area,'Installation notes' if en else '本安装更新说明',17,bold=True,raw=True).pack(anchor='w',pady=(12,7))
        notes=self.tk.Frame(area,bg=self.bg);notes.pack(fill='x');update_notes=self.keyed_labels(notes)
        self.label(area, 'Cloud workspace & recovery' if en else '云工作区与恢复', 17, bold=True, raw=True).pack(anchor='w', pady=(15, 7))
        self.label(area, 'Cloud computers can retain state between uses, but local files alone are not a durability guarantee. Workspace directories have been observed unavailable; the cause is unconfirmed, not evidence of a daily reset. Recovery relies on the last verified private Library snapshot. GitHub contains source only, never private DATA.' if en else '云电脑可在使用之间保留状态，但本机文件不能单独作为持久保存保证。曾观察到工作区目录不可用，原因未确认，不能据此断言每天重置。恢复以私有 Library 最后核验快照为准；GitHub 只同步源码，不含私有 DATA。', 14, self.muted, raw=True, wrap=800).pack(anchor='w', pady=(0, 8))
        self.filter_chip(area, 'Backup details →' if en else '查看备份与恢复 →', lambda: self.navigate('settings')).pack(anchor='w')
        self.label(area,'Local version is not remote release status. Manually verified observations; no live update or publication.' if en else '本地版本不等于远端发布状态；这里只读展示人工核验记录，不更新安装或发布。',14,self.muted,raw=True,wrap=800).pack(anchor='w',pady=(15,5))
        def refresh():
            about=self.snapshot.get('about',{});release=about.get('release',{});state=lambda key:labels.get(key,labels['unknown'])[1 if en else 0]
            current={'installed':about.get('installed_version',VERSION),'release':state(release.get('release_status'))+(' · '+release['release_tag'] if release.get('release_tag') else ''),'sync':state(release.get('sync_status')),'commit':release.get('remote_commit') or '—','checked':self.stamp(release['checked_at']) if release.get('checked_at') else ('Not checked' if en else '尚未核验')}
            for key,value in current.items():
                if values.get(key)!=value:value_labels[key].configure(text=value)
            values.update(current)
            try:url=verified_repository_url(release.get('repo_url'))
            except ValueError:url=None
            if url!=link_state['url'] or 'link' not in values:
                link_state['url']=url;values['link']=url;link_label.configure(text=url or ('No verified GitHub project configured' if en else '尚未登记已核验的 GitHub 项目'))
                if url:link.pack(anchor='w',pady=(7,4),before=link_label)
                else:link.pack_forget()
            refresh_doctor(about.get('doctor',{}));update_notes([(str(i),'• '+row.get('en' if en else 'zh','')) for i,row in enumerate(about.get('install_notes',[]))])
        refresh();self.background_refresh=refresh

    def render_rules(self):
        area=self.scroll_area();en=self.language=='en';language='en' if en else 'zh'
        version=self.label(area,'',14,self.accent,raw=True);version.pack(anchor='w',pady=(0,6))
        self.label(area,'App enforced, executor workflow, or planned; these guidelines do not grant permissions.' if en else '程序校验、执行约定或待落地；规则本身不授予权限。',14,self.muted,raw=True,wrap=830).pack(anchor='w',pady=(0,12))
        self.label(area,'Your installed Skills' if en else '用户安装的 Skills',16,self.fg,True,raw=True).pack(anchor='w',pady=(0,4))
        self.label(area,'Manually recorded summaries · no automatic sync or guaranteed activation' if en else '人工登记的用途摘要 · 不自动同步，不保证每次触发',14,self.muted,raw=True,wrap=830).pack(anchor='w',pady=(0,8))
        skill_area=self.tk.Frame(area,bg=self.bg);skill_area.pack(fill='x')
        def skill_model(item):
            key=item.get('id',item['name']);source=item.get('source',{});expanded=key in getattr(self,'expanded_skills',set());details=[]
            actions=[('details',('Less ⌃' if en else '收起 ⌃') if expanded else ('Details ⌄' if en else '详情 ⌄'),lambda key=key:self.toggle_registry_detail('skills',key))]
            if expanded:
                details=[('origin',skill_origin_label(source.get('origin'),language)+' · '+skill_publication_label(source.get('publication'),language)),('when',('When: ' if en else '使用场景：')+agent_text(item,'when_used',language)),('observed',('Manual observation · ' if en else '人工观察 · ')+self.stamp(item.get('observed_at'))+' · '+skill_version_label(item.get('version_status'),language))]
                if item.get('version_note') or item.get('version_note_en'):details.append(('version',agent_text(item,'version_note',language)))
                try:url=verified_skill_url(item.get('url'))
                except ValueError:url=None
                if url:
                    def open_skill(url=url):
                        import webbrowser
                        webbrowser.open(url)
                    actions.append(('manage','Manage ↗' if en else '管理 ↗',open_skill))
            return {'title':agent_text(item,'name',language),'summary':agent_text(item,'purpose',language),'status':skill_status_label(item.get('status'),language),'details':details,'actions':actions}
        refresh_skills=self.keyed_registry(skill_area,lambda:[r for r in self.snapshot.get('rules',{}).get('skills',[]) if r.get('scope')=='user_installed'],skill_model,minimum=300,maximum=3)
        legacy_holder={'url':None}
        def open_legacy():
            if legacy_holder['url']:
                import webbrowser
                webbrowser.open(legacy_holder['url'])
        legacy=self.filter_chip(area,'Task skill ↗' if en else '任务 Skill ↗',open_legacy)
        self.label(area,'Project guidelines' if en else '项目规范',16,self.fg,True,raw=True).pack(anchor='w',pady=(8,8))
        groups_area=self.tk.Frame(area,bg=self.bg);groups_area.pack(fill='x');groups={};previous={}
        levels={'enforced':('程序校验','App enforced'),'workflow':('执行约定','Workflow'),'planned':('待落地','Planned')}
        self.label(area,'Source: packaged project_rules.json · read-only' if en else '统一来源：项目 project_rules.json · 只读展示',14,self.muted,raw=True).pack(anchor='w',pady=10)
        state={}
        def refresh():
            data=self.snapshot.get('rules',{});caption=('Rules version · ' if en else '规则版本 · ')+data.get('version','—')
            if state.get('version')!=caption:version.configure(text=caption);state['version']=caption
            refresh_skills()
            try:url=verified_skill_url(data.get('skill_url'))
            except ValueError:url=None
            if any(item.get('url')==url for item in data.get('skills',[])):url=None
            if url!=legacy_holder['url']:
                legacy_holder['url']=url
                if url:legacy.pack(anchor='w',pady=(0,8),before=groups_area)
                else:legacy.pack_forget()
            wanted=[g.get('id',g['title'][language]) for g in data.get('groups',[])]
            for key in list(groups):
                if key not in wanted:groups.pop(key)['box'].destroy();previous.pop(key,None)
            for group,key in zip(data.get('groups',[]),wanted):
                expanded=key in getattr(self,'expanded_rule_groups',set());caption=group['title'][language]+('  ⌃' if expanded else '  ⌄')
                if key not in groups:
                    box=self.tk.Frame(groups_area,bg=self.panel,highlightthickness=1,highlightbackground='#e3ebe1',padx=12,pady=9);box.pack(fill='x',pady=(0,8))
                    button=self.filter_chip(box,caption,lambda key=key:self.toggle_registry_detail('rule_groups',key));button.pack(anchor='w')
                    count=self.label(box,'',13,self.muted,raw=True);count.pack(anchor='w',pady=(4,0));body=self.tk.Frame(box,bg=self.panel)
                    if expanded:body.pack(fill='x',pady=(8,0))
                    groups[key]={'box':box,'button':button,'count':count,'labels':self.keyed_labels(body)}
                item=groups[key];self.patch_caption(item['button'],caption)
                count=str(len(group['items']))+(' guidelines' if en else ' 条规范')
                if previous.get(key)!=count:item['count'].configure(text=count);previous[key]=count
                item['labels']([(rule.get('id',str(i)),levels.get(rule['level'],levels['planned'])[1 if en else 0]+' · '+rule['title'][language]+'\n'+rule['body'][language]) for i,rule in enumerate(group['items'])])
        refresh();self.background_refresh=refresh

    def close_viewer(self):
        from tkinter import messagebox
        if messagebox.askyesno(self.t("确认关闭此窗口？"), self.t("只关闭当前看板窗口，不会停止任务、自动化或其他服务。可从桌面启动器重新打开。"), parent=self.root):
            if self.timer:
                self.root.after_cancel(self.timer)
            if getattr(self, "notifications", None) is not None:
                self.notifications.close()
            self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description="Read-only native dots-panel viewer (no HTTP)")
    parser.add_argument("--data-dir", type=Path, default=default_data_dir())
    parser.add_argument("--layout-diagnostics", action="store_true", help="Log public Tk geometry for task-detail layout diagnosis")
    parser.add_argument("--font-diagnostics", action="store_true", help="Report local Tk font selection and exit")
    parser.add_argument("--language", choices=("auto", "zh", "en"), default=None, help="UI language; Auto follows LC_ALL, LC_MESSAGES, then LANG")
    args = parser.parse_args()
    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError:
        print("Native viewer needs Python's optional tkinter module. No packages were installed.", file=sys.stderr)
        return 2
    try:
        root = tk.Tk(className="DotsPanel")
        if args.font_diagnostics:
            root.withdraw()
            import tkinter.font as font
            families = font.families(root)
            selected = font.Font(root=root, family=choose_font(families), size=-16)
            print(json.dumps({"selected": selected.actual(), "scaling": root.tk.call("tk", "scaling"), "metrics": selected.metrics(), "cjk_width": selected.measure("任务与资源看板"), "cjk_families": sorted(f for f in families if "cjk" in f.casefold())}, ensure_ascii=False))
            root.destroy()
            return 0
        store = ReadOnlyStore(args.data_dir)
        view=Dashboard(root, store, Metrics(store.directory), tk, ttk, args.language or load_language(store.directory))
        view.layout_diagnostics=args.layout_diagnostics
        root.mainloop()
    except (OSError, sqlite3.Error, tk.TclError) as error:
        print(f"Native viewer unavailable: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
