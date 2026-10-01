"""Manually imported platform scheduler observations, never a scheduler client."""
import json
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from .result_links import _object, _text, _timestamp

SCHEMA = 'dots-panel.platform-schedule.v1'
TABLE_SQL = '''CREATE TABLE IF NOT EXISTS platform_schedules (
 schedule_id TEXT PRIMARY KEY REFERENCES schedules(id),
 platform TEXT NOT NULL, task_id TEXT NOT NULL, payload TEXT NOT NULL,
 UNIQUE(platform, task_id))'''


def validate_schedule(value, timezone):
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError('Invalid bounded schedule')
    lines = value.split('\n')
    if len(lines) != 4 or lines[0] != 'BEGIN:VEVENT' or lines[-1] != 'END:VEVENT':
        raise ValueError('Use BEGIN:VEVENT, DTSTART, RRULE and END:VEVENT only')
    match = re.fullmatch(r'DTSTART(?:;TZID=([A-Za-z0-9_+/-]{1,100}))?:(\d{8}T\d{6})(Z?)', lines[1])
    if not match or (match[1] and (match[1] != timezone or match[3])) or (not match[1] and not match[3]):
        raise ValueError('DTSTART needs the observed timezone or UTC Z')
    datetime.strptime(match[2], '%Y%m%dT%H%M%S')
    if not lines[2].startswith('RRULE:'):
        raise ValueError('Missing recurrence rule')
    fields = {}
    for part in lines[2][6:].split(';'):
        if part.count('=') != 1:
            raise ValueError('Invalid recurrence field')
        key, entry = part.split('=')
        if key in fields:
            raise ValueError('Duplicate recurrence field')
        fields[key] = entry
    if fields.get('FREQ') not in ('MINUTELY', 'HOURLY', 'DAILY', 'WEEKLY', 'MONTHLY', 'YEARLY'):
        raise ValueError('Invalid recurrence frequency')
    bounds = {'INTERVAL': (1,10000), 'COUNT': (1,1000000), 'BYHOUR': (0,23), 'BYMINUTE': (0,59), 'BYSECOND': (0,59), 'BYMONTH': (1,12), 'BYMONTHDAY': (1,31)}
    for key, entry in fields.items():
        if key == 'FREQ':
            continue
        if key in bounds:
            values = entry.split(',')
            if key in ('COUNT','INTERVAL') and len(values) != 1:
                raise ValueError('Invalid recurrence count')
            if any(not re.fullmatch('[0-9]{1,7}', v) or not bounds[key][0] <= int(v) <= bounds[key][1] for v in values):
                raise ValueError('Recurrence number outside supported bounds')
        elif key == 'BYDAY':
            if not re.fullmatch(r'(?:MO|TU|WE|TH|FR|SA|SU)(?:,(?:MO|TU|WE|TH|FR|SA|SU))*', entry):
                raise ValueError('Invalid recurrence weekdays')
        elif key == 'UNTIL':
            if not re.fullmatch(r'\d{8}T\d{6}Z', entry):
                raise ValueError('UNTIL requires UTC timestamp')
            datetime.strptime(entry, '%Y%m%dT%H%M%SZ')
        else:
            raise ValueError('Unsupported recurrence field')
    if 'UNTIL' in fields and 'COUNT' in fields:
        raise ValueError('UNTIL and COUNT cannot be combined')
    return value


def validate_import(value, now=None):
    now = time.time() if now is None else now
    _object(value, ('schema_version','platform','task_id','title','enabled','timezone','timing_mode','schedule','last_run_at','next_run_at','observed_at'))
    if value['schema_version'] != SCHEMA or value['platform'] != 'dot':
        raise ValueError('Unsupported platform observation schema or platform')
    if not isinstance(value['task_id'],str) or not re.fullmatch('[A-Za-z0-9_-]{1,100}',value['task_id']):
        raise ValueError('Invalid platform task identity')
    _text(value['title'],120)
    if value['enabled'] is not None and type(value['enabled']) is not bool:
        raise ValueError('Enabled state must be boolean or unknown')
    zone = _text(value['timezone'],100)
    if not re.fullmatch('[A-Za-z0-9_+/-]+',zone):
        raise ValueError('Invalid timezone')
    try:
        ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError('Unknown IANA timezone') from None
    if value['timing_mode'] not in ('exact_schedule','flexible_schedule','condition_watch'):
        raise ValueError('Invalid timing mode')
    if value['schedule'] is not None:
        validate_schedule(value['schedule'],zone)
    observed = _timestamp(value['observed_at'])
    if observed > now + 300:
        raise ValueError('Observation cannot be in the future')
    for key in ('last_run_at','next_run_at'):
        if value[key] is not None:
            moment = _timestamp(value[key])
            if key == 'last_run_at' and moment > observed + 300:
                raise ValueError('Last run cannot be newer than observation')
    result = {k:v for k,v in value.items() if k != 'schema_version'}
    result.update(observed_at=observed, sync_mode='manual', first_scheduled_execution='unverified')
    return result


def import_observation(db, schedule_id, value):
    result = validate_import(value)
    if not db.execute('SELECT id FROM schedules WHERE id=?',(schedule_id,)).fetchone():
        raise ValueError('Register schedule metadata first')
    old = db.execute('SELECT payload FROM platform_schedules WHERE schedule_id=?',(schedule_id,)).fetchone()
    if old:
        previous = json.loads(old['payload'])
        if any(previous[k] != result[k] for k in ('platform','task_id')):
            raise ValueError('Cannot silently replace a platform task association')
        if result['observed_at'] < previous['observed_at']:
            raise ValueError('Older platform observation rejected')
        if result['observed_at'] == previous['observed_at']:
            if result != {k:v for k,v in previous.items() if k != 'synced_at'}:
                raise ValueError('Conflicting observation at identical timestamp')
            return previous
    other = db.execute('SELECT schedule_id FROM platform_schedules WHERE platform=? AND task_id=?',(result['platform'],result['task_id'])).fetchone()
    if other and other['schedule_id'] != schedule_id:
        raise ValueError('Platform task already associated with another row')
    result['synced_at'] = time.time()
    db.execute('INSERT INTO platform_schedules VALUES(?,?,?,?) ON CONFLICT(schedule_id) DO UPDATE SET payload=excluded.payload',
               (schedule_id,result['platform'],result['task_id'],json.dumps(result,ensure_ascii=False,allow_nan=False)))
    return result


def attach_observations(db, schedules):
    if not db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='platform_schedules'").fetchone():
        return
    records = {r['schedule_id']:json.loads(r['payload']) for r in db.execute('SELECT * FROM platform_schedules')}
    for row in schedules:
        row['platform_observation'] = records.get(row['id'])
