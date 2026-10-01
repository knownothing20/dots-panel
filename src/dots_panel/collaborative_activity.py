"""Activity-scoped collaboration records. No discovery, dispatch or live inventory."""
import hashlib
import json
import sqlite3
import time
import uuid

OPEN = ('running', 'waiting_user', 'waiting_external', 'paused', 'awaiting_review')
KINDS = ('task', 'project')
MODES = ('single', 'team')
SCHEMA = '''
CREATE TABLE IF NOT EXISTS assignment_episodes (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
 agent_id TEXT NOT NULL REFERENCES agents(id), work_type TEXT NOT NULL,
 assigned_at REAL NOT NULL, ended_at REAL, end_reason TEXT NOT NULL DEFAULT '',
 provenance TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS one_open_assignment_episode
 ON assignment_episodes(run_id,agent_id) WHERE ended_at IS NULL;
CREATE TRIGGER IF NOT EXISTS immutable_assignment_role BEFORE UPDATE OF
 id,run_id,agent_id,work_type,assigned_at,provenance ON assignment_episodes
 BEGIN SELECT RAISE(ABORT,'Assignment identity and role are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_assignment_end BEFORE UPDATE OF ended_at,end_reason ON assignment_episodes
 WHEN OLD.ended_at IS NOT NULL
 BEGIN SELECT RAISE(ABORT,'Ended assignment is immutable'); END;
CREATE TABLE IF NOT EXISTS activity_structure_history (
 id INTEGER PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id),
 created REAL NOT NULL, previous_json TEXT NOT NULL, current_json TEXT NOT NULL,
 reason TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS event_attributions (
 row_kind TEXT NOT NULL CHECK(row_kind IN ('activity','event')), row_id INTEGER NOT NULL,
 run_id TEXT NOT NULL REFERENCES runs(id), agent_id TEXT NOT NULL REFERENCES agents(id),
 assignment_id TEXT NOT NULL REFERENCES assignment_episodes(id), work_type TEXT NOT NULL,
 actor_name TEXT NOT NULL, actor_name_en TEXT NOT NULL, portrait TEXT NOT NULL,
 actor_display_id TEXT NOT NULL, color_key TEXT NOT NULL, recorded_at REAL NOT NULL,
 PRIMARY KEY(row_kind,row_id));
CREATE TRIGGER IF NOT EXISTS immutable_event_attribution BEFORE UPDATE ON event_attributions
 BEGIN SELECT RAISE(ABORT,'Event attribution is immutable'); END;
'''


def migrate(db):
    db.execute('SAVEPOINT collaboration_migration')
    try:
        _migrate(db)
        db.execute('RELEASE collaboration_migration')
    except Exception:
        db.execute('ROLLBACK TO collaboration_migration')
        db.execute('RELEASE collaboration_migration')
        raise


def _migrate(db):
    columns = {r[1] for r in db.execute('PRAGMA table_info(tasks)')}
    for name, definition in (
        ('activity_kind', "TEXT NOT NULL DEFAULT 'task'"),
        ('collaboration_mode', "TEXT NOT NULL DEFAULT 'single'"),
        ('mode_source', "TEXT NOT NULL DEFAULT 'legacy_default'"),
        ('parent_task_id', 'TEXT REFERENCES tasks(id)')):
        if name not in columns:
            db.execute('ALTER TABLE tasks ADD COLUMN '+name+' '+definition)
    statement = ""
    for line in SCHEMA.splitlines(True):
        statement += line
        if sqlite3.complete_statement(statement):
            db.execute(statement)
            statement = ""
    attribution_columns = {r[1] for r in db.execute("PRAGMA table_info(event_attributions)")}
    if "actor_short_id" not in attribution_columns:
        db.execute("ALTER TABLE event_attributions ADD COLUMN actor_short_id TEXT")
    # Only preserve the last known legacy association. Never invent earlier roles.
    for row in db.execute('SELECT a.*,r.status,r.finished FROM agent_run_assignments a JOIN runs r ON r.id=a.run_id').fetchall():
        if db.execute('SELECT 1 FROM assignment_episodes WHERE run_id=? AND agent_id=?', (row['run_id'],row['agent_id'])).fetchone():
            continue
        key = 'legacy-' + hashlib.sha256((row['run_id']+'\0'+row['agent_id']).encode()).hexdigest()[:24]
        ended = None if row['status'] in OPEN else max(row['assigned_at'], row['finished'] or row['assigned_at'])
        db.execute('INSERT INTO assignment_episodes VALUES(?,?,?,?,?,?,?,?)',
                   (key,row['run_id'],row['agent_id'],row['work_type'],row['assigned_at'],ended,
                    'Legacy terminal association' if ended is not None else '', 'legacy_snapshot'))


def validate_structure(db, task_id, kind, mode, parent):
    if kind not in KINDS or mode not in MODES:
        raise ValueError('Invalid activity kind or collaboration mode')
    if parent:
        if kind != 'task' or parent == task_id:
            raise ValueError('Only tasks may belong to a different project')
        row = db.execute('SELECT * FROM tasks WHERE id=?', (parent,)).fetchone()
        if not row or row['activity_kind'] != 'project' or row['parent_task_id']:
            raise ValueError('Parent must be an existing root project')
        previous = db.execute('SELECT parent_task_id FROM tasks WHERE id=?',(task_id,)).fetchone()
        if not previous or previous['parent_task_id'] != parent:
            latest = db.execute('SELECT status FROM runs WHERE task_id=? ORDER BY started DESC,id DESC LIMIT 1',(parent,)).fetchone()
            if latest and latest['status'] not in OPEN and not db.execute('SELECT 1 FROM runs WHERE task_id=? AND status IN (?,?,?,?,?)',(parent,*OPEN)).fetchone():
                raise ValueError('Start an authorized new parent run before adding scope to a finished project')
    if kind != 'project' and db.execute('SELECT 1 FROM tasks WHERE parent_task_id=?',(task_id,)).fetchone():
        raise ValueError('A project with children cannot become a task')


def assignment_context(db, assignment_id, run_id=None, task_id=None):
    row = db.execute('SELECT e.*,r.task_id,r.status,a.name,a.name_en,a.portrait,a.identity_verification,a.identity_source,a.identity_evidence FROM assignment_episodes e JOIN runs r ON r.id=e.run_id JOIN agents a ON a.id=e.agent_id WHERE e.id=?',(assignment_id,)).fetchone()
    if not row or (run_id is not None and row['run_id'] != run_id) or (task_id is not None and row['task_id'] != task_id):
        raise ValueError('Assignment does not match the event run and activity')
    if row['ended_at'] is not None or row['status'] not in OPEN:
        raise ValueError('New attribution requires an open assignment and unfinished run')
    if row['provenance'] == 'legacy_snapshot' or row['identity_verification'] != 'observed' or row['identity_source'] != 'manual' or not row['identity_evidence'].strip():
        raise ValueError('Attribution requires an explicitly assigned and verified actor')
    return dict(row)


def attribute(db, row_kind, row_id, context):
    if not context:
        return
    if row_kind not in ('activity','event'):
        raise ValueError('Invalid attribution row kind')
    row = db.execute('SELECT * FROM '+('activity' if row_kind=='activity' else 'events')+' WHERE id=?',(row_id,)).fetchone()
    if not row or (row_kind=='activity' and row['task_id']!=context['task_id']) or (row_kind=='event' and row['run_id']!=context['run_id']):
        raise ValueError('Attribution target mismatch')
    # A full panel-local ID is collision-free and explicitly not a platform ID.
    from .agent_identity import profile_short_ids
    short_id = profile_short_ids([dict(r) for r in db.execute('SELECT id FROM agents')])[context['agent_id']]
    db.execute('INSERT INTO event_attributions(row_kind,row_id,run_id,agent_id,assignment_id,work_type,actor_name,actor_name_en,portrait,actor_display_id,color_key,recorded_at,actor_short_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (row_kind,row_id,context['run_id'],context['agent_id'],context['id'],context['work_type'],
         context['name'],context['name_en'],context['portrait'] or '',context['agent_id'],
         hashlib.sha256(context['agent_id'].encode()).hexdigest()[:8],time.time(),short_id))


def decorate(rows, attributions, kind):
    lookup = {(a['row_kind'],a['row_id']): a for a in attributions}
    for row in rows:
        attribution = lookup.get((kind,row['id']))
        row['attribution'] = dict(attribution) if attribution else None
        row['attribution_state'] = 'recorded' if attribution else 'historical_unattributed'
        if attribution:
            from .agent_identity import portrait_spec, PORTRAITS
            # Render only the frozen portrait key, never today's mutable profile.
            row['attribution']['portrait_spec'] = portrait_spec({'portrait':attribution['portrait']}) if attribution.get('portrait') in PORTRAITS else None
            row['run_id'] = attribution['run_id']
            row['agent_id'] = attribution['agent_id']
            row['assignment_id'] = attribution['assignment_id']
            row['work_type_at_event'] = attribution['work_type']
    return rows


def guard_project_closeout(db, task_id, run_id=None):
    task = db.execute('SELECT activity_kind FROM tasks WHERE id=?',(task_id,)).fetchone()
    if not task or task['activity_kind'] != 'project':
        return
    if run_id and db.execute('SELECT 1 FROM runs WHERE task_id=? AND id<>? AND status IN (?,?,?,?,?)',(task_id,run_id,*OPEN)).fetchone():
        raise ValueError('Project has another unfinished coordination run')
    for child in db.execute('SELECT id FROM tasks WHERE parent_task_id=?',(task_id,)).fetchall():
        runs = db.execute('SELECT * FROM runs WHERE task_id=? ORDER BY started DESC,id DESC',(child['id'],)).fetchall()
        if not runs or any(r['status'] in OPEN for r in runs) or runs[0]['status'] != 'succeeded':
            raise ValueError('Project has an unresolved child activity: '+child['id'])


class CollaborationStoreMixin:
    def activity_structure(self, task_id, activity_kind=None, collaboration_mode=None, parent_task_id=None, reason='', clear_parent=False):
        from .app import text
        reason = text(reason,2000)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM tasks WHERE id=?',(task_id,)).fetchone()
            if not row:
                raise ValueError('Unknown activity')
            if clear_parent and parent_task_id:
                raise ValueError('Choose a parent or clear it, not both')
            before = {k:row[k] for k in ('activity_kind','collaboration_mode','parent_task_id','mode_source')}
            after = dict(before, activity_kind=activity_kind or row['activity_kind'],
                         collaboration_mode=collaboration_mode or row['collaboration_mode'],
                         parent_task_id=None if clear_parent else parent_task_id if parent_task_id is not None else row['parent_task_id'],mode_source='explicit')
            validate_structure(db,task_id,after['activity_kind'],after['collaboration_mode'],after['parent_task_id'])
            if before == after:
                return {'task_id':task_id,'deduplicated':True,**after}
            db.execute('UPDATE tasks SET activity_kind=?,collaboration_mode=?,parent_task_id=?,mode_source=? WHERE id=?',
                       tuple(after[k] for k in ('activity_kind','collaboration_mode','parent_task_id','mode_source'))+(task_id,))
            db.execute('INSERT INTO activity_structure_history(task_id,created,previous_json,current_json,reason) VALUES(?,?,?,?,?)',
                       (task_id,time.time(),json.dumps(before),json.dumps(after),reason))
        return {'task_id':task_id,'deduplicated':False,**after}

    def assignment_end(self, assignment_id, reason):
        from .app import text
        reason = text(reason,2000)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM assignment_episodes WHERE id=?',(assignment_id,)).fetchone()
            if not row:
                raise ValueError('Unknown assignment')
            if row['ended_at'] is not None:
                if row['end_reason'] != reason:
                    raise ValueError('Assignment already ended with different evidence')
                return {'assignment_id':assignment_id,'deduplicated':True}
            db.execute('UPDATE assignment_episodes SET ended_at=?,end_reason=? WHERE id=?',(time.time(),reason,assignment_id))
        return {'assignment_id':assignment_id,'deduplicated':False,'record_only':True}

    def collaboration_timeline(self, task_id, include_children=False, agent_id=None, work_type=None, child_task_id=None, limit=100, offset=0):
        if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=500 or isinstance(offset,bool) or not isinstance(offset,int) or offset<0:
            raise ValueError('Timeline limit must be 1..500 and offset nonnegative')
        with self.connect() as db:
            task = db.execute('SELECT * FROM tasks WHERE id=?',(task_id,)).fetchone()
            if not task:
                raise ValueError('Unknown activity')
            ids = [task_id]
            if include_children and 'activity_kind' in task.keys() and task['activity_kind']=='project':
                ids += [r['id'] for r in db.execute('SELECT id FROM tasks WHERE parent_task_id=? ORDER BY id',(task_id,))]
            if child_task_id:
                if child_task_id not in ids:
                    raise ValueError('Task filter is outside the selected activity')
                ids = [child_task_id]
            placeholders = ','.join('?' for _ in ids)
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            attributions = [dict(r) for r in db.execute('SELECT * FROM event_attributions')] if 'event_attributions' in tables else []
            rows = decorate([dict(r) for r in db.execute('SELECT * FROM activity WHERE task_id IN ('+placeholders+')',ids)],attributions,'activity')
            for r in rows:
                r.update(kind='activity',key='activity:'+str(r['id']))
            mirrors = {(r['task_id'],r['created'],r['message']) for r in rows if not r['attribution']}
            events = decorate([dict(r) for r in db.execute('SELECT e.*,r.task_id FROM events e JOIN runs r ON r.id=e.run_id WHERE r.task_id IN ('+placeholders+')',ids)],attributions,'event')
            for r in events:
                if not r['attribution'] and (r['task_id'],r['created'],r['message']) in mirrors:
                    continue
                r.update(kind='event',key='event:'+str(r['id'])); rows.append(r)
            if agent_id:
                rows = [r for r in rows if (r['attribution'] or {}).get('agent_id')==agent_id or agent_id=='unattributed' and not r['attribution']]
            if work_type:
                rows = [r for r in rows if (r['attribution'] or {}).get('work_type')==work_type or work_type=='unattributed' and not r['attribution']]
            rows.sort(key=lambda r:(-r['created'],r['kind'],r['id']))
            total = len(rows)
            return {'task_id':task_id,'rows':rows[offset:offset+limit],'total':total,'offset':offset,'limit':limit,
                    'has_more':offset+limit<total,'source':'manual_records','includes_children':include_children,'record_only':True}
