"""Append-only directory-observation events, with explicit estimates and UTC/CST."""
import hashlib
import json
import math
import sqlite3
import os
import stat
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime,timezone
from zoneinfo import ZoneInfo

TYPES=('baseline_present','initial_absent','path_missing','identity_changed','path_reappeared','observation_gap','clock_rollback','inspection_error','historical_estimate')
LEVELS=('observed','estimated','unknown')
SCHEMA='''CREATE TABLE IF NOT EXISTS reset_installation_binding (id INTEGER PRIMARY KEY CHECK(id=1), identity TEXT NOT NULL, evidence TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS immutable_reset_binding BEFORE UPDATE ON reset_installation_binding
 BEGIN SELECT RAISE(ABORT,'Reset installation identity is immutable'); END;
CREATE TABLE IF NOT EXISTS reset_events (
 event_id TEXT PRIMARY KEY, observed_at REAL NOT NULL, event_type TEXT NOT NULL,
 evidence_level TEXT NOT NULL, payload_json TEXT NOT NULL, content_sha256 TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS immutable_reset_event BEFORE UPDATE ON reset_events
 BEGIN SELECT RAISE(ABORT,'Reset observations are immutable'); END;
CREATE TRIGGER IF NOT EXISTS undeletable_reset_event BEFORE DELETE ON reset_events
 BEGIN SELECT RAISE(ABORT,'Reset observations are retained'); END;'''


def migrate(db):
    statement=''
    for line in SCHEMA.splitlines(True):
        statement+=line
        if sqlite3.complete_statement(statement):db.execute(statement);statement=''
    if statement.strip():db.execute(statement)


def _stamp(value):
    if value is None:return None
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
        raise ValueError('Invalid observed timestamp')
    return value


def normalize_event(event):
    allowed={'event_id','observed_at','event_type','evidence_level','summary','source_kind','source_reference','target_label','last_present_at','first_missing_at','planned_at','previous_identity','current_identity','gap_started_at','gap_ended_at'}
    if not isinstance(event,dict) or set(event)-allowed:raise ValueError('Unknown reset event fields')
    e=dict(event)
    for k in ('event_id','summary','source_kind','source_reference','target_label'):
        v=e.get(k)
        if not isinstance(v,str) or not v.strip() or len(v)>(2000 if k=='summary' else 400):raise ValueError('Missing or invalid reset provenance')
    if e.get('event_type') not in TYPES or e.get('evidence_level') not in LEVELS:raise ValueError('Invalid reset event type or evidence')
    e['observed_at']=_stamp(e.get('observed_at'))
    if e['observed_at'] is None:raise ValueError('Observation time required')
    for k in ('last_present_at','first_missing_at','planned_at','gap_started_at','gap_ended_at'):
        if k in e:e[k]=_stamp(e[k])
    for k in ('previous_identity','current_identity'):
        if k in e and e[k] is not None:
            v=e[k]
            if not isinstance(v,dict) or set(v)!={'device','inode'} or any(isinstance(x,bool) or not isinstance(x,int) or x<0 for x in v.values()):raise ValueError('Invalid directory identity')
    if e.get('last_present_at') is not None and e.get('first_missing_at') is not None and e['last_present_at']>e['first_missing_at']:
        raise ValueError('Invalid missing-observation interval')
    if e['event_type']=='historical_estimate' and e['evidence_level']!='estimated':raise ValueError('Historical estimates must be labelled estimated')
    return e


def insert_event(db,event):
    e=normalize_event(event);raw=json.dumps(e,sort_keys=True,ensure_ascii=False,separators=(',',':'));digest=hashlib.sha256(raw.encode()).hexdigest()
    row=db.execute('SELECT content_sha256 FROM reset_events WHERE event_id=?',(e['event_id'],)).fetchone()
    if row:
        if row[0]!=digest:raise ValueError('Reset event identity has conflicting content')
        return False
    db.execute('INSERT INTO reset_events VALUES(?,?,?,?,?,?)',(e['event_id'],e['observed_at'],e['event_type'],e['evidence_level'],raw,digest));return True


def display_event(e):
    e=dict(e)
    for key in ('observed_at','last_present_at','first_missing_at','planned_at','gap_started_at','gap_ended_at'):
        value=e.get(key)
        e[key+'_utc']=datetime.fromtimestamp(value,timezone.utc).isoformat() if value is not None else None
        e[key+'_beijing']=datetime.fromtimestamp(value,ZoneInfo('Asia/Shanghai')).isoformat() if value is not None else None
    e['reset_cause_confirmed']=False
    return e


def read_events(db):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='reset_events'").fetchone():return []
    return [display_event(json.loads(r[0])) for r in db.execute('SELECT payload_json FROM reset_events ORDER BY observed_at DESC,event_id DESC')]


def read_installation_identity(directory):
    from .reset_monitor import open_dir
    fd=open_dir(Path(directory)/'config')
    try:handle=os.open('backup-identity.json',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
    finally:os.close(fd)
    with os.fdopen(handle,'rb') as file:
        info=os.fstat(file.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode&0o077 or info.st_size>4096:raise ValueError('Invalid installation identity file')
        data=json.loads(file.read(4097))
    if not isinstance(data,dict) or data.get('schema')!='dots-panel.backup.v2' or not isinstance(data.get('identity'),str) or not data['identity'].strip():raise ValueError('Installation identity unavailable')
    return data['identity']


@contextmanager
def existing_database(path,mode='ro'):
    from .reset_monitor import open_dir
    path=Path(path);parent=open_dir(path.parent);handle=None;db=None
    try:
        handle=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
        info=os.fstat(handle);expected=(info.st_dev,info.st_ino)
        if not stat.S_ISREG(info.st_mode) or info.st_mode&0o077:raise ValueError('Database must be a private regular file')
        def check():
            current=os.stat(path.name,dir_fd=parent,follow_symlinks=False)
            visible=os.stat(path,follow_symlinks=False)
            if not stat.S_ISREG(current.st_mode) or not stat.S_ISREG(visible.st_mode) or (current.st_dev,current.st_ino)!=expected or (visible.st_dev,visible.st_ino)!=expected:raise ValueError('Database path changed during connection')
        from .sqlite_bound import connect_bound
        check();db=connect_bound(path,expected,mode=mode);db.row_factory=sqlite3.Row;check()
        if mode=='ro':db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN IMMEDIATE' if mode=='rw' else 'BEGIN');check()
        yield db,check
        check()
        if mode=='rw':db.commit()
    except BaseException:
        if db is not None:db.rollback()
        raise
    finally:
        if db is not None:db.close()
        if handle is not None:os.close(handle)
        os.close(parent)


class ResetStoreMixin:
    def reset_import(self,events,expected_identity=None):
        if not isinstance(events,list) or len(events)>10000:raise ValueError('Bounded event list required')
        if not expected_identity or read_installation_identity(self.directory)!=expected_identity:raise ValueError('Explicit verified installation identity required for reset imports')
        normalized=[normalize_event(e) for e in events]
        with existing_database(Path(self.directory)/'db/panel.sqlite3','rw') as (db,check):
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {'tasks','runs','artifacts','reset_events','reset_installation_binding'}.issubset(tables):raise ValueError('Existing compatible panel schema required')
            bound=db.execute('SELECT identity FROM reset_installation_binding WHERE id=1').fetchone()
            if not bound or bound[0]!=expected_identity:raise ValueError('Explicit database installation binding required')
            check()
            if read_installation_identity(self.directory)!=expected_identity:raise ValueError('Installation identity changed during import')
            count=sum(insert_event(db,e) for e in normalized)
        return {'imported':count,'deduplicated':len(events)-count,'record_only':True}
    def reset_bind(self,expected_identity,evidence):
        if not isinstance(evidence,str) or not evidence.strip() or len(evidence)>2000:raise ValueError('Explicit installation verification evidence required')
        if not expected_identity or read_installation_identity(self.directory)!=expected_identity:raise ValueError('Installation identity mismatch')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT identity FROM reset_installation_binding WHERE id=1').fetchone()
            if row and row[0]!=expected_identity:raise ValueError('A different installation is already bound')
            if not row:db.execute('INSERT INTO reset_installation_binding VALUES(1,?,?)',(expected_identity,evidence))
        return {'bound':True,'deduplicated':bool(row),'record_only':True}
    def reset_list(self):
        with existing_database(Path(self.directory)/'db/panel.sqlite3') as (db,check):
            return {'events':read_events(db),'read_only':True,'reset_cause_confirmed':False}



def monitor_status(directory,now=None):
    """Read a separately configured observer; a configuration is not a live process."""
    import time
    from .reset_monitor import open_dir
    result={'status':'unknown','reason':'No verified local monitor observation'}
    try:
        parent=open_dir(Path(directory)/'config')
        try:handle=os.open('reset-monitor.json',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
        finally:os.close(parent)
        with os.fdopen(handle,'rb') as stream:
            info=os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_mode&0o077 or info.st_size>8192:raise ValueError('Invalid monitor config')
            config=json.loads(stream.read(8193))
        if not isinstance(config,dict) or not config.get('state_directory') or not config.get('expected_installation_identity'):raise ValueError('Missing monitor binding')
        expected=config['expected_installation_identity']
        if read_installation_identity(directory)!=expected:raise ValueError('Monitor panel identity mismatch')
        with existing_database(Path(config['state_directory'])/'monitor.sqlite3') as (db,check):
            source=json.loads(db.execute("SELECT value FROM monitor_state WHERE key='config'").fetchone()[0])
            if source.get('expected_panel_identity')!=expected:raise ValueError('Monitor source identity mismatch')
            row=db.execute("SELECT value FROM monitor_state WHERE key='last'").fetchone()
            if not row:return {**result,'reason':'Configured observer has no recorded sample'}
            last=json.loads(row[0]);at=last['observed_at'];now=time.time() if now is None else now
            age=now-at;healthy=0<=age<=source['interval']*2.5
            return {'status':'recent_observation' if healthy else 'stale','last_observed_at':at,
                    'last_observed_at_utc':datetime.fromtimestamp(at,timezone.utc).isoformat(),
                    'last_observed_at_beijing':datetime.fromtimestamp(at,ZoneInfo('Asia/Shanghai')).isoformat(),
                    'interval_seconds':source['interval'],'path_count':len(source['paths']),
                    'process_running':'not_inferred','reason':'Recent recorded sample; no permanence guarantee' if healthy else 'No recent sample; monitor execution is unconfirmed'}
    except FileNotFoundError:return result
    except (OSError,ValueError,TypeError,KeyError,sqlite3.Error):return {**result,'reason':'Monitor state or binding could not be safely verified'}
