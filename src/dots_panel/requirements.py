"""Explicit, append-only requirement records. No import, dispatch or acceptance inference."""
import hashlib
import json
import math
import sqlite3
import time
import uuid
from datetime import datetime

STATUSES = ('received', 'in_progress', 'pending_acceptance', 'blocked', 'completed', 'cancelled')
TERMINAL = ('completed', 'cancelled')
SCHEMA = '''
CREATE TABLE IF NOT EXISTS requirement_stream (
 id INTEGER PRIMARY KEY CHECK(id=1), stream_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS requirements (
 id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), summary TEXT NOT NULL,
 source_event_id TEXT NOT NULL, observed_at REAL NOT NULL, recorded_at REAL NOT NULL,
 evidence TEXT NOT NULL, content_sha256 TEXT NOT NULL, UNIQUE(task_id,source_event_id));
CREATE TABLE IF NOT EXISTS requirement_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, requirement_id TEXT NOT NULL REFERENCES requirements(id),
 kind TEXT NOT NULL CHECK(kind IN ('receipt','state','owner','link')),
 source_event_id TEXT NOT NULL, observed_at REAL NOT NULL, recorded_at REAL NOT NULL,
 payload_json TEXT NOT NULL, content_sha256 TEXT NOT NULL,
 UNIQUE(requirement_id,kind,source_event_id));
CREATE INDEX IF NOT EXISTS requirement_events_card ON requirement_events(requirement_id,id);
CREATE TABLE IF NOT EXISTS requirement_receipts (
 requirement_id TEXT PRIMARY KEY REFERENCES requirements(id), task_id TEXT NOT NULL REFERENCES tasks(id),
 source_event_id TEXT NOT NULL, run_id TEXT NOT NULL REFERENCES runs(id), observed_at REAL NOT NULL,
 recorded_at REAL NOT NULL, content_sha256 TEXT NOT NULL, payload_json TEXT NOT NULL,
 owner_status TEXT NOT NULL CHECK(owner_status='assignment_unconfirmed'), UNIQUE(task_id,source_event_id));
'''


def migrate(db):
    statement = ''
    for line in SCHEMA.splitlines(True):
        statement += line
        if sqlite3.complete_statement(statement):
            db.execute(statement)
            statement = ''
    db.execute('INSERT OR IGNORE INTO requirement_stream VALUES(1,?)', (uuid.uuid4().hex,))
    for table in ('requirements', 'requirement_events', 'requirement_receipts', 'requirement_stream'):
        for operation in ('UPDATE', 'DELETE'):
            db.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'Requirement history is append-only'); END")


def _text(value, limit=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c) < 32 and c not in '\n\t' for c in value):
        raise ValueError('Requirement text must be nonempty printable text within its limit')
    return value.strip()


def observed(value):
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                raise ValueError('Source time must include timezone')
            value = parsed.timestamp()
        except (ValueError, OverflowError) as exc:
            raise ValueError('Source time must be timezone ISO or UTC epoch') from exc
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0 or value > time.time():
        raise ValueError('Source time must be finite, nonnegative and not future')
    return float(value)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _event(row):
    value = dict(row)
    value.update(json.loads(value.pop('payload_json')))
    value['event_id'] = value['id']
    return value


def _base(db, requirement_id):
    row = db.execute('SELECT * FROM requirements WHERE id=?', (requirement_id,)).fetchone()
    if not row:
        raise ValueError('Unknown requirement')
    return dict(row)


def _append(db, requirement_id, kind, source, at, payload):
    fingerprint = digest({'observed_at': at, 'payload': payload})
    old = db.execute('SELECT * FROM requirement_events WHERE requirement_id=? AND kind=? AND source_event_id=?', (requirement_id, kind, source)).fetchone()
    if old:
        if old['content_sha256'] != fingerprint:
            raise ValueError('Source identity conflicts with recorded requirement content')
        return {**_event(old), 'deduplicated': True, 'record_only': True}
    key = db.execute('INSERT INTO requirement_events(requirement_id,kind,source_event_id,observed_at,recorded_at,payload_json,content_sha256) VALUES(?,?,?,?,?,?,?)', (requirement_id, kind, source, at, time.time(), json.dumps(payload, ensure_ascii=False, sort_keys=True), fingerprint)).lastrowid
    return {**_event(db.execute('SELECT * FROM requirement_events WHERE id=?', (key,)).fetchone()), 'deduplicated': False, 'record_only': True}


def _retry(db, requirement_id, kind, source, at, payload):
    old = db.execute('SELECT * FROM requirement_events WHERE requirement_id=? AND kind=? AND source_event_id=?', (requirement_id, kind, source)).fetchone()
    if old:
        if old['content_sha256'] != digest({'observed_at': at, 'payload': payload}):
            raise ValueError('Source identity conflicts with recorded requirement content')
        return {**_event(old), 'deduplicated': True, 'record_only': True}


def _owner(db, assignment_id, task_id, at):
    from .collaborative_activity import assignment_context
    ctx = assignment_context(db, assignment_id, task_id=task_id)
    if at < ctx['assigned_at']:
        raise ValueError('Owner source time predates the assignment')
    keys = ('agent_id', 'run_id', 'work_type', 'name', 'name_en', 'portrait', 'requested_model', 'requested_effort', 'actual_model', 'actual_effort', 'config_verification', 'config_provider', 'config_evidence', 'config_observed_at')
    owner = {key: ctx.get(key) for key in keys}
    owner.update(assignment_id=assignment_id, status='confirmed', verification='confirmed')
    for field in ('config_verification',):
        owner[field] = owner.get(field) or 'unknown'
    return owner


def cards(db, task_id=None, scope='all'):
    if scope not in ('all', 'open', 'active', 'completed', 'cancelled'):
        raise ValueError('Invalid requirement scope')
    if task_id is not None and not db.execute('SELECT 1 FROM tasks WHERE id=?', (task_id,)).fetchone():
        raise ValueError('Unknown activity')
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='requirements'").fetchone():
        return []
    query = 'SELECT q.*,t.name AS task_name FROM requirements q JOIN tasks t ON t.id=q.task_id'
    rows = [dict(row) for row in db.execute(query + (' WHERE q.task_id=?' if task_id else '') + ' ORDER BY q.observed_at,q.recorded_at,q.id', (task_id,) if task_id else ())]
    all_events = [_event(row) for row in db.execute('SELECT e.* FROM requirement_events e' + (' JOIN requirements q ON q.id=e.requirement_id WHERE q.task_id=?' if task_id else '') + ' ORDER BY e.id', (task_id,) if task_id else ())]
    grouped = {}
    for event in all_events:
        grouped.setdefault(event['requirement_id'], []).append(event)
    result = []
    for row in rows:
        history = grouped.get(row['id'], [])
        states = [e for e in history if e['kind'] in ('receipt', 'state')]
        owners = [e for e in history if e['kind'] == 'owner']
        latest = max(states, key=lambda e: (e['observed_at'], e['id'])) if states else None
        current_owner = max(owners, key=lambda e: (e['observed_at'], e['id'])) if owners else None
        row.update(status=latest['status'] if latest else 'received', current_event_id=latest['id'] if latest else 0,
                   current_owner_event_id=current_owner['id'] if current_owner else 0,
                   owner=current_owner['owner'] if current_owner else {'status': 'assignment_unconfirmed', 'actual_model': 'unknown', 'actual_effort': 'unknown'},
                   status_history=states, owner_history=owners, history=history,
                   links=[e for e in history if e['kind'] == 'link'])
        row['source_created'] = row['observed_at']
        row['source_time'] = row['observed_at']
        row['created'] = row['observed_at']
        row['current_step'] = ''
        row['latest_progress'] = None
        for link in reversed(row['links']):
            if link['target_type'] == 'progress':
                progress = db.execute('SELECT * FROM progress_updates WHERE id=?', (link['target_id'],)).fetchone()
                if progress:
                    row['latest_progress'] = dict(progress)
                    row['current_step'] = progress['current_step']
                    break
        if not row['current_step'] and latest and latest['kind'] == 'state' and row['status'] in ('in_progress', 'blocked'):
            row['current_step'] = latest.get('next_step') or latest.get('evidence', '')
        row['state'] = row['status']
        row['bookmarked'] = row['status'] not in TERMINAL
        row['run_ids'] = list(dict.fromkeys(e['target_id'] for e in row['links'] if e['target_type'] == 'run'))
        if scope in ('open', 'active') and row['status'] in TERMINAL or scope in TERMINAL and row['status'] != scope:
            continue
        result.append(row)
    return result


def feed(db):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='requirement_stream'").fetchone():
        return {'requirements': [], 'requirement_events': [], 'requirement_stream_id': None, 'requirement_counters': {}}
    events = [_event(row) for row in db.execute('SELECT e.*,q.task_id FROM requirement_events e JOIN requirements q ON q.id=e.requirement_id ORDER BY e.id')]
    return {'requirements': cards(db), 'requirement_events': events,
            'requirement_stream_id': db.execute('SELECT stream_id FROM requirement_stream WHERE id=1').fetchone()[0],
            'requirement_counters': {kind: max((e['id'] for e in events if e['kind'] == kind), default=0) for kind in ('receipt', 'state', 'owner', 'link')}}


def _create(db, task_id, summary, source, at, evidence, assignment_id=None):
    if not db.execute('SELECT 1 FROM tasks WHERE id=?', (task_id,)).fetchone():
        raise ValueError('Register the matching activity first')
    fingerprint = digest([summary, at, evidence, assignment_id])
    old = db.execute('SELECT * FROM requirements WHERE task_id=? AND source_event_id=?', (task_id, source)).fetchone()
    if old:
        if old['content_sha256'] != fingerprint:
            raise ValueError('Source identity conflicts with original requirement')
        return old['id'], True
    key = uuid.uuid4().hex
    owner = _owner(db, assignment_id, task_id, at) if assignment_id else None
    db.execute('INSERT INTO requirements VALUES(?,?,?,?,?,?,?,?)', (key, task_id, summary, source, at, time.time(), evidence, fingerprint))
    _append(db, key, 'receipt', source, at, {'status': 'received', 'evidence_kind': 'receipt', 'evidence_ref': source, 'evidence': evidence})
    if owner:
        _append(db, key, 'owner', source, at, {'owner': owner, 'assignment_id': assignment_id, 'expected_owner_event_id': 0, 'evidence': evidence})
    return key, False


def _same_task_target(db, task_id, target_type, target_id):
    target_id = str(target_id)
    table = {'run': 'runs', 'progress': 'progress_updates', 'activity': 'activity', 'event': 'events', 'artifact': 'artifacts'}.get(target_type)
    if not table:
        raise ValueError('Invalid target type')
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
        raise ValueError('Link target does not exist')
    if target_type in ('event', 'progress'):
        row = db.execute('SELECT r.task_id FROM '+table+' x JOIN runs r ON r.id=x.run_id WHERE x.id=?', (target_id,)).fetchone()
    else:
        row = db.execute('SELECT task_id FROM '+table+' WHERE id=?', (target_id,)).fetchone()
    if not row or row['task_id'] != task_id:
        raise ValueError('Link target must exist in the same activity')


def _link(db, key, link_kind, target_type, target_id, source, at, evidence):
    valid = {'run': ('run',), 'progress': ('progress', 'activity', 'event'), 'result': ('progress', 'activity', 'event'), 'artifact': ('artifact',)}
    if target_type not in valid.get(link_kind, ()):
        raise ValueError('Invalid requirement link kind/target combination')
    base = _base(db, key)
    if at < base['observed_at']:
        raise ValueError('Link source time predates requirement')
    payload = {'link_kind': link_kind, 'target_type': target_type, 'target_id': str(target_id), 'evidence': evidence}
    retry = _retry(db, key, 'link', source, at, payload)
    if retry:
        return retry
    _same_task_target(db, base['task_id'], target_type, target_id)
    return _append(db, key, 'link', source, at, payload)


class RequirementStoreMixin:
    def requirement_create(self, task_id, summary, source_event_id, observed_at, evidence, assignment_id=None):
        summary, source, at, evidence = _text(summary, 2000), _text(source_event_id, 200), observed(observed_at), _text(evidence, 4000)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            key, duplicate = _create(db, task_id, summary, source, at, evidence, assignment_id)
            value = next(c for c in cards(db, task_id) if c['id'] == key)
        return {**value, 'requirement_id': key, 'deduplicated': duplicate, 'record_only': True}

    def requirement_list(self, task_id, scope='all'):
        with self.connect() as db:
            db.execute('BEGIN')
            return cards(db, task_id, scope)

    def requirement_assign(self, requirement_id, assignment_id, source_event_id, observed_at, expected_owner_event_id, evidence):
        source, at, evidence = _text(source_event_id, 200), observed(observed_at), _text(evidence, 4000)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            base = _base(db, requirement_id)
            # Freeze the original snapshot on replay, even if profile or runtime later changed.
            previous = db.execute("SELECT * FROM requirement_events WHERE requirement_id=? AND kind='owner' AND source_event_id=?", (requirement_id, source)).fetchone()
            if previous:
                payload = json.loads(previous['payload_json'])
                if (payload['assignment_id'], payload['expected_owner_event_id'], payload['evidence'], previous['observed_at']) != (assignment_id, expected_owner_event_id, evidence, at):
                    raise ValueError('Source identity conflicts with recorded owner')
                return {**_event(previous), 'deduplicated': True, 'record_only': True}
            card = next(c for c in cards(db, base['task_id']) if c['id'] == requirement_id)
            _cas(expected_owner_event_id, card['current_owner_event_id'])
            if card['status'] in TERMINAL:
                raise ValueError('Reopen terminal requirement before assigning')
            old_at = card['owner_history'][-1]['observed_at'] if card['owner_history'] else base['observed_at']
            if at < old_at:
                raise ValueError('Owner source time cannot move backwards')
            owner = _owner(db, assignment_id, base['task_id'], at)
            return _append(db, requirement_id, 'owner', source, at, {'owner': owner, 'assignment_id': assignment_id, 'expected_owner_event_id': expected_owner_event_id, 'evidence': evidence})

    def requirement_link(self, requirement_id, link_kind, target_type, target_id, source_event_id, observed_at, evidence):
        source, at, evidence = _text(source_event_id, 200), observed(observed_at), _text(evidence, 4000)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            return _link(db, requirement_id, link_kind, target_type, target_id, source, at, evidence)

    def requirement_transition(self, requirement_id, status, expected_event_id, source_event_id, observed_at, evidence_kind, evidence_ref, evidence, assignment_id=None, next_step=''):
        if status not in STATUSES:
            raise ValueError('Invalid requirement status')
        source, at, evidence, ref, kind = _text(source_event_id, 200), observed(observed_at), _text(evidence, 4000), _text(str(evidence_ref), 500), _text(evidence_kind, 80)
        payload = {'status': status, 'expected_event_id': expected_event_id, 'evidence_kind': kind, 'evidence_ref': ref, 'evidence': evidence, 'assignment_id': assignment_id, 'next_step': next_step}
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            base = _base(db, requirement_id)
            old = db.execute("SELECT payload_json FROM requirement_events WHERE requirement_id=? AND kind='state' AND source_event_id=?", (requirement_id, source)).fetchone()
            if old and 'recorder' in json.loads(old[0]):
                payload['recorder'] = json.loads(old[0])['recorder']
            retry = _retry(db, requirement_id, 'state', source, at, payload)
            if retry:
                return retry
            card = next(c for c in cards(db, base['task_id']) if c['id'] == requirement_id)
            _cas(expected_event_id, card['current_event_id'])
            last = card['status_history'][-1]
            if at < last['observed_at']:
                raise ValueError('State source time cannot move backwards')
            if status == card['status']:
                raise ValueError('Status unchanged; record progress explicitly')
            if card['status'] in TERMINAL and (kind != 'reopen' or status not in ('received', 'in_progress')):
                raise ValueError('Terminal requirement needs explicit reopen evidence')
            if status == 'received' and kind != 'reopen':
                raise ValueError('Received is an intake or explicit reopen state')
            if status == 'pending_acceptance':
                links = [e for e in card['links'] if e['link_kind'] in ('result', 'artifact')]
                if kind != 'result' or not any(ref in (e['target_id'], e['source_event_id']) for e in links):
                    raise ValueError('Acceptance handoff requires an explicitly linked result reference')
            if status == 'completed':
                if card['status'] != 'pending_acceptance' or kind != 'acceptance' or ref in {last['evidence_ref'], last['source_event_id']} or source == last['source_event_id']:
                    raise ValueError('Completion requires pending acceptance and distinct acceptance evidence')
                if any(ref in (e['target_id'], e['source_event_id']) for e in card['links'] if e['link_kind'] in ('result', 'artifact')):
                    raise ValueError('A linked result is not acceptance evidence')
            if status == 'blocked' and not str(next_step).strip():
                raise ValueError('Blocked requirement requires a next step')
            if assignment_id:
                owner = _owner(db, assignment_id, base['task_id'], at)
                payload['recorder'] = owner
            return _append(db, requirement_id, 'state', source, at, payload)

    def requirement_receive(self, task_id, source_event_id, observed_at, summary, evidence, reason, next_step, run_id=None):
        from .requirement_sync import receive
        return receive(self, task_id, source_event_id, observed_at, summary, evidence, reason, next_step, run_id)

    def requirement_sync_status(self, task_id):
        from .requirement_sync import sync_status
        with self.connect() as db:
            db.execute('BEGIN')
            return sync_status(db, task_id)

    def requirement_diagnose(self, task_id):
        with self.connect() as db:
            db.execute('BEGIN')
            result = []
            for card in cards(db, task_id):
                if any(e['link_kind'] in ('result', 'artifact') for e in card['links']) and card['status'] not in ('pending_acceptance', 'completed', 'cancelled'):
                    result.append({'requirement_id': card['id'], 'status': card['status'], 'finding': 'linked_result_needs_state_review', 'result_links': [e for e in card['links'] if e['link_kind'] in ('result', 'artifact')]})
            return {'schema': 'dots-panel.requirement-diagnose.v1', 'task_id': task_id, 'findings': result, 'record_only': True, 'acceptance_inferred': False}


def _cas(expected, actual):
    if isinstance(expected, bool) or not isinstance(expected, int) or expected < 0 or expected != actual:
        raise ValueError('Requirement changed; refresh expected event ID before writing')
