"""Read-only installation diagnostics; no account scanning, repair or scheduling."""
import os
from pathlib import Path
import sqlite3
import time
from .workflow_bundle import bundle_status

COMPONENTS = ('account_task_skill', 'account_personal_skill', 'scheduler_configuration', 'scheduler_execution')
OBSERVATION_STATES = ('verified', 'failed', 'unknown')
REQUIRED_TABLES = {'tasks','runs','events','activity','artifacts','agents','agent_assignments','task_bindings','schedules','software','user_skills','skill_origins','artifact_designations','artifact_delivery','closeout_records','closeout_artifacts','closeout_completions','installation_observations'}
REQUIRED_RUN_COLUMNS = {'lifecycle_reason','next_step','lifecycle_evidence','closeout_required'}


def installation_report(observations, skills=(), origins=()):
    latest = {}
    for row in observations:
        old = latest.get(row['component'])
        if old is None or (row['observed_at'],row['id']) > (old['observed_at'],old['id']):
            latest[row['component']] = row
    profiles = {row['id']:row for row in skills}
    sources = {row['skill_id']:row for row in origins}
    result = {}
    for component in COMPONENTS:
        row = latest.get(component)
        status = row['status'] if row else 'unknown'
        reason = 'manual_observation' if row else 'not_observed'
        if row and status == 'verified' and component.startswith('account_'):
            skill = profiles.get(row.get('skill_id'), {})
            origin = sources.get(row.get('skill_id'), {})
            expected = 'project_bundled' if component == 'account_task_skill' else 'personal'
            if skill.get('scope') != 'user_installed' or skill.get('status') != 'available' or skill.get('version_status') != 'saved_verified' or origin.get('origin') != expected:
                status, reason = 'unknown', 'skill_metadata_unverified'
            elif component == 'account_personal_skill' and origin.get('publication') != 'not_applicable':
                status, reason = 'unknown', 'personal_skill_not_private'
        if row and status == 'verified' and component == 'scheduler_execution':
            config = latest.get('scheduler_configuration')
            if not config or config['status'] != 'verified' or row.get('configuration_id') != config['id']:
                status, reason = 'unknown', 'configuration_changed'
        result[component] = {'status':status,'reason':reason,'observed_at':row['observed_at'] if row else None,
                             'evidence':row['evidence'] if row else '', 'manual':True}
    return result


def install_doctor(source, directory):
    """Permission probes and read-only schema/metadata inspection. Never initializes DATA."""
    source, directory = Path(source).absolute(), Path(directory).expanduser().absolute()
    checks = []
    def add(key, status): checks.append({'id':key,'status':status})
    add('source_readable','ok' if source.is_dir() and os.access(source,os.R_OK|os.X_OK) and (source/'src/dots_panel/app.py').is_file() else 'unavailable')
    add('source_writable','ok' if source.is_dir() and os.access(source,os.W_OK) else 'read_only')
    safe = directory.is_dir() and not any(part.is_symlink() for part in (directory,*directory.parents))
    private = safe and directory.stat().st_mode & 0o077 == 0
    add('data_separate','ok' if not directory.is_relative_to(source) and not source.is_relative_to(directory) else 'unsafe')
    add('data_readable','ok' if safe and os.access(directory,os.R_OK|os.X_OK) else 'missing' if not directory.exists() else 'unsafe')
    add('data_writable','ok' if safe and os.access(directory,os.W_OK) else 'unavailable')
    add('data_private','ok' if private else 'unsafe' if directory.exists() else 'missing')
    observations, skills, origins = [], [], []
    schema = 'missing'
    path = directory/'db/panel.sqlite3'
    if safe and private and path.is_file():
        if path.is_symlink() or path.parent.is_symlink() or path.stat().st_mode & 0o077 or path.parent.stat().st_mode & 0o077:
            schema = 'unsafe'
        else:
            try:
                connection = sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=1)
                try:
                    connection.row_factory = sqlite3.Row
                    connection.execute('PRAGMA query_only=ON')
                    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    columns = {row[1] for row in connection.execute('PRAGMA table_info(runs)')}
                    schema = 'ok' if REQUIRED_TABLES <= tables and REQUIRED_RUN_COLUMNS <= columns else 'migration_required'
                    if 'installation_observations' in tables: observations=[dict(row) for row in connection.execute('SELECT * FROM installation_observations')]
                    if 'user_skills' in tables: skills=[dict(row) for row in connection.execute('SELECT * FROM user_skills')]
                    if 'skill_origins' in tables: origins=[dict(row) for row in connection.execute('SELECT * FROM skill_origins')]
                finally:
                    connection.close()
            except (sqlite3.Error,OSError):
                schema = 'unavailable'
    elif directory.exists() and not private:
        schema = 'unsafe'
    add('schema',schema)
    try:
        bundle_status(source)
        bundled = 'ok'
    except (OSError,ValueError,UnicodeError):
        bundled = 'unavailable'
    add('bundled_skill',bundled)
    return {'read_only':True,'permission_probe_only':True,'sampled_at':time.time(),'checks':checks,
            'observations':installation_report(observations,skills,origins)}


def doctor_rows(report, language='zh'):
    en = language == 'en'
    names = {'source_readable':('源码可读','Source readable'),'source_writable':('源码可写','Source writable'),
             'data_separate':('源码/数据分离','Source/data separate'),'data_readable':('数据可读','Data readable'),
             'data_writable':('数据可写','Data writable'),'data_private':('数据私有权限','Private data permissions'),
             'schema':('数据库结构','Database schema'),'bundled_skill':('随附任务 Skill','Bundled task Skill'),
             'account_task_skill':('账户任务 Skill','Account task Skill'),'account_personal_skill':('账户个人规则 Skill','Account personal rules Skill'),
             'scheduler_configuration':('定时器配置','Scheduler configuration'),'scheduler_execution':('定时器执行验证','Scheduler execution verification')}
    states = {'ok':('通过','OK'),'read_only':('只读','Read-only'),'missing':('缺失','Missing'),
              'unsafe':('需核对安全边界','Safety review needed'),'unavailable':('不可用','Unavailable'),
              'migration_required':('需显式升级','Migration required'),'verified':('人工核验','Manually verified'),
              'failed':('核验失败','Check failed'),'unknown':('未核验','Unverified')}
    local = [(names.get(row['id'],(row['id'],row['id']))[en],states.get(row['status'],states['unknown'])[en]) for row in report.get('checks',[])]
    manual = []
    for component in COMPONENTS:
        row = report.get('observations',{}).get(component,{})
        manual.append((names[component][en],states.get(row.get('status'),states['unknown'])[en]))
    return local, manual
