"""Activity-related profiles only. Assignment records never prove live execution."""
from .agent_identity import profile_short_ids


def activity_participants(snapshot, task_id, now=None):
    """Roster for the selected open run only; historical authors stay elsewhere."""
    import time
    from .progress import current_run
    now=time.time() if now is None else now
    run=current_run(snapshot,task_id,now)
    if not run or run.get('status') not in {'pending','running','waiting_user','waiting_external','awaiting_review'}:
        return []
    agents={a['id']:a for a in snapshot.get('agents',[])}
    links={}
    for link in snapshot.get('agent_run_assignments',[]):
        if link.get('run_id')==run['id'] and link.get('task_id') in (None,task_id) and link.get('agent_id') in agents:
            links.setdefault(link['agent_id'],[]).append(link)
    episodes={}
    for episode in snapshot.get('assignment_episodes',[]):
        if episode.get('run_id')==run['id'] and episode.get('task_id') in (None,task_id) and episode.get('agent_id') in agents:
            episodes.setdefault(episode['agent_id'],[]).append(episode)
    keys=profile_short_ids(list(agents.values()));rows=[]
    for key in links.keys() | episodes.keys():
        candidates=[e for e in episodes[key] if e.get('ended_at') is None] if key in episodes else links[key]
        candidates=[a for a in candidates if isinstance(a.get('assigned_at'),(int,float)) and not isinstance(a['assigned_at'],bool) and 0<=a['assigned_at']<=now]
        if not candidates:continue
        assignment=max(candidates,key=lambda a:(a['assigned_at'],a.get('id','')))
        rows.append({'agent':agents[key],'short_id':keys[key],'assignments':[{'run_id':run['id'],'work_type':assignment.get('work_type','unspecified'),'assigned_at':assignment['assigned_at'],'source':'run'}]})
    rows.sort(key=lambda r:(-r['assignments'][0]['assigned_at'],r['agent']['id']))
    return rows


def profile_reference(agent,language='zh'):
    if not agent:return 'Unassigned' if language=='en' else '未分配'
    short=agent.get('panel_short_id') or profile_short_ids([agent])[agent['id']]
    return ('Panel ID ' if language=='en' else '面板编号 ')+short
