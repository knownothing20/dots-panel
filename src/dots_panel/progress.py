"""Explicit meaningful work updates. Read models never invent executor progress."""
import hashlib
import json
import math
import time

TABLE_SQL = '''CREATE TABLE IF NOT EXISTS progress_updates (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id), created REAL NOT NULL,
 current_step TEXT NOT NULL, result TEXT NOT NULL, next_step TEXT NOT NULL,
 completed REAL, total REAL, unit TEXT NOT NULL, evidence TEXT NOT NULL,
 source_event_id TEXT, UNIQUE(run_id,source_event_id));'''


def record_progress(store, run_id, current_step, result, next_step, evidence, completed=None, total=None, unit='', source_event_id=None, assignment_id=None):
    from .app import text, OPEN_STATUSES
    current_step, evidence = text(current_step, 1000), text(evidence, 2000)
    result = text(result, 2000) if result else ''
    next_step = text(next_step, 1000) if next_step else ''
    unit = text(unit, 40) if unit else ''
    if (completed is None) != (total is None):
        raise ValueError('Completed and total must be supplied together')
    if completed is not None:
        if isinstance(completed,bool) or isinstance(total,bool) or not all(isinstance(n,(int,float)) and math.isfinite(n) for n in (completed,total)) or total <= 0 or not 0 <= completed <= total or not unit:
            raise ValueError('Measured progress requires 0 <= completed <= total, total > 0 and a unit')
    if source_event_id is not None:
        source_event_id = text(source_event_id, 200)
    content = {'run_id':run_id,'current_step':current_step,'result':result,'next_step':next_step,'completed':completed,'total':total,'unit':unit,'evidence':evidence}
    if assignment_id is not None:
        content['assignment_id'] = assignment_id
    fingerprint = hashlib.sha256(json.dumps(content,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    now = time.time()
    with store.connect() as db:
        db.execute(TABLE_SQL)
        db.execute('BEGIN IMMEDIATE')
        run = db.execute('SELECT * FROM runs WHERE id=?',(run_id,)).fetchone()
        if not run or run['status'] not in OPEN_STATUSES:
            raise ValueError('Progress requires an existing unfinished run')
        from .collaborative_activity import assignment_context, attribute
        previous = db.execute('SELECT * FROM progress_updates WHERE run_id=? ORDER BY created DESC,id DESC LIMIT 1',(run_id,)).fetchone()
        duplicate = db.execute('SELECT * FROM progress_updates WHERE run_id=? AND source_event_id=?',(run_id,source_event_id)).fetchone() if source_event_id else None
        if duplicate:
            if duplicate['id'] != fingerprint:
                raise ValueError('Source event ID already records different progress')
            return {'id':duplicate['id'],'run_id':run_id,'deduplicated':True}
        if previous and previous['id'] == fingerprint:
            return {'id':previous['id'],'run_id':run_id,'deduplicated':True}
        # Identical content anywhere in this run is not a new milestone.
        if db.execute('SELECT id FROM progress_updates WHERE id=?',(fingerprint,)).fetchone():
            return {'id':fingerprint,'run_id':run_id,'deduplicated':True}
        context = assignment_context(db,assignment_id,run_id=run_id) if assignment_id else None
        db.execute('INSERT INTO progress_updates VALUES(?,?,?,?,?,?,?,?,?,?,?)',(fingerprint,run_id,now,current_step,result,next_step,completed,total,unit,evidence,source_event_id))
        message = current_step + (('\n'+result) if result else '') + ((f'\n{completed:g}/{total:g} {unit}') if completed is not None else '') + (('\n下一步 / Next: '+next_step) if next_step else '')
        task = db.execute('SELECT project FROM tasks WHERE id=?',(run['task_id'],)).fetchone()
        cursor = db.execute('INSERT INTO activity(created,project,role,stage,message,task_id,state,source_event_id) VALUES(?,?,?,?,?,?,?,?)',(now,task['project'],'assistant','progress',message,run['task_id'],'in_progress','progress-update:'+fingerprint))
        attribute(db,'activity',cursor.lastrowid,context)
    return {'id':fingerprint,'run_id':run_id,'deduplicated':False,'created':now}


def observed_run_ids(snapshot, now=None):
    """Fresh profiles only support their most recently assigned topic, not old ones."""
    runs = {r['id']: r for key in ('runs', 'latest_runs', 'current_runs', 'open_runs') for r in snapshot.get(key, []) if 'id' in r}
    active = set()
    for agent in snapshot.get('agents', []):
        if agent.get('status') != 'running' or not agent_observation(agent, snapshot, now)['recent']:
            continue
        links = [a for a in snapshot.get('agent_run_assignments', []) if a['agent_id'] == agent['id']]
        latest = max((a.get('assigned_at', 0) for a in links), default=None)
        newest = [runs.get(a['run_id']) for a in links if a.get('assigned_at', 0) == latest]
        if not newest or any(r is None for r in newest):
            continue
        topics = {r['task_id'] for r in newest}
        if len(topics) == 1 and any(r['status'] == 'running' for r in newest):
            active.update(a['run_id'] for a in links if a['run_id'] in runs and runs[a['run_id']]['task_id'] in topics and runs[a['run_id']]['status'] == 'running')
    return active


def current_run(snapshot, task_id, now=None):
    """Fresh assigned execution first, then newest unfinished, then newest terminal."""
    now = time.time() if now is None else now
    runs = {r.get('id', str(i)):r for i,r in enumerate([*snapshot.get('runs',[]), *snapshot.get('latest_runs',[]), *snapshot.get('current_runs',[]), *snapshot.get('open_runs',[])]) if r['task_id']==task_id}
    open_states = {'pending','running','waiting_user','waiting_external','paused','awaiting_review'}
    active_ids = observed_run_ids(snapshot, now)
    def order(run):
        return (run['status'] in open_states, run['status']=='running' and run.get('id') in active_ids, run.get('started',0), run.get('id',''))
    return max(runs.values(),key=order,default=None)


def agent_observation(agent, snapshot, now=None):
    now = time.time() if now is None else now
    observed = (agent or {}).get('observed_at')
    known = isinstance(observed, (int, float)) and not isinstance(observed, bool) and math.isfinite(observed)
    return {'known': known, 'recent': known and (agent or {}).get('identity_verification') != 'historical' and 0 <= now-observed <= snapshot.get('stale_after_seconds', 120),
            'status': agent.get('status', 'unknown') if agent and known else 'unknown'}


def task_participants(snapshot, task_id, now=None):
    """Keep assignment identity independently of observation age, scoped to its run."""
    current = current_run(snapshot, task_id, now)
    agents = {a['id']: a for a in snapshot.get('agents', [])}
    owner_id = next((a['agent_id'] for a in snapshot.get('agent_assignments', []) if a['task_id'] == task_id), None)
    links = [a for a in snapshot.get('agent_run_assignments', []) if current and a['run_id'] == current['id'] and a['agent_id'] in agents]
    links.sort(key=lambda a: (-a.get('assigned_at', 0), a['agent_id']))
    assigned = [agents[a['agent_id']] for a in links]
    owner = agents.get(owner_id)
    candidates = assigned or ([owner] if owner else [])
    active = [a for a in candidates if current and current['status'] == 'running' and a.get('status') == 'running' and agent_observation(a, snapshot, now)['recent']
              and (current['id'] in observed_run_ids(dict(snapshot, agents=[a]), now) if any(link['agent_id'] == a['id'] for link in snapshot.get('agent_run_assignments', [])) else not assigned)]
    active.sort(key=lambda a: (-a['observed_at'], a['id']))
    return {'assigned': assigned, 'active': active, 'owner': owner, 'agent': next(iter(active or assigned), owner),
            'run_id': current['id'] if current else None}


def dispatch_check(snapshot, task_id, agent_id, now=None):
    """Narrow evidence hint, never a lock or a declaration of executor availability."""
    now = time.time() if now is None else now
    if not any(t['id'] == task_id for t in snapshot.get('tasks', [])):
        raise ValueError('Unknown task ID')
    agent = next((a for a in snapshot.get('agents', []) if a['id'] == agent_id), None)
    if not agent:
        raise ValueError('Unknown agent ID')
    result = {'task_id': task_id, 'agent_id': agent_id, 'assessment': 'unverified', 'conflicts': [],
              'record_only': True, 'platform_check_required': True}
    observation = agent_observation(agent, snapshot, now)
    links = [a for a in snapshot.get('agent_run_assignments', []) if a['agent_id'] == agent_id]
    latest_time = max((a.get('assigned_at', 0) for a in links), default=None)
    latest = [a for a in links if a.get('assigned_at', 0) == latest_time]
    runs = {r['id']: r for key in ('runs', 'latest_runs', 'current_runs', 'open_runs') for r in snapshot.get(key, []) if 'id' in r}
    # A missing/terminal latest assignment must not resurrect an older busy record.
    latest_runs = [runs.get(a['run_id']) for a in latest]
    if (not observation['recent'] or agent.get('status') != 'running' or latest_time is None
            or agent['observed_at'] < latest_time or not latest_runs or any(r is None for r in latest_runs)):
        return result
    goals = {r['task_id'] for r in latest_runs}
    if len(goals) != 1 or task_id in goals:
        return result
    result['conflicts'] = [{'task_id': r['task_id'], 'run_id': r['id'], 'assigned_at': latest_time,
                            'observed_at': agent['observed_at']} for r in latest_runs if r['status'] == 'running']
    if result['conflicts']:
        result['assessment'] = 'recorded_conflict'
    return result


def task_progress(snapshot, task_id, now=None):
    now = time.time() if now is None else now
    runs = {r['id']:r for r in [*snapshot.get('runs',[]),*snapshot.get('latest_runs',[]),*snapshot.get('open_runs',[])] if r['task_id']==task_id}
    open_states = {'pending','running','waiting_user','waiting_external','paused','awaiting_review'}
    open_runs = sorted([r for r in runs.values() if r['status'] in open_states],key=lambda r:(r.get('started',0),r['id']),reverse=True)
    current = current_run(snapshot, task_id, now)
    all_updates = snapshot.get('progress_updates',[])
    def activity_run(row):
        if row.get('run_id') in runs:
            return row['run_id']
        linked = [u['run_id'] for u in all_updates if (row.get('source_event_id')=='progress-update:'+u['id'] or (row.get('stage')=='progress' and row.get('created')==u['created'] and row.get('message','').split('\n',1)[0]==u['current_step'].split('\n',1)[0]))]
        linked += [e['run_id'] for e in snapshot.get('events',[]) if e['run_id'] in runs and e.get('created')==row.get('created') and e.get('message')==row.get('message')]
        unique = set(linked)
        return next(iter(unique)) if len(unique)==1 else None
    updates = sorted([r for r in snapshot.get('progress_updates',[]) if current and r['run_id']==current['id']],key=lambda r:(r['created'],r['id']),reverse=True)
    latest = updates[0] if updates else None
    meaningful = sorted([r for r in snapshot.get('activity',[]) if r.get('task_id')==task_id and r.get('created',0)>=(current.get('started',0) if current else 0) and r.get('stage') not in ('assignment','work_type','heartbeat') and (activity_run(r) is None or current and activity_run(r)==current['id'])],key=lambda r:(r['created'],str(r.get('id',''))),reverse=True)
    if latest and meaningful and meaningful[0]['created']>latest['created']:
        latest = None
    participants = task_participants(snapshot, task_id, now)
    return {'scope':'task' if not latest and meaningful and activity_run(meaningful[0]) is None else 'run','open_runs':[{'id':r['id'],'status':r['status'],'note':r.get('note',''),'started':r.get('started')} for r in open_runs],'unpaused_runs':[{'id':r['id'],'status':r['status'],'note':r.get('note',''),'started':r.get('started')} for r in open_runs if r['status']!='paused'],'latest':latest,'steps':updates[:8],'milestones':meaningful[:5],'active_participants':participants['active'],'assigned_participants':participants['assigned'],'lead':participants,'current_run_id':current['id'] if current else None,'current_step':latest['current_step'] if latest else meaningful[0]['message'] if meaningful else ((current.get('next_step') or current.get('note','')) if current else ''), 'updated_at':latest['created'] if latest else meaningful[0]['created'] if meaningful else current.get('started') if current else None,'counts':{'completed':latest['completed'],'total':latest['total'],'unit':latest['unit']} if latest and latest.get('completed') is not None and current and current['status']=='running' else None}


def task_meaningful_updated(snapshot, task_id):
    """Sorting timestamp: actual work/lifecycle evidence, never a heartbeat."""
    runs = {row.get('id', (task_id, row.get('started'))): row for key in ('runs', 'latest_runs', 'current_runs', 'open_runs')
            for row in snapshot.get(key, []) if row.get('task_id') == task_id}
    values = [row.get('created', 0) for row in snapshot.get('tasks', []) if row['id'] == task_id]
    values += [row.get(field, 0) for row in runs.values() for field in ('started', 'finished')]
    values += [row.get('created', 0) for row in snapshot.get('activity', [])
               if row.get('task_id') == task_id and row.get('stage') not in ('heartbeat', 'assignment', 'work_type')]
    values += [row.get('created', 0) for row in snapshot.get('progress_updates', []) if row.get('run_id') in runs]
    values += [row.get('created', 0) for row in snapshot.get('events', [])
               if row.get('run_id') in runs and row.get('kind') != 'heartbeat' and row.get('stage') != 'heartbeat']
    return max((value for value in values if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)), default=0)
