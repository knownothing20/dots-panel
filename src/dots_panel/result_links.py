"""Explicit external-result observations. No network, timers or platform writes."""
from datetime import datetime
import json
import re
import time

MAX_IMPORT_BYTES = 262144
SCHEMA = "dots-panel.external-result.v1"
TABLE_SQL = """CREATE TABLE IF NOT EXISTS schedule_results (
 schedule_id TEXT PRIMARY KEY REFERENCES schedules(id), payload TEXT NOT NULL)"""


def _object(value, fields):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError("Unexpected result observation fields")
    return value


def _text(value, limit=200):
    if not isinstance(value, str) or not value or len(value) > limit or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("Invalid bounded result text")
    return value


def _path(value):
    _text(value, 512)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", value) or any(p in ('.', '..') for p in value.split('/')):
        raise ValueError("Use a relative repository file path")
    return value


def _timestamp(value):
    _text(value, 40)
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None or parsed.timestamp() < 0:
            raise ValueError()
    except (ValueError, OverflowError):
        raise ValueError("Timestamp requires a valid explicit timezone") from None
    return parsed.timestamp()


def _date(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError("Invalid calendar date")
    datetime.strptime(value, '%Y-%m-%d')
    return value


def _count(value):
    if type(value) is not int or not 0 <= value <= 10000000:
        raise ValueError("Invalid result count")
    return value


def decode_import(raw):
    if len(raw) > MAX_IMPORT_BYTES:
        raise ValueError("Result import exceeds size limit")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON field")
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON number")))
    except (RecursionError, UnicodeError, json.JSONDecodeError):
        raise ValueError("Invalid result JSON") from None


def validate_import(value, now=None):
    now = time.time() if now is None else now
    _object(value, ('schema_version', 'repository', 'ref', 'status_path', 'index_path', 'checked_at', 'observation', 'fetch_error'))
    if value['schema_version'] != SCHEMA:
        raise ValueError("Unsupported external result schema")
    repo = _text(value['repository'], 140)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}', repo) or repo.split('/')[1] in ('.', '..'):
        raise ValueError("Invalid GitHub repository")
    ref = _path(value['ref'])
    paths = [_path(value[key]) for key in ('status_path', 'index_path')]
    checked = _timestamp(value['checked_at'])
    if checked > now + 300:
        raise ValueError("Observation cannot be in the future")
    observation = value['observation']
    error = value['fetch_error']
    if (observation is None) == (error is None):
        raise ValueError("Import either a successful observation or a fetch error")
    if error is not None:
        _text(error, 500)
    else:
        _object(observation, ('latest', 'index', 'evidence'))
        latest = _object(observation['latest'], ('calendar_date', 'run_id', 'collected_at', 'status', 'selected_count', 'stale'))
        _date(latest['calendar_date']); _text(latest['run_id'], 200)
        if _timestamp(latest['collected_at']) > checked + 300:
            raise ValueError("Source result is newer than its observation")
        if not re.fullmatch('[A-Za-z0-9_-]{1,64}', _text(latest['status'], 64)):
            raise ValueError("Invalid result status")
        _count(latest['selected_count'])
        if latest['stale'] is not None and type(latest['stale']) is not bool:
            raise ValueError("Source stale must be boolean or unknown")
        index = _object(observation['index'], ('generated_at', 'entry_count', 'latest_date'))
        if _timestamp(index['generated_at']) > checked + 300:
            raise ValueError("Index is newer than its observation")
        _count(index['entry_count'])
        if index['latest_date'] is not None:
            _date(index['latest_date'])
        if (index['entry_count'] == 0) != (index['latest_date'] is None):
            raise ValueError("Index count and date disagree")
        evidence = _object(observation['evidence'], ('status_sha', 'index_sha', 'status_url', 'index_url'))
        for kind, path in zip(('status', 'index'), paths):
            if not isinstance(evidence[kind + '_sha'], str) or not re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}', evidence[kind + '_sha']):
                raise ValueError("Missing source blob hash")
            expected = f'https://github.com/{repo}/blob/{ref}/{path}'
            if evidence[kind + '_url'] != expected:
                raise ValueError("Source URL must match the observed repository file")
    return {'repository': repo, 'ref': ref, 'status_path': paths[0], 'index_path': paths[1], 'checked_at': checked,
            'last_good_at': checked if observation else None, 'fetch_error': error, 'observation': observation,
            'platform_configuration': 'unverified', 'sync_mode': 'manual'}


def import_result(db, schedule_id, value):
    result = validate_import(value)
    if not db.execute('SELECT id FROM schedules WHERE id=?', (schedule_id,)).fetchone():
        raise ValueError("Register the schedule metadata first")
    previous = db.execute('SELECT payload FROM schedule_results WHERE schedule_id=?', (schedule_id,)).fetchone()
    if previous:
        previous = json.loads(previous['payload'])
        for key in ('repository', 'ref', 'status_path', 'index_path'):
            if result[key] != previous[key]:
                raise ValueError("Existing result association cannot be silently replaced")
        if result['checked_at'] < previous['checked_at']:
            raise ValueError("An older observation cannot replace a newer check")
        if result['fetch_error']:
            result['observation'] = previous['observation']
            result['last_good_at'] = previous['last_good_at']
    db.execute('INSERT INTO schedule_results VALUES(?,?) ON CONFLICT(schedule_id) DO UPDATE SET payload=excluded.payload',
               (schedule_id, json.dumps(result, ensure_ascii=False, allow_nan=False)))
    return result


def attach_results(db, schedules):
    if not db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schedule_results'").fetchone():
        return
    results = {row['schedule_id']: json.loads(row['payload']) for row in db.execute('SELECT * FROM schedule_results')}
    for schedule in schedules:
        schedule['external_result'] = results.get(schedule['id'])
