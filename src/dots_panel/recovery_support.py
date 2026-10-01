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
            db.execute("INSERT INTO agents(id,name,avatar,created,updated,name_en,note,note_en) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,avatar=excluded.avatar,updated=excluded.updated,name_en=excluded.name_en,note=excluded.note,note_en=excluded.note_en",values)
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

    def agent_register(self, key, name, avatar='mint', name_en=''):
        with self.connect() as db:
            if db.execute('SELECT 1 FROM agents WHERE id=?',(key,)).fetchone():
                raise ValueError('Agent already registered')
        return self.agent_upsert(key,name,avatar,name_en)

    def agent_profile(self, key, name=None, avatar=None, name_en=None):
        with self.connect() as db:
            row=db.execute('SELECT * FROM agents WHERE id=?',(key,)).fetchone()
            if not row: raise ValueError('Unknown agent ID')
            old=dict(row)
        return self.agent_upsert(key,name if name is not None else old['name'],avatar if avatar is not None else old['avatar'],name_en if name_en is not None else old['name_en'],old['note'],old['note_en'])

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
