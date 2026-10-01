"""Activity-related profiles only. Assignment records never prove live execution."""
from .agent_identity import profile_short_ids


def activity_participants(snapshot, task_id):
    agents={a['id']:a for a in snapshot.get('agents',[])}
    runs={r['id']:r for field in ('runs','latest_runs','open_runs','current_runs') for r in snapshot.get(field,[])}
    grouped={}
    for link in snapshot.get('agent_run_assignments',[]):
        run=runs.get(link['run_id'],{})
        if (link.get('task_id') or run.get('task_id'))!=task_id or link['agent_id'] not in agents:continue
        grouped.setdefault(link['agent_id'],[]).append({'run_id':link['run_id'],'work_type':link.get('work_type','unspecified'),'assigned_at':link.get('assigned_at'), 'source':'run'})
    for link in snapshot.get('agent_assignments',[]):
        if link['task_id']==task_id and link['agent_id'] in agents and link['agent_id'] not in grouped:
            grouped[link['agent_id']]=[{'run_id':None,'work_type':link.get('work_type','unspecified'),'assigned_at':link.get('assigned_at'),'source':'owner'}]
    keys=profile_short_ids(list(agents.values()))
    rows=[]
    for key,links in grouped.items():
        links.sort(key=lambda a:(-(a['assigned_at'] or 0),a['run_id'] or ''))
        rows.append({'agent':agents[key],'short_id':keys[key],'assignments':links})
    rows.sort(key=lambda r:(-(r['assignments'][0]['assigned_at'] or 0),r['agent']['id']))
    return rows


def profile_reference(agent,language='zh'):
    if not agent:return 'Unassigned' if language=='en' else '未分配'
    short=agent.get('panel_short_id') or profile_short_ids([agent])[agent['id']]
    return ('Panel ID ' if language=='en' else '面板编号 ')+short
