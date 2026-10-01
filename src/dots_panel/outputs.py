"""Registered output summaries and explicit native folder opening; no HTTP commands."""
import os
from pathlib import Path
import re
import stat
import subprocess

VIDEO_BRANDS = frozenset((b'isom', b'iso2', b'iso4', b'iso5', b'iso6', b'mp41', b'mp42', b'avc1', b'av01', b'M4V ', b'dash'))


def validate_mp4_header(header, file_size):
    """Validate a bounded ISO-BMFF ftyp header, not media decoding or playback."""
    if not isinstance(header, bytes) or len(header) < 16 or file_size < 24:
        raise ValueError('MP4 requires a complete recognized ftyp header')
    box_size = int.from_bytes(header[:4], 'big')
    if header[4:8] != b'ftyp' or not 16 <= box_size <= 4096 or box_size > len(header) or box_size > file_size or (box_size-16) % 4:
        raise ValueError('Unsupported or malformed MP4 ftyp header')
    brands = {header[8:12], *(header[index:index+4] for index in range(16, box_size, 4))}
    if not brands & VIDEO_BRANDS:
        raise ValueError('MP4 brand is not in the metadata-only allowlist')


def output_summaries(db):
    """Counts and preferred main file from the whole registry, not an API window."""
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'artifacts' not in tables:
        return {}
    summaries = {}
    for row in db.execute('SELECT task_id,kind,COUNT(*) AS count FROM artifacts GROUP BY task_id,kind'):
        item = summaries.setdefault(row['task_id'], {'count': 0, 'kinds': [], 'main': None})
        item['count'] += row['count']
        item['kinds'].append({'kind': row['kind'], 'count': row['count']})
    query = '''SELECT a.*,COALESCE((SELECT designation FROM artifact_designations d WHERE d.artifact_id=a.id ORDER BY d.created DESC,d.id DESC LIMIT 1),'unclassified') AS designation
               FROM artifacts a ORDER BY a.created DESC,a.id DESC'''
    if 'artifact_designations' not in tables:
        query = "SELECT a.*,'unclassified' AS designation FROM artifacts a ORDER BY a.created DESC,a.id DESC"
    for row in db.execute(query):
        item = summaries[row['task_id']]
        main = item['main']
        if main is not None and (main['designation'] == 'final' or row['designation'] != 'final'):
            continue
        observed = sorted({r['status'] for r in db.execute('SELECT status FROM artifact_delivery WHERE artifact_id=? AND sha256=?', (row['id'], row['sha256'])) if r['status'] in ('sent', 'opened', 'accepted')}) if 'artifact_delivery' in tables else []
        item['main'] = {key: row[key] for key in ('id','title','kind','size','created','designation')}
        item['main'].update(filename=Path(row['relative_path']).name, delivery=observed)
    return summaries


def task_output_summary(snapshot, task_id):
    return snapshot.get('output_summaries', {}).get(task_id, {'count': 0, 'kinds': [], 'main': None})


def output_summary_text(summary, language='zh'):
    en = language == 'en'
    kinds = {'report':('报告','reports'),'image':('图片','images'),'document':('文档','documents'),'data':('数据','data'),'video':('视频','videos'),'other':('其他','other')}
    count = summary.get('count', 0)
    if not count:
        return 'No registered outputs' if en else '尚无已登记成果'
    types = ' · '.join(f"{row['count']} {kinds.get(row['kind'],kinds['other'])[en]}" if en else f"{kinds.get(row['kind'],kinds['other'])[0]} {row['count']}" for row in summary.get('kinds', []))
    return (f'Outputs {count}' if en else f'成果 {count}') + (' · ' + types if types else '')


class TaskFolderOpener:
    """Validate the registered canonical folder immediately before native opening.

    No arbitrary paths, shell strings or HTTP action endpoint. The application
    rejects symlinks and a changed directory during validation; it does not claim
    to defend against a malicious process running as the same local user.
    """
    def __init__(self):
        self._processes = []

    def open(self, store, task_id):
        if not isinstance(task_id, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', task_id):
            raise ValueError('Invalid registered task ID')
        with store.connect() as db:
            if not db.execute('SELECT 1 FROM tasks WHERE id=?', (task_id,)).fetchone():
                raise ValueError('Unknown task ID')
            if not db.execute('SELECT 1 FROM artifacts WHERE task_id=?', (task_id,)).fetchone():
                raise ValueError('No registered outputs for this task')
        with store.task_directory(task_id, 'outputs', create=False) as current:
            before = os.fstat(current)
            if not stat.S_ISDIR(before.st_mode) or before.st_mode & 0o077:
                raise ValueError('Unsafe task output directory')
            target = store.directory / 'tasks' / task_id / 'outputs'
            with store.task_directory(task_id, 'outputs', create=False) as checked:
                identity = os.fstat(checked)
                if (before.st_dev,before.st_ino) != (identity.st_dev,identity.st_ino) or target.resolve(strict=True) != target or not target.is_relative_to(store.directory):
                    raise ValueError('Task output directory changed while opening')
                self._processes = [process for process in self._processes if process.poll() is None]
                process = subprocess.Popen(['/usr/bin/xdg-open', str(target)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, shell=False)
                self._processes.append(process)
                return process

    def close(self):
        # Never terminate a file manager the user is using.
        self._processes = [process for process in self._processes if process.poll() is None]


def output_main_text(summary, language='zh'):
    main = summary.get('main')
    if not main:
        return ''
    en = language == 'en'
    designation = {'final':('最终稿','Final'),'draft':('草稿','Draft'),'unclassified':('未指定版本','Unclassified')}.get(main.get('designation'),('未指定版本','Unclassified'))[en]
    labels = ['Archived' if en else '已归档', designation]
    for status,zh,english in (('sent','已记录发送','Sent recorded'),('opened','已记录打开','Opened recorded'),('accepted','已记录验收','Acceptance recorded')):
        if status in main.get('delivery', []):labels.append(english if en else zh)
    prefix = ('Latest final: ' if en else '最近最终稿：') if main.get('designation') == 'final' else ('Recently registered: ' if en else '最近登记：')
    return prefix + str(main.get('title') or main.get('filename') or '') + ' · ' + ' · '.join(labels)
