"""Fail-closed Linux SQLite connection identity checks using this process's FDs.

No other process or file contents are inspected. Path checks alone cannot bind
an SQLite connection to the regular file the caller already opened.
"""
import os
import sqlite3
import stat
import threading

_open_lock=threading.RLock()


def _regular_descriptors():
    try:names=os.listdir('/proc/self/fd')
    except OSError as exc:raise OSError('SQLite descriptor identity verification is unavailable') from exc
    result={}
    for name in names:
        if not name.isdigit():continue
        try:info=os.fstat(int(name))
        except OSError:continue
        if stat.S_ISREG(info.st_mode):result[int(name)]=(info.st_dev,info.st_ino)
    return result


def connect_bound(path,identity,mode='ro',timeout=10):
    """Return a connection only after its actual newly opened regular FD matches.

    Concurrent unrelated regular-file opens or unavailable descriptor evidence
    cause a conservative failure, never acceptance of an unverified database.
    The caller retains its validating FD through the connection lifetime.
    """
    if mode not in ('ro','rw'):raise ValueError('Existing-only SQLite mode required')
    with _open_lock:
        before=_regular_descriptors();db=None
        try:
            db=sqlite3.connect(path.as_uri()+'?mode='+mode,uri=True,timeout=timeout)
            after=_regular_descriptors()
            opened=[value for fd,value in after.items() if before.get(fd)!=value]
            if not opened or any(value!=tuple(identity) for value in opened):
                raise ValueError('SQLite actual database descriptor identity could not be verified')
            return db
        except BaseException:
            if db is not None:db.close()
            raise


# Serialize application connection lifetimes and reuse the already verified
# transaction for nested calls in the same thread. This avoids SQLite's native
# same-inode FD reuse obscuring the provenance of a second nested connection.
from contextlib import contextmanager
_local=threading.local()


@contextmanager
def connection_scope(store):
    key=(str(store.path),bool(getattr(store,'read_only',False)))
    with _open_lock:
        active=getattr(_local,'connections',None)
        if active is None:active={};_local.connections=active
        if key in active:
            db,identity=active[key]
            info=store.path.stat(follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or (info.st_dev,info.st_ino)!=identity:
                raise ValueError('Nested database path identity changed')
            yield db
            return
        with store._connect_fresh() as db:
            info=store.path.stat(follow_symlinks=False)
            active[key]=(db,(info.st_dev,info.st_ino))
            try:yield db
            finally:active.pop(key,None)
