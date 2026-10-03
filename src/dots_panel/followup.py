"""Evidence-bearing goal checkpoints and scoped, read-only responsibility audits.

This module never dispatches, retries, changes schedules or infers executor liveness.
"""
import hashlib
import json
import math
import re
import sqlite3
import time

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


def technical_failure(text):
    """Narrow, disclosed heuristic; never treats evidence prose as current failure."""
    if not re.search(r'\bERR_[A-Z0-9_]+\b|Traceback \(most recent call last\)',text):
        return False
    negative=re.search(r'\b(?:not|never|unresolved|cannot|can\x27t|hasn\x27t|isn\x27t|wasn\x27t)\b.{0,35}\b(?:resolv|fix|recover)|尚未|未修|未解|没有解决',text,re.I)
    affirmative=re.search(r'\b(?:resolved|fixed|recovered)\b|已修复|已解决|已恢复',text,re.I)
    return bool(negative) or not affirmative


class FollowupStoreMixin:
    def followup_checkpoint(self,run_id,goal_status,remaining_scope,blocker_class,next_owner,next_action,recheck_condition,evidence,source_event_id,observed_at):
        from .app import text,timestamp
        if goal_status not in GOAL_STATES or blocker_class not in BLOCKERS:
            raise ValueError('Invalid goal state or blocker class')
        source_event_id=text(source_event_id,300);observed_at=timestamp(observed_at)
        if not math.isfinite(observed_at) or observed_at<0 or observed_at>time.time()+300:
            raise ValueError('Invalid source observation time')
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
                return {'checkpoint_id':old['id'],'run_id':run_id,'deduplicated':True,'record_only':True}
            run=db.execute('SELECT status FROM runs WHERE id=?',(run_id,)).fetchone()
            if not run or run['status'] not in OPEN:raise ValueError('Checkpoint needs an existing unfinished run')
            cur=db.execute('INSERT INTO followup_checkpoints(run_id,source_event_id,observed_at,created,goal_status,remaining_scope,blocker_class,next_owner,next_action,recheck_condition,evidence,content_sha256) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                (run_id,source_event_id,observed_at,time.time(),goal_status,fields['remaining_scope'],blocker_class,fields['next_owner'],fields['next_action'],fields['recheck_condition'],fields['evidence'],digest))
            return {'checkpoint_id':cur.lastrowid,'run_id':run_id,'deduplicated':False,'record_only':True}

    def followup_audit(self,task_ids,now=None,stale_seconds=3600,executor_observations=None):
        if not isinstance(task_ids,(list,tuple)) or not task_ids or any(not isinstance(t,str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}',t) for t in task_ids):
            raise ValueError('Explicit, nonempty task IDs required')
        if isinstance(stale_seconds,bool) or not isinstance(stale_seconds,(int,float)) or not math.isfinite(stale_seconds) or stale_seconds<=0:
            raise ValueError('Invalid stale interval')
        now=time.time() if now is None else now
        if isinstance(now,bool) or not isinstance(now,(int,float)) or not math.isfinite(now):raise ValueError('Invalid audit time')
        task_ids=list(dict.fromkeys(task_ids));receipts=[]
        # Connect explicitly read-only even if this Store is a writable instance.
        from .app import open_directory
        fd=open_directory(self.directory/'db')
        try:
            import os
            dbfd=os.open('panel.sqlite3',os.O_RDONLY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(dbfd)
        finally:
            import os
            os.close(fd)
        db=sqlite3.connect('file:'+str(self.directory/'db'/'panel.sqlite3')+'?mode=ro',uri=True)
        db.row_factory=sqlite3.Row
        try:
            db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for task_id in task_ids:
                if not db.execute('SELECT 1 FROM tasks WHERE id=?',(task_id,)).fetchone():raise ValueError('Unknown selected activity: '+task_id)
                runs=db.execute('SELECT * FROM runs WHERE task_id=? AND status IN (?,?,?,?,?) ORDER BY started,id',(task_id,*OPEN)).fetchall()
                for row in runs:
                    run=dict(row);checkpoint=None;progress=None
                    if 'followup_checkpoints' in tables:
                        checkpoint=db.execute('SELECT * FROM followup_checkpoints WHERE run_id=? ORDER BY observed_at DESC,created DESC,id DESC LIMIT 1',(run['id'],)).fetchone()
                        checkpoint=dict(checkpoint) if checkpoint else None
                    if 'progress_updates' in tables:
                        progress=db.execute('SELECT * FROM progress_updates WHERE run_id=? ORDER BY created DESC,id DESC LIMIT 1',(run['id'],)).fetchone()
                        progress=dict(progress) if progress else None
                    flags=[]
                    if not checkpoint:flags.append('missing_checkpoint')
                    elif checkpoint['blocker_class'] in ('security','access','approval','failure','internal_handoff','unknown'):
                        flags.append('unresolved_'+checkpoint['blocker_class'])
                    if checkpoint and checkpoint['goal_status']=='complete':flags.append('closeout_needs_verification')
                    current_text=' '.join(str((progress or {}).get(k) or '') for k in ('current_step','result'))
                    if technical_failure(current_text):flags.append('technical_failure_hint')
                    progress_time=(progress or {}).get('created')
                    if isinstance(progress_time,(float,int)) and now-progress_time>stale_seconds:flags.append('stale_progress')
                    if progress_time is None:flags.append('progress_unobserved')
                    observation=(executor_observations or {}).get(run['id'])
                    receipts.append({'task_id':task_id,'run_id':run['id'],'lifecycle_status':run['status'],
                        'disposition':'coordinator_action_required' if flags else 'waiting_for_recorded_condition' if checkpoint and checkpoint['blocker_class']=='external_wait' else 'no_immediate_flag',
                        'flags':flags,'reason':'; '.join(flags) if flags else 'Recorded checkpoint and progress have no scoped immediate flag',
                        'checkpoint':checkpoint,'latest_progress':progress,'executor_observation':observation,
                        'executor_state':'unknown' if not observation else observation.get('status','unknown'),
                        'observation_is_not_lifecycle':True,'next_owner':(checkpoint or {}).get('next_owner') or 'coordinator',
                        'next_action':(checkpoint or {}).get('next_action') or 'Inspect current authorized scope and record an evidence-backed checkpoint',
                        'recheck_condition':(checkpoint or {}).get('recheck_condition') or 'Fresh supported executor and outcome evidence',
                        'backup_status':'separate_not_checked'})
        finally:db.close()
        return {'read_only':True,'dispatches':False,'sampled_at':now,'scope':task_ids,'open_run_count':len(receipts),'receipts':receipts,'upstream_message_coverage':'not_connected'}
