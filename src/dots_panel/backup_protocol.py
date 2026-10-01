"""Offline, fail-closed private backup protocol (Python standard library only).

This module never uploads, schedules, deletes old objects, or activates a restore.
A trusted operator supplies platform receipts. Receipts are strictly matched to
local bytes but are not authenticated platform responses. Downloaded bytes are
required for new-upload and latest-index confirmation. See ``--help`` and the public functions.

Policy JSON keys (all optional): ``checkpoints`` (SOURCE/ or DATA/ relative file
paths <= 2 MB, or explicit path/sha256/size_bytes records <= 32 MB),
``reviewed_binary_sha256`` (manually reviewed opaque bytes),
``external_files`` (fixed file_id/library_file_id/version/sha256/size_bytes and
restore_path), ``excluded_outputs`` (explicit DATA output omissions) and ``excluded_inputs``
(exact registered-task input files, never directory patterns). All omissions are
audited as not restorable.
The privacy audit records every included file, exclusion and external dependency.
No generic tmp recursion or media discovery is performed.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import stat
import sys
import tempfile
import uuid
import zipfile
import zlib

SCHEMA = 'dots-panel.backup.v2'
INDEX_SCHEMA = 'dots-panel.backup-index.v2'
RECEIPT_SCHEMA = 'dots-panel.upload-receipts.v2'
MAX_PACKAGE_BYTES = 19_000_000  # strict upper bound, including ZIP headers
CHUNK_BYTES = 8_000_000
CHECKPOINT_BYTES = 2_000_000
PINNED_CHECKPOINT_BYTES = 32_000_000
IDENTITY_PATH = 'config/backup-identity.json'
DB_PATH = 'db/panel.sqlite3'
CAPTURE_MODES = ('strict-live', 'database-snapshot-cutoff')
HASH_RE = re.compile(r'[0-9a-f]{64}\Z')
RUN_RE = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}\Z')
EXCLUDED_DIRS = {'.git', '__pycache__', '.pytest_cache', 'node_modules', '.venv',
                 'venv', 'logs', 'run', 'cache', 'caches', '.cache', 'backups',
                 '.backups', 'render-frames', 'frames', 'credentials', '.ssh', '.aws'}
SECRET_RE = re.compile(rb'(?:(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{24,}|'
                       rb'(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{25,}|'
                       rb'AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|'
                       rb'(?i:authorization\s*[:=]\s*[\"\']?bearer\s+)[A-Za-z0-9._~-]{12,}|'
                       rb'(?i:(?:password|api[_-]?key|access[_-]?token|client[_-]?secret)'
                       rb'\s*[\"\']?\s*[:=]\s*[\"\'])[^\"\'\r\n]{8,}[\"\'])')


class BackupError(ValueError):
    """A safety, integrity, dependency or state check failed."""


def _fail(message):
    raise BackupError(message)


def _json_bytes(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')) + '\n').encode()


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _load(path):
    try:
        return json.loads(_read_file(Path(path)))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BackupError('Cannot read valid JSON: ' + Path(path).name) from exc


def _safe_rel(value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value or '\x00' in value:
        _fail('Invalid relative path')
    p = PurePosixPath(value)
    if p.is_absolute() or any(x in ('', '.', '..') for x in value.split('/')) or any(ord(c) < 32 for c in value):
        _fail('Unsafe relative path: ' + value)
    return value


def _restore_rel(value):
    _safe_rel(value)
    if value.split('/')[0] not in ('SOURCE', 'DATA') or len(value.split('/')) < 2:
        _fail('Restore path must be beneath SOURCE or DATA')
    return value


def _no_links(path, *, exists=True):
    path = Path(os.path.abspath(path))
    for part in [*reversed(path.parents), path]:
        try:
            st = part.lstat()
        except FileNotFoundError:
            if exists:
                _fail('Required path is missing: ' + path.name)
            continue
        if stat.S_ISLNK(st.st_mode):
            _fail('Symbolic links are not allowed: ' + part.name)
    return path


def _root(path):
    p = _no_links(path)
    if not p.is_dir():
        _fail('Required root is not a directory')
    return p


def _path(root, rel):
    return _no_links(root / _safe_rel(rel))


def _fingerprint(st):
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns, stat.S_IMODE(st.st_mode))


def _entity(path, directory=False):
    """Pin filesystem identity without treating ordinary SQLite writes as resets."""
    st = _no_links(path).lstat()
    if not (stat.S_ISDIR(st.st_mode) if directory else stat.S_ISREG(st.st_mode)):
        _fail('Capture root/database/identity has the wrong type: ' + path.name)
    return st.st_dev, st.st_ino, stat.S_IFMT(st.st_mode)


def _check_capture_identity(entities, identity_path, identity_bytes):
    for path, directory, expected in entities:
        if _entity(path, directory) != expected:
            _fail('Capture root/database/identity was replaced: ' + path.name)
    if _read_file(identity_path) != identity_bytes:
        _fail('Persisted installation identity changed during capture')


def _read_file(path):
    path = _no_links(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        _fail('Only regular files are supported: ' + path.name)
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as stream:
        if _fingerprint(before) != _fingerprint(os.fstat(stream.fileno())):
            _fail('File changed before reading: ' + path.name)
        raw = stream.read()
        after = os.fstat(stream.fileno())
    if _fingerprint(before) != _fingerprint(after) or _fingerprint(after) != _fingerprint(path.lstat()):
        _fail('File changed during reading: ' + path.name)
    return raw


def _write(path, raw, *, exclusive=False):
    path = _no_links(path, exists=False)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _no_links(path.parent)
    if exclusive:
        with path.open('xb') as f:
            os.chmod(path, 0o600)
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
    else:
        tmp = path.parent / ('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
        _write(tmp, raw, exclusive=True)
        os.replace(tmp, path)
    # Also persist the rename where supported.
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _save(path, value):
    _write(path, _json_bytes(value))


def _hash(value):
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        _fail('Invalid SHA-256')
    return value


def _integer(value, name, *, minimum=0):
    if type(value) is not int or value < minimum:
        _fail('Invalid ' + name)
    return value


def _pinned(ref):
    for name in ('file_id', 'library_file_id'):
        if not isinstance(ref.get(name), str) or not RUN_RE.fullmatch(ref[name]):
            _fail('Missing or invalid pinned ' + name)
    version = ref.get('version')
    if type(version) is not int or version < 0:
        _fail('Missing fixed platform version')
    _hash(ref.get('sha256'))
    _integer(ref.get('size_bytes'), 'size_bytes')
    return {k: ref[k] for k in ('file_id', 'library_file_id', 'version', 'sha256', 'size_bytes')}


def _policy(value):
    value = {} if value is None else value
    if not isinstance(value, dict) or set(value) - {'checkpoints', 'reviewed_binary_sha256', 'external_files', 'excluded_outputs', 'excluded_inputs'}:
        _fail('Unknown policy fields')
    result = {k: value.get(k, []) for k in ('checkpoints', 'reviewed_binary_sha256', 'external_files', 'excluded_outputs', 'excluded_inputs')}
    if any(not isinstance(v, list) for v in result.values()):
        _fail('Policy fields must be lists')
    for p in result['checkpoints']:
        if isinstance(p, str):
            _restore_rel(p)
        elif isinstance(p, dict) and set(p) == {'path', 'sha256', 'size_bytes'}:
            _restore_rel(p['path'])
            _hash(p['sha256'])
            if _integer(p['size_bytes'], 'checkpoint size') > PINNED_CHECKPOINT_BYTES:
                _fail('Pinned checkpoint exceeds bounded size limit')
        else:
            _fail('Checkpoint must be a path or exact path/hash/size record')
    for h in result['reviewed_binary_sha256']:
        _hash(h)
    for p in result['excluded_outputs'] + result['excluded_inputs']:
        _safe_rel(p)
        if any(c in p for c in '*?[]'):
            _fail('Policy exclusions must be exact paths, never glob patterns')
    for p in result['excluded_inputs']:
        parts = p.split('/')
        if len(parts) < 4 or parts[0] != 'tasks' or parts[2] != 'inputs':
            _fail('Input exclusion must name a task inputs file')
    paths = set()
    for ref in result['external_files']:
        if not isinstance(ref, dict) or set(ref) != {'file_id', 'library_file_id', 'version', 'sha256', 'size_bytes', 'restore_path'}:
            _fail('External reference requires all six fixed identity/content/path fields')
        _pinned(ref)
        path = _restore_rel(ref['restore_path'])
        if not path.startswith('DATA/tasks/') or path in paths:
            _fail('External references must be unique task files')
        paths.add(path)
    return result


def _excluded(rel, *, checkpoint=False):
    parts = PurePosixPath(rel).parts
    if any(p.lower() in EXCLUDED_DIRS for p in parts):
        return 'runtime-cache-credentials-or-nested-backup'
    name = parts[-1].lower()
    if name in {'credentials.json', 'secrets.json', 'tokens.json', 'cookies.json',
                'cookies.txt', 'cookiejar', 'cookie-jar.json', '.netrc', '.npmrc', '.pypirc'}:
        return 'credential-file-name'
    if name == '.env' or name.startswith('.env.') or name.endswith(('.pem', '.key', '.p12', '.pfx', '.pid', '.log')):
        return 'credential-or-runtime-file'
    # Archive names do not determine scope: registered editable projects can
    # contain 'backup' or 'checkpoint'. Exclude prior backups by exact policy.
    if not checkpoint and 'tmp' in parts:
        return 'temporary-files-not-allowlisted'
    return None


def _walk(root, base='', *, checkpoint=False):
    """Return files and auditable exclusions, refusing symlinks in scanned scope."""
    start = root if not base else _path(root, base)
    files, excluded = [], []
    if not start.is_dir():
        _fail('Expected directory: ' + base)
    for directory, dirs, names in os.walk(start, followlinks=False):
        for name in sorted(dirs + names):
            p = Path(directory) / name
            rel = p.relative_to(root).as_posix()
            st = p.lstat()
            if stat.S_ISLNK(st.st_mode):
                _fail('Symbolic link in selected scope: ' + rel)
            reason = _excluded(rel, checkpoint=checkpoint)
            if reason:
                excluded.append({'path': rel, 'reason': reason})
                if name in dirs:
                    dirs.remove(name)
                continue
            if stat.S_ISREG(st.st_mode):
                files.append(rel)
            elif not stat.S_ISDIR(st.st_mode):
                _fail('Special file in selected scope: ' + rel)
    return sorted(files), excluded


def _scan(raw, name, reviewed, *, sqlite=False, depth=0):
    if SECRET_RE.search(raw):
        _fail('Suspected secret; review required: ' + name)
    if sqlite:
        return
    if raw.startswith(b'PK\x03\x04'):
        if depth >= 3:
            _fail('Nested archive review required: ' + name)
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                _zip_members(z)
                if sum(x.file_size for x in z.infolist()) > 100_000_000:
                    _fail('Archive scan budget exceeded: ' + name)
                for entry in z.infolist():
                    if entry.filename == 'DATA/db/panel.sqlite3':
                        _fail('Nested panel database backup requires an explicit policy exclusion: ' + name)
                    nested = z.read(entry)
                    if entry.filename.lower().endswith('.json') and len(nested) <= 1_000_000:
                        try:
                            document = json.loads(nested)
                        except (ValueError, UnicodeError):
                            document = None
                        if isinstance(document, dict) and (
                                document.get('schema') == SCHEMA and 'files' in document and 'objects' in document or
                                document.get('schema') == INDEX_SCHEMA and ('manifest' in document or 'candidate' in document)):
                            _fail('Nested v2 backup manifest requires an explicit policy exclusion: ' + name)
                    _scan(nested, name + '/' + entry.filename, reviewed, depth=depth + 1)
            return
        except (zipfile.BadZipFile, RuntimeError) as exc:
            raise BackupError('Unreadable archive: ' + name) from exc
    try:
        raw.decode('utf-8')
        # NUL-bearing data is opaque even if it happens to decode as UTF-8.
        if b'\x00' in raw:
            raise UnicodeError()
    except UnicodeError:
        if _digest(raw) not in reviewed:
            _fail('Opaque binary needs explicit hash review: ' + name)


def _quote(name):
    return '"' + name.replace('"', '""') + '"'


def _sqlite_info(path):
    path = _no_links(path)
    with contextlib.closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        if [r[0] for r in db.execute('PRAGMA integrity_check')] != ['ok']:
            _fail('SQLite integrity check failed')
        if db.execute('PRAGMA foreign_key_check').fetchone() is not None:
            _fail('SQLite foreign key check failed')
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        if 'tasks' not in tables or 'artifacts' not in tables:
            _fail('Database is not a supported panel database')
        counts = {t: db.execute('SELECT count(*) FROM ' + _quote(t)).fetchone()[0] for t in tables}
        if counts['tasks'] == 0:
            _fail('Empty panel database is not a recovery point')
        schema = list(db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"))
        # B-tree pages concatenate adjacent field bytes. Scan logical values too:
        # token boundaries must not depend on the last byte of a previous column.
        for table in tables:
            for row in db.execute('SELECT * FROM ' + _quote(table)):
                for value in row:
                    raw = value.encode('utf-8') if isinstance(value, str) else value if isinstance(value, bytes) else None
                    if raw is not None and SECRET_RE.search(raw):
                        _fail('Suspected secret in SQLite value; review required: ' + table)

        db.row_factory = sqlite3.Row
        artifacts = [dict(r) for r in db.execute('SELECT * FROM artifacts ORDER BY relative_path')]
        tasks = [r[0] for r in db.execute('SELECT id FROM tasks ORDER BY id')]
    return {'table_counts': counts, 'schema_sha256': _digest(_json_bytes(schema))}, artifacts, tasks


def _legacy(value):
    if not isinstance(value, dict) or 'index_schema_version' not in value or 'latest_available_checkpoint' not in value:
        return None
    counts = value.get('validation', {}).get('table_counts')
    if not isinstance(counts, dict) or not counts:
        _fail('migration_required: legacy v10 has no validated table-count baseline')
    for name, count in counts.items():
        if not isinstance(name, str):
            _fail('Invalid legacy table name')
        _integer(count, 'legacy table count')
    if counts.get('tasks', 0) < 1 or counts.get('runs', 0) < 1:
        _fail('migration_required: legacy tasks/runs baseline is empty')
    return {'content': value, 'canonical_sha256': _digest(_json_bytes(value)),
            'identity_scope': 'Explicit first v2 identity; cross-reset identity is not proven.',
            'migration': 'Independent v2 snapshot; legacy chain retained for audit, not reused.'}


def _check_counts(old, new):
    for table, count in old.items():
        if count and new.get(table, 0) < count * 0.7:
            _fail('Anomalous database reduction: ' + table)


def _previous(value):
    if value is None:
        return None
    if isinstance(value, dict) and 'index_schema_version' in value:
        _fail('migration_required: legacy v10 dependencies must be audited/materialized; create an independent v2 bootstrap')
    if not isinstance(value, dict) or value.get('schema') != INDEX_SCHEMA or value.get('status') != 'committed':
        _fail('Previous index must be a confirmed v2 committed envelope')
    candidate = value.get('candidate')
    receipt = value.get('platform_receipt')
    if not isinstance(candidate, dict) or not isinstance(receipt, dict):
        _fail('Incomplete previous index')
    _validate_index_receipt(receipt, candidate, value.get('expected_current_version'))
    _manifest(candidate.get('manifest'))
    policy_ref = candidate.get('supporting_files', {}).get('policy.json')
    if 'policy' not in candidate['manifest'] or policy_ref is None:
        _fail('migration_required: earlier v2 index has no pinned complete policy; audited migration required')
    _pinned(policy_ref)
    if any(policy_ref.get(k) != candidate['manifest']['policy'][k] for k in ('filename', 'sha256', 'size_bytes')):
        _fail('Committed policy reference differs from snapshot')
    runner_ref = candidate.get('supporting_files', {}).get('recovery-runner.py')
    if 'recovery_runner' not in candidate['manifest'] or runner_ref is None:
        _fail('migration_required: earlier v2 index has no pinned standalone recovery runner')
    _pinned(runner_ref)
    if any(runner_ref.get(k) != candidate['manifest']['recovery_runner'][k] for k in ('filename', 'sha256', 'size_bytes')):
        _fail('Committed runner reference differs from snapshot')
    if candidate.get('snapshot_sha256') != _digest(_json_bytes(candidate['manifest'])):
        _fail('Previous snapshot hash mismatch')
    for h, locator in candidate.get('objects', {}).items():
        _pinned(locator['package'])
        original = candidate['manifest']['objects'].get(h)
        if original is None or locator['size_bytes'] != original['size_bytes'] or locator['member'] != original['member']:
            _fail('Committed object map conflicts with its snapshot')
        for field in ('filename', 'sha256', 'size_bytes'):
            if locator['package'][field] != original['package'][field]:
                _fail('Committed package map conflicts with its snapshot')
    if set(candidate.get('objects', {})) != set(candidate['manifest']['objects']):
        _fail('Previous object map is incomplete')
    return value


def _logical(manifest):
    content = {'identity': manifest['identity'], 'files': manifest['files'],
               'external_files': manifest['external_files']}
    if 'policy' in manifest:
        content['policy_sha256'] = manifest['policy']['sha256']
    if 'recovery_runner' in manifest:
        content['runner_sha256'] = manifest['recovery_runner']['sha256']
    if 'capture_details' in manifest:
        # Mode affects the guarantee; timestamps must not defeat deduplication.
        content['capture_mode'] = manifest['capture_details']['mode']
    return _digest(_json_bytes(content))


def _manifest(m):
    if not isinstance(m, dict) or m.get('schema') != SCHEMA:
        _fail('Unsupported or incomplete snapshot manifest')
    if not isinstance(m.get('identity'), str) or not RUN_RE.fullmatch(m['identity']):
        _fail('Invalid snapshot identity')
    if not isinstance(m.get('files'), list) or not isinstance(m.get('objects'), dict):
        _fail('Invalid manifest files or objects')
    if 'capture_details' in m:
        capture = m['capture_details']
        if not isinstance(capture, dict) or capture.get('mode') not in CAPTURE_MODES:
            _fail('Invalid snapshot capture mode')
        try:
            times = [dt.datetime.fromisoformat(capture[key]) for key in (
                'database_backup_started_at', 'database_backup_completed_at',
                'files_capture_started_at', 'files_capture_completed_at')]
            if any(t.tzinfo is None for t in times) or times != sorted(times):
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            _fail('Invalid snapshot capture window')
        if capture.get('database_cutoff_upper_bound') != capture['database_backup_completed_at']:
            _fail('Invalid database snapshot cutoff')
    if 'policy' in m:
        if not isinstance(m['policy'], dict) or m['policy'].get('filename') != 'policy.json':
            _fail('Invalid pinned policy descriptor')
        _hash(m['policy']['sha256'])
        _integer(m['policy']['size_bytes'], 'policy size', minimum=1)
    if 'recovery_runner' in m:
        runner = m['recovery_runner']
        if not isinstance(runner, dict) or runner.get('filename') != 'recovery-runner.py':
            _fail('Invalid recovery runner descriptor')
        _hash(runner['sha256'])
        _integer(runner['size_bytes'], 'runner size', minimum=1)
    paths, referenced = set(), set()
    for f in m['files']:
        path = _restore_rel(f['path'])
        checkpoints = {c if isinstance(c, str) else c['path'] for c in m.get('checkpoints', [])}
        if _excluded(path.split('/', 1)[1], checkpoint=path in checkpoints):
            _fail('Manifest includes forbidden runtime/credential/backup path')
        if path in paths or f.get('mode') not in (0o600, 0o700):
            _fail('Duplicate path or unsafe mode in manifest')
        paths.add(path)
        _hash(f['sha256'])
        _integer(f['size_bytes'], 'file size')
        if not isinstance(f.get('chunks'), list):
            _fail('Invalid chunk list')
        total = 0
        for chunk in f['chunks']:
            h = _hash(chunk['sha256'])
            size = _integer(chunk['size_bytes'], 'chunk size', minimum=1)
            if h not in m['objects'] or m['objects'][h]['size_bytes'] != size:
                _fail('Missing or conflicting content object')
            total += size
            referenced.add(h)
        if total != f['size_bytes']:
            _fail('Chunk sizes do not reconstruct file')
    ext = _policy({'external_files': m.get('external_files', [])})['external_files']
    for f in ext:
        if _excluded(f['restore_path'].split('/', 1)[1]):
            _fail('External restore path targets excluded content')
        if f['restore_path'] in paths:
            _fail('External and stored file path collision')
        paths.add(f['restore_path'])
    if 'DATA/' + DB_PATH not in paths or not any(p.startswith('SOURCE/') for p in paths):
        _fail('Snapshot lacks database or source')
    if set(m['objects']) != referenced:
        _fail('Unreferenced objects in manifest')
    for h, obj in m['objects'].items():
        _hash(h)
        _integer(obj['size_bytes'], 'object size', minimum=1)
        package = obj['package']
        _safe_rel(package['filename'])
        if '/' in package['filename']:
            _fail('Package filename must be a basename')
        _hash(package['sha256'])
        size = _integer(package['size_bytes'], 'package size', minimum=1)
        if size >= MAX_PACKAGE_BYTES:
            _fail('Package exceeds strict upload limit')
        if obj.get('member') != 'objects/' + h:
            _fail('Invalid object member')
    # Reject file/directory collisions before any extraction.
    for p in paths:
        if any(str(parent) in paths for parent in PurePosixPath(p).parents):
            _fail('File/directory collision in manifest')
    if _logical(m) != m.get('content_sha256'):
        _fail('Logical snapshot hash mismatch')
    return m


def _new_directory(path):
    path = _no_links(path, exists=False)
    if path.exists():
        _fail('Destination must not exist')
    path.mkdir(mode=0o700, parents=False)
    return path


def _identity(data, bootstrap, identity):
    path = data / IDENTITY_PATH
    if path.exists():
        record = _load(path)
        if set(record) != {'schema', 'identity'} or record['schema'] != SCHEMA:
            _fail('Invalid persisted identity')
        actual = record['identity']
        if identity is not None and actual != identity:
            _fail('Persisted identity mismatch')
    else:
        if not bootstrap:
            _fail('Persistent identity missing; explicit bootstrap required')
        actual = identity or uuid.uuid4().hex
        if not isinstance(actual, str) or not RUN_RE.fullmatch(actual):
            _fail('Invalid explicit identity')
        _write(path, _json_bytes({'schema': SCHEMA, 'identity': actual}), exclusive=True)
    if not isinstance(actual, str) or not RUN_RE.fullmatch(actual):
        _fail('Invalid persisted identity')
    return actual


def _selection(source, data, artifacts, tasks, policy):
    files, audit = {}, []
    source_files, exclusions = _walk(source)
    for rel in source_files:
        files['SOURCE/' + rel] = (source / rel, None)
    audit.extend({'path': 'SOURCE/' + x['path'], 'reason': x['reason']} for x in exclusions)
    if not source_files:
        _fail('Source root is empty')
    def add_tree(rel):
        if not (data / rel).exists():
            return
        selected, omitted = _walk(data, rel)
        for p in selected:
            files['DATA/' + p] = (data / p, None)
        audit.extend({'path': 'DATA/' + x['path'], 'reason': x['reason']} for x in omitted)
    add_tree('config')
    if (data / 'recovery-ledger.json').exists():
        files['DATA/recovery-ledger.json'] = (data / 'recovery-ledger.json', None)
    for task in tasks:
        _safe_rel(task)
        if '/' in task:
            _fail('Invalid registered task identity')
        add_tree('tasks/' + task + '/inputs')
    for rel in policy['excluded_inputs']:
        if rel.split('/')[1] not in tasks:
            _fail('Input exclusion is outside registered tasks')
        path = 'DATA/' + rel
        # Intentionally excluded bytes are absent after restoration. Validate every
        # existing path component, but never require or recreate those bytes.
        local = _no_links(data / rel, exists=False)
        missing = not local.exists()
        if not missing and (path not in files or not local.is_file()):
            _fail('Input exclusion must identify an existing selected regular file')
        files.pop(path, None)
        audit.append({'path': path, 'reason': 'explicit-input-policy-exclusion-not-restorable',
                      'currently_missing': missing})
    explicit_exclusions = set(policy['excluded_outputs'])
    seen_exclusions = set()
    for a in artifacts:
        rel = _safe_rel(a['relative_path'])
        expected_prefix = 'tasks/' + _safe_rel(a['task_id']) + '/outputs/'
        if not rel.startswith(expected_prefix):
            _fail('Registered output escapes its task outputs')
        reason = _excluded(rel)
        if rel in explicit_exclusions:
            seen_exclusions.add(rel)
            reason = 'explicit-policy-exclusion-not-restorable'
        if reason:
            audit.append({'path': 'DATA/' + rel, 'reason': reason, 'artifact_id': a['id']})
            continue
        _hash(a['sha256'])
        _integer(a['size'], 'registered artifact size')
        files['DATA/' + rel] = (data / rel, a)
    if seen_exclusions != explicit_exclusions:
        _fail('Excluded output is not a registered artifact')
    for checkpoint in policy['checkpoints']:
        path = checkpoint if isinstance(checkpoint, str) else checkpoint['path']
        if path.startswith('DATA/') and path[5:] in policy['excluded_inputs'] + policy['excluded_outputs']:
            _fail('Checkpoint conflicts with an explicit exclusion')
        root_name, rel = path.split('/', 1)
        if _excluded(rel, checkpoint=True):
            _fail('Checkpoint targets an excluded credential/runtime/backup path')
        p = (source if root_name == 'SOURCE' else data) / rel
        size = _no_links(p).stat().st_size
        if isinstance(checkpoint, str):
            if size > CHECKPOINT_BYTES:
                _fail('Checkpoint exceeds small-file limit; use explicit hash/size pin')
        elif size != checkpoint['size_bytes'] or _digest(_read_file(p)) != checkpoint['sha256']:
            _fail('Pinned checkpoint hash/size mismatch')
        files.setdefault(path, (p, None))
    external = {f['restore_path']: f for f in policy['external_files']}
    for path, ref in external.items():
        if path.startswith('DATA/') and path[5:] in policy['excluded_inputs'] + policy['excluded_outputs']:
            _fail('External reference conflicts with an explicit exclusion')
        if path not in files:
            if not any(path.startswith('DATA/tasks/' + task + '/inputs/') for task in tasks):
                _fail('External reference is outside the selected task inputs/outputs')
            if _excluded(path):
                _fail('External input targets excluded content')
            artifact = None
        else:
            _, artifact = files.pop(path)
        if artifact and (artifact['sha256'] != ref['sha256'] or artifact['size'] != ref['size_bytes'] or artifact.get('library_id') != ref['library_file_id']):
            _fail('External reference conflicts with registered artifact')
    audit.extend({'path': x, 'reason': 'out-of-scope-by-selection-rule'} for x in ('DATA/logs/**', 'DATA/run/**', 'DATA/tmp/**', 'DATA/tasks/*/tmp/**', 'DATA/unregistered-outputs/**'))
    return files, audit


def _pack(run_dir, objects, max_bytes):
    if not 4096 <= max_bytes <= MAX_PACKAGE_BYTES:
        _fail('Invalid package byte limit')
    groups, group, used = [], [], 22
    for h in sorted(objects):
        size = (run_dir / 'objects' / h).stat().st_size
        # ZIP_STORED, ASCII names, no extras, no ZIP64: exact payload + header budget.
        cost = size + 76 + 2 * len('objects/' + h)
        if cost + 22 >= max_bytes:
            _fail('Object cannot fit package; reduce chunk size')
        if group and used + cost >= max_bytes:
            groups.append(group)
            group, used = [], 22
        group.append(h)
        used += cost
    if group:
        groups.append(group)
    packages = []
    for i, hashes in enumerate(groups, 1):
        filename = 'objects-' + run_dir.name + '-' + str(i).zfill(4) + '.zip'
        target = run_dir / filename
        with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
            for h in hashes:
                entry = zipfile.ZipInfo('objects/' + h, date_time=(1980, 1, 1, 0, 0, 0))
                entry.external_attr = (stat.S_IFREG | 0o600) << 16
                archive.writestr(entry, _read_file(run_dir / 'objects' / h))
        os.chmod(target, 0o600)
        raw = _read_file(target)
        if len(raw) >= max_bytes:
            _fail('Final ZIP exceeds strict size limit')
        desc = {'filename': filename, 'sha256': _digest(raw), 'size_bytes': len(raw)}
        for h in hashes:
            objects[h].update(package=desc, member='objects/' + h)
        packages.append(desc)
    return packages


def _guard(state, run_id):
    path = state / 'guard.json'
    if path.exists():
        existing = _load(path)
        if existing.get('run_id') != run_id:
            _fail('Another run or uncertain transaction holds the guard')
    else:
        _write(path, _json_bytes({'run_id': run_id, 'created_at': _now()}), exclusive=True)



def _validate_review_png(raw):
    """Validate a bounded, noninterlaced PNG before accepting a late hash review."""
    if not raw.startswith(b'\x89PNG\r\n\x1a\n'):
        _fail('Review refresh currently supports verified PNG artifacts only')
    pos, header, compressed, ended = 8, None, bytearray(), False
    saw_data = False
    while pos < len(raw):
        if pos + 12 > len(raw):
            _fail('Truncated PNG during review refresh')
        length = int.from_bytes(raw[pos:pos + 4], 'big')
        kind = raw[pos + 4:pos + 8]
        if length > len(raw) - pos - 12:
            _fail('Invalid PNG chunk size')
        body = raw[pos + 8:pos + 8 + length]
        crc = int.from_bytes(raw[pos + 8 + length:pos + 12 + length], 'big')
        if zlib.crc32(kind + body) & 0xffffffff != crc:
            _fail('PNG chunk checksum failed')
        if header is None and kind != b'IHDR':
            _fail('PNG must begin with IHDR')
        if kind == b'IHDR':
            if header is not None or length != 13:
                _fail('Invalid PNG header')
            header = body
        elif kind == b'IDAT':
            saw_data = True
            compressed.extend(body)
        elif kind == b'IEND':
            if length != 0 or pos + 12 != len(raw):
                _fail('Invalid PNG end or trailing data')
            ended = True
            break
        pos += 12 + length
    if header is None or not saw_data or not ended:
        _fail('Incomplete PNG')
    width, height = int.from_bytes(header[:4], 'big'), int.from_bytes(header[4:8], 'big')
    depth, color, compression, filtering, interlace = header[8:]
    valid_depths = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}
    if (not width or not height or width > 32768 or height > 32768 or
            depth not in valid_depths.get(color, set()) or compression or filtering or interlace):
        _fail('Unsupported PNG type for controlled review refresh')
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
    row_bytes = 1 + (width * depth * channels + 7) // 8
    expected = row_bytes * height
    if expected > 64_000_000:
        _fail('PNG decoded review budget exceeded')
    try:
        decoder = zlib.decompressobj()
        decoded = decoder.decompress(bytes(compressed), expected + 1)
    except zlib.error as exc:
        raise BackupError('Invalid PNG image stream') from exc
    if (len(decoded) != expected or not decoder.eof or decoder.unused_data or
            decoder.unconsumed_tail or any(decoded[p] > 4 for p in range(0, expected, row_bytes))):
        _fail('PNG image data does not match its dimensions')
    return {'type': 'image/png', 'width': width, 'height': height}



def _assert_unpackaged_preparation(run_dir):
    remote_markers = {'upload-plan.json', 'upload-receipts.json', 'candidate-index.json',
                      'index-update-plan.json', 'platform-receipt.json', 'committed-index.json'}
    for path in run_dir.rglob('*'):
        _no_links(path)
        if path.name in remote_markers or path.suffix.lower() == '.zip':
            _fail('Preparing-only action blocked by packaged or remote-transaction evidence')


def _apply_review_refresh(run_dir, journal, request, refresh, data):
    """One explicit, auditable late-PNG review extension before any upload plan."""
    if not isinstance(refresh, dict) or set(refresh) != {'no_remote_actions', 'previous_reviewed_binary_sha256', 'reviews'}:
        _fail('Review refresh requires explicit no-remote-actions assertion, prior hashes and review evidence')
    if refresh['no_remote_actions'] is not True:
        _fail('Review refresh cannot follow any remote action')
    if journal.get('status') != 'preparing':
        _fail('Review refresh is allowed only while preparing')
    _assert_unpackaged_preparation(run_dir)
    old_hashes = refresh['previous_reviewed_binary_sha256']
    reviews = refresh['reviews']
    if not isinstance(old_hashes, list) or not isinstance(reviews, list):
        _fail('Invalid review refresh lists')
    for h in old_hashes:
        _hash(h)
    new_hashes = request['policy']['reviewed_binary_sha256']
    if len(set(old_hashes)) != len(old_hashes) or len(set(new_hashes)) != len(new_hashes):
        _fail('Review hash lists must be unique')
    added = set(new_hashes) - set(old_hashes)
    if not added or not set(old_hashes) < set(new_hashes):
        _fail('Review refresh must only add reviewed binary hashes')
    old_request = dict(request, policy=dict(request['policy'], reviewed_binary_sha256=old_hashes))
    old_request_hash, new_request_hash = _digest(_json_bytes(old_request)), _digest(_json_bytes(request))
    authorization_hash = _digest(_json_bytes(refresh))
    history = journal.get('review_refreshes', [])
    already_applied = any(item.get('authorization_sha256') == authorization_hash and
                          item.get('request_after_sha256') == new_request_hash and
                          item.get('request_before_sha256') == old_request_hash for item in history)
    if journal['request_sha256'] != old_request_hash:
        if journal['request_sha256'] != new_request_hash or not already_applied:
            _fail('Review refresh changes locked request scope or lacks matching prior authorization')
    if not reviews or any(not isinstance(r, dict) or set(r) != {'sha256', 'artifact_id', 'path', 'evidence'} for r in reviews):
        _fail('Each added hash needs artifact, path and concrete review evidence')
    if {r.get('sha256') for r in reviews} != added or len(reviews) != len(added):
        _fail('Review evidence must cover each newly added hash exactly once')
    _, artifacts, _ = _sqlite_info(_path(data, DB_PATH))
    by_id = {a['id']: a for a in artifacts}
    checked = []
    for review in reviews:
        digest = _hash(review['sha256'])
        path = _restore_rel(review['path'])
        if not isinstance(review['evidence'], str) or not 12 <= len(review['evidence'].strip()) <= 2000:
            _fail('Concrete nonempty binary-review evidence is required')
        artifact = by_id.get(review['artifact_id'])
        if (artifact is None or path != 'DATA/' + artifact['relative_path'] or
                not artifact['relative_path'].startswith('tasks/' + _safe_rel(artifact['task_id']) + '/outputs/')):
            _fail('Review refresh does not match a currently registered output artifact')
        if path in {'DATA/' + x for x in request['policy']['excluded_outputs']}:
            _fail('Excluded output cannot authorize an active binary review')
        raw = _read_file(_path(data, artifact['relative_path']))
        if _digest(raw) != digest or digest != artifact['sha256'] or len(raw) != artifact['size']:
            _fail('Reviewed artifact hash/size differs from current registered bytes')
        png = _validate_review_png(raw)
        _scan(raw, path, {digest})
        checked.append(dict(review, checked_type=png))
    if not already_applied:
        history.append({'request_before_sha256': old_request_hash, 'request_after_sha256': new_request_hash,
                        'authorization_sha256': authorization_hash, 'added_sha256': sorted(added),
                        'reviews': checked, 'no_remote_actions': True, 'applied_at': _now()})
        journal['review_refreshes'] = history
        journal['request_sha256'] = new_request_hash
        _save(run_dir / 'journal.json', journal)
    return journal


def _prepare(source, data, state, *, policy=None, previous=None, run_id=None,
            bootstrap=False, identity=None, chunk_bytes=CHUNK_BYTES,
            max_package_bytes=MAX_PACKAGE_BYTES, review_refresh=None,
            capture_mode='strict-live'):
    """Prepare only. State must be outside both roots. Reuse run_id to resume.

    Strict-live (default) requires stable live SQLite data_version through file
    capture. Explicit database-snapshot-cutoff selects database records only from
    the completed read-only online backup, allowing later live commits. Both
    modes pin root/database/installation identity and rehash selected files.
    Neither mode is a filesystem-wide atomic transaction. No remote operation.
    """
    source, data = _root(source), _root(data)
    state = _no_links(state, exists=False)
    roots = [source, data, state]
    if any(a == b or a in b.parents or b in a.parents for i, a in enumerate(roots) for b in roots[i + 1:]):
        _fail('SOURCE, DATA and state must be independent roots')
    db_path = _path(data, DB_PATH)
    if not db_path.is_file() or db_path.stat().st_size == 0:
        _fail('Database is missing or empty')
    if capture_mode not in CAPTURE_MODES:
        _fail('Unknown capture mode')
    entities = [(p, directory, _entity(p, directory)) for p, directory in
                ((source, True), (data, True), (db_path, False))]
    # Preflight DB before creating identity/state.
    _sqlite_info(db_path)
    if not any(source.iterdir()):
        _fail('Source root is empty')
    policy = _policy(policy)
    legacy = _legacy(previous)
    original_previous = previous
    if legacy:
        if not bootstrap or identity is None:
            _fail('migration_required: v10 requires explicit --bootstrap and --identity')
        _scan(_json_bytes(legacy), 'legacy-index', set(), sqlite=True)
        _check_counts(legacy['content']['validation']['table_counts'], _sqlite_info(db_path)[0]['table_counts'])
        previous = None
    else:
        previous = _previous(previous)
    if previous is None and not bootstrap:
        _fail('First v2 recovery point requires explicit bootstrap')
    if previous is not None and bootstrap:
        _fail('Bootstrap cannot reuse a previous index')
    identity = _identity(data, bootstrap, identity)
    identity_path = _path(data, IDENTITY_PATH)
    identity_bytes = _read_file(identity_path)
    if json.loads(identity_bytes) != {'schema': SCHEMA, 'identity': identity}:
        _fail('Persisted installation identity changed before capture')
    entities.append((identity_path, False, _entity(identity_path)))
    _check_capture_identity(entities, identity_path, identity_bytes)
    if previous and previous['candidate']['manifest']['identity'] != identity:
        _fail('Identity changed from previous recovery point')
    _integer(chunk_bytes, 'chunk size', minimum=1)
    if chunk_bytes > 16_000_000:
        _fail('Chunk size exceeds bounded object size')
    run_id = run_id or uuid.uuid4().hex
    if not RUN_RE.fullmatch(run_id):
        _fail('Invalid run_id')
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    run_dir = state / run_id
    request = {'source': str(source), 'data': str(data), 'identity': identity, 'policy': policy,
               'previous_sha256': _digest(_json_bytes(original_previous)) if original_previous else None,
               'chunk_bytes': chunk_bytes, 'max_package_bytes': max_package_bytes}
    # Absent mode is the original strict-live request representation. Preserve
    # legacy preparing/prepared retries; the new mode always changes the lock.
    if capture_mode != 'strict-live':
        request['capture_mode'] = capture_mode
    request_hash = _digest(_json_bytes(request))
    journal_path = run_dir / 'journal.json'
    if journal_path.exists():
        journal = _load(journal_path)
        if journal.get('status') == 'abandoned':
            _fail('Abandoned run cannot be resumed; use a new run ID after reviewing the policy')
        if journal.get('capture_mode', 'strict-live') != capture_mode:
            _fail('Run ID is already bound to a different capture mode')
        if review_refresh is not None:
            journal = _apply_review_refresh(run_dir, journal, request, review_refresh, data)
        if journal.get('request_sha256') != request_hash:
            _fail('Run ID is already bound to different parameters')
        if journal.get('status') != 'preparing':
            if journal.get('status') in ('committed', 'skipped_unchanged'):
                if (state / 'guard.json').exists() and _load(state / 'guard.json').get('run_id') == run_id:
                    (state / 'guard.json').unlink()
            else:
                _guard(state, run_id)
            if journal.get('snapshot_sha256') and _digest(_read_file(run_dir / 'manifest.json')) != journal['snapshot_sha256']:
                _fail('Prepared manifest has changed')
            return {'run_id': run_id, 'run_dir': str(run_dir), 'status': journal['status'], 'resumed': True}
        _guard(state, run_id)
        # No upload plan exists during preparing; only our temporary attempt may be replaced.
        for p in run_dir.iterdir():
            if p.name == 'journal.json':
                continue
            _no_links(p)
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
    else:
        if review_refresh is not None:
            _fail('Review refresh requires an existing interrupted preparing run')
        _guard(state, run_id)
        _new_directory(run_dir)
        journal = {'schema': SCHEMA, 'run_id': run_id, 'request_sha256': request_hash,
                   'status': 'preparing', 'created_at': _now(), 'capture_mode': capture_mode}
        _save(journal_path, journal)
    (run_dir / 'objects').mkdir(mode=0o700)
    snapshot_path = run_dir / 'database.sqlite3'
    _check_capture_identity(entities, identity_path, identity_bytes)
    with contextlib.closing(sqlite3.connect(db_path.as_uri() + '?mode=ro', uri=True)) as live:
        version_before = live.execute('PRAGMA data_version').fetchone()[0]
        capture = {'mode': capture_mode, 'database_backup_started_at': _now()}
        with contextlib.closing(sqlite3.connect(snapshot_path)) as snapshot:
            live.backup(snapshot)
        capture['database_backup_completed_at'] = _now()
        capture['database_cutoff_upper_bound'] = capture['database_backup_completed_at']
        capture['cutoff_semantics'] = ('Consistent SQLite view obtained during the backup window; '
            'completion is an upper bound, not proof that every commit before that time is included. '
            'Later database records are not included; tasks/artifacts are selected only from this frozen database.')
        capture['filesystem_semantics'] = ('Not a filesystem-wide atomic snapshot. Selected filesystem bytes '
            'are read during the separate file capture window, with stable pre/post hashes and sizes.')
        _check_capture_identity(entities, identity_path, identity_bytes)
        os.chmod(snapshot_path, 0o600)
        db_info, artifacts, tasks = _sqlite_info(snapshot_path)
        capture['files_capture_started_at'] = _now()
        selected, exclusions = _selection(source, data, artifacts, tasks, policy)
        source_inventory = sorted(p for p in selected if p.startswith('SOURCE/'))
        selected['DATA/' + DB_PATH] = (snapshot_path, None)
        objects, files, originals = {}, [], {}
        prior_objects = previous['candidate']['objects'] if previous else {}
        reviewed = set(policy['reviewed_binary_sha256'])
        for path, (local, artifact) in sorted(selected.items()):
            raw = _read_file(local)
            h = _digest(raw)
            if artifact and (h != artifact['sha256'] or len(raw) != artifact['size']):
                _fail('Registered artifact content mismatch: ' + path)
            _scan(raw, path, reviewed, sqlite=path == 'DATA/' + DB_PATH)
            originals[path] = (h, len(raw))
            chunks = []
            for offset in range(0, len(raw), chunk_bytes):
                chunk = raw[offset:offset + chunk_bytes]
                ch = _digest(chunk)
                chunks.append({'sha256': ch, 'size_bytes': len(chunk)})
                if ch in objects:
                    continue
                if ch in prior_objects:
                    locator = prior_objects[ch]
                    if locator['size_bytes'] != len(chunk):
                        _fail('Prior object size conflict')
                    objects[ch] = locator
                else:
                    _write(run_dir / 'objects' / ch, chunk, exclusive=True)
                    objects[ch] = {'size_bytes': len(chunk)}
            mode = 0o700 if path.startswith('SOURCE/') and _no_links(local).stat().st_mode & 0o111 else 0o600
            files.append({'path': path, 'sha256': h, 'size_bytes': len(raw), 'mode': mode, 'chunks': chunks})
        for path, (local, _) in selected.items():
            raw = _read_file(local)
            if (_digest(raw), len(raw)) != originals[path]:
                _fail('Selected file changed during capture: ' + path)
        after, _ = _selection(source, data, artifacts, tasks, policy)
        if sorted(after) != sorted(p for p in selected if p != 'DATA/' + DB_PATH):
            _fail('Selected file set changed during capture')
        if sorted(p for p in after if p.startswith('SOURCE/')) != source_inventory:
            _fail('Source changed during capture')
        _check_capture_identity(entities, identity_path, identity_bytes)
        if capture_mode == 'strict-live' and version_before != live.execute('PRAGMA data_version').fetchone()[0]:
            _fail('Database changed during capture; retry in a quiet window')
        capture['files_capture_completed_at'] = _now()
    lineage = legacy or (previous['candidate'].get('legacy_previous_index') if previous else None)
    policy_raw = _json_bytes(policy)
    _scan(policy_raw, 'policy.json', set())
    policy_descriptor = {'filename': 'policy.json', 'sha256': _digest(policy_raw), 'size_bytes': len(policy_raw)}
    runner_raw = _read_file(Path(__file__))
    _scan(runner_raw, 'recovery-runner.py', set())
    runner_descriptor = {'filename': 'recovery-runner.py', 'sha256': _digest(runner_raw), 'size_bytes': len(runner_raw)}
    manifest = {'schema': SCHEMA, 'identity': identity, 'run_id': run_id, 'created_at': _now(),
                'files': files, 'external_files': policy['external_files'], 'objects': objects,
                'database': db_info, 'capture': 'SQLite Connection.backup from mode=ro; selected files rehashed; ' + capture_mode,
                'capture_details': capture,
                'deletion_semantics': 'This full manifest alone defines membership; old objects are retained.',
                'checkpoints': policy['checkpoints'], 'legacy_previous_index': lineage,
                'privacy_exclusions': exclusions, 'policy': policy_descriptor, 'recovery_runner': runner_descriptor}
    manifest['content_sha256'] = _logical(manifest)
    audit = {'schema': SCHEMA, 'included': [f['path'] for f in files], 'excluded': exclusions,
             'external_dependencies': policy['external_files'], 'reviewed_binary_sha256': policy['reviewed_binary_sha256'],
             'limits': ['Content scanning is heuristic; uncertain opaque files block until explicit hash review.',
                        'Cross-directory capture is not a filesystem transaction.',
                        'Database cutoff does not date filesystem bytes; selected files are captured and rehashed later.',
                        'No unregistered outputs or generic temporary trees are included.']}
    _save(run_dir / 'privacy-audit.json', audit)
    if previous:
        old = previous['candidate']['manifest']
        for label, before, after_count in [('files', len(old['files']), len(files)),
                                            ('bytes', sum(x['size_bytes'] for x in old['files']), sum(x['size_bytes'] for x in files))]:
            if before and after_count < before * 0.7:
                _fail('Anomalous reduction in ' + label + '; explicit investigation required')
        for prefix in ('SOURCE/', 'DATA/'):
            before_files = [f for f in old['files'] if f['path'].startswith(prefix)]
            after_files = [f for f in files if f['path'].startswith(prefix)]
            for label, before, after_count in [('file count', len(before_files), len(after_files)),
                    ('bytes', sum(f['size_bytes'] for f in before_files), sum(f['size_bytes'] for f in after_files))]:
                if before and after_count < before * 0.7:
                    _fail('Anomalous ' + prefix[:-1] + ' reduction in ' + label)
        _check_counts(old['database']['table_counts'], db_info['table_counts'])
        if manifest['content_sha256'] == old['content_sha256']:
            _check_capture_identity(entities, identity_path, identity_bytes)
            journal.update(status='skipped_unchanged', content_sha256=manifest['content_sha256'],
                           capture_details=capture)
            _save(journal_path, journal)
            (state / 'guard.json').unlink()
            return {'run_id': run_id, 'run_dir': str(run_dir), 'status': 'skipped_unchanged'}
    new_objects = {h: o for h, o in objects.items() if 'package' not in o}
    packages = _pack(run_dir, new_objects, max_package_bytes)
    objects.update(new_objects)
    _manifest(manifest)
    manifest_raw = _json_bytes(manifest)
    if len(manifest_raw) >= MAX_PACKAGE_BYTES:
        _fail('Manifest exceeds supported transport size')
    _write(run_dir / 'manifest.json', manifest_raw)
    _write(run_dir / 'policy.json', policy_raw)
    _write(run_dir / 'recovery-runner.py', runner_raw)
    coverage = {'schema': SCHEMA, 'checkpoints': policy['checkpoints'], 'temporary_directory_hints': [],
                'not_restorable_policy_exclusions': policy['excluded_outputs'],
                'not_restorable_input_exclusions': policy['excluded_inputs'],
                'limits': 'Names and direct-child counts only; these hints do not prove coverage of unfinished work.'}
    for task in tasks:
        tmp = data / 'tasks' / task / 'tmp'
        if tmp.exists():
            _no_links(tmp)
            if not tmp.is_dir():
                _fail('Task tmp path is not a directory')
            children = sorted(tmp.iterdir())
            coverage['temporary_directory_hints'].append({'path': 'DATA/tasks/' + task + '/tmp',
                'direct_child_count': len(children),
                'directory_names': [p.name for p in children if p.is_dir() and not p.is_symlink()],
                'allowlisted_files': [c if isinstance(c, str) else c['path'] for c in policy['checkpoints']
                                     if (c if isinstance(c, str) else c['path']).startswith('DATA/tasks/' + task + '/tmp/')]})
    _save(run_dir / 'coverage.json', coverage)
    items = list(packages)
    for filename in ('manifest.json', 'privacy-audit.json', 'coverage.json', 'policy.json', 'recovery-runner.py'):
        raw = _read_file(run_dir / filename)
        if len(raw) >= MAX_PACKAGE_BYTES:
            _fail('Metadata file exceeds supported transport size')
        items.append({'filename': filename, 'sha256': _digest(raw), 'size_bytes': len(raw)})
    for item in items:
        item['operation_id'] = run_id + ':' + item['sha256']
    plan = {'schema': SCHEMA, 'run_id': run_id, 'action': 'external_platform_upload_required',
            'retry_rule': 'Reconcile unknown operations by operation_id; never blindly repeat an upload.', 'items': items}
    _check_capture_identity(entities, identity_path, identity_bytes)
    _save(run_dir / 'upload-plan.json', plan)
    journal.update(status='prepared', snapshot_sha256=_digest(manifest_raw), content_sha256=manifest['content_sha256'],
                   upload_plan_sha256=_digest(_json_bytes(plan)), capture_details=capture)
    _save(journal_path, journal)
    return {'run_id': run_id, 'run_dir': str(run_dir), 'status': 'prepared', 'file_count': len(files),
            'new_packages': len(packages), 'external_dependencies': len(policy['external_files'])}


def _zip_members(archive):
    names = set()
    for info in archive.infolist():
        _safe_rel(info.filename)
        mode = info.external_attr >> 16
        if info.filename in names or info.is_dir() or stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG)):
            _fail('Unsafe or duplicate ZIP member')
        if info.flag_bits & 1:
            _fail('Encrypted ZIP members are unsupported')
        names.add(info.filename)
    return names


def _restore_parent(destination, relative_path):
    """Create every restore parent privately, including intermediate roots.

    Path.mkdir(parents=True, mode=0o700) applies its mode only to the leaf;
    intermediate DATA/SOURCE directories otherwise depend on the user's umask.
    Never change permissions on an existing path to conceal an unsafe tree.
    """
    parent = _root(destination)
    for part in PurePosixPath(_restore_rel(relative_path)).parts[:-1]:
        parent = parent / part
        try:
            parent.mkdir(mode=0o700)
        except FileExistsError:
            pass
        _root(parent)
        if parent.stat().st_mode & 0o077:
            _fail('Restore parent is not private: ' + parent.name)
    return parent


def _materialize_into(manifest_path, packages_dir, external_dir, destination, object_cache):
    raw = _read_file(Path(manifest_path))
    m = _manifest(json.loads(raw))
    policy_verified = False
    if 'policy' in m:
        policy_raw = _read_file(Path(manifest_path).parent / 'policy.json')
        if _digest(policy_raw) != m['policy']['sha256'] or len(policy_raw) != m['policy']['size_bytes']:
            _fail('Pinned policy hash/size mismatch')
        policy = _policy(json.loads(policy_raw))
        if _json_bytes(policy) != policy_raw:
            _fail('Policy is not the complete canonical policy')
        if policy['checkpoints'] != m.get('checkpoints') or policy['external_files'] != m['external_files']:
            _fail('Policy scope differs from manifest')
        policy_verified = True
    runner_verified = False
    if 'recovery_runner' in m:
        runner_raw = _read_file(Path(manifest_path).parent / 'recovery-runner.py')
        if _digest(runner_raw) != m['recovery_runner']['sha256'] or len(runner_raw) != m['recovery_runner']['size_bytes']:
            _fail('Pinned recovery runner hash/size mismatch')
        runner_verified = True
    packages_dir = _root(packages_dir)
    external_dir = _root(external_dir) if external_dir else None
    checked, chunks = {}, {}
    for h, obj in m['objects'].items():
        desc = obj['package']
        key = desc['filename']
        if key not in checked:
            package_raw = _read_file(_path(packages_dir, key))
            if len(package_raw) != desc['size_bytes'] or _digest(package_raw) != desc['sha256']:
                _fail('Package hash/size mismatch: ' + key)
            with zipfile.ZipFile(io.BytesIO(package_raw)) as archive:
                names = _zip_members(archive)
                for member in names:
                    if not re.fullmatch(r'objects/[0-9a-f]{64}', member):
                        _fail('Unexpected ZIP member')
                expected = {x['member'] for x in m['objects'].values() if x['package']['filename'] == key}
                if not expected <= names:
                    _fail('Package lacks required members')
                if any(x.file_size > 16_000_000 for x in archive.infolist()):
                    _fail('Unbounded object size in ZIP')
                checked[key] = desc
                for member in expected:
                    data = archive.read(member)
                    if _digest(data) != member.split('/')[1]:
                        _fail('Content-addressed object mismatch')
                    cache_path = object_cache / member.split('/')[1]
                    _write(cache_path, data, exclusive=True)
                    chunks[member.split('/')[1]] = cache_path
        elif checked[key] != desc:
            _fail('Conflicting package identity')
        if chunks[h].stat().st_size != obj['size_bytes']:
            _fail('Object size mismatch')
    for f in m['files']:
        target = destination / f['path']
        _restore_parent(destination, f['path'])
        digest, size = hashlib.sha256(), 0
        with target.open('xb') as stream:
            os.chmod(target, f['mode'])
            for c in f['chunks']:
                block = _read_file(chunks[c['sha256']])
                stream.write(block)
                digest.update(block)
                size += len(block)
        if digest.hexdigest() != f['sha256'] or size != f['size_bytes']:
            _fail('Reconstructed file mismatch')
    for ref in m['external_files']:
        if external_dir is None:
            _fail('External bytes missing; recovery is not verified')
        # The materialization folder uses exact restore paths, never mutable names/URLs.
        data = _read_file(_path(external_dir, ref['restore_path']))
        if len(data) != ref['size_bytes'] or _digest(data) != ref['sha256']:
            _fail('Pinned external bytes mismatch')
        _restore_parent(destination, ref['restore_path'])
        _write(destination / ref['restore_path'], data, exclusive=True)
    identity = _load(destination / 'DATA' / IDENTITY_PATH)
    if identity != {'schema': SCHEMA, 'identity': m['identity']}:
        _fail('Restored identity does not match snapshot identity')
    info, artifacts, _ = _sqlite_info(destination / 'DATA' / DB_PATH)
    omitted = {(x.get('path'), x.get('artifact_id')) for x in m.get('privacy_exclusions', [])}
    restored_files = {f['path']: f for f in m['files']}
    restored_files.update({f['restore_path']: f for f in m['external_files']})
    for artifact in artifacts:
        path = 'DATA/' + _safe_rel(artifact['relative_path'])
        if path not in restored_files:
            if (path, artifact['id']) not in omitted:
                _fail('Registered output missing without an auditable exclusion')
        elif restored_files[path]['sha256'] != artifact['sha256'] or restored_files[path]['size_bytes'] != artifact['size']:
            _fail('Restored registered output conflicts with database')
    if info != m['database']:
        _fail('Restored database metadata mismatch')
    return {'schema': SCHEMA, 'snapshot_sha256': _digest(raw), 'content_sha256': m['content_sha256'],
            'complete_restore_bytes': True, 'policy_verified': policy_verified, 'runner_verified': runner_verified,
            'verified_at': _now(), 'file_count': len(m['files']),
            'external_file_count': len(m['external_files']), 'database': info}



def _materialize(manifest_path, packages_dir, external_dir, destination):
    # Keep only a bounded package/chunk in memory, even for multi-package restores.
    with tempfile.TemporaryDirectory(prefix='panel-backup-objects-') as cache:
        return _materialize_into(manifest_path, packages_dir, external_dir, destination, Path(cache))


def verify(snapshot, packages_dir, *, external_dir=None, report=None):
    """Actually reconstruct all bytes in a temporary isolated directory and check DB."""
    with tempfile.TemporaryDirectory(prefix='panel-backup-verify-') as temp:
        result = _materialize(snapshot, packages_dir, external_dir, Path(temp))
    if report is not None:
        _save(Path(report), result)
    return result


def restore(snapshot, packages_dir, destination, *, external_dir=None):
    """Restore to a nonexistent directory only; never activate or apply runtime PIDs."""
    snapshot, packages_dir = Path(snapshot), _root(packages_dir)
    destination = _no_links(destination, exists=False)
    if any(destination == p or destination in p.parents or p in destination.parents for p in [packages_dir, snapshot.parent]):
        _fail('Restore directory must be independent of backup storage')
    target = _new_directory(destination)
    try:
        result = _materialize(snapshot, packages_dir, external_dir, target)
    except Exception:
        # Preserve a failed attempt for diagnosis; never silently retry into it.
        _save(target / 'RESTORE-FAILED.json', {'status': 'incomplete', 'do_not_activate': True})
        raise
    _save(target / 'RESTORE-VERIFIED.json', result)
    return result


def _validate_upload_receipt(receipt, item):
    if not isinstance(receipt, dict) or receipt.get('status') != 'confirmed':
        _fail('Upload outcome is unknown or unconfirmed; reconcile before continuing')
    if receipt.get('filename') != item['filename'] or receipt.get('operation_id') != item['operation_id']:
        _fail('Receipt does not match the planned upload')
    pinned = _pinned(receipt)
    if pinned['sha256'] != item['sha256'] or pinned['size_bytes'] != item['size_bytes']:
        _fail('Upload receipt hash/size mismatch')
    pinned['filename'] = item['filename']
    pinned['download_verified'] = False
    if 'download_path' not in receipt:
        _fail('New upload requires downloaded bytes for readback verification')
    if 'download_path' in receipt:
        raw = _read_file(Path(receipt['download_path']))
        if _digest(raw) != item['sha256'] or len(raw) != item['size_bytes']:
            _fail('Downloaded upload bytes do not match')
        pinned['download_verified'] = True
    return pinned


def _validate_index_receipt(receipt, candidate, expected):
    if not isinstance(receipt, dict) or receipt.get('status') != 'committed':
        _fail('A confirmed platform index receipt is required')
    if receipt.get('expected_current_version') != expected or receipt.get('operation_id') != candidate.get('index_operation_id'):
        _fail('Index CAS receipt does not match expected version/operation')
    pinned = _pinned(receipt)
    if pinned['sha256'] != _digest(_json_bytes(candidate)) or pinned['size_bytes'] != len(_json_bytes(candidate)):
        _fail('Index receipt does not match candidate bytes')
    if type(expected) is int and pinned['version'] <= expected:
        _fail('Platform did not advance the index version')
    if candidate.get('target_library_file_id') is not None and pinned['library_file_id'] != candidate['target_library_file_id']:
        _fail('Index receipt targets a different Library file')
    return pinned


def _commit_index(run_dir, receipts, *, expected_current_version, verification,
                 platform_receipt=None, previous=None, index_library_file_id=None,
                 packages_dir=None, external_dir=None):
    """Create candidate/CAS plan; only a matching platform receipt marks committed.

    This is an offline transaction journal, not a platform CAS implementation.
    The external connector must enforce expected_current_version atomically.
    On conflict or uncertainty the guard is retained and no latest is changed.
    """
    run_dir = _root(run_dir)
    journal = _load(run_dir / 'journal.json')
    if journal.get('status') == 'committed':
        if (run_dir.parent / 'guard.json').exists() and _load(run_dir.parent / 'guard.json').get('run_id') == run_dir.name:
            (run_dir.parent / 'guard.json').unlink()
        return _previous(_load(run_dir / 'committed-index.json'))
    if journal.get('status') == 'abandoned':
        _fail('Abandoned run cannot be committed or revived')
    if journal.get('status') not in ('prepared', 'uploads_uncertain', 'candidate_ready'):
        _fail('Run is not prepared for index commitment')
    _guard(run_dir.parent, run_dir.name)
    if not (expected_current_version == 'absent' or type(expected_current_version) is int and expected_current_version >= 0):
        _fail('Expected current version is required')
    legacy = _legacy(previous)
    previous = None if legacy else _previous(previous)
    if previous:
        target = previous['platform_receipt']['library_file_id']
        if index_library_file_id is not None and index_library_file_id != target:
            _fail('Index target changed from previous committed identity')
        index_library_file_id = target
        if previous['platform_receipt']['version'] != expected_current_version:
            _fail('Expected version differs from previous committed index')
    elif expected_current_version != 'absent' and legacy is None:
        _fail('Existing index requires its confirmed previous envelope')
    if legacy and (not isinstance(index_library_file_id, str) or not RUN_RE.fullmatch(index_library_file_id)):
        _fail('Legacy migration requires the actual existing index Library file ID')
    if previous is None and legacy is None and index_library_file_id is not None:
        _fail('First bootstrap must create a new index')
    manifest_raw = _read_file(run_dir / 'manifest.json')
    manifest = _manifest(json.loads(manifest_raw))
    lineage = legacy or (previous['candidate'].get('legacy_previous_index') if previous else None)
    if manifest.get('legacy_previous_index') != lineage:
        _fail('Legacy migration provenance must match prepared snapshot')
    if _digest(manifest_raw) != journal['snapshot_sha256']:
        _fail('Prepared snapshot was modified')
    if not isinstance(verification, dict) or verification.get('snapshot_sha256') != journal['snapshot_sha256'] or verification.get('complete_restore_bytes') is not True or verification.get('database') != manifest['database']:
        _fail('Matching complete byte/SQLite verification is required')
    # Reconstruct bytes ourselves; a caller-provided report is not verification.
    checked = verify(run_dir / 'manifest.json', packages_dir or run_dir, external_dir=external_dir)
    if any(verification.get(k) != checked[k] for k in ('snapshot_sha256', 'content_sha256', 'file_count', 'external_file_count', 'database', 'complete_restore_bytes', 'policy_verified', 'runner_verified')):
        _fail('Verification report differs from current reconstructed bytes')
    stable_keys = ('snapshot_sha256', 'content_sha256', 'file_count', 'external_file_count', 'database', 'complete_restore_bytes', 'policy_verified', 'runner_verified')
    verified_path = run_dir / 'verification.json'
    if verified_path.exists():
        stable = _load(verified_path)
        if any(stable.get(k) != checked[k] for k in stable_keys):
            _fail('Persisted verification differs from reconstructed snapshot')
        verification = stable
    else:
        verification = checked
        _save(verified_path, verification)
    plan = _load(run_dir / 'upload-plan.json')
    if _digest(_json_bytes(plan)) != journal.get('upload_plan_sha256'):
        _fail('Upload plan changed after preparation')
    if not isinstance(receipts, dict) or receipts.get('schema') != RECEIPT_SCHEMA or receipts.get('run_id') != journal['run_id'] or not isinstance(receipts.get('items'), list):
        _fail('Invalid upload receipt envelope')
    items = receipts['items']
    if len({x.get('filename') for x in items}) != len(items):
        _fail('Duplicate upload receipts')
    by_name = {x.get('filename'): x for x in items}
    planned = {x['filename']: x for x in plan['items']}
    if set(by_name) - set(planned):
        _fail('Receipt targets an unplanned upload')
    receipt_path = run_dir / 'upload-receipts.json'
    if receipt_path.exists():
        old_receipts = _load(receipt_path)
        for old in old_receipts['items']:
            name = old['filename']
            if name not in planned:
                _fail('Persisted receipt is outside upload plan')
            if old.get('status') == 'confirmed':
                new = by_name.get(name)
                if new is None:
                    by_name[name] = old
                elif new.get('status') != 'confirmed' or _pinned(old) != _pinned(new):
                    _fail('Confirmed upload identity cannot change or regress on retry')
    locators = {}
    merged = []
    for name, item in planned.items():
        receipt = by_name.get(name)
        if receipt is None:
            receipt = dict(item, status='not_reported')
        elif receipt.get('status') == 'confirmed':
            locators[name] = _validate_upload_receipt(receipt, item)
        else:
            if receipt.get('operation_id') != item['operation_id']:
                _fail('Uncertain receipt operation differs from plan')
            receipt = dict(item, status='unknown')
        merged.append(receipt)
    saved_receipts = {'schema': RECEIPT_SCHEMA, 'run_id': journal['run_id'], 'items': merged}
    _save(receipt_path, saved_receipts)
    if len(locators) != len(planned):
        journal['status'] = 'uploads_uncertain'
        _save(run_dir / 'journal.json', journal)
        _fail('Partial or unknown upload outcome recorded; reconcile by operation_id without reuploading')
    object_map = {}
    for h, obj in manifest['objects'].items():
        package = locators.get(obj['package']['filename'])
        if package is None:
            if previous is None or h not in previous['candidate']['objects']:
                _fail('Reused object lacks confirmed persistent dependency')
            old = previous['candidate']['objects'][h]
            if old != obj:
                _fail('Reused object changed from previous receipt')
            package = old['package']
        if any(package[field] != obj['package'][field] for field in ('filename', 'sha256', 'size_bytes')):
            _fail('Confirmed package conflicts with prepared object location')
        object_map[h] = {'size_bytes': obj['size_bytes'], 'package': package, 'member': obj['member']}
    if locators['manifest.json']['sha256'] != journal['snapshot_sha256']:
        _fail('Confirmed manifest differs from prepared snapshot')
    candidate = {'schema': INDEX_SCHEMA, 'identity': manifest['identity'], 'run_id': journal['run_id'],
                 'manifest': manifest, 'snapshot': locators['manifest.json'],
                 'snapshot_sha256': journal['snapshot_sha256'], 'objects': object_map,
                 'verified': verification, 'previous_version': expected_current_version,
                 'index_operation_id': journal['run_id'] + ':latest', 'legacy_previous_index': lineage,
                 'supporting_files': {n: locators[n] for n in ('privacy-audit.json', 'coverage.json', 'policy.json', 'recovery-runner.py')},
                 'target_library_file_id': index_library_file_id}
    candidate_path = run_dir / 'candidate-index.json'
    if candidate_path.exists() and _load(candidate_path) != candidate:
        _fail('Candidate changed after CAS preparation; guard retained')
    _save(candidate_path, candidate)
    _save(run_dir / 'index-update-plan.json', {'schema': INDEX_SCHEMA, 'operation_id': candidate['index_operation_id'],
          'expected_current_version': expected_current_version, 'target_library_file_id': index_library_file_id, 'sha256': _digest(_json_bytes(candidate)),
          'size_bytes': len(_json_bytes(candidate)), 'action': 'external_platform_atomic_compare_and_swap_required'})
    journal['status'] = 'candidate_ready'
    _save(run_dir / 'journal.json', journal)
    if platform_receipt is None:
        return {'status': 'candidate_ready', 'candidate_path': str(candidate_path), 'guard_retained': True}
    _validate_index_receipt(platform_receipt, candidate, expected_current_version)
    if 'download_path' not in platform_receipt:
        _fail('Final index confirmation requires downloaded candidate bytes')
    if 'download_path' in platform_receipt:
        downloaded = _read_file(Path(platform_receipt['download_path']))
        if downloaded != _json_bytes(candidate):
            _fail('Downloaded latest index does not match candidate')
    envelope = {'schema': INDEX_SCHEMA, 'status': 'committed', 'expected_current_version': expected_current_version,
                'candidate': candidate, 'platform_receipt': {k: v for k, v in platform_receipt.items() if k != 'download_path'}}
    _save(run_dir / 'platform-receipt.json', envelope['platform_receipt'])
    _save(run_dir / 'committed-index.json', envelope)
    journal['status'] = 'committed'
    _save(run_dir / 'journal.json', journal)
    (run_dir.parent / 'guard.json').unlink()
    return envelope




@contextlib.contextmanager
def _writer_lock(state):
    """OS-lifetime lock, separate from the durable cross-upload transaction guard."""
    try:
        import fcntl
    except ImportError as exc:
        raise BackupError('Safe writer locking requires a supported POSIX runtime') from exc
    state = _root(state)
    path = _no_links(state / '.writer.lock', exists=False)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            _fail('Writer lock is not a regular file')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise BackupError('Another preparation or commit process is active; retry after it stops') from exc
        yield
    finally:
        os.close(fd)


def prepare(source, data, state, **kwargs):
    """See _prepare. Public serialized entry point; no network operations."""
    source, data = _root(source), _root(data)
    state = _no_links(state, exists=False)
    roots = [source, data, state]
    if any(a == b or a in b.parents or b in a.parents for i, a in enumerate(roots) for b in roots[i + 1:]):
        _fail('SOURCE, DATA and state must be independent roots')
    db_path = _path(data, DB_PATH)
    if not db_path.is_file() or db_path.stat().st_size == 0:
        _fail('Database is missing or empty')
    db_info, _, _ = _sqlite_info(db_path)
    if not any(source.iterdir()):
        _fail('Source root is empty')
    legacy = _legacy(kwargs.get('previous'))
    if legacy:
        if not kwargs.get('bootstrap') or kwargs.get('identity') is None:
            _fail('migration_required: v10 requires explicit --bootstrap and --identity')
        _check_counts(legacy['content']['validation']['table_counts'], db_info['table_counts'])
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    with _writer_lock(state):
        return _prepare(source, data, state, **kwargs)


def commit_index(run_dir, receipts, **kwargs):
    """Serialized offline candidate/receipt transaction; see _commit_index."""
    run_dir = _root(run_dir)
    with _writer_lock(run_dir.parent):
        return _commit_index(run_dir, receipts, **kwargs)



def abandon_preparing(run_dir, *, expected_request_sha256, no_remote_actions, reason, evidence):
    """Record an explicitly abandoned, unpackaged preparation; retain all bytes.

    The caller must assert no remote actions occurred. Local state can prove only
    that this protocol has no package, upload plan or recorded remote action.
    A terminal abandoned run cannot subsequently prepare or commit.
    """
    run_dir = _root(run_dir)
    with _writer_lock(run_dir.parent):
        _hash(expected_request_sha256)
        if no_remote_actions is not True:
            _fail('Abandonment requires an explicit no-remote-actions assertion')
        for field, value, minimum in (('reason', reason, 8), ('evidence', evidence, 12)):
            if not isinstance(value, str) or not minimum <= len(value.strip()) <= 2000:
                _fail('Abandonment requires concrete nonempty ' + field)
        authorization = {'request_sha256': expected_request_sha256, 'no_remote_actions': True,
                         'reason': reason.strip(), 'evidence': evidence.strip()}
        journal_path = run_dir / 'journal.json'
        journal = _load(journal_path)
        if journal.get('run_id') != run_dir.name or journal.get('request_sha256') != expected_request_sha256:
            _fail('Abandonment run identity or expected request hash does not match')
        status = journal.get('status')
        if status not in ('preparing', 'abandoned'):
            _fail('Only an unpackaged preparing run can be abandoned')
        _assert_unpackaged_preparation(run_dir)
        guard_path = run_dir.parent / 'guard.json'
        guard = _load(guard_path) if guard_path.exists() else None
        if status == 'abandoned':
            recorded = journal.get('abandonment', {})
            if any(recorded.get(k) != v for k, v in authorization.items()):
                _fail('Run was already abandoned under different evidence')
            released = False
            # Also recover a crash after the terminal journal write but before unlink.
            if guard is not None and guard.get('run_id') == run_dir.name:
                guard_path.unlink()
                released = True
            return {'status': 'abandoned', 'run_id': run_dir.name,
                    'deduplicated': True, 'guard_released': released}
        if guard is None or guard.get('run_id') != run_dir.name:
            _fail('Abandonment requires this run to own the durable guard')
        journal['status'] = 'abandoned'
        journal['abandonment'] = dict(authorization, abandoned_at=_now())
        _save(journal_path, journal)
        # Never release a different guard even if an out-of-protocol writer changed it.
        if _load(guard_path).get('run_id') != run_dir.name:
            _fail('Guard ownership changed; abandoned evidence retained without releasing guard')
        guard_path.unlink()
        return {'status': 'abandoned', 'run_id': run_dir.name,
                'deduplicated': False, 'guard_released': True}


def hydrate_index(candidate, platform_receipt, *, output=None):
    """Rebuild local committed state from persistent candidate + trusted readback.

    The platform receipt must pin the currently observed index bytes and version.
    This establishes the current baseline, not independent historical CAS proof.
    It does not upload, commit or change any remote file.
    """
    if not isinstance(candidate, dict) or candidate.get('schema') != INDEX_SCHEMA:
        _fail('Invalid persisted index candidate')
    if not isinstance(platform_receipt, dict) or 'download_path' not in platform_receipt:
        _fail('Hydration needs actual downloaded latest-index bytes')
    if _read_file(Path(platform_receipt['download_path'])) != _json_bytes(candidate):
        _fail('Downloaded latest-index bytes differ from candidate')
    _validate_index_receipt(platform_receipt, candidate, candidate.get('previous_version'))
    envelope = {'schema': INDEX_SCHEMA, 'status': 'committed',
                'expected_current_version': candidate['previous_version'], 'candidate': candidate,
                'platform_receipt': {k: v for k, v in platform_receipt.items() if k != 'download_path'},
                'hydration_evidence': 'Trusted platform current-version readback; historical CAS not independently proven.'}
    _previous(envelope)
    if output is not None:
        _save(Path(output), envelope)
    return envelope


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('prepare', help='Freeze an offline private recovery point; never upload')
    for name in ('source', 'data', 'state'):
        p.add_argument('--' + name, required=True)
    p.add_argument('--policy')
    p.add_argument('--previous')
    p.add_argument('--run-id')
    p.add_argument('--bootstrap', action='store_true')
    p.add_argument('--identity')
    p.add_argument('--capture-mode', choices=CAPTURE_MODES, default='strict-live',
                   help='Explicit database-snapshot-cutoff permits live commits after the frozen SQLite view; default strict-live')
    p.add_argument('--review-refresh', help='Explicit preparing-only prior-hash and registered PNG review evidence JSON')
    for name in ('verify', 'restore'):
        p = commands.add_parser(name)
        p.add_argument('--snapshot', required=True)
        p.add_argument('--packages-dir', required=True)
        p.add_argument('--external-dir')
        if name == 'restore':
            p.add_argument('--destination', required=True)
        else:
            p.add_argument('--report', required=True)
    p = commands.add_parser('commit-index', help='Prepare CAS candidate, then accept confirmed platform receipt')
    for name in ('run-dir', 'receipts', 'expected-current-version', 'verification'):
        p.add_argument('--' + name, required=True)
    p.add_argument('--previous')
    p.add_argument('--platform-receipt')
    p.add_argument('--index-library-file-id')
    p.add_argument('--packages-dir')
    p.add_argument('--external-dir')
    p = commands.add_parser('abandon-preparing', help='Retain and close an explicitly failed, unpackaged preparation')
    p.add_argument('--run-dir', required=True)
    p.add_argument('--expected-request-sha256', required=True)
    p.add_argument('--no-remote-actions', action='store_true')
    p.add_argument('--reason', required=True)
    p.add_argument('--evidence', required=True)
    p = commands.add_parser('hydrate-index', help='Reconstruct local state from downloaded latest candidate and platform receipt')
    p.add_argument('--candidate', required=True)
    p.add_argument('--platform-receipt', required=True)
    p.add_argument('--output', required=True)
    args = vars(parser.parse_args(argv))
    command = args.pop('command')
    for key in ('policy', 'previous', 'receipts', 'verification', 'platform_receipt', 'candidate', 'review_refresh'):
        if key in args and args[key] is not None:
            args[key] = _load(args[key])
    if 'expected_current_version' in args and args['expected_current_version'].isdigit():
        args['expected_current_version'] = int(args['expected_current_version'])
    try:
        result = {'prepare': prepare, 'verify': verify, 'restore': restore, 'commit-index': commit_index, 'hydrate-index': hydrate_index, 'abandon-preparing': abandon_preparing}[command](**args)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (BackupError, OSError, sqlite3.Error, zipfile.BadZipFile, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({'status': 'blocked', 'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
