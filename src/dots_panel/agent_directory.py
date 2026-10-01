"""Conservative read-only profile counts, not a platform-wide executor inventory."""
import math
import time
from .progress import agent_observation

OPEN_RUNS = {'running', 'waiting_user', 'waiting_external', 'awaiting_review'}
DIRECTORY_STATES = ('running', 'idle', 'unconfirmed', 'blocked', 'unavailable')
LABELS = {'all': ('已核实 Agent', 'Verified agents'), 'running': ('工作中', 'Working'), 'idle': ('待命', 'Standby'),
          'unconfirmed': ('状态待核实', 'State unconfirmed'), 'unverified': ('身份待核实档案', 'Unverified identities'), 'blocked': ('受阻', 'Blocked'), 'unavailable': ('不可用', 'Unavailable'),
          'historical': ('历史档案', 'Historical profiles')}
REASONS = {
    'historical': ('历史留存，当前执行者未核实', 'Historical record; current executor unverified'),
    'identity': ('执行者对应关系尚未核实', 'Executor match is unverified'),
    'observation': ('状态观察缺失、过期或时间无效', 'Status observation is missing, expired or invalid'),
    'assignment': ('缺少当前有效运行关联或关联时间', 'Current valid run assignment or assignment time is missing'),
    'conflict': ('最新关联包含不同任务，当前归属待核实', 'Latest assignments span different tasks; current ownership is unconfirmed'),
    'before_assignment': ('状态观察早于最新分派', 'Status was observed before the latest assignment'),
    'paused': ('最新关联运行已暂停，不计为工作中', 'Latest assigned run is paused; not counted as working'),
    'terminal': ('最新关联运行已结束，不能据旧观察计为工作中', 'Latest assigned run is terminal; the old observation cannot establish working'),
    'running': ('近期运行观察、已核实身份及有效开放运行相符', 'Recent running observation, verified identity and valid open run agree'),
    'idle': ('近期观察为待命，不代表所关联任务已完成', 'Recently observed standby; associated tasks are not necessarily complete'),
    'blocked': ('近期观察为受阻', 'Recently observed blocked'),
    'unavailable': ('近期观察为不可用', 'Recently observed unavailable'),
}


def directory_label(key, language='zh'):
    return LABELS.get(key, LABELS['unconfirmed'])[language == 'en']


def directory_reason(key, language='zh'):
    return REASONS.get(key, REASONS['observation'])[language == 'en']


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def agent_directory(snapshot, now=None):
    now = time.time() if now is None else now
    agents = {a['id']: a for a in snapshot.get('agents', [])}
    tasks = {t['id']: t for t in snapshot.get('tasks', [])}
    runs = {r['id']: r for key in ('runs', 'latest_runs', 'current_runs', 'open_runs') for r in snapshot.get(key, [])}
    counts = dict.fromkeys(('all', 'profiles', *DIRECTORY_STATES, 'historical', 'unverified'), 0)
    rows = []
    for agent in agents.values():
        historical = agent.get('identity_verification') == 'historical' or agent.get('identity_source') == 'historical'
        links = [a for a in snapshot.get('agent_run_assignments', []) if a.get('agent_id') == agent['id']]
        timestamps_valid = bool(links) and all(finite(a.get('assigned_at')) for a in links)
        latest = max((a['assigned_at'] for a in links), default=None) if timestamps_valid else None
        latest_links = [a for a in links if a['assigned_at'] == latest] if latest is not None else []
        linked = [runs.get(a.get('run_id')) for a in latest_links]
        complete = bool(linked) and all(r and r.get('task_id') in tasks for r in linked)
        work = []
        if complete:
            pairs=sorted(zip(linked,latest_links),key=lambda pair:(pair[0]['status'] not in OPEN_RUNS,-(pair[0].get('started') or 0),pair[0]['id']))
            for run, link in pairs:
                if not any(w['task']['id'] == run['task_id'] for w in work):
                    work.append({'task': tasks[run['task_id']], 'run_id': run['id'], 'status': run['status'], 'work_type': link.get('work_type', 'unspecified'), 'source': 'run'})
        elif not links:
            owners = [a for a in snapshot.get('agent_assignments', []) if a.get('agent_id') == agent['id'] and a.get('task_id') in tasks]
            owners.sort(key=lambda a: (a.get('assigned_at', 0), a['task_id']), reverse=True)
            if owners:
                a = owners[0]
                work.append({'task': tasks[a['task_id']], 'run_id': None, 'status': None, 'work_type': a.get('work_type', 'unspecified'), 'source': 'owner'})
        observation = agent_observation(agent, snapshot, now)
        identity_time = agent.get('identity_observed_at')
        verified = isinstance(agent.get('identity_evidence'),str) and bool(agent['identity_evidence'].strip()) and agent.get('identity_verification') == 'observed' and agent.get('identity_source') == 'manual' and finite(identity_time) and identity_time <= now
        state, reason = 'unconfirmed', 'observation'
        if historical:
            reason = 'historical'
        elif not verified:
            reason = 'identity'
        elif not observation['recent']:
            reason = 'observation'
        elif agent.get('status') in ('idle', 'blocked', 'unavailable'):
            state = reason = agent['status']
        elif agent.get('status') == 'running':
            if not complete:
                reason = 'assignment'
            elif len({r['task_id'] for r in linked}) != 1:
                reason = 'conflict'
            elif agent['observed_at'] < latest:
                reason = 'before_assignment'
            elif not any(r['status'] in OPEN_RUNS for r in linked):
                reason = 'paused' if any(r['status']=='paused' for r in linked) else 'terminal'
            else:
                state = reason = 'running'
        counts['profiles'] += 1; counts['historical'] += int(historical)
        if not historical:
            if verified:
                counts['all'] += 1
                counts[state] += 1
            else:
                counts['unverified'] += 1
        rows.append({'agent': agent, 'state': state, 'reason': reason, 'historical': historical, 'verified': bool(verified and not historical), 'work': work})
    rows.sort(key=lambda r: (r['historical'], DIRECTORY_STATES.index(r['state']), -(r['agent']['observed_at'] if finite(r['agent'].get('observed_at')) else 0), r['agent']['id']))
    return {'counts': counts, 'rows': rows}


def directory_work_label(row, language='zh'):
    en = language == 'en'
    if not row['work']:
        return ('Current task unconfirmed' if en else '当前任务待核实') if row['state'] == 'unconfirmed' else ('No task recorded' if en else '暂无任务记录')
    label = ('Current task' if en else '当前任务') if row['state'] == 'running' else ('Linked task' if en else '关联任务') if row['work'][0]['source'] == 'owner' else ('Recent task' if en else '最近任务')
    return label + ' · ' + ' / '.join(w['task']['name'] for w in row['work'])
