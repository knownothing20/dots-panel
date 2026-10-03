"""Evidence-bearing goal checkpoints and scoped, read-only responsibility audits.

This module never dispatches, retries, changes schedules or infers executor liveness.
"""
import hashlib
import json
import math
import re
import sqlite3
import time
import uuid

GOAL_STATES=('incomplete','complete','unknown')
BLOCKERS=('none','internal_handoff','external_wait','security','access','approval','failure','unknown')
OPEN=('running','waiting_user','waiting_external','paused','awaiting_review')
SCHEMA='''
CREATE TABLE IF NOT EXISTS followup_checkpoints (
 id INTEGER PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
 source_event_id TEXT NOT NULL, observed_at REAL NOT NULL, created REAL NOT NULL,
 goal_status TEXT NOT NULL, remaining_scope TEXT NOT NULL, blocker_class TEXT NOT NULL,
 next_owner TEXT NOT NULL, next_action TEXT NOT NULL, recheck_condition TEXT NOT NULL,
 evidence TEXT NOT NULL, content_sha256 TEXT NOT NULL,
 UNIQUE(run_id,source_event_id));
CREATE TRIGGER IF NOT EXISTS immutable_followup_checkpoint BEFORE UPDATE ON followup_checkpoints
 BEGIN SELECT RAISE(ABORT,'Follow-up checkpoint is immutable'); END;
'''


def migrate(db):
    statement=''
    for line in SCHEMA.splitlines(True):
        statement+=line
        if sqlite3.complete_statement(statement):
            db.execute(statement);statement=''
    columns = {row[1] for row in db.execute('PRAGMA table_info(followup_checkpoints)')}
    if 'event_id' not in columns:
        db.execute('ALTER TABLE followup_checkpoints ADD COLUMN event_id TEXT')
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS unique_followup_event_id ON followup_checkpoints(event_id) WHERE event_id IS NOT NULL')
    db.execute("CREATE TRIGGER IF NOT EXISTS retained_followup_checkpoint BEFORE DELETE ON followup_checkpoints BEGIN SELECT RAISE(ABORT,'Follow-up checkpoint is append-only'); END")


def _checkpoint_projection(row):
    if row is None:
        return None
    value = dict(row)
    local_id = value['id']
    value['record_id'] = local_id
    value['id'] = value.get('event_id') or local_id
    value['identity_kind'] = 'uuid' if value.get('event_id') else 'legacy_local_id'
    value['source_time_known'] = value.get('observed_at') is not None
    return value


def technical_failure(text):
    """Narrow, disclosed heuristic; never treats evidence prose as current failure."""
    if not re.search(r'\bERR_[A-Z0-9_]+\b|Traceback \(most recent call last\)',text):
        return False
    negative=re.search(r'\b(?:not|never|unresolved|cannot|can\x27t|hasn\x27t|isn\x27t|wasn\x27t)\b.{0,35}\b(?:resolv|fix|recover|clear)|尚未|未修|未解|没有解决',text,re.I)
    affirmative=re.search(r'\b(?:resolved|cleared|fixed|recovered)\b|已修复|已解决|已恢复',text,re.I)
    return bool(negative) or not affirmative


EXECUTOR_STATES = ('running', 'idle', 'blocked', 'unavailable', 'unknown')
OBSERVATION_FIELDS = frozenset(('run_id', 'status', 'provider', 'observed_at', 'evidence'))
MAX_EXECUTOR_OBSERVATIONS = 10000


def _executor_observations(value, checked_at):
    """Validate the documented bounded five-field list without guessing evidence."""
    if value is None:
        return {}
    if not isinstance(value, list) or len(value) > MAX_EXECUTOR_OBSERVATIONS:
        raise ValueError('Executor observations must be a bounded list of at most 10000 records')
    result = {}
    for row in value:
        if not isinstance(row, dict) or set(row) != OBSERVATION_FIELDS:
            raise ValueError('Executor observations require exactly run_id, status, provider, observed_at and evidence')
        for field, maximum in (('run_id', 200), ('provider', 200), ('evidence', 4000)):
            text = row[field]
            if not isinstance(text, str) or not text.strip() or len(text) > maximum or any(ord(c) < 32 and c not in '\n\t' for c in text):
                raise ValueError('Invalid executor observation ' + field)
        stamp = row['observed_at']
        if isinstance(stamp, bool) or not isinstance(stamp, (int, float)) or not math.isfinite(stamp) or stamp < 0 or stamp > checked_at:
            raise ValueError('Executor observation time must be finite, nonnegative and no later than audit time')
        if row['status'] not in EXECUTOR_STATES:
            raise ValueError('Invalid executor observation status')
        if row['run_id'] in result:
            raise ValueError('Duplicate executor observation run_id; reconcile observations first')
        result[row['run_id']] = dict(row)
    return result


def _disposition(checkpoint, progress, observation, checked_at, stale_seconds):
    """Return contract vocabulary; observations never dispatch or change lifecycle."""
    blocker = (checkpoint or {}).get('blocker_class')
    goal = (checkpoint or {}).get('goal_status', 'unknown')
    observed_at = (observation or {}).get('observed_at')
    fresh = observation is not None and checked_at - observed_at <= min(300, stale_seconds)
    executor = observation['status'] if fresh else 'unknown'
    stamp = (progress or {}).get('created')
    recent = isinstance(stamp, (int, float)) and math.isfinite(stamp) and 0 <= checked_at - stamp <= stale_seconds
    current_text = ' '.join(str((progress or {}).get(k) or '') for k in ('current_step', 'result'))
    flags = []
    if not checkpoint:
        flags.append('missing_checkpoint')
    elif blocker in ('security', 'access', 'approval', 'failure', 'internal_handoff', 'unknown'):
        flags.append('unresolved_' + blocker)
    if technical_failure(current_text):
        flags.append('technical_failure_hint')
    if goal == 'complete':
        flags.append('closeout_needs_verification')
    if stamp is None:
        flags.append('progress_unobserved')
    elif not recent:
        flags.append('stale_progress')
    if observation is None:
        flags.append('executor_observation_missing')
    elif not fresh:
        flags.append('executor_observation_stale')
    elif executor == 'unknown':
        flags.append('executor_observation_unknown')

    if blocker in ('security', 'access', 'approval'):
        disposition, reason = 'blocked_requires_authority', 'unresolved_' + blocker
    elif blocker in ('failure', 'unknown') or 'technical_failure_hint' in flags:
        disposition, reason = 'coordinator_diagnosis', 'unresolved_' + blocker if blocker in ('failure', 'unknown') else 'technical_failure_hint'
    elif blocker == 'internal_handoff':
        disposition, reason = 'coordinator_followup', 'unresolved_internal_handoff'
    elif goal == 'complete':
        disposition, reason = 'coordinator_closeout_check', 'closeout_needs_verification'
    elif not checkpoint:
        disposition, reason = 'checkpoint_required', 'missing_checkpoint'
    elif executor == 'idle' and goal in ('incomplete', 'unknown'):
        disposition, reason = 'coordinator_followup', 'executor_idle_with_residual_scope'
    elif executor in ('blocked', 'unavailable'):
        disposition, reason = 'coordinator_diagnosis', 'executor_' + executor
    elif blocker == 'external_wait':
        disposition, reason = 'wait_with_owner', 'recorded_external_wait'
    elif not recent:
        disposition, reason = 'coordinator_followup', 'progress_unobserved' if stamp is None else 'stale_progress'
    elif executor == 'unknown':
        disposition, reason = 'needs_executor_observation', 'executor_observation_missing' if observation is None else 'executor_observation_stale' if not fresh else 'executor_observation_unknown'
    else:
        disposition, reason = 'no_flag', 'recent_progress'
    return disposition, reason, executor, fresh, flags


class FollowupStoreMixin:
    def followup_checkpoint(self,run_id,goal_status,remaining_scope,blocker_class,next_owner,next_action,recheck_condition,evidence,source_event_id,observed_at):
        from .app import text,timestamp
        if goal_status not in GOAL_STATES or blocker_class not in BLOCKERS:
            raise ValueError('Invalid goal state or blocker class')
        if not isinstance(source_event_id, str):
            raise ValueError('A stable source event ID is required')
        source_event_id=text(source_event_id,300);observed_at=timestamp(observed_at)
        fields={'goal_status':goal_status,'remaining_scope':text(remaining_scope,4000),
                'blocker_class':blocker_class,'next_owner':text(next_owner,200),
                'next_action':text(next_action,2000),'recheck_condition':text(recheck_condition,2000),
                'evidence':text(evidence,4000),'source_event_id':source_event_id,'observed_at':observed_at}
        digest=hashlib.sha256(json.dumps(fields,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT * FROM followup_checkpoints WHERE run_id=? AND source_event_id=?',(run_id,source_event_id)).fetchone()
            if old:
                if old['content_sha256']!=digest:raise ValueError('Source identity conflicts with the recorded checkpoint')
                old = _checkpoint_projection(old)
                return {'checkpoint_id':old['id'],'identity_kind':old['identity_kind'],'content_sha256':old['content_sha256'],'run_id':run_id,'deduplicated':True,'record_only':True}
            run=db.execute('SELECT status,started FROM runs WHERE id=?',(run_id,)).fetchone()
            if not run or run['status'] not in OPEN:raise ValueError('Checkpoint needs an existing unfinished run')
            now = time.time()
            if observed_at < run['started'] or observed_at > now:
                raise ValueError('Source observation time cannot predate the run or lie in the future')
            event_id = str(uuid.uuid4())
            db.execute('INSERT INTO followup_checkpoints(run_id,source_event_id,observed_at,created,goal_status,remaining_scope,blocker_class,next_owner,next_action,recheck_condition,evidence,content_sha256,event_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (run_id,source_event_id,observed_at,now,goal_status,fields['remaining_scope'],blocker_class,fields['next_owner'],fields['next_action'],fields['recheck_condition'],fields['evidence'],digest,event_id))
            return {'checkpoint_id':event_id,'identity_kind':'uuid','content_sha256':digest,'run_id':run_id,'deduplicated':False,'record_only':True}

    def followup_audit(self,task_ids,now=None,stale_seconds=3600,executor_observations=None):
        if not isinstance(task_ids,(list,tuple)) or not task_ids or any(not isinstance(t,str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}',t) for t in task_ids):
            raise ValueError('Explicit, nonempty task IDs required')
        if isinstance(stale_seconds,bool) or not isinstance(stale_seconds,(int,float)) or not math.isfinite(stale_seconds) or not 1<=stale_seconds<=86400:
            raise ValueError('Stale interval must be 1–86400 seconds')
        now=time.time() if now is None else now
        if isinstance(now,bool) or not isinstance(now,(int,float)) or not math.isfinite(now) or now<0:raise ValueError('Invalid audit time')
        task_ids=list(dict.fromkeys(task_ids));receipts=[]
        observations = _executor_observations(executor_observations, now)
        # Use an independent read-only store, never the caller's writable connect.
        from .desktop_view import ReadOnlyStore
        with ReadOnlyStore(self.directory).connect() as db:
            db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            marks = ','.join('?' for _ in task_ids)
            scoped_run_ids = {r[0] for r in db.execute('SELECT id FROM runs WHERE task_id IN (' + marks + ')', task_ids)}
            if set(observations) - scoped_run_ids:
                raise ValueError('Executor observation run_id is unknown or outside the explicit task scope')
            for task_id in task_ids:
                if not db.execute('SELECT 1 FROM tasks WHERE id=?',(task_id,)).fetchone():raise ValueError('Unknown selected activity: '+task_id)
                runs=db.execute('SELECT * FROM runs WHERE task_id=? AND status IN (?,?,?,?,?) ORDER BY started,id',(task_id,*OPEN)).fetchall()
                for row in runs:
                    run=dict(row);checkpoint=None;progress=None
                    if 'followup_checkpoints' in tables:
                        checkpoint=db.execute('SELECT * FROM followup_checkpoints WHERE run_id=? ORDER BY COALESCE(observed_at,created) DESC,created DESC,id DESC LIMIT 1',(run['id'],)).fetchone()
                        checkpoint=_checkpoint_projection(checkpoint)
                    if 'progress_updates' in tables:
                        progress=db.execute('SELECT * FROM progress_updates WHERE run_id=? ORDER BY created DESC,id DESC LIMIT 1',(run['id'],)).fetchone()
                        progress=dict(progress) if progress else None
                    observation = observations.get(run['id'])
                    disposition, reason, executor, fresh, flags = _disposition(checkpoint, progress, observation, now, stale_seconds)
                    receipts.append({'task_id':task_id, 'run_id':run['id'], 'checked_at':now,
                        'lifecycle':run['status'], 'latest_progress_at':(progress or {}).get('created'),
                        'executor_status':executor, 'executor_observation':observation,
                        'checkpoint':checkpoint, 'disposition':disposition, 'reason':reason,
                        'next_action':(checkpoint or {}).get('next_action') or 'Inspect current authorized scope and record an evidence-backed checkpoint',
                        'notification':'not_sent_by_audit', 'record_only':True,
                        'executor_observation_fresh':fresh, 'executor_observation_max_age_seconds':min(300, stale_seconds),
                        'flags':flags})
        return {'schema':'dots-panel.followup-audit.v1', 'checked_at':now, 'task_scope':task_ids,
                'receipts':receipts, 'run_count':len(receipts), 'source':'local_recorded_data',
                'record_only':True, 'scheduler_hook':'not_verified_by_audit', 'backup_result':'separate_not_inferred'}
