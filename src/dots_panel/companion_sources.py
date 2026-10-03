"""Evidence-only bundled component labels; never infer from names or enabled state."""
def skill_is_bundled(skill):
    return isinstance(skill, dict) and (skill.get('source') or {}).get('origin') == 'project_bundled'


def latest_scheduler_configuration(observations):
    if isinstance(observations, dict):
        observations = list(observations.values())
    rows = [row for row in observations or [] if isinstance(row, dict) and row.get('component') == 'scheduler_configuration']
    return max(rows, key=lambda row: (row.get('observed_at') or 0, row.get('id') or 0), default=None)


def scheduler_is_bundled(schedule, installation_observations):
    explicit=[r for r in installation_observations or [] if isinstance(r,dict) and r.get('explicit_current_binding') is True]
    if explicit:
        task_id=(schedule.get('platform_observation') or {}).get('task_id')
        return any(r.get('status')=='verified' and r.get('reference')==task_id and r.get('source_reference') for r in explicit)
    latest = latest_scheduler_configuration(installation_observations)
    reference = latest.get('reference') if latest else None
    task_id = (schedule.get('platform_observation') or {}).get('task_id')
    return bool(latest and latest.get('status') == 'verified' and isinstance(reference, str) and reference.strip() and reference == task_id)


def installation_observations(snapshot):
    current=snapshot.get('current_companion_scheduler_bindings')
    if current is not None:return current or [{'explicit_current_binding':True,'status':'unknown','reference':None,'source_reference':'explicit-empty-current-set'}]
    rows = snapshot.get('installation_observations')
    if rows is not None:
        return rows
    observations = snapshot.get('about', {}).get('doctor', {}).get('observations', {})
    return [{**row, 'component': key} for key, row in observations.items()]


def companion_snapshot(snapshot):
    observations = installation_observations(snapshot)
    return {'project_rules': True,
            'skills': [item['id'] for item in snapshot.get('rules', {}).get('skills', []) if skill_is_bundled(item)],
            'schedules': [item['id'] for item in snapshot.get('schedules', []) if scheduler_is_bundled(item, observations)]}


def load_current_scheduler_bindings(directory):
    """Explicit private current-binding set; never inferred from a schedule title."""
    import json,os,stat
    from pathlib import Path
    from .app import open_directory
    path=Path(directory)/'config/panel-companion-bindings.json'
    try:
        parent=open_directory(path.parent)
        try:fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
        finally:os.close(parent)
        with os.fdopen(fd,'rb') as stream:
            info=os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_mode&0o077 or info.st_size>32768:return None
            data=json.loads(stream.read(32769))
        if data.get('schema')!='dots-panel.current-companion-bindings.v1' or not isinstance(data.get('bindings'),list) or len(data['bindings'])>20:return None
        result=[]
        for row in data['bindings']:
            if not isinstance(row,dict) or not isinstance(row.get('platform_task_id'),str) or not row['platform_task_id'].strip() or row.get('verification')!='confirmed_configuration' or not isinstance(row.get('source_reference'),str) or not row['source_reference'].strip() or not isinstance(row.get('observed_at'),(float,int)):return None
            result.append({'component':'scheduler_configuration','status':'verified','reference':row['platform_task_id'],'observed_at':row['observed_at'],'source_reference':row['source_reference'],'explicit_current_binding':True})
        return result
    except (OSError,ValueError,TypeError,AttributeError):return None
