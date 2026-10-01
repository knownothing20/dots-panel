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
from .progress import task_progress, current_run, task_meaningful_updated, agent_observation
from .agent_identity import draw_portrait, identity_label, source_label
from .participants import activity_participants, profile_reference
from .app import artifact_delivery_label, verification_label, attention_items, attention_draft, artifact_kind_label, VERSION, verified_repository_url, verified_link, skill_origin_label, skill_publication_label
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import stat
import uuid
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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

from .app import (Metrics, Store, ROOT, default_data_dir, agent_text, agent_work, work_type_label,
                  verified_skill_url, skill_status_label, skill_version_label)

STATUS = {"waiting_user": "等待用户", "waiting_external": "等待外部结果", "paused": "已暂停记录", "awaiting_review": "等待验收", "running": "进行中", "succeeded": "已完成", "failed": "失败", "cancelled": "已取消", "pending": "待开始"}
STATES = {"unknown": "历史状态未保留","planned": "计划", "in_progress": "进行中", "verified": "已验证"}
PAGE_NAMES = {"overview": "概览", "conversations": "活动", "schedules": "定时任务", "software": "软件", "rules": "规则", "about": "关于与版本", "settings": "设置"}
EN = {"设置": "Settings", "语言": "Language", "显示时区": "Display timezone", "应用时区": "Apply timezone", "默认北京时间；支持 IANA 时区。仅调整显示，不改变系统时间或任务调度。": "Beijing time by default; supports IANA timezones. Display only; system time and task schedules stay unchanged.", "设置保存在本机": "Settings are saved locally", "无效或不支持的 IANA 时区": "Invalid or unsupported IANA timezone", "未保存偏好；当前仅本次有效": "Preferences not saved; applied for this session only","已登记活动与工作记录；执行会话绑定情况见详情": "Registered activities and work records; see details for execution-session bindings","关于与版本": "About & version", "↻ 刷新": "↻ Refresh", "每 5 秒 · 最近刷新": "Every 5s · Last refreshed", "尚未刷新": "Not refreshed yet","历史状态未保留": "Historical state unavailable", "recovered_summary": "Recovered summary","等待用户": "Waiting for user", "等待外部结果": "Waiting for external result", "已暂停记录": "Recorded as paused", "等待验收": "Awaiting review",

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
    "概览": "Overview", "活动": "Activities", "定时任务": "Schedules", "软件": "Software",
    "你的本地工作空间": "Your local workspace", "资源、工作与计划，一目了然": "Resources, work and plans at a glance",
    "已登记活动与工作记录；尚未绑定独立执行会话": "Registered activities and work records; no separate execution session is linked",
    "只展示已登记计划；此面板不会执行定时任务": "Registered plans only; this panel does not execute schedules",
    "本地软件登记与检测；不会运行任意命令": "Local software registry and checks; no arbitrary commands",
    "本地优先": "Local first", "工作中": "Active work", "查看活动 →": "View activities →",
    "查看计划 →": "View schedules →", "没有进行中的已登记任务": "No registered task is currently running",
    "尚未登记任务": "No tasks registered yet", "尚未登记定时任务": "No schedules registered yet",
    "尚未登记其他软件": "No other software registered yet", "未接入": "Disconnected", "已暂停": "Paused",
    "下次运行未知": "Next run unknown", "计划时间": "Planned time", "来源": "Source", "计划数量": "Registered plans",
    "未接入调度器": "No scheduler connected", "此页仅显示元数据，不代表任务已安排或会运行": "Metadata only; a listed plan is not confirmation of scheduling or execution",
    "全部活动": "All activities", "打开所选活动": "Open selected activity",
    "双击任务或按 Enter 打开记录；Esc 返回列表": "Double-click a task or press Enter to open; Esc returns to the list",
    "← 返回列表": "← Back to list", "工作时间线": "Work timeline", "暂无工作记录": "No work records yet",
    "活动进展记录；尚未绑定独立执行会话": "Activity progress records; no separate execution session is linked",
    "此窗口正在运行": "This viewer is running", "本地任务与资源看板": "Local task and resource dashboard",
    "关闭此窗口": "Close this viewer", "确认关闭此窗口？": "Close this viewer?",
    "只关闭当前看板窗口，不会停止任务、定时任务或其他服务。可从桌面启动器重新打开。": "Only this viewer will close. Tasks, schedules and other services will keep their current state. Reopen it from the desktop launcher.",
    "可用": "Available", "未检测到": "Not detected", "未验证": "Not verified", "最近检测": "Last checked", "版本": "Version",
    "此处未提供进程控制": "Process controls are not available here", "数据来自显式登记；不读取内部会话": "Explicitly registered data only; internal sessions are not read",
    "可见指标可能来自宿主机；配额以容器值为准": "Visible metrics may reflect the host; use container quota values",
    "近期运行：{running} 进行中 · {done} 完成": "Latest runs: {running} active · {done} done",
    "已登记 {count} 个计划": "{count} registered plans", "刷新失败，保留上次数据": "Refresh failed; retaining the last data",
    "每 5 秒刷新": "Refreshes every 5s", "最近 100 条工作记录": "Up to 100 recent work records", "本机时间": "Local time", "未保存语言偏好": "Language preference was not saved",
    "心跳跟踪": "Heartbeat tracking", "手动记录": "Manual record", "已登记的软件": "Registered software", "资源使用情况": "Resource usage",
    "可见指标；内存优先使用容器配额": "Visible metrics; memory uses quota when available", "工作区": "Workspace", "全部": "All", "待开始": "Pending", "心跳过期": "Heartbeat stale",
    "该状态暂无任务": "No tasks with this status", "另有 {count} 个活动，可在活动页查看": "{count} more activities in Activities",
}

EN.update({"等待用户": "Waiting for user", "等待外部": "Waiting externally", "待验收": "Awaiting review", "规则": "Rules", "关于": "About"})


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
    return sorted(rows, key=lambda row: (row["status"] in {"succeeded", "cancelled"}, -task_meaningful_updated(snapshot, row["id"]), row["id"]))


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
    runs = {row["id"]: row for row in snapshot.get("runs", []) if row["task_id"] == task_id}
    records = []
    for item in snapshot.get("activity", []):
        if item.get("task_id") == task_id:
            records.append({"created": item["created"], "title": item["stage"], "state": item.get("state"), "message": item["message"], "kind": "activity", "source_id": str(item.get("id", ""))})
    mirrored = {(row["created"], row["message"]) for row in records}
    for item in snapshot.get("events", []):
        if item["run_id"] in runs and (item["created"], item["message"]) not in mirrored:
            records.append({"created": item["created"], "title": "运行事件", "state": None, "message": item["message"], "kind": "event", "source_id": str(item.get("id", ""))})
    for item in runs.values():
        if item.get("note"):
            records.append({"created": item["started"], "title": "启动说明：", "state": None, "message": item["note"], "kind": "note", "source_id": str(item["id"])})
    order = {"activity": 0, "event": 1, "note": 2}
    return sorted(records, key=lambda row: (-row["created"], order[row["kind"]], row["source_id"], row["message"]))


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
        root.geometry("1260x850")
        root.minsize(760, 620)
        root.configure(bg=self.bg)
        try:
            root.attributes("-zoomed", True)
        except tk.TclError:
            try:
                root.state("zoomed")
            except tk.TclError:
                pass
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

    def card(self, parent, height=130):
        canvas = self.tk.Canvas(parent, height=height, bg=self.bg, highlightthickness=0, bd=0)
        inner = self.tk.Frame(canvas, bg=self.panel)
        window = canvas.create_window(20, 17, window=inner, anchor="nw")
        def redraw(event):
            for shape in canvas.find_all():
                if shape != window:
                    canvas.delete(shape)
            self.surface_layers(canvas, event.width, event.height)
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
        top.bind("<Configure>", lambda event: self.health.configure(wraplength=max(160, event.width-250)))
        self.subtitle = self.label(main, "", 15, self.muted)
        self.subtitle.pack(anchor="w", pady=(5, 13))
        self.recovery_banner = self.label(main, "", 12, "#946a25", raw=True, wrap=900)
        self.recovery_banner.pack(anchor="w", pady=(0, 4))
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
        self.label(timezone_box, region_info, 15, self.muted, raw=True, wrap=660).pack(anchor="w", pady=(10, 0))
        self.fit_card(timezone_card, timezone_box)

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
            if not self.scroll_dragging and not getattr(self, "filter_menu_open", False):
                if self.page == "overview" or self.view_signature() != self.last_render_signature:
                    self.render_page()
                else:
                    for update in self.live_updates:
                        update()
            if notification_result is not None and getattr(self, "notifications", None) is not None:
                self.notifications.observe(notification_result)
        except (OSError, sqlite3.Error, ValueError, KeyError):
            self.read_error = True
        if getattr(self, "recovery_banner", None) is not None:
            recovery = self.snapshot.get("recovery") or {}
            self.recovery_banner.configure(text=recovery.get("notice_en" if self.language == "en" else "notice_zh", ""))
        self.update_health()
        self.timer = self.root.after(5000, self.refresh)

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
        for widget in self.content.winfo_children():
            widget.destroy()
        self.page_title.configure(text=self.t("工作区" if self.page == "overview" else PAGE_NAMES[self.page]))
        subtitles = {"overview": "资源、工作与计划，一目了然", "conversations": "已登记活动与工作记录；执行会话绑定情况见详情", "schedules": "只展示已登记计划；此面板不会执行定时任务", "software": "本地软件登记与检测；不会运行任意命令"}
        self.subtitle.configure(text=self.t(subtitles.get(self.page, "")))
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
        canvas.create_text(width/2, 17, text=text, fill="white" if selected else self.muted, font=(self.font, -14, "bold" if selected else "normal"))
        canvas.bind("<Button-1>", lambda event: command())
        canvas.bind("<Return>", lambda event: command())
        canvas.bind("<space>", lambda event: command())
        return canvas

    def set_workspace_filter(self, status):
        self.workspace_filter = status
        if not getattr(self, "filter_menu_open", False):
            self.render_page()
            button = getattr(self, "filter_buttons", {}).get(status, getattr(self, "more_filter_button", None))
            if button is not None and button.winfo_exists():
                button.focus_set()

    def open_filter_menu(self):
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
        width, height = 292, 410
        x, y = popup_position(self.more_filter_button.winfo_rootx(), self.more_filter_button.winfo_rooty(),
            self.more_filter_button.winfo_width(), self.more_filter_button.winfo_height(), width, height,
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
        buttons, position = [], [next((i for i, pair in enumerate(options) if pair[0] == self.workspace_filter), 0)]
        focus_job = {"id": None}
        def close(event=None):
            if focus_job["id"] is not None:
                popup.after_cancel(focus_job["id"])
                focus_job["id"] = None
            if popup.winfo_exists():
                popup.grab_release()
                popup.destroy()
            self.filter_popup = None
            self.filter_menu_open = False
            self.render_page()
            if self.more_filter_button.winfo_exists():
                self.more_filter_button.focus_set()
            return "break"
        def choose(choice):
            close()
            self.set_workspace_filter(choice)
            return "break"
        for choice, label in options:
            button = self.tk.Button(panel, text=("✓  " if choice == self.workspace_filter else "    ")+label,
                anchor="w", command=lambda value=choice: choose(value), font=(self.font, -14),
                bg=self.tint if choice == self.workspace_filter else self.panel, fg=self.accent if choice == self.workspace_filter else self.fg,
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
        text = self.tk.Text(parent, wrap="char", relief="flat", bd=0, bg=self.panel, fg=self.fg, font=(self.font, -16), width=1, height=1, padx=0, pady=0, highlightthickness=0, spacing1=0, spacing2=0, spacing3=0, takefocus=1)
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
        return (self.page, self.selected_task, self.language, self.workspace_filter, self.search_query.get(), fresh, display_signature(self.snapshot))

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
        def cancel():
            restore["pending"] = False
            if restore["job"] is not None:
                self.root.after_cancel(restore["job"])
                restore["job"] = None
        canvas.cancel_restore = cancel
        def finish_restore():
            restore["job"] = None
            if restore["pending"] and canvas.winfo_exists():
                restore["pending"] = False
                height, fraction = scroll_extent(body.winfo_reqheight(), canvas.winfo_height(), position)
                canvas.yview_moveto(fraction)
        def layout(event=None):
            if not canvas.winfo_exists():
                return
            height, fraction = scroll_extent(body.winfo_reqheight(), canvas.winfo_height(), canvas.yview()[0])
            canvas.configure(scrollregion=(0, 0, max(1, canvas.winfo_width()), height))
            if body.winfo_reqheight() <= canvas.winfo_height():
                canvas.yview_moveto(0)
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
        exact = self.workspace_filter not in self.filter_buttons
        more = (self.t(STATUS.get(self.workspace_filter, "未知")) + f" {len(workspace_rows(self.rows, self.workspace_filter))}" if exact else ("More filters" if self.language == "en" else "更多筛选")) + " ⌄"
        self.more_filter_button = self.filter_chip(filters, more, self.open_filter_menu, exact)
        self.more_filter_button.pack(side="left")
        self.more_filter_button.bind("<Down>", lambda event: self.open_filter_menu())
        if self.page != "conversations":
            return
        search = self.tk.Canvas(bar, width=170, height=34, bg=self.bg, bd=0, highlightthickness=0)
        search.grid(row=0, column=1, sticky="e", padx=(10, 0))
        def toolbar_layout(event):
            narrow = event.width < 620
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
        card = self.tk.Canvas(parent, height=240, bg=self.bg, bd=0, highlightthickness=0, cursor="hand2", takefocus=1)
        if hasattr(parent, "card_items"):
            parent.card_items.append(card)
            parent.reflow_cards()
        else:
            card.grid(row=index//2, column=index%2, sticky="nsew", padx=(0 if index%2 == 0 else 13, 0), pady=(0, 12))
            parent.grid_columnconfigure(index%2, weight=1, uniform="task_cards")
        colors = {"running": ("#e0f6e8", "#219363"), "succeeded": ("#eeebff", "#8569db"), "pending": ("#fff2d9", "#c48b26"), "cancelled": ("#fbe9e8", "#b86b68"), "failed": ("#fbe5e5", "#c55353")}
        icon_bg, icon_color = colors.get(row["status"], colors["pending"])
        latest = next((item for item in sorted(self.snapshot.get("activity", []), key=lambda item: item["created"], reverse=True) if item.get("task_id") == row["id"]), None)
        outputs = task_output_summary(self.snapshot, row["id"])
        output_button = self.output_button(card, "View files" if self.language == "en" else "查看文件", lambda key=row["id"]:self.open_task_files(key), row["id"]) if outputs.get("count") else None
        def draw(event):
            width = event.width
            card.delete("all")
            active = row["status"] == "running"
            self.surface_layers(card, width, 240, "#f3fcf6" if active else self.panel, "#cfe9d7" if active else "#e7ece5")
            self.round_shape(card, 19, 17, 39, 39, icon_bg, 12)
            card.create_rectangle(30, 29, 47, 43, outline=icon_color, width=2)
            card.create_line(30, 33, 47, 33, fill=icon_color, width=2)
            card.create_line(34, 27, 34, 31, fill=icon_color, width=2)
            pill_text = row["values"][2]
            import tkinter.font as font
            pill_width = font.Font(root=self.root, family=self.font, size=-13).measure(pill_text)+26
            pill_colors = {"running": ("#24845b", "#e5f5eb"), "succeeded": ("#24845b", "#e5f5eb"), "pending": ("#8c712e", "#fff3d9"), "cancelled": ("#946461", "#f6e9e6"), "failed": ("#b4554a", "#fbe8e4")}
            pill_fg, pill_bg = pill_colors.get(row["status"], pill_colors["pending"])
            self.pill(card, width-pill_width-20, 22, pill_text, pill_fg, pill_bg)
            self.draw_participant_group(card,activity_participants(self.snapshot,row['id']),width-pill_width-32,22,lambda key=row['id']:self.open_task(key))
            card.create_text(20, 76, text=self.cut_text(row["values"][0], width-40, 18, True), anchor="w", fill=self.fg, font=(self.font, -18, "bold"))
            progress = task_progress(self.snapshot, row["id"])
            description = progress["current_step"].split("\n",1)[0] if progress["current_step"] else (row.get("run") or {}).get("lifecycle_reason") or activity_summary(self.snapshot, row["id"], self.language)
            card.create_text(20, 103, text=self.cut_text(description, width-40, 14), anchor="w", fill=self.muted, font=(self.font, -14))
            progress = task_progress(self.snapshot, row["id"])
            owner = progress["lead"]["agent"]
            owner_name = profile_reference(owner,self.language) if owner else ("Unassigned" if self.language == "en" else "未分配")
            if owner:
                role=next((a.get("work_type") for a in self.snapshot.get("agent_run_assignments",[]) if a["agent_id"]==owner["id"] and a["run_id"]==progress["current_run_id"]),None)
                owner_name += " · "+work_type_label(role,self.language)
            observed = participant_observation(owner, self.snapshot, self.language, timezone=self.timezone)
            owner_line = participant_caption(progress, self.language) + owner_name + " · " + observed + (" · Run " if self.language == "en" else " · 运行 ") + str(progress["current_run_id"] or "—")
            detail = owner_line + " | " + (row["warning"] or (self.t("最新阶段") + ": " + row["values"][3]))
            color = "#8b6b36" if row["warning"] else self.muted
            card.create_text(20, 127, text=self.cut_text(detail, width-40, 12), anchor="w", fill=color, font=(self.font, -12))
            card.create_line(20, 142, width-20, 142, fill="#e4eee5" if active else "#edf0ea")
            mode = "心跳跟踪" if row["run"] and row["run"].get("tracking_mode") == "heartbeat" else "手动记录"
            counts = progress["counts"]
            footer = (f"{counts['completed']:g}/{counts['total']:g} {counts['unit']}" if counts else self.t(mode)) + "  ·  " + row["values"][5]
            card.create_text(20, 156, text=self.cut_text(footer, width-65, 12), anchor="w", fill=self.muted, font=(self.font, -12))
            card.create_text(width-23, 154, text="›", fill=self.accent, font=(self.font, -23))
            card.create_line(20,171,width-20,171,fill="#e4eee5")
            available = max(60,width-(165 if output_button is not None else 40))
            card.create_text(20,188,text=self.cut_text(output_summary_text(outputs,self.language),available,12),anchor="w",fill=self.accent,font=(self.font,-12,"bold"))
            card.create_text(20,211,text=self.cut_text(output_main_text(outputs,self.language),available,11),anchor="w",fill=self.muted,font=(self.font,-11))
            if output_button is not None:
                card.create_window(width-20,201,window=output_button,anchor="e")
        card.bind("<Configure>", draw)
        def update_live():
            latest_row = next((item for item in self.rows if item["id"] == row["id"]), None)
            if latest_row and card.winfo_exists():
                row.update(latest_row)
                from types import SimpleNamespace
                draw(SimpleNamespace(width=card.winfo_width()))
        self.live_updates.append(update_live)
        card.bind("<Button-1>", lambda event: self.open_task(row["id"]))
        card.bind("<Return>", lambda event: self.open_task(row["id"]))
        return card

    def resource_card(self, parent):
        card = self.tk.Canvas(parent, height=181, bg=self.bg, bd=0, highlightthickness=0)
        metrics = self.metric_values
        memory = percent(metrics.get("cgroup_memory_current"), metrics.get("memory_quota"))
        if memory is None and metrics.get("memory_total") and metrics.get("memory_available") is not None:
            memory = percent(metrics["memory_total"]-metrics["memory_available"], metrics["memory_total"])
        values = [("CPU", metrics.get("cpu_percent"), "#54bd84"), (self.t("内存"), memory, "#6b9de8"), (self.t("磁盘"), percent(metrics.get("disk_used"), metrics.get("disk_total")), "#e7a64b")]
        def draw(event):
            width = event.width
            card.delete("all")
            self.surface_layers(card, width, 181)
            card.create_text(19, 26, text=self.t("资源使用情况"), anchor="w", fill=self.fg, font=(self.font, -17, "bold"))
            for index, (title, value, color) in enumerate(values):
                center, y, radius = width * (index+.5)/3, 88, 31
                card.create_oval(center-radius, y-radius, center+radius, y+radius, outline="#edf0ec", width=6)
                if value is not None:
                    card.create_arc(center-radius, y-radius, center+radius, y+radius, start=90, extent=-max(.01, min(99.99,value))*3.6, style="arc", outline=color, width=6)
                card.create_text(center, y, text=f"{value:.0f}%" if value is not None else "—", fill=self.fg, font=(self.font, -18, "bold"))
                card.create_text(center, 135, text=title, fill=self.muted, font=(self.font, -13))
            card.create_text(19, 159, text=self.cut_text(self.t("可见指标；内存优先使用容器配额"), width-38, 11), anchor="w", fill=self.muted, font=(self.font, -11))
        card.bind("<Configure>", draw)
        return card

    def schedules_summary_card(self, parent):
        card = self.tk.Canvas(parent, height=181, bg=self.bg, bd=0, highlightthickness=0, cursor="hand2", takefocus=1)
        records = self.snapshot.get("schedules", [])
        def draw(event):
            width = event.width
            card.delete("all")
            self.surface_layers(card, width, 181)
            card.create_text(19, 26, text=self.t("定时任务"), anchor="w", fill=self.fg, font=(self.font, -17, "bold"))
            card.create_text(width-22, 26, text=self.t("全部"), anchor="e", fill=self.accent, font=(self.font, -13))
            for index, record in enumerate(records[:2]):
                y = 68 + index*54
                card.create_oval(20, y-12, 46, y+14, fill="#e2f7e9", outline="")
                card.create_oval(27, y-5, 39, y+7, outline=self.accent, width=2)
                card.create_line(33, y-2, 33, y+2, 36, y+2, fill=self.accent)
                card.create_text(57, y-3, text=self.cut_text(record["name"], width-95, 15, True), anchor="w", fill=self.fg, font=(self.font, -15, "bold"))
                state, timing = schedule_summary(record, self.language, self.timezone)
                card.create_text(57, y+19, text=self.cut_text(state+" · "+timing, width-80, 12), anchor="w", fill=self.muted, font=(self.font, -12))
            if not records:
                card.create_text(20, 76, text=self.t("尚未登记定时任务"), anchor="w", fill=self.muted, font=(self.font, -15))
            boundary = "Recorded observations · not live scheduling" if self.language == "en" else "已记录观察 · 非实时调度状态"
            card.create_text(20, 157, text=boundary, anchor="w", fill=self.muted, font=(self.font, -11))
        card.bind("<Configure>", draw)
        card.bind("<Button-1>", lambda event: self.navigate("schedules"))
        card.bind("<Return>", lambda event: self.navigate("schedules"))
        return card

    def render_overview(self):
        self.workspace_toolbar()
        area = self.scroll_area()
        filtered = workspace_rows(self.rows, self.workspace_filter, self.search_query.get())
        grid = self.card_grid(area, minimum=370, maximum=2)
        for index, row in enumerate(filtered[:4]):
            self.airy_task_card(grid, row, index)
        if not filtered:
            card, body = self.card(area, 115)
            card.pack(fill="x", pady=(0, 12))
            self.label(body, "该状态暂无任务", 18, self.muted).pack(anchor="w", pady=20)
        if len(filtered) > 4:
            more = self.label(area, self.t("另有 {count} 个活动，可在活动页查看", count=len(filtered)-4), 13, self.accent)
            more.pack(anchor="w", pady=(0, 10))
            more.bind("<Button-1>", lambda event: self.navigate("conversations"))
        bottom = self.tk.Frame(area, bg=self.bg)
        bottom.pack(fill="x", pady=(3, 0))
        bottom.grid_columnconfigure(0, weight=1, uniform="summary")
        bottom.grid_columnconfigure(1, weight=1, uniform="summary")
        self.resource_card(bottom).grid(row=0, column=0, sticky="nsew")
        self.schedules_summary_card(bottom).grid(row=0, column=1, sticky="nsew", padx=(13, 0))


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
        header = self.tk.Frame(self.content, bg=self.bg)
        header.pack(fill="x", pady=(5, 8))
        titleline = self.tk.Frame(header, bg=self.bg)
        titleline.pack(fill="x")
        self.filter_chip(titleline, "←", self.go_back).pack(side="left", padx=(0, 10))
        self.label(titleline, row["values"][0], 21, bold=True, raw=True).pack(side="left")
        self.label(titleline, row["values"][2], 13, self.accent, raw=True).pack(side="right", padx=6)
        progress = task_progress(self.snapshot, self.selected_task)
        agent = progress["lead"]["agent"]
        owner = profile_reference(agent,self.language) if agent else ("Unassigned" if en else "未分配")
        current = [item for item in self.snapshot.get('agent_run_assignments',[]) if agent and item['agent_id']==agent['id'] and item['run_id']==progress['current_run_id']]
        work = work_type_label(current[0]["work_type"], self.language) if current else ("Standby" if en else "待命") if agent and agent.get("status") == "idle" else ("Unconfirmed" if en else "未确认")
        meta = participant_caption(progress, self.language) + owner + "  ·  " + work + "  ·  " + ("Updated: " if en else "更新：") + row["values"][5]
        meta += " · " + participant_observation(agent, self.snapshot, self.language, timezone=self.timezone) + (" · Run " if en else " · 运行 ") + str(progress["current_run_id"] or "—")
        self.label(header, meta, 12, self.muted, raw=True).pack(anchor="w", pady=(7, 3))
        self.render_output_bar(header, self.selected_task, detail=True)
        closeout = (row.get("run") or {}).get("closeout")
        if closeout:
            pinned = ("Deliverables: " if en else "交付：") + self.cut_text(closeout["summary"], 600, 12)
            self.label(header, pinned, 12, self.fg, raw=True).pack(anchor="w", pady=(3, 2))
            checked = verification_label(closeout["verification"], self.language) + " · " + ("Limits: " if en else "限制：") + self.cut_text(closeout["limits"], 580, 12)
            self.label(header, checked, 12, self.muted, raw=True).pack(anchor="w")
        tabs = self.tk.Frame(header, bg=self.bg)
        tabs.pack(fill="x", pady=(4, 0))
        files = [item for item in self.snapshot.get("artifacts", []) if item["task_id"] == self.selected_task]
        self.filter_chip(tabs, "Timeline" if en else "时间线", lambda: self.set_detail_tab("timeline"), getattr(self, "detail_tab", "timeline") == "timeline").pack(side="left", padx=(0, 7))
        self.filter_chip(tabs, ("Files" if en else "文件")+f" · {len(files)}", lambda: self.set_detail_tab("files"), getattr(self, "detail_tab", "timeline") == "files").pack(side="left")
        self.filter_chip(tabs, ("Less ⌃" if en else "收起 ⌃") if getattr(self, "detail_meta", False) else ("Details ⌄" if en else "更多信息 ⌄"), self.toggle_detail_meta).pack(side="right")
        area = self.scroll_area()
        if getattr(self, "detail_tab", "timeline") == "timeline":
            self.render_task_participants(area,self.selected_task)
            self.render_progress_detail(area, self.selected_task, progress)
        lifecycle = row.get("run") or {}
        if getattr(self, "detail_tab", "timeline") == "files" and not getattr(self, "detail_meta", False):
            self.render_task_files(area, files)
            return
        if closeout:
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
        elif lifecycle.get("status") == "succeeded":
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
        records = timeline_records(self.snapshot, self.selected_task)
        self.label(area, "Newest first · original timestamps" if en else "最新在前 · 按原始时间排序", 13, self.muted, raw=True).pack(anchor="w", pady=(0, 10))
        for record in records:
            surface, inner = self.card(area, 150)
            surface.pack(fill="x", pady=(0, 12))
            title = self.t(record["title"]) if record["kind"] in ("event", "note") else stage_label(record["title"], self.language)
            if record["state"]:
                title += "  ·  " + self.t(STATES.get(record["state"], record["state"]))
            self.label(inner, title, 16, self.accent, True, raw=True).pack(anchor="w")
            self.label(inner, self.stamp(record["created"]), 12, self.muted).pack(anchor="w", pady=(3, 9))
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
        if not records:
            self.label(area, "暂无工作记录", 17, self.muted).pack(anchor="w", pady=15)


    def render_task_files(self, area, files):
        en = self.language == "en"
        self.label(area, "Registered outputs only · private task folder" if en else "只列已登记正式产出 · 私有任务文件夹", 12, self.muted, raw=True).pack(anchor="w", pady=(2, 12))
        for artifact in files:
            surface, body = self.card(area, 140)
            surface.pack(fill="x", pady=(0, 12))
            self.label(body, artifact["title"], 17, bold=True, raw=True).pack(anchor="w")
            line = artifact_kind_label(artifact["kind"], self.language) + f" · {artifact['size']:,} B · " + self.stamp(artifact["created"])
            self.label(body, line, 12, self.muted, raw=True).pack(anchor="w", pady=5)
            self.label(body, artifact_delivery_label(artifact, self.language), 12, self.muted, raw=True, wrap=760).pack(anchor="w", pady=3)
            self.label(body, artifact["relative_path"], 11, self.muted, raw=True, wrap=760).pack(anchor="w")
            self.label(body, "SHA-256 · " + artifact["sha256"][:20] + "…", 11, self.muted, raw=True).pack(anchor="w", pady=5)
            if artifact["relative_path"].endswith(".png"):
                self.filter_chip(body, "Preview PNG" if en else "预览 PNG", lambda key=artifact["id"]: self.preview_artifact(key)).pack(anchor="w", pady=4)
            elif Path(artifact["relative_path"]).suffix in (".txt", ".md", ".json", ".csv"):
                self.filter_chip(body, "Read text" if en else "阅读文本", lambda key=artifact["id"]: self.preview_text_artifact(key)).pack(anchor="w", pady=4)
            elif artifact["kind"] == "video":
                self.label(body, "Video metadata only; open the output folder to use the file. No automatic playback." if en else "视频仅登记元数据；可从成果文件夹使用文件，不会自动播放。", 11, self.muted, raw=True, wrap=760).pack(anchor="w", pady=4)
            else:
                self.label(body, "Metadata only; view the delivered attachment separately" if en else "仅显示登记信息；请查看另行交付的附件", 11, self.muted, raw=True).pack(anchor="w", pady=4)
            self.fit_card(surface, body)
        if not files:
            self.label(area, "No registered outputs yet" if en else "尚无已登记产出", 17, self.muted, raw=True).pack(anchor="w", pady=20)

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
        rows=activity_participants(self.snapshot,task_id)
        if not rows:return
        en=self.language=='en'
        self.label(area,('Activity participants · ' if en else '活动参与者 · ')+str(len(rows)),16,self.fg,True,raw=True).pack(anchor='w',pady=(0,8))
        grid=self.card_grid(area,minimum=285,maximum=3)
        for row in rows:
            agent=row['agent'];roles=list(dict.fromkeys(work_type_label(a['work_type'],self.language) for a in row['assignments']))
            summary=('Recorded roles · ' if en else '已登记职责 · ')+' / '.join(roles)
            if getattr(self,'detail_meta',False):
                summary+='\n'+('Nickname · ' if en else '昵称 · ')+agent_text(agent,'name',self.language)+'\n'+identity_label(agent,self.language)
                summary+='\n'+source_label(agent,self.language)+(' · Identity checked at ' if en else ' · 身份核验时间 ')+timestamp_label(agent.get('identity_observed_at'),self.timezone)
                summary+='\n'+('Panel-local display ID; not a platform UUID' if en else '面板短编号，不是平台 UUID')
                for assignment in row['assignments']:
                    summary+='\n'+(assignment['run_id'] or ('Owner record' if en else '负责人记录'))+' · '+work_type_label(assignment['work_type'],self.language)
            self.compact_row(grid,('Panel ID ' if en else '面板编号 ')+row['short_id'],summary,participant_observation(agent,self.snapshot,self.language,timezone=self.timezone),avatar=agent)

    def compact_row(self, parent, title, summary, status="", command=None, avatar=None, participants=None):
        surface, box = self.card(parent, 170)
        if hasattr(parent, "card_items"):
            parent.card_items.append(surface)
            parent.reflow_cards()
        else:
            surface.pack(fill="x", pady=(0, 8))
        if participants:
            top=self.tk.Frame(box,bg=self.panel);top.pack(fill='x',pady=(0,8))
            self.label(top,status,12,self.accent,raw=True).pack(side='right')
            width=min(3,len(participants))*24+10+(32 if len(participants)>3 else 0)
            group=self.tk.Canvas(top,width=width,height=32,bg=self.panel,highlightthickness=0)
            group.pack(side='right',padx=(0,10));self.draw_participant_group(group,participants,width,0,command)
        if status and not avatar and not participants:
            self.label(box, status, 14, self.accent, raw=True).pack(anchor="w", fill="x", pady=(0, 8))
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
            self.label(box, title, 20, self.fg, True, raw=True).pack(anchor="w", fill="x")
        self.label(box, summary, 15, self.muted, raw=True).pack(anchor="w", fill="x", pady=(9, 0))
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
        box.bind("<Configure>", wrap_children, add="+")
        self.fit_card(surface, box)
        return box

    def render_conversation_list(self, selection=()):
        self.workspace_toolbar()
        area = self.scroll_area()
        rows = workspace_rows(self.rows, self.workspace_filter, self.search_query.get())
        grid = self.card_grid(area, minimum=370, maximum=2)
        for row in rows:
            values = row["values"]
            summary = values[1] + " · " + values[3] + "\n" + self.t("最后更新：") + values[5]
            progress = task_progress(self.snapshot, row["id"])
            owner = progress["lead"]["agent"]
            owner_name = profile_reference(owner,self.language) if owner else ("Unassigned" if self.language == "en" else "未分配")
            if owner:
                role=next((a.get("work_type") for a in self.snapshot.get("agent_run_assignments",[]) if a["agent_id"]==owner["id"] and a["run_id"]==progress["current_run_id"]),None)
                owner_name += " · "+work_type_label(role,self.language)
            observed = participant_observation(owner, self.snapshot, self.language, timezone=self.timezone)
            owner_caption = participant_caption(progress, self.language)
            summary = owner_caption + owner_name + " · " + observed + (" · Run " if self.language == "en" else " · 运行 ") + str(progress["current_run_id"] or "—") + " · " + values[1] + "\n" + values[3] + " · " + self.t("最后更新：") + values[5]
            if len(progress.get("unpaused_runs", [])) > 1:
                summary += "\n" + ("Unfinished runs: " if self.language == "en" else "未完成运行：") + str(len(progress["unpaused_runs"]))
            if progress["current_step"]:
                step = progress["current_step"].split("\n", 1)[0]
                summary += "\n" + (("Task update: " if self.language == "en" else "任务近况：") if progress.get("scope") == "task" else ("Step: " if self.language == "en" else "当前步骤：")) + step
            if progress["counts"]:
                count = progress["counts"]
                summary += f"\n{count['completed']:g}/{count['total']:g} {count['unit']}"
            state = values[2] + ((" · Older update" if self.language == "en" else " · 更新较旧待核对") if row["warning"] else "")
            box = self.compact_row(grid, values[0], summary, state, lambda key=row["id"]: self.open_task(key), participants=activity_participants(self.snapshot,row["id"]))
            self.render_output_bar(box, row["id"])
        if not rows:
            self.label(area, "该状态暂无任务", 16, self.muted).pack(anchor="w", pady=20)

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
        area = self.scroll_area()
        en = self.language == "en"
        self.label(area, "Platform observations and result snapshots" if en else "平台配置观察与结果快照", 18, self.accent, True, raw=True).pack(anchor="w")
        self.label(area, "Saved result snapshots do not prove schedules are enabled. Every 5 seconds refreshes local data only, without polling GitHub; external results require manual sync." if en else "已保存的结果快照不证明定时器已启用。每 5 秒只刷新本地数据，不轮询 GitHub；外部结果须手动同步。", 13, self.muted, raw=True, wrap=800).pack(anchor="w", pady=(6, 14))
        grid = self.card_grid(area, minimum=370, maximum=2)
        for record in self.snapshot.get("schedules", []):
            state, timing = schedule_summary(record, self.language, self.timezone)
            result = schedule_result_view(record, self.language, self.timezone)
            platform = schedule_platform_view(record, self.language, self.timezone)
            if result:
                timing = ((platform["compact"]+"\n") if platform else "") + "\n".join(result["compact"])
            box = self.compact_row(grid, record["name"], timing, state)
            if result and result["error"]:
                self.label(box, result["error"], 14, "#9c611c", raw=True, wrap=800).pack(anchor="w", pady=(5, 0))
            expanded = record["id"] in getattr(self, "expanded_schedules", set())
            self.filter_chip(box, ("Less ⌃" if en else "收起 ⌃") if expanded else ("Details ⌄" if en else "详情 ⌄"), lambda key=record["id"]: self.toggle_registry_detail("schedules", key)).pack(anchor="e", pady=(4,0))
            if expanded:
                technical_labels = {"平台任务 ID", "Platform task ID", "计划", "Schedule", "源运行编号", "Source run ID", "状态文件", "Status path", "索引文件", "Index path", "Status blob SHA", "Index blob SHA", "状态来源 URL", "Status source URL", "索引来源 URL", "Index source URL"}
                technical = []
                for label, value in ((platform["rows"] if platform else []) + (result["rows"] if result else [])):
                    if label in technical_labels:
                        technical.append((label,value))
                    else:
                        self.label(box,label+": "+str(value),14,self.muted,raw=True,wrap=800).pack(anchor="w",pady=3)
                if technical:
                    technical_open = record["id"] in getattr(self, "expanded_schedule_technical", set())
                    self.filter_chip(box, ("Hide technical details ⌃" if en else "收起技术信息 ⌃") if technical_open else ("Technical details ⌄" if en else "技术信息 ⌄"), lambda key=record["id"]: self.toggle_registry_detail("schedule_technical",key)).pack(anchor="w",pady=(8,4))
                    if technical_open:
                        for label,value in technical:
                            self.label(box,label+": "+str(value),13,self.muted,raw=True,wrap=800).pack(anchor="w",pady=3)
                metadata = (("Project" if en else "项目",record.get("project")), ("Source" if en else "来源",record.get("source")), ("Registered state (metadata)" if en else "登记状态（元数据）",record.get("state")), ("Registered planned time (unverified)" if en else "登记计划时间（未核验）",self.stamp(record["next_run"]) if record.get("next_run") is not None else ("Unknown" if en else "未知")), ("Last recorded update" if en else "最近登记更新",self.stamp(record["updated"]) if record.get("updated") is not None else ("Unknown" if en else "未知")))
                for label, value in metadata:
                    self.label(box,label+": "+str(value or "—"),14,self.muted,raw=True,wrap=800).pack(anchor="w",pady=3)
                self.label(box,"Registration does not create, start or resume a scheduler" if en else "登记不会创建、启动或恢复任何定时器",14,self.muted,raw=True,wrap=800).pack(anchor="w",pady=(5,0))
        if not self.snapshot.get("schedules"):
            self.label(area, "尚未登记定时任务", 16, self.muted).pack(anchor="w", pady=18)

    def render_software(self):
        # Recovery reconstruction of read-only compact software detail controls.
        area = self.scroll_area()
        en = self.language == "en"
        records = list(self.snapshot.get("software", []))
        if not any(item.get("kind") == "dots-panel" for item in records):
            records.insert(0,{"id":"current-viewer","name":"dots-panel","description":self.t("此窗口正在运行"),"kind":"dots-panel","version":VERSION,"available":True,"controls":["close_current_viewer"]})
        grid = self.card_grid(area, minimum=285, maximum=3)
        for record in records:
            available = record.get("available")
            state = self.t("可用" if available is True else "未检测到" if available is False else "未验证")
            box = self.compact_row(grid, record["name"], str(record.get("version") or "—"), state)
            key = record.get("id", record["name"])
            expanded = key in getattr(self, "expanded_software", set())
            self.filter_chip(box,("Less ⌃" if en else "收起 ⌃") if expanded else ("Details ⌄" if en else "详情 ⌄"),lambda key=key:self.toggle_registry_detail("software",key)).pack(anchor="e",pady=(4,0))
            if expanded:
                for label,value in (("Description" if en else "简介",record.get("description")),("Kind" if en else "类型",record.get("kind")),("Availability" if en else "可用性",state),("Version" if en else "版本",record.get("version")),("Checked" if en else "检测时间",observation_label(record.get("verified_at"),self.language,self.timezone))):
                    self.label(box,label+": "+str(value or "—"),14,self.muted,raw=True,wrap=800).pack(anchor="w",pady=3)
                self.label(box,"Detected availability is not proof of a running service" if en else "检测到可用不代表服务正在运行",14,self.muted,raw=True,wrap=800).pack(anchor="w",pady=4)
                if "close_current_viewer" in record.get("controls",[]) and record.get("kind")=="dots-panel":
                    self.filter_chip(box,self.t("关闭此窗口"),self.close_viewer).pack(anchor="w",pady=(5,0))
                else:
                    self.label(box,"No launch/stop controls are connected" if en else "未接入启动或停止控制",14,self.muted,raw=True).pack(anchor="w",pady=4)


    def render_install_doctor(self, area, report):
        en = self.language == "en"
        section = self.tk.Frame(area, bg=self.panel, padx=12, pady=10)
        section.pack(fill="x", pady=(0, 12))
        self.label(section, "Installation checks · read-only" if en else "安装自检 · 只读", 16, self.fg, True, raw=True).pack(anchor="w")
        local, manual = doctor_rows(report, self.language)
        passed = sum(row["status"] == "ok" for row in report.get("checks", []))
        summary = (f"Local checks: {passed}/{len(local)} OK · permission probes only" if en else f"本机检查：{passed}/{len(local)} 通过 · 仅探测权限") if local else ("No diagnostics available" if en else "尚未运行检查")
        self.label(section, summary, 14, self.muted, raw=True).pack(anchor="w", pady=(4, 5))
        for title, value in manual:
            self.label(section, title + " · " + value, 14, self.muted, raw=True).pack(anchor="w", pady=2)
        def toggle():
            self.doctor_expanded = not getattr(self, "doctor_expanded", False)
            self.render_page()
        self.filter_chip(section, ("Less ⌃" if en else "收起 ⌃") if getattr(self, "doctor_expanded", False) else ("Local check details ⌄" if en else "本机检查详情 ⌄"), toggle).pack(anchor="w", pady=(6, 3))
        if getattr(self, "doctor_expanded", False):
            for title, value in local:
                self.label(section, title + " · " + value, 14, self.muted, raw=True).pack(anchor="w", pady=2)
            for component, observation in report.get("observations", {}).items():
                if observation.get("evidence"):
                    when = self.stamp(observation["observed_at"]) if observation.get("observed_at") is not None else "—"
                    self.label(section, when + " · " + observation["evidence"], 11, self.muted, raw=True, wrap=800).pack(anchor="w", pady=2)
        self.label(section, "No account scan, installation or scheduling; source availability does not verify account setup" if en else "不扫描账户、不安装、不创建定时器；源码可用不等于账户已配置", 11, self.muted, raw=True, wrap=800).pack(anchor="w", pady=(5, 0))

    def render_about(self):
        area = self.scroll_area()
        en = self.language == "en"
        about = self.snapshot.get("about", {})
        release = about.get("release", {})
        labels = {"unknown": ("未核验", "Not checked"), "unpublished": ("未发布", "Unpublished"), "published": ("已发布", "Published"),
                  "matched": ("已核验一致", "Verified matching"), "different": ("已核验不同", "Verified different"), "local_changes": ("有本地更改", "Local changes")}
        def state_label(value):
            return labels.get(value, labels["unknown"])[1 if en else 0]
        rows = [("Installed version" if en else "当前安装版本", about.get("installed_version", VERSION)),
                ("Published release" if en else "已发布版本", state_label(release.get("release_status", "unknown")) + (" · " + release["release_tag"] if release.get("release_tag") else "")),
                ("Source synchronization" if en else "源码同步状态", state_label(release.get("sync_status", "unknown"))),
                ("Verified remote commit" if en else "已核验远端提交", release.get("remote_commit") or "—"),
                ("Last checked" if en else "最近核验", self.stamp(release["checked_at"]) if release.get("checked_at") else ("Not checked" if en else "尚未核验"))]
        for title, value in rows:
            row = self.tk.Frame(area, bg=self.panel, highlightthickness=1, highlightbackground="#e3ebe1", padx=13, pady=11)
            row.pack(fill="x", pady=(0, 6))
            self.label(row, title, 15, self.muted, raw=True).pack(side="left", padx=(0, 25))
            value_label = self.label(row, value, 15, self.fg, raw=True, wrap=620)
            value_label.pack(side="left", fill="x", expand=True)
            row.bind("<Configure>", lambda event, label=value_label: label.configure(wraplength=max(150, event.width-200)))
        try:
            url = verified_repository_url(release.get("repo_url"))
        except ValueError:
            url = None
        if url:
            def open_repository():
                import webbrowser
                webbrowser.open(url)
            self.filter_chip(area, "GitHub project ↗" if en else "GitHub 项目 ↗", open_repository).pack(anchor="w", pady=(7, 4))
            self.label(area, url, 14, self.muted, raw=True).pack(anchor="w", pady=(0, 9))
        else:
            self.label(area, "No verified GitHub project configured" if en else "尚未登记已核验的 GitHub 项目", 14, self.muted, raw=True).pack(anchor="w", pady=8)
        self.render_install_doctor(area, about.get("doctor", {}))
        self.label(area, "Installation notes" if en else "本安装更新说明", 17, bold=True, raw=True).pack(anchor="w", pady=(12, 7))
        for item in about.get("install_notes", []):
            self.label(area, "• "+item.get("en" if en else "zh", ""), 15, self.muted, raw=True, wrap=800).pack(anchor="w", pady=4)
        note = "Local version is not remote release status. These are manually verified observations, not live checks. This page does not update, publish, or use credentials." if en else "本地版本不等于远端发布状态。此处是人工核验记录，不是实时查询；本页不更新安装、不发布代码、不使用凭据。"
        self.label(area, note, 14, self.muted, raw=True, wrap=800).pack(anchor="w", pady=(15, 5))


    def render_rules(self):
        area = self.scroll_area()
        en = self.language == "en"
        language = "en" if en else "zh"
        data = self.snapshot.get("rules", {})
        levels = {"enforced": ("程序校验", "App enforced"), "workflow": ("执行约定", "Workflow"), "planned": ("待落地", "Planned")}
        self.label(area, ("Rules version · " if en else "规则版本 · ") + data.get("version", "—"), 14, self.accent, raw=True).pack(anchor="w", pady=(0, 6))
        note = "App enforced: checked by existing panel operations. Workflow: followed by the executor. Planned: not implemented. These guidelines do not grant permissions." if en else "程序校验：现有面板操作已实施检查；执行约定：由执行者遵循；待落地：尚未实现。规则本身不授予权限。"
        self.label(area, note, 14, self.muted, raw=True, wrap=830).pack(anchor="w", pady=(0, 12))
        self.label(area, "Your installed Skills" if en else "用户安装的 Skills", 16, self.fg, True, raw=True).pack(anchor="w", pady=(0, 4))
        self.label(area, "Manually recorded summaries · no automatic sync or guaranteed activation" if en else "人工登记的用途摘要 · 不自动同步，不保证每次触发", 14, self.muted, raw=True, wrap=830).pack(anchor="w", pady=(0, 8))
        skills = [item for item in data.get("skills", []) if item.get("scope") == "user_installed"]
        grid = self.card_grid(area, minimum=300, maximum=3)
        for item in skills:
            key = item.get("id", item["name"])
            source = item.get("source", {})
            box = self.compact_row(grid, agent_text(item, "name", language), agent_text(item, "purpose", language), skill_status_label(item.get("status"), language))
            expanded = key in getattr(self, "expanded_skills", set())
            self.filter_chip(box, ("Less ⌃" if en else "收起 ⌃") if expanded else ("Details ⌄" if en else "详情 ⌄"), lambda key=key: self.toggle_registry_detail("skills", key)).pack(anchor="w", pady=(12, 0))
            if expanded:
                self.label(box, skill_origin_label(source.get("origin"), language)+" · "+skill_publication_label(source.get("publication"), language), 14, self.muted, raw=True).pack(anchor="w", fill="x", pady=(8, 0))
                self.label(box, ("When: " if en else "使用场景：") + agent_text(item, "when_used", language), 15, self.fg, raw=True).pack(anchor="w", fill="x", pady=(8, 0))
                observation = ("Manual observation · " if en else "人工观察 · ") + self.stamp(item.get("observed_at")) + " · " + skill_version_label(item.get("version_status"), language)
                self.label(box, observation, 14, self.muted, raw=True).pack(anchor="w", fill="x", pady=(8, 0))
                if item.get("version_note") or item.get("version_note_en"):
                    self.label(box, agent_text(item, "version_note", language), 14, self.muted, raw=True).pack(anchor="w", fill="x")
                try:
                    url = verified_skill_url(item.get("url"))
                except ValueError:
                    url = None
                if url:
                    def open_skill(target=url):
                        import webbrowser
                        webbrowser.open(target)
                    self.filter_chip(box, "Manage ↗" if en else "管理 ↗", open_skill).pack(anchor="w", pady=(8, 0))
        if not skills:
            self.label(area, "No user Skills registered" if en else "尚未登记用户 Skills", 14, self.muted, raw=True).pack(anchor="w", pady=(0, 8))
        # Preserve old explicit links without inventing a catalog record from them.
        if not any(item.get("url") == data.get("skill_url") for item in skills):
            try:
                legacy_url = verified_skill_url(data.get("skill_url"))
            except ValueError:
                legacy_url = None
            if legacy_url:
                def open_legacy_skill(target=legacy_url):
                    import webbrowser
                    webbrowser.open(target)
                self.filter_chip(area, "Task skill ↗" if en else "任务 Skill ↗", open_legacy_skill).pack(anchor="w", pady=(0, 8))
        self.label(area, "Project guidelines" if en else "项目规范", 16, self.fg, True, raw=True).pack(anchor="w", pady=(8, 8))
        for group in data.get("groups", []):
            box = self.tk.Frame(area, bg=self.panel, highlightthickness=1, highlightbackground="#e3ebe1", padx=12, pady=9)
            box.pack(fill="x", pady=(0, 8))
            body = self.tk.Frame(box, bg=self.panel)
            caption = group["title"][language]
            key = group.get("id", caption)
            expanded = key in getattr(self, "expanded_rule_groups", set())
            self.filter_chip(box, caption + ("  ⌃" if expanded else "  ⌄"), lambda key=key: self.toggle_registry_detail("rule_groups", key)).pack(anchor="w")
            self.label(box, (str(len(group["items"])) + (" guidelines" if en else " 条规范")), 13, self.muted, raw=True).pack(anchor="w", pady=(4, 0))
            if expanded:
                body.pack(fill="x", pady=(8, 0))
            for rule in group["items"]:
                level = levels.get(rule["level"], levels["planned"])[1 if en else 0]
                self.label(body, level + " · " + rule["title"][language], 14, self.accent, True, raw=True).pack(anchor="w", pady=(9, 3))
                self.label(body, rule["body"][language], 15, self.fg, raw=True, wrap=810).pack(anchor="w", pady=(0, 7))
        self.label(area, "Source: packaged project_rules.json · read-only" if en else "统一来源：项目 project_rules.json · 只读展示", 14, self.muted, raw=True).pack(anchor="w", pady=10)

    def close_viewer(self):
        from tkinter import messagebox
        if messagebox.askyesno(self.t("确认关闭此窗口？"), self.t("只关闭当前看板窗口，不会停止任务、定时任务或其他服务。可从桌面启动器重新打开。"), parent=self.root):
            if self.timer:
                self.root.after_cancel(self.timer)
            if getattr(self, "notifications", None) is not None:
                self.notifications.close()
            self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description="Read-only native dots-panel viewer (no HTTP)")
    parser.add_argument("--data-dir", type=Path, default=default_data_dir())
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
        Dashboard(root, store, Metrics(store.directory), tk, ttk, args.language or load_language(store.directory))
        root.mainloop()
    except (OSError, sqlite3.Error, tk.TclError) as error:
        print(f"Native viewer unavailable: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
