"""Opt-in 60-second directory identity observer; no recursive content scanning.

Independent state must be outside all monitored roots. Missing data never causes
panel initialization. No daemon installation, auto-start, network or credentials.
"""
import argparse
import errno
import json
import os
from pathlib import Path
import signal
import sqlite3
import stat
import threading
import time
import uuid
from .reset_events import migrate, insert_event, read_events, existing_database, read_installation_identity

MAX_JSON=2*1024*1024


def open_dir(path):
    p=Path(path)
    if not p.is_absolute() or '..' in p.parts:raise ValueError('Absolute normalized directory required')
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in p.parts[1:]:
            new=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=new
        return fd
    except BaseException:
        os.close(fd);raise


def inspect_path(path):
    try:
        fd=open_dir(path)
        try:i=os.fstat(fd)
        finally:os.close(fd)
        return {'state':'present','identity':{'device':i.st_dev,'inode':i.st_ino}}
    except FileNotFoundError:return {'state':'missing','identity':None}
    except OSError as e:return {'state':'unreadable','identity':None,'error':'errno:'+str(e.errno)}


def _state_path(directory):
    directory=Path(directory)
    fd=open_dir(directory)
    try:
        if os.fstat(fd).st_mode&0o077:raise ValueError('Monitor state directory must be private')
        f=os.open('monitor.sqlite3',os.O_RDONLY|os.O_NOFOLLOW,dir_fd=fd)
        try:
            i=os.fstat(f)
            if not stat.S_ISREG(i.st_mode) or i.st_mode&0o077:raise ValueError('Monitor database must be private regular file')
        finally:os.close(f)
    finally:os.close(fd)
    return directory/'monitor.sqlite3',(i.st_dev,i.st_ino)


def initialize(directory,paths,interval=60,panel_data=None,expected_panel_identity=None):
    directory=Path(directory).absolute()
    if interval<60:raise ValueError('Minimum local interval is 60 seconds')
    if not paths or len(paths)>20:raise ValueError('Select 1 to 20 exact directory paths')
    normalized={}
    for label,path in paths.items():
        if not isinstance(label,str) or not label or len(label)>100:raise ValueError('Invalid path label')
        p=Path(path)
        if not p.is_absolute() or '..' in p.parts or str(p)=='/':raise ValueError('Invalid monitored directory')
        if directory==p or p in directory.parents:raise ValueError('Monitor state must be outside monitored roots')
        normalized[label]=str(p)
    if panel_data and (not expected_panel_identity or read_installation_identity(panel_data)!=expected_panel_identity):raise ValueError('Explicit verified panel installation identity required')
    if directory.exists():raise ValueError('Monitor initialization requires a fresh state directory')
    parent=open_dir(directory.parent)
    try:os.mkdir(directory.name,0o700,dir_fd=parent)
    finally:os.close(parent)
    f=os.open(directory/'monitor.sqlite3',os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600);os.close(f)
    db=sqlite3.connect(directory/'monitor.sqlite3')
    try:
        migrate(db);db.execute('CREATE TABLE monitor_state(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
        config={'paths':normalized,'interval':interval,'instance_id':uuid.uuid4().hex,'panel_data':str(Path(panel_data).absolute()) if panel_data else None,'expected_panel_identity':expected_panel_identity}
        db.execute('INSERT INTO monitor_state VALUES(?,?)',('config',json.dumps(config,sort_keys=True)));db.commit()
    finally:db.close()
    return {'initialized':True,'path_count':len(paths),'interval':interval,'running':False}


class DirectoryMonitor:
    def __init__(self,directory):
        self.directory=Path(directory).absolute();self.path,self.identity=_state_path(self.directory)
        parent=open_dir(self.path.parent)
        try:self.state_handle=os.open(self.path.name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=parent)
        finally:os.close(parent)
        self.db=None
        try:
            self.db=sqlite3.connect(self.path.as_uri()+'?mode=rw',uri=True)
            self._validate_state()
        except BaseException:
            if self.db is not None:self.db.close()
            os.close(self.state_handle)
            raise
        self.db.row_factory=sqlite3.Row;self.lock=threading.Lock()
        self.config=json.loads(self.db.execute("SELECT value FROM monitor_state WHERE key='config'").fetchone()[0])
    def close(self):self.db.close();os.close(self.state_handle)
    def _validate_state(self):
        _,identity=_state_path(self.directory)
        if identity!=self.identity or (os.fstat(self.state_handle).st_dev,os.fstat(self.state_handle).st_ino)!=self.identity:raise RuntimeError('Monitor state identity changed; observation continuity is unknown')
    def sample(self,now=None,monotonic=None):
        now=time.time() if now is None else now;monotonic=time.monotonic() if monotonic is None else monotonic
        with self.lock:
            self._validate_state();self.db.execute('BEGIN IMMEDIATE');self._validate_state()
            try:
                row=self.db.execute("SELECT value FROM monitor_state WHERE key='last'").fetchone();previous=json.loads(row[0]) if row else None
                samples={label:inspect_path(path) for label,path in self.config['paths'].items()};events=[]
                def event(kind,label,summary,level='observed',**extra):
                    e={'event_id':self.config['instance_id']+':'+uuid.uuid4().hex,'event_type':kind,'evidence_level':level,'observed_at':now,'summary':summary,'source_kind':'local_directory_monitor','source_reference':self.config['instance_id'],'target_label':label,**extra};insert_event(self.db,e);events.append(e)
                if previous:
                    elapsed=now-previous['observed_at']
                    if elapsed<0:event('clock_rollback','monitor','Wall clock moved backward; ordering/time interval is uncertain','unknown',gap_started_at=now,gap_ended_at=previous['observed_at'])
                    elif elapsed>self.config['interval']*2.5:event('observation_gap','monitor','No samples were recorded for this interval; no reset time is inferred','unknown',gap_started_at=previous['observed_at'],gap_ended_at=now)
                for label,current in samples.items():
                    old=(previous or {}).get('paths',{}).get(label)
                    if current['state']=='unreadable':
                        if not old or old.get('state')!='unreadable' or current.get('error')!=old.get('error'):
                            event('inspection_error',label,'Directory identity inspection failed: '+current.get('error','unknown'),'unknown')
                    elif current['state']=='missing':
                        if not old:event('initial_absent',label,'Directory was absent at first observation; disappearance time unknown','unknown',first_missing_at=now)
                        elif old['state']=='present':event('path_missing',label,'Directory became inaccessible between the last present and first missing observations; whole-machine reset is unproven',last_present_at=old.get('last_present_at',previous['observed_at']),first_missing_at=now,previous_identity=old['identity'])
                    else:
                        if not old:event('baseline_present',label,'Directory identity recorded; this is a baseline observation',current_identity=current['identity'])
                        elif old['state']!='present':event('path_reappeared',label,'Directory is readable again; this does not establish the cause of the prior interruption',current_identity=current['identity'])
                        elif old['identity']!=current['identity']:event('identity_changed',label,'Directory device/inode changed; replacement or remount is possible and full reset is unproven',previous_identity=old['identity'],current_identity=current['identity'],last_present_at=old.get('last_present_at',previous['observed_at']))
                        current['last_present_at']=now
                value={'observed_at':now,'monotonic_at':monotonic,'paths':samples}
                self.db.execute("INSERT INTO monitor_state VALUES('last',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(value,sort_keys=True),));self._validate_state();self.db.commit()
            except BaseException:self.db.rollback();raise
            self._validate_state()
            return {'sampled_at':now,'events':events,'path_count':len(samples),'status':'observed','interval':self.config['interval']}
    def export(self):
        self._validate_state()
        return [json.loads(r[0]) for r in self.db.execute('SELECT payload_json FROM reset_events ORDER BY observed_at,event_id')]
    def import_into_panel(self):
        """Only an existing migrated panel DB; never creates SOURCE/DATA/schema."""
        directory=self.config.get('panel_data')
        if not directory:return {'status':'not_configured'}
        expected=self.config.get('expected_panel_identity')
        if not expected or read_installation_identity(directory)!=expected:raise ValueError('Expected panel installation identity is missing or mismatched')
        with existing_database(Path(directory)/'db/panel.sqlite3','rw') as (db,check):
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {'tasks','runs','artifacts','reset_events','reset_installation_binding'}.issubset(tables):return {'status':'schema_unavailable'}
            binding=db.execute('SELECT identity FROM reset_installation_binding WHERE id=1').fetchone()
            if not binding or binding[0]!=expected:raise ValueError('Database installation binding does not match')
            check()
            if read_installation_identity(directory)!=expected:raise ValueError('Installation identity changed during import')
            count=sum(insert_event(db,e) for e in self.export());check()
            return {'status':'imported','new_events':count}



def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    for name in ('init','once','run','export'):
        item=sub.add_parser(name);item.add_argument('--state',required=True)
        if name=='init':item.add_argument('--path',action='append',required=True);item.add_argument('--interval',type=int,default=60);item.add_argument('--panel-data');item.add_argument('--expected-panel-identity')
    a=p.parse_args(argv)
    if a.action=='init':
        pairs=[s.split('=',1) for s in a.path]
        if any(len(s)!=2 for s in pairs) or len(dict(pairs))!=len(pairs):raise ValueError('Use distinct --path label=/absolute/path')
        result=initialize(a.state,dict(pairs),a.interval,a.panel_data,a.expected_panel_identity);print(json.dumps(result));return
    m=DirectoryMonitor(a.state)
    try:
        if a.action=='export':print(json.dumps(m.export(),ensure_ascii=False));return
        if a.action=='once':print(json.dumps(m.sample(),ensure_ascii=False));return
        stop=threading.Event()
        for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda *_:stop.set())
        while not stop.is_set():
            start=time.monotonic();result=m.sample()
            try:result['panel_import']=m.import_into_panel()
            except (OSError,ValueError,sqlite3.Error):result['panel_import']={'status':'unavailable','retained_in_independent_journal':True}
            print(json.dumps(result,ensure_ascii=False),flush=True)
            stop.wait(max(0,m.config['interval']-(time.monotonic()-start)))
    finally:m.close()

if __name__=='__main__':main()
