"""Single-transaction requirement intake and read-only association diagnosis."""
import json
import time
import uuid
from .requirements import _text, observed, digest, _create, _link, cards

OPEN = ('running', 'waiting_user', 'waiting_external', 'paused', 'awaiting_review')


def receive(store, task_id, source_event_id, observed_at, summary, evidence, reason, next_step, run_id=None):
    source, at = _text(source_event_id, 200), observed(observed_at)
    summary, evidence, reason, next_step = (_text(v, 4000 if i == 1 else 2000) for i, v in enumerate((summary, evidence, reason, next_step)))
    payload = {'summary': summary, 'evidence': evidence, 'reason': reason, 'next_step': next_step, 'selected_run_id': run_id, 'observed_at': at}
    fingerprint = digest(payload)
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        old = db.execute('SELECT * FROM requirement_receipts WHERE task_id=? AND source_event_id=?', (task_id, source)).fetchone()
        if old:
            if old['content_sha256'] != fingerprint:
                raise ValueError('Source identity conflicts with original requirement intake')
            return {'requirement_id': old['requirement_id'], 'run_id': old['run_id'], 'receipt': dict(old), 'deduplicated': True, 'record_only': True}
        task = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
        if not task:
            raise ValueError('Register the matching activity before requirement intake')
        # Reconcile an exact earlier receive, rather than duplicate a recorded request.
        legacy = db.execute('SELECT * FROM task_receipts WHERE task_id=? AND request_id=?', (task_id, source)).fetchone()
        if legacy:
            expected = __import__('hashlib').sha256(json.dumps([summary, reason, evidence, next_step], ensure_ascii=False).encode()).hexdigest()
            if legacy['content_sha256'] != expected or run_id is not None and run_id != legacy['run_id']:
                raise ValueError('Legacy receipt differs; reconcile its original intake')
            selected = legacy['run_id']
        else:
            selected = run_id
        if selected:
            run = db.execute('SELECT * FROM runs WHERE id=?', (selected,)).fetchone()
            if not run or run['task_id'] != task_id:
                raise ValueError('Selected intake run must belong to the same activity')
            if run['status'] not in OPEN:
                original = db.execute('SELECT id FROM requirements WHERE task_id=? AND source_event_id=?', (task_id, source)).fetchone()
                exact_link = False
                if legacy and original:
                    for row in db.execute("SELECT payload_json FROM requirement_events WHERE requirement_id=? AND kind='link'", (original['id'],)):
                        link = json.loads(row[0])
                        exact_link = exact_link or (link.get('link_kind'), link.get('target_type'), link.get('target_id')) == ('run', 'run', selected)
                if not exact_link:
                    raise ValueError('Terminal run cannot accept a new requirement intake')
        key, duplicate = _create(db, task_id, summary, source, at, evidence)
        now = time.time()
        if not selected:
            selected = uuid.uuid4().hex[:16]
            db.execute('INSERT INTO runs(id,task_id,status,started,updated,note,lifecycle_reason,lifecycle_evidence,next_step,closeout_required) VALUES(?,?,?,?,?,?,?,?,?,1)', (selected, task_id, 'waiting_external', now, now, summary, reason, evidence, next_step))
        _link(db, key, 'run', 'run', selected, source, at, evidence)
        db.execute('INSERT INTO requirement_receipts VALUES(?,?,?,?,?,?,?,?,?)', (key, task_id, source, selected, at, now, fingerprint, json.dumps(payload, ensure_ascii=False, sort_keys=True), 'assignment_unconfirmed'))
        # Shared legacy receipt helps the ordinary receive path reuse the same request.
        if not legacy:
            legacy_hash = __import__('hashlib').sha256(json.dumps([summary, reason, evidence, next_step], ensure_ascii=False).encode()).hexdigest()
            db.execute('INSERT INTO task_receipts VALUES(?,?,?,?)', (task_id, source, selected, legacy_hash))
        receipt = dict(db.execute('SELECT * FROM requirement_receipts WHERE requirement_id=?', (key,)).fetchone())
        return {'requirement_id': key, 'run_id': selected, 'receipt': receipt, 'deduplicated': False, 'record_only': True, 'status': 'received', 'owner_status': 'assignment_unconfirmed'}


def sync_status(db, task_id):
    findings = []
    for card in cards(db, task_id, 'open'):
        reasons = []
        if not card['run_ids']:
            reasons.append('missing_run_link')
        if not card['current_owner_event_id']:
            reasons.append('assignment_unconfirmed')
        if reasons:
            findings.append({'requirement_id': card['id'], 'task_id': task_id, 'status': card['status'], 'run_ids': card['run_ids'], 'findings': reasons})
    return {'schema': 'dots-panel.requirement-sync-status.v1', 'task_id': task_id, 'findings': findings, 'upstream_message_coverage': 'not_connected', 'record_only': True}
