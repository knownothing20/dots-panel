"""Newly reconstructed Agent CRUD for a retained SQLite schema.

Not a byte-identical recovery. Profiles and assignments are manually maintained
metadata; they neither start executors nor prove a task is actively running.
"""
import re
import time

class RecoveryStoreMixin:
    def agent_upsert(self, key, name, avatar='mint', name_en='', note='', note_en=''):
        from .app import text, AGENT_AVATARS
        if not isinstance(key, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', key):
            raise ValueError('Invalid stable agent key')
        if avatar not in AGENT_AVATARS:
            raise ValueError('Invalid agent avatar')
        now = time.time()
        values = (key,text(name,120),avatar,now,now,text(name_en,120) if name_en else '',text(note,500) if note else '',text(note_en,500) if note_en else '')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT name,name_en,avatar,portrait FROM agents WHERE id=?',(key,)).fetchone()
            from .agent_identity import default_portrait, available_portrait
            fixed_portrait = (old['portrait'] or default_portrait(key,old['avatar'])) if old else available_portrait(db,key,avatar)
            if old and (old['name'],old['name_en']) != (values[1],values[5]):
                db.execute('INSERT INTO agent_profile_history(agent_id,name,name_en,changed_at) VALUES(?,?,?,?)',(key,old['name'],old['name_en'],now))
            db.execute("INSERT INTO agents(id,name,avatar,created,updated,name_en,note,note_en) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,avatar=excluded.avatar,updated=excluded.updated,name_en=excluded.name_en,note=excluded.note,note_en=excluded.note_en",values)
            db.execute('UPDATE agents SET portrait=? WHERE id=?',(fixed_portrait,key))
        return key

    def agent_observe(self, key, status, observed_at, note='', note_en=''):
        from .app import text, timestamp, AGENT_STATUSES
        if status not in AGENT_STATUSES:
            raise ValueError('Invalid observed executor status')
        observed_at = timestamp(observed_at)
        if observed_at > time.time()+300:
            raise ValueError('Observation cannot be in the future')
        with self.connect() as db:
            old = db.execute('SELECT * FROM agents WHERE id=?',(key,)).fetchone()
            if not old:
                raise ValueError('Unknown agent ID')
            if old['observed_at'] is not None and observed_at < old['observed_at']:
                raise ValueError('Observation is older than the existing profile')
            db.execute('UPDATE agents SET status=?,observed_at=?,note=?,note_en=?,updated=? WHERE id=?',
                       (status,observed_at,text(note,500) if note else '',text(note_en,500) if note_en else '',time.time(),key))
        return key

    def agent_assign(self, task_id, agent_id, replace=False, work_type=None):
        from .app import WORK_TYPES
        if work_type is not None and work_type not in WORK_TYPES:
            raise ValueError('Invalid assignment work type')
        with self.connect() as db:
            if not db.execute('SELECT 1 FROM agents WHERE id=?',(agent_id,)).fetchone():
                raise ValueError('Unknown agent ID')
            if not db.execute('SELECT 1 FROM tasks WHERE id=?',(task_id,)).fetchone():
                raise ValueError('Unknown task ID')
            current = db.execute('SELECT agent_id,work_type FROM agent_assignments WHERE task_id=?',(task_id,)).fetchone()
            if current and current['agent_id'] != agent_id and not replace:
                raise ValueError('Assignment exists; explicit replacement required')
            effective_type = work_type if work_type is not None else current['work_type'] if current and current['agent_id'] == agent_id else 'unspecified'
            db.execute('INSERT INTO agent_assignments(task_id,agent_id,assigned_at,work_type) VALUES(?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET agent_id=excluded.agent_id,assigned_at=excluded.assigned_at,work_type=excluded.work_type',
                       (task_id,agent_id,time.time(),effective_type))
            if not current or current['agent_id'] != agent_id or current['work_type'] != effective_type:
                project=db.execute('SELECT project FROM tasks WHERE id=?',(task_id,)).fetchone()['project']
                stage='assignment' if not current or current['agent_id'] != agent_id else 'work_type'
                name=db.execute('SELECT name FROM agents WHERE id=?',(agent_id,)).fetchone()['name']
                db.execute('INSERT INTO activity(created,project,role,stage,message,task_id,state) VALUES(?,?,?,?,?,?,?)',
                           (time.time(),project,'system',stage,'负责人 / Owner: '+name+' · '+effective_type,task_id,'verified'))
        return {'agent_id':agent_id,'task_id':task_id}

    def agent_run_assign(self, run_id, agent_id, work_type='unspecified'):
        from .app import WORK_TYPES
        if work_type not in WORK_TYPES: raise ValueError('Invalid assignment work type')
        with self.connect() as db:
            if not db.execute('SELECT 1 FROM agents WHERE id=?',(agent_id,)).fetchone():
                raise ValueError('Unknown agent ID')
            if not db.execute('SELECT 1 FROM runs WHERE id=?',(run_id,)).fetchone():
                raise ValueError('Unknown run ID')
            db.execute('INSERT INTO agent_run_assignments VALUES(?,?,?,?) ON CONFLICT(run_id,agent_id) DO UPDATE SET work_type=excluded.work_type',
                       (run_id,agent_id,work_type,time.time()))
        return {'run_id':run_id,'agent_id':agent_id,'record_only':True}

    def agent_register(self, key, name, avatar='mint', name_en='', portrait=None):
        import sqlite3
        from .app import text, AGENT_AVATARS
        from .agent_identity import PORTRAITS, available_portrait
        if not isinstance(key,str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}',key):
            raise ValueError('Invalid stable agent key')
        if avatar not in AGENT_AVATARS:
            raise ValueError('Invalid agent avatar')
        if portrait is not None and portrait not in PORTRAITS:
            raise ValueError('Invalid fixed portrait')
        now=time.time()
        values=(key,text(name,120),avatar,now,now,text(name_en,120) if name_en else '')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            fixed_portrait = portrait or available_portrait(db,key,avatar)
            try:
                db.execute('INSERT INTO agents(id,name,avatar,created,updated,name_en,portrait) VALUES(?,?,?,?,?,?,?)',(*values,fixed_portrait))
            except sqlite3.IntegrityError as error:
                raise ValueError('Agent already registered') from error
        return key

    def agent_profile(self, key, name=None, avatar=None, name_en=None, portrait=None):
        from .app import text, AGENT_AVATARS
        from .agent_identity import PORTRAITS, default_portrait
        if avatar is not None and avatar not in AGENT_AVATARS:
            raise ValueError('Invalid agent avatar')
        if portrait is not None and portrait not in PORTRAITS:
            raise ValueError('Invalid fixed portrait')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT * FROM agents WHERE id=?',(key,)).fetchone()
            if not old: raise ValueError('Unknown agent ID')
            new_name = text(name,120) if name is not None else old['name']
            new_en = text(name_en,120) if name_en else '' if name_en is not None else old['name_en']
            if (new_name,new_en) != (old['name'],old['name_en']):
                db.execute('INSERT INTO agent_profile_history(agent_id,name,name_en,changed_at) VALUES(?,?,?,?)', (key,old['name'],old['name_en'],time.time()))
            db.execute('UPDATE agents SET name=?,name_en=?,avatar=?,portrait=?,updated=? WHERE id=?',
                       (new_name,new_en,avatar if avatar is not None else old['avatar'],portrait or old['portrait'] or default_portrait(key,old['avatar']),time.time(),key))
        return key

    def agent_identity(self, key, source, verification, evidence, observed_at):
        from .app import text, timestamp
        from .agent_identity import IDENTITY_SOURCES, IDENTITY_VERIFICATIONS
        if source not in IDENTITY_SOURCES or verification not in IDENTITY_VERIFICATIONS:
            raise ValueError('Invalid identity provenance')
        if (verification == 'observed' and source != 'manual') or (verification == 'historical' and source != 'historical'):
            raise ValueError('Verification must match its actual source')
        observed_at = timestamp(observed_at)
        evidence = text(evidence,1000)
        if observed_at > time.time()+300:
            raise ValueError('Identity observation cannot be in the future')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT * FROM agents WHERE id=?',(key,)).fetchone()
            if not old: raise ValueError('Unknown agent ID')
            if old['identity_observed_at'] is not None and observed_at < old['identity_observed_at']:
                raise ValueError('Identity observation is older than the existing evidence')
            db.execute('UPDATE agents SET identity_source=?,identity_verification=?,identity_evidence=?,identity_observed_at=?,updated=? WHERE id=?',
                       (source,verification,evidence,observed_at,time.time(),key))
        return {'agent_id':key,'record_only':True,'platform_binding_created':False}

    def release_observe(self, repo_url, release_status, sync_status, checked_at, release_tag=None, remote_commit=None):
        """Record a manual release observation; never contacts or publishes to GitHub."""
        from .app import text, timestamp, verified_repository_url, RELEASE_STATUSES, SYNC_STATUSES
        repo_url=verified_repository_url(repo_url)
        if release_status not in RELEASE_STATUSES or sync_status not in SYNC_STATUSES:
            raise ValueError('Invalid release or synchronization state')
        checked_at=timestamp(checked_at)
        if checked_at>time.time()+300:raise ValueError('Observation cannot be in the future')
        release_tag=text(release_tag,120) if release_tag else None
        if remote_commit is not None and not re.fullmatch(r'[0-9a-f]{40}',remote_commit):
            raise ValueError('A full verified commit SHA is required')
        if release_status=='published' and not release_tag:
            raise ValueError('Published releases require a verified tag')
        if sync_status in ('matched','different') and not remote_commit:
            raise ValueError('Verified sync states require a verified remote commit')
        with self.connect() as db:
            old=db.execute('SELECT checked_at FROM release_observation WHERE id=1').fetchone()
            if old and checked_at<old['checked_at']:raise ValueError('Observation is older than the existing record')
            db.execute('INSERT INTO release_observation VALUES(1,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET repo_url=excluded.repo_url,release_status=excluded.release_status,release_tag=excluded.release_tag,remote_commit=excluded.remote_commit,sync_status=excluded.sync_status,checked_at=excluded.checked_at,recorded_at=excluded.recorded_at',
                       (repo_url,release_status,release_tag,remote_commit,sync_status,checked_at,time.time()))
        return {'record_only':True,'repo_url':repo_url}


def recovery_notice(directory):
    """Expose only a fixed incomplete-history notice from a bounded private marker."""
    import json,os,stat
    from pathlib import Path
    path=Path(directory)/'config/recovery.json'
    try:
        if path.parent.is_symlink():return None
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as file:
            info=os.fstat(file.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size>4096:return None
            marker=json.loads(file.read(4097))
        if marker.get('source_kind')!='retained_records' or marker.get('incomplete') is not True:return None
        return {'source_kind':'retained_records','incomplete':True,
                'notice_zh':'从留存记录恢复，历史不完整。事件为非逐字摘要；旧状态不代表当前执行。',
                'notice_en':'Restored from retained records; history is incomplete. Events are non-verbatim summaries; historical states do not establish current execution.'}
    except (OSError,ValueError,UnicodeError,AttributeError):
        return None
