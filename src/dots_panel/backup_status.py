"""Bounded, read-only local backup evidence. Never contacts Library or restores data.

The private config opts into one STATE root. A validated local committed envelope
is historical receipt evidence, never a live assertion about remote durability.
"""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import stat
import time

CONFIG_SCHEMA = 'dots-panel.backup-status-config.v1'
OBSERVATION_SCHEMA = 'dots-panel.backup-observation.v1'
WATCH_SCHEMA = 'dots-panel.task-watch-observation.v1'
MAX_ENVELOPE = 16 * 1024 * 1024
STAGES = frozenset(('preflight', 'prepare', 'verify', 'upload', 'readback', 'index', 'commit'))
RESULTS = frozenset(('failed', 'unavailable', 'running', 'committed', 'unchanged'))


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('duplicate_key')
        result[key] = value
    return result


def _text(value, limit=512):
    if not isinstance(value, str) or not value or len(value) > limit or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError('invalid_text')
    return value


def _absolute(value):
    path = Path(_text(str(value), 4096))
    if not path.is_absolute() or '..' in path.parts or str(path) != str(value):
        raise ValueError('invalid_path')
    return path


def _open_directory(path, private=False):
    """Walk with dir_fd/O_NOFOLLOW; a replaced ancestor cannot redirect the read."""
    path = _absolute(path)
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        info = os.fstat(fd)
        if private and (info.st_uid != os.geteuid() or info.st_mode & 0o077):
            raise ValueError('unsafe_directory')
        return fd
    except BaseException:
        os.close(fd)
        raise


def _read_at(parent, relative, limit=65536):
    parts = relative.split('/')
    if any(not part or part in ('.', '..') for part in parts):
        raise ValueError('invalid_path')
    folder = os.dup(parent)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=folder)
            os.close(folder)
            folder = child
            info = os.fstat(folder)
            if info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise ValueError('unsafe_directory')
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder)
        with os.fdopen(fd, 'rb') as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid() or before.st_mode & 0o077 or before.st_size > limit:
                raise ValueError('unsafe_file')
            raw = handle.read(limit + 1)
            after = os.fstat(handle.fileno())
            if len(raw) > limit or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise ValueError('changed_file')
            value = json.loads(raw, object_pairs_hook=_pairs)
            if not isinstance(value, dict):
                raise ValueError('invalid_json')
            return value
    finally:
        os.close(folder)


def _epoch(value, now):
    if not isinstance(value, str):
        raise ValueError('invalid_time')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('invalid_time')
    stamp = parsed.timestamp()
    if not math.isfinite(stamp) or stamp <= 0 or stamp > now + 300:
        raise ValueError('invalid_time')
    return stamp


def _observation(value, now):
    if value.get('schema') != OBSERVATION_SCHEMA or value.get('result') not in RESULTS or value.get('stage') not in STAGES:
        raise ValueError('invalid_observation')
    error = value.get('error_type')
    if error is not None and (not isinstance(error, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,79}', error)):
        raise ValueError('invalid_observation')
    point = value.get('recovery_point_sha256')
    if point is not None and (not isinstance(point, str) or not re.fullmatch(r'[0-9a-f]{64}', point)):
        raise ValueError('invalid_observation')
    return {'checked_at': _epoch(value.get('checked_at'), now), 'result': value['result'],
            'stage': value['stage'], 'error_type': error, 'recovery_point_sha256': point}


def _watch_observation(value, now, stale_after):
    if set(value) != {'schema', 'status', 'checked_at', 'last_success_at', 'error_type'} or value.get('schema') != WATCH_SCHEMA or value.get('status') not in ('checked', 'failed', 'unavailable'):
        raise ValueError('invalid_watch_observation')
    checked = _epoch(value.get('checked_at'), now)
    last_good = _epoch(value['last_success_at'], now) if value['last_success_at'] is not None else None
    error = value.get('error_type')
    if error is not None and (not isinstance(error, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,79}', error)):
        raise ValueError('invalid_watch_observation')
    if last_good is not None and last_good > checked:
        raise ValueError('invalid_watch_observation')
    if value['status'] == 'checked' and (last_good != checked or error is not None):
        raise ValueError('invalid_watch_success')
    return {'status': 'stale' if value['status'] == 'checked' and now - checked > stale_after else value['status'],
            'observed_status': value['status'], 'checked_at': checked,
            'last_success_at': last_good, 'error_type': error, 'source': 'local_observation'}


def load(directory, *, source=None, now=None):
    """Read explicit private config + exact state files, returning safe display data.

    Does not create/migrate DATA, scan run directories, follow a guard, or expose
    the raw manifest, receipt, operation IDs, arbitrary errors or credentials.
    """
    now = time.time() if now is None else now
    result = {'status': 'unconfigured', 'reason': 'not_configured', 'configured': False,
              'remote_live': False, 'destination': None, 'state_dir': None,
              'last_verified': None, 'last_attempt': None, 'observation_state': 'unknown',
              'task_watch': {'status': 'unverified', 'checked_at': None, 'last_success_at': None, 'error_type': None, 'source': 'local_observation'}}
    data_fd = state_fd = None
    try:
        data_path = _absolute(directory)
        data_fd = _open_directory(data_path, private=True)
        try:
            config = _read_at(data_fd, 'config/backup-status.json')
        except FileNotFoundError:
            return result
        result.update(configured=True, status='unavailable', reason='invalid_config')
        allowed = {'schema', 'state_dir', 'destination_label', 'destination_path', 'index_library_file_id', 'stale_after_seconds'}
        if set(config) - allowed or config.get('schema') != CONFIG_SCHEMA:
            return result
        state_path = _absolute(config.get('state_dir', ''))
        roots = [data_path] + ([_absolute(source)] if source is not None else [])
        if any(state_path == root or state_path in root.parents or root in state_path.parents for root in roots):
            return result
        target = _text(config.get('index_library_file_id'), 200)
        if not re.fullmatch(r'libfile_[A-Za-z0-9_-]+', target):
            return result
        stale_after = config.get('stale_after_seconds', 7200)
        if type(stale_after) is not int or not 3600 <= stale_after <= 604800:
            return result
        result.update(state_dir=str(state_path), destination={
            'provider': 'ChatGPT Library', 'label': _text(config.get('destination_label'), 200),
            'path': _text(config.get('destination_path'), 1000), 'index_library_file_id': target})
        result['reason'] = 'state_unavailable'
        state_fd = _open_directory(state_path, private=True)
        try:
            result['task_watch'] = _watch_observation(_read_at(state_fd, 'operations/task-watch-observation.json'), now, stale_after)
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError, KeyError, OverflowError):
            result['task_watch']['status'] = 'invalid'
        try:
            result['last_attempt'] = _observation(_read_at(state_fd, 'operations/backup-observation.json'), now)
            result['observation_state'] = 'recorded'
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError, KeyError, OverflowError):
            result['observation_state'] = 'invalid'
        result.update(status='unverified', reason='no_committed_envelope')
        try:
            envelope = _read_at(state_fd, 'latest-committed.json', MAX_ENVELOPE)
        except FileNotFoundError:
            envelope = None
        if envelope is not None:
            # Reuse the installed protocol's pure validators, never prepare/restore.
            from . import backup_protocol as bp
            result['reason'] = 'invalid_commit_evidence'
            bp._previous(envelope)
            candidate, receipt = envelope['candidate'], envelope['platform_receipt']
            manifest, checked = candidate['manifest'], candidate.get('verified', {})
            identity = _read_at(data_fd, 'config/backup-identity.json')
            if identity != {'schema': bp.SCHEMA, 'identity': manifest['identity']} or receipt['library_file_id'] != target or candidate.get('identity') != manifest['identity']:
                raise ValueError('identity_mismatch')
            if checked.get('schema') != bp.SCHEMA or checked.get('snapshot_sha256') != candidate['snapshot_sha256'] or checked.get('content_sha256') != manifest['content_sha256']:
                raise ValueError('invalid_verification')
            if any(checked.get(key) is not True for key in ('complete_restore_bytes', 'policy_verified', 'runner_verified')) or checked.get('database') != manifest['database']:
                raise ValueError('incomplete_verification')
            if checked.get('file_count') != len(manifest['files']) or checked.get('external_file_count') != len(manifest['external_files']):
                raise ValueError('incomplete_verification')
            captured = _epoch(manifest['created_at'], now)
            verified = _epoch(checked['verified_at'], now)
            if verified + 300 < captured:
                raise ValueError('invalid_verification_time')
            files = manifest['files']
            checkpoint_paths = [x if isinstance(x, str) else x['path'] for x in manifest.get('checkpoints', [])]
            exclusions = sorted({_text(x['reason'], 200) for x in manifest.get('privacy_exclusions', []) if isinstance(x, dict) and x.get('reason')})
            result['last_verified'] = {
                'captured_at': captured, 'verified_at': verified, 'index_version': receipt['version'],
                'snapshot_sha256': candidate['snapshot_sha256'], 'file_count': len(files),
                'size_bytes': sum(x['size_bytes'] for x in files),
                'source_file_count': sum(x['path'].startswith('SOURCE/') for x in files),
                'data_file_count': sum(x['path'].startswith('DATA/') for x in files),
                'external_file_count': len(manifest['external_files']),
                'checkpoint_count': len(checkpoint_paths), 'exclusion_count': len(manifest.get('privacy_exclusions', [])),
                'exclusion_reasons': exclusions[:20], 'hydrated': bool(envelope.get('hydration_evidence')),
                'evidence': 'local_committed_receipt', 'stale': now - verified > stale_after}
            result.update(status='stale' if result['last_verified']['stale'] else 'verified', reason='historical_commit')
        attempt = result['last_attempt']
        # An older failure/pending observation cannot override a newer verified point.
        if attempt and result['last_verified'] and attempt['checked_at'] < result['last_verified']['verified_at']:
            attempt = None
        if attempt and attempt['result'] in ('failed', 'unavailable'):
            result.update(status=attempt['result'], reason='observed_attempt_failed')
        elif attempt and attempt['result'] == 'running':
            result.update(status='pending', reason='recorded_attempt_pending')
        return result
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        result['status'] = 'unavailable' if result['reason'] in ('state_unavailable', 'not_configured') else 'unverified'
        if result['reason'] == 'state_unavailable':
            result['task_watch']['status'] = 'record_unavailable'
        if result['reason'] == 'not_configured':
            result['reason'] = 'config_unavailable'
        return result
    finally:
        if state_fd is not None:
            os.close(state_fd)
        if data_fd is not None:
            os.close(data_fd)


LABELS = {
    'unconfigured': ('未配置备份展示', 'Backup display not configured'),
    'unavailable': ('备份记录不可用', 'Backup records unavailable'),
    'unverified': ('尚无可核验恢复点', 'No verified recovery point'),
    'verified': ('有已核验恢复点', 'Verified recovery point recorded'),
    'stale': ('恢复记录较旧', 'Recovery evidence is older'),
    'failed': ('最近尝试受阻', 'Latest attempt blocked'),
    'pending': ('有未完成尝试记录', 'Pending attempt recorded'),
}


def presentation(value, language='zh', stamp=None):
    """Shared native display contract; all values stay literal, never hyperlinks."""
    value = value or {}
    en = language == 'en'
    text = lambda zh, english: english if en else zh
    unknown = text('未知', 'Unknown')
    stamp = stamp or (lambda x: datetime.fromtimestamp(x, timezone.utc).isoformat())
    point, destination, attempt = value.get('last_verified'), value.get('destination'), value.get('last_attempt')
    title = LABELS.get(value.get('status'), LABELS['unconfigured'])[int(en)]
    watch = value.get('task_watch') or {}
    watch_labels = {'unverified': ('巡检未核验', 'Task checks unverified'), 'checked': ('最近任务巡检成功', 'Last task check succeeded'), 'stale': ('任务巡检记录较旧', 'Task check observation is older'), 'failed': ('任务巡检失败', 'Task check failed'), 'unavailable': ('任务巡检不可用', 'Task checks unavailable'), 'record_unavailable': ('巡检记录不可用', 'Task check records unavailable'), 'invalid': ('巡检记录无效', 'Task check record invalid')}
    watch_title = watch_labels.get(watch.get('status'), watch_labels['unverified'])[int(en)]
    watch_success = stamp(watch['last_success_at']) if watch.get('last_success_at') else unknown
    watch_compact = watch_title + ' · ' + text('最后成功：', 'Last successful: ') + watch_success
    rows = [('destination', text('私有备份目的地', 'Private destination'), (destination['label'] if destination['label'] == destination['provider'] or destination['label'].startswith(destination['provider'] + ' · ') else destination['provider'] + ' · ' + destination['label']) if destination else unknown),
            ('path', text('Library 路径', 'Library path'), destination['path'] if destination else unknown),
            ('state', text('本机状态目录', 'Local state directory'), value.get('state_dir') or unknown),
            ('snapshot', text('最后核验快照', 'Last verified snapshot'), stamp(point['captured_at']) if point else unknown),
            ('verified', text('恢复核验时间', 'Restore verification time'), stamp(point['verified_at']) if point else unknown),
            ('version', text('已记录索引版本', 'Recorded index version'), str(point['index_version']) if point else unknown)]
    if point:
        rows.extend([
            ('scope', text('已核验清单', 'Verified inventory'), text(f"源码 {point['source_file_count']} · 数据 {point['data_file_count']} · 外部固定依赖 {point['external_file_count']} · checkpoint {point['checkpoint_count']}", f"Source {point['source_file_count']} · Data {point['data_file_count']} · Pinned external dependencies {point['external_file_count']} · Checkpoints {point['checkpoint_count']}")),
            ('exclusions', text('清单排除记录', 'Recorded exclusions'), str(point['exclusion_count'])),
            ('logical_size', text('快照逻辑体积（非云端占用）', 'Snapshot logical size (not cloud storage use)'), f"{point['size_bytes']:,} bytes" if type(point.get('size_bytes')) is int else unknown),
        ])
    rows.extend([
        ('attempt', text('最近尝试观察', 'Last attempt observation'), (stamp(attempt['checked_at']) + ' · ' + attempt['stage'] + ' · ' + attempt['result'] + (' · ' + attempt['error_type'] if attempt.get('error_type') else '')) if attempt else unknown),
        ('watch_check', text('任务巡检最近检查', 'Last task check attempt'), stamp(watch['checked_at']) if watch.get('checked_at') else unknown),
        ('watch_success', text('任务巡检最后成功', 'Last successful task check'), watch_success),
        ('watch_error', text('任务巡检错误类别', 'Task check error type'), watch.get('error_type') or unknown),
        ('quota', text('Library 容量与剩余额度', 'Library quota and free capacity'), unknown),
        ('live', text('远端当前状态', 'Current remote state'), text('未实时查询；本页只读本机历史回执', 'Not queried live; local historical receipts only')),
        ('limits', text('覆盖边界', 'Coverage limits'), text('按已核验清单恢复源码、数据库、登记文件与选定 checkpoint；不恢复平台会话、账户 Skill 或调度器', 'Restore source, database, registered files and selected checkpoints per the verified manifest; not platform sessions, account Skills or schedulers')),
        ('excluded', text('默认排除', 'Excluded by default'), text('凭据、cookie、环境秘密、日志、缓存、逐帧渲染及未授权目录；具体以冻结 policy 和清单为准', 'Credentials, cookies, environment secrets, logs, caches, render frames and unapproved folders; frozen policy and manifest are authoritative')),
    ])
    note = text('本机缓存不是异地备份；恢复必须先在全新私有目录核验。快照之后的进展未必已备份。', 'Local cache is not an off-machine backup. Verify recovery in a new private directory first. Progress after the snapshot may not be backed up.')
    if value.get('observation_state') == 'invalid':
        note = text('最近尝试观察无效；保留已核验恢复点。', 'Latest attempt observation is invalid; retaining the verified recovery point. ') + note
    if point and point.get('hydrated'):
        note += text(' 本机状态由远端回读重建，不代表原历史提交过程已独立证明。', ' Local state was rebuilt from remote readback; original historical commit steps were not independently proven.')
    return {'title': title, 'rows': rows, 'note': note, 'watch_compact': watch_compact, 'compact': title + (' · ' + text('最后核验快照：', 'Last verified snapshot: ') + stamp(point['captured_at']) if point else '')}
