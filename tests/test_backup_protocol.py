"""Synthetic backup protocol lifecycle and failure checks; never use real DATA."""
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zlib
import zipfile

from dots_panel import backup_protocol as bp


class BackupProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='backup-protocol-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source, self.data, self.state = [self.root / n for n in ('source', 'data', 'state')]
        self.source.mkdir()
        (self.data / 'db').mkdir(parents=True)
        (self.data / 'tasks/synthetic/inputs').mkdir(parents=True)
        (self.data / 'tasks/synthetic/outputs').mkdir()
        (self.data / 'tasks/synthetic/tmp').mkdir()
        (self.source / 'main.py').write_text('print("synthetic example")\n')
        with sqlite3.connect(self.data / bp.DB_PATH) as db:
            db.executescript('''
                CREATE TABLE tasks(id TEXT PRIMARY KEY);
                INSERT INTO tasks VALUES ('synthetic');
                CREATE TABLE runs(id TEXT PRIMARY KEY, task_id TEXT REFERENCES tasks(id));
                INSERT INTO runs VALUES ('example-run', 'synthetic');
                CREATE TABLE artifacts(id TEXT PRIMARY KEY, task_id TEXT REFERENCES tasks(id),
                    relative_path TEXT, size INTEGER, sha256 TEXT, library_id TEXT);
            ''')

    def bootstrap(self, **kwargs):
        return bp.prepare(self.source, self.data, self.state, run_id='run-first',
                          bootstrap=True, identity='synthetic-identity', **kwargs)

    def uploads(self, run):
        plan = bp._load(run / 'upload-plan.json')
        return {'schema': bp.RECEIPT_SCHEMA, 'run_id': run.name, 'items': [
            dict(item, status='confirmed', file_id='file_test_' + str(i),
                 library_file_id='libfile_test_' + str(i), version=0,
                 download_path=str(run / item['filename']))
            for i, item in enumerate(plan['items'])]}

    def commit(self, prepared, *, previous=None, version=0, index_id=None):
        run = Path(prepared['run_dir'])
        verification = bp.verify(run / 'manifest.json', run)
        receipts = self.uploads(run)
        expected = previous['platform_receipt']['version'] if previous else 'absent'
        kwargs = dict(expected_current_version=expected, verification=verification, previous=previous)
        if index_id:
            kwargs['index_library_file_id'] = index_id
        bp.commit_index(run, receipts, **kwargs)
        raw = (run / 'candidate-index.json').read_bytes()
        candidate = json.loads(raw)
        platform = {'status': 'committed', 'expected_current_version': expected,
                    'operation_id': candidate['index_operation_id'], 'file_id': 'file_index_test',
                    'library_file_id': index_id or 'libfile_index_test', 'version': version,
                    'sha256': bp._digest(raw), 'size_bytes': len(raw),
                    'download_path': str(run / 'candidate-index.json')}
        return bp.commit_index(run, receipts, platform_receipt=platform, **kwargs)

    def test_large_file_chunks_and_strict_package_limit_roundtrip(self):
        raw = ('0123456789' * 800).encode()
        (self.data / 'tasks/synthetic/inputs/large.txt').write_bytes(raw)
        prepared = self.bootstrap(chunk_bytes=1024, max_package_bytes=4096)
        run = Path(prepared['run_dir'])
        self.assertGreater(len(list(run.glob('*.zip'))), 1)
        self.assertTrue(all(p.stat().st_size < 4096 for p in run.glob('*.zip')))
        m = bp._load(run / 'manifest.json')
        f = next(x for x in m['files'] if x['path'].endswith('large.txt'))
        self.assertGreater(len(f['chunks']), 1)
        destination = self.root / 'restored'
        self.assertTrue(bp.restore(run / 'manifest.json', run, destination)['complete_restore_bytes'])
        self.assertEqual((destination / f['path']).read_bytes(), raw)

    def test_pinned_model_checkpoint_and_coverage_hints(self):
        raw = b'BLENDER\x00' + b'\x80' * 8_300_000
        path = 'DATA/tasks/synthetic/tmp/unfinished.blend'
        local = self.data / path[5:]
        local.write_bytes(raw)
        (local.parent / 'review').mkdir()
        (local.parent / 'render.log').write_text('excluded diagnostic output')
        policy = {'checkpoints': [{'path': path, 'size_bytes': len(raw), 'sha256': bp._digest(raw)}],
                  'reviewed_binary_sha256': [bp._digest(raw)]}
        result = self.bootstrap(policy=policy)
        run = Path(result['run_dir'])
        coverage = bp._load(run / 'coverage.json')
        self.assertEqual(coverage['temporary_directory_hints'][0]['directory_names'], ['review'])
        self.assertIn(path, [f['path'] for f in bp._load(run / 'manifest.json')['files']])
        self.assertTrue(bp.verify(run / 'manifest.json', run)['complete_restore_bytes'])
        self.assertNotIn('DATA/tasks/synthetic/tmp/render.log', [f['path'] for f in bp._load(run / 'manifest.json')['files']])

    def test_checkpoint_size_or_hash_mismatch_blocks(self):
        p = self.data / 'tasks/synthetic/tmp/model.txt'
        p.write_text('model')
        with self.assertRaisesRegex(bp.BackupError, 'checkpoint hash/size'):
            self.bootstrap(policy={'checkpoints': [{'path': 'DATA/tasks/synthetic/tmp/model.txt',
                                                   'size_bytes': 5, 'sha256': 'a' * 64}]})

    @staticmethod
    def png_bytes():
        def chunk(kind, data):
            return len(data).to_bytes(4, 'big') + kind + data + (zlib.crc32(kind + data) & 0xffffffff).to_bytes(4, 'big')
        header = (1).to_bytes(4, 'big') * 2 + bytes([8, 2, 0, 0, 0])
        return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) +
                chunk(b'IDAT', zlib.compress(b'\x00\x50\x80\x30')) + chunk(b'IEND', b''))

    def blocked_review_fixture(self, *, old_hashes=None, raw=None):
        raw = self.png_bytes() if raw is None else raw
        relative = 'tasks/synthetic/outputs/late-picture.png'
        (self.data / relative).write_bytes(raw)
        digest = bp._digest(raw)
        with sqlite3.connect(self.data / bp.DB_PATH) as db:
            db.execute('INSERT INTO artifacts VALUES (?,?,?,?,?,?)',
                       ('late-picture', 'synthetic', relative, len(raw), digest, None))
        old_hashes = [] if old_hashes is None else old_hashes
        old_policy = {'reviewed_binary_sha256': old_hashes}
        with self.assertRaisesRegex(bp.BackupError, 'Opaque binary'):
            self.bootstrap(policy=old_policy)
        policy = {'reviewed_binary_sha256': old_hashes + [digest]}
        refresh = {'no_remote_actions': True, 'previous_reviewed_binary_sha256': old_hashes,
                   'reviews': [{'sha256': digest, 'artifact_id': 'late-picture',
                       'path': 'DATA/' + relative,
                       'evidence': 'Synthetic PNG pixels inspected; no text or credentials; registered bytes checked.'}]}
        return self.state / 'run-first', policy, refresh

    def interrupted_preparation_fixture(self):
        original_scan = bp._scan
        def interrupted(raw, name, reviewed, **kwargs):
            if name == 'SOURCE/main.py':
                raise bp.BackupError('Synthetic interrupted preparation')
            return original_scan(raw, name, reviewed, **kwargs)
        with patch.object(bp, '_scan', side_effect=interrupted):
            with self.assertRaisesRegex(bp.BackupError, 'Synthetic interrupted'):
                self.bootstrap()
        run = self.state / 'run-first'
        options = {'expected_request_sha256': bp._load(run / 'journal.json')['request_sha256'],
                   'no_remote_actions': True, 'reason': 'Synthetic source checkpoint changed during preparation.',
                   'evidence': 'Test verified preparing status and absence of package, upload plan and remote receipts.'}
        return run, options

    def test_abandon_preparing_preserves_bytes_is_idempotent_and_cannot_revive(self):
        run, options = self.interrupted_preparation_fixture()
        objects = {p.name: p.read_bytes() for p in (run / 'objects').iterdir()}
        snapshot = (run / 'database.sqlite3').read_bytes()
        source_before = (self.source / 'main.py').read_bytes()
        result = bp.abandon_preparing(run, **options)
        self.assertEqual(result['status'], 'abandoned')
        self.assertTrue(result['guard_released'])
        self.assertFalse((self.state / 'guard.json').exists())
        self.assertEqual(bp._load(run / 'journal.json')['abandonment']['request_sha256'], options['expected_request_sha256'])
        self.assertEqual({p.name: p.read_bytes() for p in (run / 'objects').iterdir()}, objects)
        self.assertEqual((run / 'database.sqlite3').read_bytes(), snapshot)
        self.assertEqual((self.source / 'main.py').read_bytes(), source_before)
        journal = bp._load(run / 'journal.json')
        self.assertTrue(bp.abandon_preparing(run, **options)['deduplicated'])
        self.assertEqual(bp._load(run / 'journal.json'), journal)
        with self.assertRaisesRegex(bp.BackupError, 'Abandoned run'):
            self.bootstrap()
        with self.assertRaisesRegex(bp.BackupError, 'Abandoned run'):
            bp.commit_index(run, {}, expected_current_version='absent', verification={})
        self.assertFalse((self.state / 'guard.json').exists())
        fresh = bp.prepare(self.source, self.data, self.state, run_id='new-reviewed-run',
                           bootstrap=True, identity='synthetic-identity')
        self.assertEqual(fresh['status'], 'prepared')
        self.assertTrue(bp.abandon_preparing(run, **options)['deduplicated'])
        self.assertEqual(bp._load(self.state / 'guard.json')['run_id'], 'new-reviewed-run')

    def test_abandon_refuses_all_nonpreparing_states(self):
        run, options = self.interrupted_preparation_fixture()
        initial = bp._load(run / 'journal.json')
        for status in ('prepared', 'uploads_uncertain', 'candidate_ready', 'committed', 'skipped_unchanged'):
            with self.subTest(status=status):
                journal = dict(initial, status=status)
                bp._save(run / 'journal.json', journal)
                with self.assertRaisesRegex(bp.BackupError, 'Only an unpackaged preparing'):
                    bp.abandon_preparing(run, **options)
                self.assertEqual(bp._load(run / 'journal.json'), journal)
                self.assertEqual(bp._load(self.state / 'guard.json')['run_id'], run.name)

    def test_abandon_refuses_packaging_plans_and_remote_receipts(self):
        run, options = self.interrupted_preparation_fixture()
        for name in ('partial.zip', 'upload-plan.json', 'upload-receipts.json',
                     'candidate-index.json', 'index-update-plan.json', 'platform-receipt.json', 'committed-index.json'):
            marker = run / name
            marker.write_text('synthetic action evidence')
            with self.subTest(marker=name), self.assertRaisesRegex(bp.BackupError, 'remote-transaction evidence'):
                bp.abandon_preparing(run, **options)
            self.assertEqual(bp._load(run / 'journal.json')['status'], 'preparing')
            self.assertTrue((self.state / 'guard.json').exists())
            marker.unlink()

    def test_abandon_refuses_wrong_guard_request_and_missing_evidence(self):
        run, options = self.interrupted_preparation_fixture()
        initial = bp._load(run / 'journal.json')
        for change in ({'expected_request_sha256': 'f' * 64}, {'no_remote_actions': False},
                       {'reason': ''}, {'evidence': ''}):
            with self.subTest(change=next(iter(change))), self.assertRaises(bp.BackupError):
                bp.abandon_preparing(run, **dict(options, **change))
            self.assertEqual(bp._load(run / 'journal.json'), initial)
        bp._save(self.state / 'guard.json', {'run_id': 'different-run'})
        with self.assertRaisesRegex(bp.BackupError, 'own the durable guard'):
            bp.abandon_preparing(run, **options)
        self.assertEqual(bp._load(self.state / 'guard.json')['run_id'], 'different-run')
        (self.state / 'guard.json').unlink()
        with self.assertRaisesRegex(bp.BackupError, 'own the durable guard'):
            bp.abandon_preparing(run, **options)
        self.assertEqual(bp._load(run / 'journal.json'), initial)

    def test_abandon_cli_requires_explicit_no_remote_actions_flag(self):
        run, options = self.interrupted_preparation_fixture()
        missing_assertion = {k: v for k, v in options.items() if k != 'no_remote_actions'}
        with self.assertRaises(TypeError):
            bp.abandon_preparing(run, **missing_assertion)
        command = [sys.executable, bp.__file__, 'abandon-preparing', '--run-dir', str(run),
                   '--expected-request-sha256', options['expected_request_sha256'],
                   '--reason', options['reason'], '--evidence', options['evidence']]
        denied = subprocess.run(command, capture_output=True, text=True, env={})
        self.assertEqual(denied.returncode, 2)
        self.assertIn('no-remote-actions assertion', denied.stderr)
        self.assertEqual(bp._load(run / 'journal.json')['status'], 'preparing')
        accepted = subprocess.run(command + ['--no-remote-actions'], capture_output=True, text=True, env={})
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertEqual(json.loads(accepted.stdout)['status'], 'abandoned')

    def test_abandon_respects_active_writer_lock(self):
        run, options = self.interrupted_preparation_fixture()
        journal = bp._load(run / 'journal.json')
        with bp._writer_lock(self.state):
            with self.assertRaisesRegex(bp.BackupError, 'process is active'):
                bp.abandon_preparing(run, **options)
        self.assertEqual(bp._load(run / 'journal.json'), journal)
        self.assertEqual(bp._load(self.state / 'guard.json')['run_id'], run.name)

    def test_abandon_crash_window_releases_only_own_guard_and_evidence_is_immutable(self):
        run, options = self.interrupted_preparation_fixture()
        bp.abandon_preparing(run, **options)
        bp._save(self.state / 'guard.json', {'run_id': run.name})
        result = bp.abandon_preparing(run, **options)
        self.assertTrue(result['deduplicated'])
        self.assertTrue(result['guard_released'])
        self.assertFalse((self.state / 'guard.json').exists())
        journal = bp._load(run / 'journal.json')
        with self.assertRaisesRegex(bp.BackupError, 'different evidence'):
            bp.abandon_preparing(run, **dict(options, evidence='Different evidence cannot rewrite the retained history.'))
        self.assertEqual(bp._load(run / 'journal.json'), journal)

    def test_preparing_review_refresh_is_audited_and_repeated_authorization_is_idempotent(self):
        run, policy, refresh = self.blocked_review_fixture()
        before = bp._load(run / 'journal.json')['request_sha256']
        original_scan = bp._scan
        def interrupted(raw, name, reviewed, **kwargs):
            if name == 'SOURCE/main.py':
                raise bp.BackupError('Synthetic interruption after authorized refresh')
            return original_scan(raw, name, reviewed, **kwargs)
        with patch.object(bp, '_scan', side_effect=interrupted):
            for _ in range(2):
                with self.assertRaisesRegex(bp.BackupError, 'Synthetic interruption'):
                    self.bootstrap(policy=policy, review_refresh=refresh)
        journal = bp._load(run / 'journal.json')
        self.assertNotEqual(journal['request_sha256'], before)
        self.assertEqual(len(journal['review_refreshes']), 1)
        record = journal['review_refreshes'][0]
        self.assertEqual(record['request_before_sha256'], before)
        self.assertEqual(record['request_after_sha256'], journal['request_sha256'])
        self.assertEqual(record['reviews'][0]['checked_type']['type'], 'image/png')
        self.assertFalse((run / 'upload-plan.json').exists())
        self.assertFalse(list(run.glob('*.zip')))
        result = self.bootstrap(policy=policy, review_refresh=refresh)
        self.assertEqual(result['status'], 'prepared')
        self.assertTrue(bp.verify(run / 'manifest.json', run)['complete_restore_bytes'])

    def test_review_refresh_refuses_prepared_uncertain_and_committed_states(self):
        run, policy, refresh = self.blocked_review_fixture()
        self.bootstrap(policy=policy, review_refresh=refresh)
        for status in ('prepared', 'uploads_uncertain', 'committed'):
            with self.subTest(status=status):
                journal = bp._load(run / 'journal.json')
                journal['status'] = status
                bp._save(run / 'journal.json', journal)
                with self.assertRaisesRegex(bp.BackupError, 'only while preparing'):
                    self.bootstrap(policy=policy, review_refresh=refresh)

    def test_review_refresh_refuses_hash_removal_and_other_scope_changes(self):
        old = '1' * 64
        run, policy, refresh = self.blocked_review_fixture(old_hashes=[old])
        original = bp._load(run / 'journal.json')
        reduced = {'reviewed_binary_sha256': policy['reviewed_binary_sha256'][1:]}
        with self.assertRaisesRegex(bp.BackupError, 'only add'):
            self.bootstrap(policy=reduced, review_refresh=refresh)
        changed_scope = dict(policy, checkpoints=['SOURCE/main.py'])
        with self.assertRaisesRegex(bp.BackupError, 'locked request scope'):
            self.bootstrap(policy=changed_scope, review_refresh=refresh)
        self.assertEqual(bp._load(run / 'journal.json'), original)

    def test_review_refresh_refuses_unknown_hash_artifact_and_empty_evidence(self):
        run, policy, refresh = self.blocked_review_fixture()
        original = bp._load(run / 'journal.json')
        for changed in ({'sha256': 'f' * 64}, {'artifact_id': 'not-registered'}, {'evidence': ''}):
            with self.subTest(change=next(iter(changed))):
                modified = dict(refresh, reviews=[dict(refresh['reviews'][0], **changed)])
                modified_policy = {'reviewed_binary_sha256': [modified['reviews'][0]['sha256']]}
                with self.assertRaises(bp.BackupError):
                    self.bootstrap(policy=modified_policy, review_refresh=modified)
                self.assertEqual(bp._load(run / 'journal.json'), original)

    def test_review_refresh_refuses_existing_package_plan_or_remote_marker(self):
        run, policy, refresh = self.blocked_review_fixture()
        for name in ('earlier.zip', 'upload-plan.json', 'upload-receipts.json', 'platform-receipt.json'):
            marker = run / name
            marker.write_text('synthetic marker')
            with self.subTest(name=name), self.assertRaisesRegex(bp.BackupError, 'remote-transaction evidence'):
                self.bootstrap(policy=policy, review_refresh=refresh)
            marker.unlink()
        with self.assertRaisesRegex(bp.BackupError, 'any remote action'):
            self.bootstrap(policy=policy, review_refresh=dict(refresh, no_remote_actions=False))

    def test_review_refresh_refuses_other_binary_types_and_invalid_png(self):
        run, policy, refresh = self.blocked_review_fixture(raw=b'\x80unsupported binary format')
        with self.assertRaisesRegex(bp.BackupError, 'PNG artifacts only'):
            self.bootstrap(policy=policy, review_refresh=refresh)
        png = bytearray(self.png_bytes())
        png[-1] ^= 1
        with self.assertRaisesRegex(bp.BackupError, 'checksum'):
            bp._validate_review_png(bytes(png))

    def test_task_identifiers_and_adjacent_sqlite_fields_are_not_keys(self):
        identifier = 'task-' + 'A' * 48
        self.assertIsNone(bp.SECRET_RE.search(identifier.encode()))
        self.assertIsNone(bp.SECRET_RE.search(('lengthywordghp_' + 'B' * 30).encode()))
        with sqlite3.connect(self.data / bp.DB_PATH) as db:
            db.execute('CREATE TABLE adjacent_values(label TEXT, detail TEXT)')
            db.execute('INSERT INTO adjacent_values VALUES (?, ?)', ('task-', 'B' * 48))
            db.execute('INSERT INTO tasks VALUES (?)', (identifier,))
        self.assertIn(b'task-' + b'B' * 48, (self.data / bp.DB_PATH).read_bytes())
        run = Path(self.bootstrap()['run_dir'])
        self.assertTrue(bp.verify(run / 'manifest.json', run)['complete_restore_bytes'])

    def test_independent_secret_prefixes_still_block(self):
        for token in ('sk-' + 'A' * 40, 'sk-' + 'proj-' + 'A1b2' * 12, 'ghp_' + 'B' * 30):
            with self.subTest(prefix=token[:4]), self.assertRaisesRegex(bp.BackupError, 'Suspected secret'):
                bp._scan(('value: ' + token).encode(), 'synthetic.txt', set())

    def test_json_bearer_and_private_key_patterns_remain_blocked_without_leaking(self):
        examples = [
            json.dumps({'api_' + 'key': 'synthetic-' + 'fixture-value'}).encode(),
            ('Author' + 'ization: ' + 'Bea' + 'rer ' + 'synthetic-fixture-authorization').encode(),
            ('-----BEGIN ' + 'PRIVATE KEY-----').encode(),
        ]
        for raw in examples:
            with self.subTest(kind=examples.index(raw)):
                with self.assertRaisesRegex(bp.BackupError, 'Suspected secret') as raised:
                    bp._scan(raw, 'synthetic-credential-fixture.txt', set())
                self.assertNotIn(raw.decode(), str(raised.exception))

    def test_sqlite_secret_column_boundary_cannot_hide_behind_previous_column(self):
        token = 'sk-' + 'C' * 40
        with sqlite3.connect(self.data / bp.DB_PATH) as db:
            db.execute('CREATE TABLE adjacent_values(label TEXT, detail TEXT)')
            db.execute('INSERT INTO adjacent_values VALUES (?, ?)', ('ordinaryprefix', token))
        raw = (self.data / bp.DB_PATH).read_bytes()
        self.assertIn(b'ordinaryprefix' + token.encode(), raw)
        self.assertIsNone(bp.SECRET_RE.search(raw))
        with self.assertRaisesRegex(bp.BackupError, 'Suspected secret in SQLite value'):
            self.bootstrap()

    def test_secret_scan_blocks_instead_of_redacting(self):
        raw = ('sk-' + 'A' * 40).encode()
        (self.data / 'tasks/synthetic/inputs/credentials.txt').write_bytes(raw)
        with self.assertRaisesRegex(bp.BackupError, 'Suspected secret'):
            self.bootstrap()
        self.assertEqual((self.data / 'tasks/synthetic/inputs/credentials.txt').read_bytes(), raw)

    def test_unknown_binary_needs_hash_review(self):
        (self.data / 'tasks/synthetic/inputs/model.bin').write_bytes(b'\x80\x00opaque')
        with self.assertRaisesRegex(bp.BackupError, 'Opaque binary'):
            self.bootstrap()

    def test_registered_editable_backup_or_checkpoint_named_zip_is_included(self):
        files = {}
        for i, filename in enumerate(('editable-checkpoint.zip', 'backup-editable-project.zip')):
            relative = 'tasks/synthetic/outputs/' + filename
            path = self.data / relative
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('project/model.py', 'print("synthetic editable model")\n')
                archive.writestr('project/scene.json', '{"kind":"synthetic editable scene"}\n')
            raw = path.read_bytes()
            files[relative] = raw
            with sqlite3.connect(self.data / bp.DB_PATH) as db:
                db.execute('INSERT INTO artifacts VALUES (?,?,?,?,?,?)',
                    ('editable-project-' + str(i), 'synthetic', relative, len(raw), bp._digest(raw), None))
        run = Path(self.bootstrap()['run_dir'])
        included = {f['path'] for f in bp._load(run / 'manifest.json')['files']}
        self.assertTrue({'DATA/' + p for p in files} <= included)
        destination = self.root / 'editable-project-restored'
        self.assertTrue(bp.restore(run / 'manifest.json', run, destination)['complete_restore_bytes'])
        for relative, raw in files.items():
            self.assertEqual((destination / 'DATA' / relative).read_bytes(), raw)

    def test_proven_nested_backup_structure_requires_explicit_policy(self):
        for kind in ('database', 'v2-manifest'):
            archive_path = self.root / ('neutral-name-' + kind + '.zip')
            with zipfile.ZipFile(archive_path, 'w') as archive:
                if kind == 'database':
                    archive.writestr('DATA/db/panel.sqlite3', (self.data / bp.DB_PATH).read_bytes())
                else:
                    archive.writestr('manifest.json', json.dumps({'schema': bp.SCHEMA, 'files': [], 'objects': {}}))
            raw = archive_path.read_bytes()
            with self.subTest(kind=kind), self.assertRaisesRegex(bp.BackupError, 'explicit policy exclusion'):
                bp._scan(raw, archive_path.name, {bp._digest(raw)})

    def test_explicit_old_backup_policy_exclusion_is_not_nested_or_read(self):
        relative = 'tasks/synthetic/outputs/prior-point.zip'
        path = self.data / relative
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('DATA/db/panel.sqlite3', (self.data / bp.DB_PATH).read_bytes())
            archive.writestr('MANIFEST.json', '{"schema":"synthetic prior backup"}')
        raw = path.read_bytes()
        with sqlite3.connect(self.data / bp.DB_PATH) as db:
            db.execute('INSERT INTO artifacts VALUES (?,?,?,?,?,?)',
                ('prior-backup', 'synthetic', relative, len(raw), bp._digest(raw), None))
        original_read = bp._read_file
        def checked_read(candidate):
            self.assertNotEqual(Path(candidate), path, 'Explicitly excluded backup bytes must not be nested or read')
            return original_read(candidate)
        with patch.object(bp, '_read_file', side_effect=checked_read):
            run = Path(self.bootstrap(policy={'excluded_outputs': [relative]})['run_dir'])
        manifest = bp._load(run / 'manifest.json')
        self.assertNotIn('DATA/' + relative, {f['path'] for f in manifest['files']})
        self.assertIn({'path': 'DATA/' + relative, 'reason': 'explicit-policy-exclusion-not-restorable',
                       'artifact_id': 'prior-backup'}, manifest['privacy_exclusions'])
        self.assertTrue(bp.verify(run / 'manifest.json', run)['complete_restore_bytes'])
        self.assertIsNotNone(bp._excluded('tasks/synthetic/outputs/backups/old.zip'))
        self.assertIsNotNone(bp._excluded('tasks/synthetic/inputs/cache/scratch.zip'))

    def test_registered_artifact_mismatch_blocks(self):
        p = self.data / 'tasks/synthetic/outputs/report.txt'
        p.write_text('modified')
        with sqlite3.connect(self.data / bp.DB_PATH) as db:
            db.execute('INSERT INTO artifacts VALUES (?,?,?,?,?,?)',
                       ('artifact-test', 'synthetic', 'tasks/synthetic/outputs/report.txt', 4, bp._digest(b'orig'), None))
        with self.assertRaisesRegex(bp.BackupError, 'artifact content mismatch'):
            self.bootstrap()

    def test_external_refs_require_fixed_identity_and_actual_bytes(self):
        raw = b'fixed external media bytes'
        ref = {'file_id': 'file_media_test', 'library_file_id': 'libfile_media_test', 'version': 0,
               'sha256': bp._digest(raw), 'size_bytes': len(raw),
               'restore_path': 'DATA/tasks/synthetic/inputs/media.txt'}
        result = self.bootstrap(policy={'external_files': [ref]})
        run = Path(result['run_dir'])
        with self.assertRaisesRegex(bp.BackupError, 'External bytes missing'):
            bp.verify(run / 'manifest.json', run)
        external = self.root / 'external'
        p = external / ref['restore_path']
        p.parent.mkdir(parents=True)
        p.write_bytes(raw)
        self.assertTrue(bp.verify(run / 'manifest.json', run, external_dir=external)['complete_restore_bytes'])
        p.write_bytes(b'wrong')
        with self.assertRaisesRegex(bp.BackupError, 'Pinned external bytes mismatch'):
            bp.verify(run / 'manifest.json', run, external_dir=external)

    def test_external_unpinned_version_is_rejected(self):
        with self.assertRaises(bp.BackupError):
            self.bootstrap(policy={'external_files': [{'file_id': 'f', 'library_file_id': 'l',
                'version': 'latest', 'sha256': 'a' * 64, 'size_bytes': 1,
                'restore_path': 'DATA/tasks/synthetic/inputs/a'}]})

    def test_v10_schema_one_migration_retains_history(self):
        legacy = {'index_schema_version': 1, 'latest_available_checkpoint': {'synthetic': True},
                  'validation': {'table_counts': {'tasks': 1, 'runs': 1, 'artifacts': 0}},
                  'previous_checkpoints': [{'synthetic': 'retained'}]}
        result = self.bootstrap(previous=legacy)
        m = bp._load(Path(result['run_dir']) / 'manifest.json')
        self.assertEqual(m['legacy_previous_index']['content'], legacy)
        self.assertEqual(m['legacy_previous_index']['canonical_sha256'], bp._digest(bp._json_bytes(legacy)))
        self.assertIn('not proven', m['legacy_previous_index']['identity_scope'])
        self.assertTrue(all('file_id' not in o['package'] for o in m['objects'].values()))

    def test_v10_reduction_and_implicit_bootstrap_block(self):
        legacy = {'index_schema_version': 1, 'latest_available_checkpoint': {},
                  'validation': {'table_counts': {'tasks': 10, 'runs': 45}}}
        with self.assertRaisesRegex(bp.BackupError, 'Anomalous database reduction'):
            self.bootstrap(previous=legacy)
        self.assertFalse(self.state.exists())
        self.assertFalse((self.data / bp.IDENTITY_PATH).exists())
        with self.assertRaisesRegex(bp.BackupError, 'explicit --bootstrap'):
            bp.prepare(self.source, self.data, self.state, previous=legacy)

    def test_logical_deletion_does_not_restore_deleted_file(self):
        for i in range(10):
            (self.source / ('extra' + str(i) + '.txt')).write_text('small text ' + str(i))
        first = self.bootstrap()
        previous = self.commit(first)
        (self.source / 'extra0.txt').unlink()
        second = bp.prepare(self.source, self.data, self.state, previous=previous, run_id='second')
        run = Path(second['run_dir'])
        for z in Path(first['run_dir']).glob('*.zip'):
            shutil.copyfile(z, run / z.name)
        bp.restore(run / 'manifest.json', run, self.root / 'deleted-restore')
        self.assertFalse((self.root / 'deleted-restore/SOURCE/extra0.txt').exists())
        self.assertTrue((self.source / 'extra1.txt').exists())

    def test_download_readback_is_required_and_checked(self):
        result = self.bootstrap()
        run = Path(result['run_dir'])
        verification = bp.verify(run / 'manifest.json', run)
        receipts = self.uploads(run)
        del receipts['items'][0]['download_path']
        with self.assertRaisesRegex(bp.BackupError, 'requires downloaded bytes'):
            bp.commit_index(run, receipts, expected_current_version='absent', verification=verification)
        receipts = self.uploads(run)
        wrong = self.root / 'wrong-download'
        wrong.write_bytes(b'wrong')
        receipts['items'][0]['download_path'] = str(wrong)
        with self.assertRaisesRegex(bp.BackupError, 'Downloaded upload bytes'):
            bp.commit_index(run, receipts, expected_current_version='absent', verification=verification)

    def test_forged_verification_cannot_bypass_reconstruction(self):
        result = self.bootstrap()
        run = Path(result['run_dir'])
        report = bp.verify(run / 'manifest.json', run)
        next(run.glob('*.zip')).unlink()
        with self.assertRaises(bp.BackupError):
            bp.commit_index(run, self.uploads(run), expected_current_version='absent', verification=report)

    def test_hydrate_downloaded_candidate_and_continue_incremental(self):
        first = self.bootstrap()
        previous = self.commit(first)
        run = Path(first['run_dir'])
        receipt = dict(previous['platform_receipt'], download_path=str(run / 'candidate-index.json'))
        hydrated = bp.hydrate_index(previous['candidate'], receipt)
        (self.source / 'main.py').write_text('print("next version")\n')
        second = bp.prepare(self.source, self.data, self.state, previous=hydrated, run_id='second')
        second_run = Path(second['run_dir'])
        for z in run.glob('*.zip'):
            shutil.copyfile(z, second_run / z.name)
        committed = self.commit(second, previous=hydrated, version=1)
        self.assertEqual(committed['candidate']['target_library_file_id'], 'libfile_index_test')
        self.assertEqual(committed['platform_receipt']['version'], 1)

    def test_wrong_index_target_or_version_retains_guard(self):
        first = self.bootstrap()
        previous = self.commit(first)
        (self.source / 'main.py').write_text('print("changed synthetic example")\n')
        second = bp.prepare(self.source, self.data, self.state, previous=previous, run_id='second')
        run = Path(second['run_dir'])
        for z in Path(first['run_dir']).glob('*.zip'):
            shutil.copyfile(z, run / z.name)
        verification = bp.verify(run / 'manifest.json', run)
        receipts = self.uploads(run)
        with self.assertRaisesRegex(bp.BackupError, 'Index target changed'):
            bp.commit_index(run, receipts, expected_current_version=0, verification=verification,
                            previous=previous, index_library_file_id='wrong_library')
        bp.commit_index(run, receipts, expected_current_version=0, verification=verification, previous=previous)
        raw = (run / 'candidate-index.json').read_bytes()
        receipt = {'status': 'committed', 'expected_current_version': 0,
                   'operation_id': 'second:latest', 'file_id': 'file_other',
                   'library_file_id': 'wrong_library', 'version': 1,
                   'sha256': bp._digest(raw), 'size_bytes': len(raw),
                   'download_path': str(run / 'candidate-index.json')}
        with self.assertRaisesRegex(bp.BackupError, 'different Library file'):
            bp.commit_index(run, receipts, expected_current_version=0, verification=verification,
                            previous=previous, platform_receipt=receipt)
        self.assertTrue((self.state / 'guard.json').exists())

    def test_committed_crash_before_guard_cleanup_is_recoverable(self):
        first = self.bootstrap()
        previous = self.commit(first)
        bp._save(self.state / 'guard.json', {'run_id': 'run-first'})
        run = Path(first['run_dir'])
        again = bp.commit_index(run, {}, expected_current_version='absent', verification={})
        self.assertEqual(again, previous)
        self.assertFalse((self.state / 'guard.json').exists())
        bp._save(self.state / 'guard.json', {'run_id': 'another-run'})
        bp.commit_index(run, {}, expected_current_version='absent', verification={})
        self.assertEqual(bp._load(self.state / 'guard.json')['run_id'], 'another-run')

    def test_source_mutation_during_capture_blocks(self):
        original_scan = bp._scan
        changed = False
        def mutate(raw, name, reviewed, **kwargs):
            nonlocal changed
            original_scan(raw, name, reviewed, **kwargs)
            if name == 'SOURCE/main.py' and not changed:
                changed = True
                (self.source / 'main.py').write_text('changed during freeze')
        with patch.object(bp, '_scan', side_effect=mutate):
            with self.assertRaisesRegex(bp.BackupError, 'changed during capture'):
                self.bootstrap()

    def test_cutoff_continuous_live_progress_restores_only_frozen_records(self):
        database = self.data / bp.DB_PATH
        with sqlite3.connect(database) as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE progress(id INTEGER PRIMARY KEY, message TEXT)')
            db.execute("INSERT INTO progress VALUES (1, 'before cutoff')")
        for i in range(20):
            (self.source / ('part-%02d.txt' % i)).write_text('stable selected source\n')
        stopped, appended = threading.Event(), threading.Event()
        errors, writes, scan_counts = [], [], []
        def writer():
            try:
                with sqlite3.connect(database) as db:
                    late = 'tasks/synthetic/outputs/after-cutoff.txt'
                    raw = b'New artifact registered after the database snapshot.'
                    (self.data / late).write_bytes(raw)
                    db.execute('INSERT INTO artifacts VALUES (?,?,?,?,?,?)',
                               ('late-artifact', 'synthetic', late, len(raw), bp._digest(raw), None))
                    db.execute("INSERT INTO tasks VALUES ('late-task')")
                    (self.data / 'tasks/late-task/inputs').mkdir(parents=True)
                    (self.data / 'tasks/late-task/inputs/late.txt').write_text('late task input')
                    db.commit()
                    while not stopped.is_set():
                        db.execute('INSERT INTO progress(message) VALUES (?)', ('after cutoff',))
                        db.commit()
                        writes.append(len(writes) + 1)
                        appended.set()
                        stopped.wait(0.001)
            except Exception as exc:
                errors.append(exc)
                appended.set()
        worker = threading.Thread(target=writer, daemon=True)
        info, scan = bp._sqlite_info, bp._scan
        def start_after_backup(path):
            result = info(path)
            if path.name == 'database.sqlite3' and not worker.is_alive():
                worker.start()
                self.assertTrue(appended.wait(5), 'The concurrent writer did not start')
            return result
        def scan_with_live_writer(raw, name, reviewed, **kwargs):
            result = scan(raw, name, reviewed, **kwargs)
            if name.startswith('SOURCE/'):
                before = len(writes)
                deadline = time.monotonic() + 5
                while len(writes) == before and time.monotonic() < deadline and not errors:
                    time.sleep(0.001)
                self.assertGreater(len(writes), before, 'No live commit during selected-file scan')
                scan_counts.append(len(writes))
            return result
        try:
            with patch.object(bp, '_sqlite_info', side_effect=start_after_backup), \
                    patch.object(bp, '_scan', side_effect=scan_with_live_writer):
                result = self.bootstrap(capture_mode='database-snapshot-cutoff')
        finally:
            stopped.set()
            if worker.ident is not None:
                worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(result['status'], 'prepared')
        self.assertEqual(len(scan_counts), 21)
        self.assertGreaterEqual(len(writes), 21)
        run = Path(result['run_dir'])
        manifest = bp._load(run / 'manifest.json')
        capture = manifest['capture_details']
        self.assertEqual(capture['mode'], 'database-snapshot-cutoff')
        self.assertLessEqual(capture['database_backup_started_at'], capture['database_backup_completed_at'])
        self.assertEqual(capture['database_cutoff_upper_bound'], capture['database_backup_completed_at'])
        self.assertLessEqual(capture['database_backup_completed_at'], capture['files_capture_started_at'])
        self.assertLessEqual(capture['files_capture_started_at'], capture['files_capture_completed_at'])
        self.assertIn('upper bound', capture['cutoff_semantics'])
        self.assertEqual(manifest['database']['table_counts']['progress'], 1)
        self.assertFalse(any('after-cutoff.txt' in f['path'] or 'late-task' in f['path'] for f in manifest['files']))
        destination = self.root / 'cutoff-restored'
        self.assertTrue(bp.restore(run / 'manifest.json', run, destination)['complete_restore_bytes'])
        with sqlite3.connect(destination / 'DATA' / bp.DB_PATH) as restored:
            self.assertEqual(restored.execute('SELECT message FROM progress').fetchall(), [('before cutoff',)])
            self.assertEqual(restored.execute('SELECT count(*) FROM artifacts').fetchone()[0], 0)
            self.assertEqual(restored.execute('SELECT id FROM tasks').fetchall(), [('synthetic',)])
        with sqlite3.connect(database) as live:
            self.assertGreaterEqual(live.execute('SELECT count(*) FROM progress').fetchone()[0], 22)
            self.assertEqual(live.execute('SELECT count(*) FROM artifacts').fetchone()[0], 1)

    def mutate_during_file_capture(self, action, *, capture_mode='database-snapshot-cutoff'):
        scan = bp._scan
        changed = False
        def mutate(raw, name, reviewed, **kwargs):
            nonlocal changed
            scan(raw, name, reviewed, **kwargs)
            if name == 'SOURCE/main.py' and not changed:
                changed = True
                action()
        with patch.object(bp, '_scan', side_effect=mutate):
            return self.bootstrap(**({'capture_mode': capture_mode} if capture_mode is not None else {}))

    def test_strict_live_default_still_rejects_real_progress_append(self):
        def append():
            with sqlite3.connect(self.data / bp.DB_PATH) as db:
                db.execute("INSERT INTO runs VALUES ('late-progress', 'synthetic')")
        with self.assertRaisesRegex(bp.BackupError, 'Database changed during capture'):
            self.mutate_during_file_capture(append, capture_mode=None)
        self.assertEqual(bp._load(self.state / 'run-first/journal.json')['status'], 'preparing')
        self.assertFalse((self.state / 'run-first/upload-plan.json').exists())

    def test_cutoff_rejects_selected_source_content_change(self):
        with self.assertRaisesRegex(bp.BackupError, 'Selected file changed'):
            self.mutate_during_file_capture(lambda: (self.source / 'main.py').write_text('changed bytes'))

    def test_cutoff_rejects_selected_source_deletion(self):
        with self.assertRaisesRegex(bp.BackupError, 'missing'):
            self.mutate_during_file_capture(lambda: (self.source / 'main.py').unlink())

    def test_cutoff_rejects_config_content_change(self):
        config = self.data / 'config/ui.json'
        config.parent.mkdir()
        config.write_text('{"theme":"dark"}')
        with self.assertRaisesRegex(bp.BackupError, 'Selected file changed'):
            self.mutate_during_file_capture(lambda: config.write_text('{"theme":"light"}'))

    def test_cutoff_rejects_artifact_change_against_frozen_registration(self):
        path = 'tasks/synthetic/outputs/registered.txt'
        artifact = self.data / path
        artifact.write_bytes(b'registered bytes')
        with sqlite3.connect(self.data / bp.DB_PATH) as db:
            db.execute('INSERT INTO artifacts VALUES (?,?,?,?,?,?)',
                       ('registered', 'synthetic', path, artifact.stat().st_size, bp._digest(artifact.read_bytes()), None))
        def change_file_and_live_registration():
            artifact.write_bytes(b'new bytes with a new live registration')
            with sqlite3.connect(self.data / bp.DB_PATH) as db:
                db.execute('UPDATE artifacts SET size=?,sha256=? WHERE id=?',
                           (artifact.stat().st_size, bp._digest(artifact.read_bytes()), 'registered'))
        with self.assertRaisesRegex(bp.BackupError, 'Selected file changed'):
            self.mutate_during_file_capture(change_file_and_live_registration)

    def test_cutoff_rejects_database_replacement_even_when_bytes_match(self):
        def replace():
            path = self.data / bp.DB_PATH
            moved = path.with_name('original.sqlite3')
            path.rename(moved)
            shutil.copyfile(moved, path)
        with self.assertRaisesRegex(bp.BackupError, 'was replaced'):
            self.mutate_during_file_capture(replace)

    def test_cutoff_rejects_database_symlink(self):
        def replace():
            path = self.data / bp.DB_PATH
            moved = path.with_name('original.sqlite3')
            path.rename(moved)
            path.symlink_to(moved)
        with self.assertRaisesRegex(bp.BackupError, 'Symbolic links'):
            self.mutate_during_file_capture(replace)

    def test_cutoff_rejects_database_removal(self):
        with self.assertRaisesRegex(bp.BackupError, 'missing'):
            self.mutate_during_file_capture(lambda: (self.data / bp.DB_PATH).unlink())

    def test_cutoff_rejects_same_content_source_root_replacement(self):
        def replace():
            moved = self.root / 'original-source'
            self.source.rename(moved)
            shutil.copytree(moved, self.source)
        with self.assertRaisesRegex(bp.BackupError, 'was replaced'):
            self.mutate_during_file_capture(replace)

    def test_cutoff_rejects_same_content_data_root_replacement(self):
        def replace():
            moved = self.root / 'original-data'
            self.data.rename(moved)
            shutil.copytree(moved, self.data)
        with self.assertRaisesRegex(bp.BackupError, 'was replaced'):
            self.mutate_during_file_capture(replace)

    def test_cutoff_rejects_installation_identity_change(self):
        def change():
            (self.data / bp.IDENTITY_PATH).write_bytes(bp._json_bytes({'schema': bp.SCHEMA, 'identity': 'replacement'}))
        with self.assertRaisesRegex(bp.BackupError, 'Selected file changed|identity changed'):
            self.mutate_during_file_capture(change)

    def test_cutoff_rejects_same_content_identity_replacement(self):
        def replace():
            path = self.data / bp.IDENTITY_PATH
            saved = self.root / 'original-identity.json'
            path.rename(saved)
            shutil.copyfile(saved, path)
        with self.assertRaisesRegex(bp.BackupError, 'was replaced'):
            self.mutate_during_file_capture(replace)

    def test_cutoff_rechecks_identity_bytes_before_pinning_capture(self):
        identity = bp._identity
        def change_after_read(*args, **kwargs):
            result = identity(*args, **kwargs)
            (self.data / bp.IDENTITY_PATH).write_bytes(bp._json_bytes({'schema': bp.SCHEMA, 'identity': 'replacement'}))
            return result
        with patch.object(bp, '_identity', side_effect=change_after_read):
            with self.assertRaisesRegex(bp.BackupError, 'identity changed before capture'):
                self.bootstrap(capture_mode='database-snapshot-cutoff')

    def test_cutoff_source_database_connections_are_read_only_and_bytes_unchanged(self):
        connect, opened = sqlite3.connect, []
        source_database = self.data / bp.DB_PATH
        before = source_database.read_bytes()
        def track(database, *args, **kwargs):
            if str(source_database) in str(database):
                self.assertEqual(database, source_database.as_uri() + '?mode=ro')
                self.assertIs(kwargs.get('uri'), True)
                opened.append(database)
            return connect(database, *args, **kwargs)
        with patch.object(bp.sqlite3, 'connect', side_effect=track):
            self.bootstrap(capture_mode='database-snapshot-cutoff')
        self.assertGreaterEqual(len(opened), 3)
        self.assertEqual(source_database.read_bytes(), before)

    def test_cutoff_mode_is_locked_for_preparing_and_prepared_retries(self):
        with self.assertRaisesRegex(bp.BackupError, 'Selected file changed'):
            self.mutate_during_file_capture(lambda: (self.source / 'main.py').write_text('new source'))
        run = self.state / 'run-first'
        before = bp._load(run / 'journal.json')
        self.assertEqual(before['capture_mode'], 'database-snapshot-cutoff')
        with self.assertRaisesRegex(bp.BackupError, 'different capture mode'):
            self.bootstrap()
        self.assertEqual(bp._load(run / 'journal.json'), before)
        prepared = self.bootstrap(capture_mode='database-snapshot-cutoff')
        manifest = (run / 'manifest.json').read_bytes()
        self.assertEqual(prepared['status'], 'prepared')
        self.assertTrue(self.bootstrap(capture_mode='database-snapshot-cutoff')['resumed'])
        self.assertEqual((run / 'manifest.json').read_bytes(), manifest)
        with self.assertRaisesRegex(bp.BackupError, 'different capture mode'):
            self.bootstrap(capture_mode='strict-live')

    def test_old_strict_request_and_manifest_remain_compatible(self):
        prepared = self.bootstrap()
        run = Path(prepared['run_dir'])
        journal = bp._load(run / 'journal.json')
        journal.pop('capture_mode')
        bp._save(run / 'journal.json', journal)
        self.assertTrue(self.bootstrap()['resumed'])
        with self.assertRaisesRegex(bp.BackupError, 'different capture mode'):
            self.bootstrap(capture_mode='database-snapshot-cutoff')
        manifest = bp._load(run / 'manifest.json')
        manifest.pop('capture_details')
        manifest['capture'] = 'SQLite Connection.backup from mode=ro; files rehashed; data_version checked'
        manifest['content_sha256'] = bp._logical(manifest)
        bp._save(run / 'legacy-manifest.json', manifest)
        self.assertTrue(bp.restore(run / 'legacy-manifest.json', run, self.root / 'legacy-restored')['complete_restore_bytes'])

    def test_capture_mode_cli_is_explicit_validated_and_recorded(self):
        command = [sys.executable, bp.__file__, 'prepare', '--source', str(self.source),
                   '--data', str(self.data), '--state', str(self.state), '--bootstrap',
                   '--identity', 'synthetic-identity', '--run-id', 'cli-cutoff']
        invalid = subprocess.run(command + ['--capture-mode', 'unknown'], capture_output=True, text=True, env={})
        self.assertEqual(invalid.returncode, 2)
        self.assertFalse(self.state.exists())
        result = subprocess.run(command + ['--capture-mode', 'database-snapshot-cutoff'], capture_output=True, text=True, env={})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(bp._load(self.state / 'cli-cutoff/manifest.json')['capture_details']['mode'], 'database-snapshot-cutoff')

    def test_invalid_capture_mode_cannot_silently_relax_strict_capture(self):
        with self.assertRaisesRegex(bp.BackupError, 'Unknown capture mode'):
            self.bootstrap(capture_mode='ignore-database')
        self.assertFalse((self.state / 'guard.json').exists())

    def test_cutoff_capture_metadata_tampering_fails(self):
        run = Path(self.bootstrap(capture_mode='database-snapshot-cutoff')['run_dir'])
        manifest = bp._load(run / 'manifest.json')
        manifest['capture_details']['mode'] = 'strict-live'
        with self.assertRaisesRegex(bp.BackupError, 'Logical snapshot hash'):
            bp._manifest(manifest)
        manifest = bp._load(run / 'manifest.json')
        manifest['capture_details']['database_cutoff_upper_bound'] = '2099-01-01T00:00:00+00:00'
        with self.assertRaisesRegex(bp.BackupError, 'snapshot cutoff'):
            bp._manifest(manifest)

    def test_sqlite_foreign_key_failure_blocks(self):
        with sqlite3.connect(self.data / bp.DB_PATH) as db:
            db.execute("INSERT INTO runs VALUES ('invalid', 'missing-task')")
        with self.assertRaisesRegex(bp.BackupError, 'foreign key'):
            self.bootstrap()

    def test_standalone_runner_bootstraps_restore_without_source_or_pythonpath(self):
        first = self.bootstrap()
        run = Path(first['run_dir'])
        previous = self.commit(first)
        downloaded = self.root / 'fresh-downloads'
        downloaded.mkdir()
        for name in ('recovery-runner.py', 'manifest.json', 'policy.json'):
            shutil.copyfile(run / name, downloaded / name)
        for package in run.glob('*.zip'):
            shutil.copyfile(package, downloaded / package.name)
        self.source.rename(self.root / 'source-unavailable')
        destination = self.root / 'fresh-restored'
        result = subprocess.run([sys.executable, str(downloaded / 'recovery-runner.py'), 'restore',
            '--snapshot', str(downloaded / 'manifest.json'), '--packages-dir', str(downloaded),
            '--destination', str(destination)], cwd=downloaded, env={}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report['complete_restore_bytes'])
        self.assertTrue(report['runner_verified'])
        self.assertEqual((destination / 'SOURCE/main.py').read_text(), 'print("synthetic example")\n')
        runner_ref = previous['candidate']['supporting_files']['recovery-runner.py']
        self.assertEqual(runner_ref['sha256'], bp._digest((downloaded / 'recovery-runner.py').read_bytes()))
        self.assertTrue(runner_ref['download_verified'])

    def test_runner_missing_or_changed_blocks_verification(self):
        run = Path(self.bootstrap()['run_dir'])
        runner = run / 'recovery-runner.py'
        original = runner.read_bytes()
        runner.unlink()
        with self.assertRaises(bp.BackupError):
            bp.verify(run / 'manifest.json', run)
        runner.write_bytes(original + b'\n# changed')
        with self.assertRaisesRegex(bp.BackupError, 'runner hash/size'):
            bp.verify(run / 'manifest.json', run)

    def test_policy_is_pinned_uploaded_and_required_for_new_verification(self):
        first = self.bootstrap()
        run = Path(first['run_dir'])
        original = (run / 'policy.json').read_bytes()
        manifest = bp._load(run / 'manifest.json')
        self.assertEqual(manifest['policy']['sha256'], bp._digest(original))
        self.assertIn('excluded_inputs', json.loads(original))
        self.assertTrue(bp.verify(run / 'manifest.json', run)['policy_verified'])
        (run / 'policy.json').unlink()
        with self.assertRaises(bp.BackupError):
            bp.verify(run / 'manifest.json', run)
        (run / 'policy.json').write_bytes(b'{}')
        with self.assertRaisesRegex(bp.BackupError, 'policy hash/size'):
            bp.verify(run / 'manifest.json', run)
        (run / 'policy.json').write_bytes(original)
        previous = self.commit(first)
        ref = previous['candidate']['supporting_files']['policy.json']
        self.assertEqual(ref['sha256'], bp._digest(original))
        self.assertTrue(ref['download_verified'])

    def test_earlier_v2_bytes_can_restore_but_cannot_silently_continue(self):
        first = self.bootstrap()
        run = Path(first['run_dir'])
        previous = self.commit(first)
        legacy_manifest = bp._load(run / 'manifest.json')
        legacy_manifest.pop('policy')
        legacy_manifest['content_sha256'] = bp._logical(legacy_manifest)
        bp._save(run / 'earlier-v2.json', legacy_manifest)
        report = bp.verify(run / 'earlier-v2.json', run)
        self.assertTrue(report['complete_restore_bytes'])
        self.assertFalse(report['policy_verified'])
        previous['candidate']['manifest'] = legacy_manifest
        previous['candidate']['snapshot_sha256'] = bp._digest(bp._json_bytes(legacy_manifest))
        previous['candidate']['supporting_files'].pop('policy.json')
        candidate_raw = bp._json_bytes(previous['candidate'])
        previous['platform_receipt'].update(sha256=bp._digest(candidate_raw), size_bytes=len(candidate_raw))
        with self.assertRaisesRegex(bp.BackupError, 'migration_required'):
            bp.prepare(self.source, self.data, self.state, previous=previous, run_id='new')

    def test_exact_input_exclusion_never_reads_bytes_and_reports_gap(self):
        rel = 'tasks/synthetic/inputs/unneeded-reference.txt'
        sensitive = self.data / rel
        sensitive.write_text('sk-' + 'X' * 40)
        original_read = bp._read_file
        def observed_read(path):
            self.assertNotEqual(Path(path), sensitive, 'Excluded input bytes must not be read')
            return original_read(path)
        with patch.object(bp, '_read_file', side_effect=observed_read):
            first = self.bootstrap(policy={'excluded_inputs': [rel]})
        run = Path(first['run_dir'])
        audit = bp._load(run / 'privacy-audit.json')
        self.assertIn({'path': 'DATA/' + rel, 'reason': 'explicit-input-policy-exclusion-not-restorable', 'currently_missing': False}, audit['excluded'])
        self.assertNotIn('DATA/' + rel, audit['included'])
        self.assertEqual(bp._load(run / 'coverage.json')['not_restorable_input_exclusions'], [rel])
        self.assertTrue(bp.verify(run / 'manifest.json', run)['policy_verified'])
        self.assertEqual(bp._load(run / 'policy.json')['excluded_inputs'], [rel])

    def test_restored_excluded_input_can_be_missing_and_unchanged_prepare_skips(self):
        rel = 'tasks/synthetic/inputs/reference-video.bin'
        excluded = self.data / rel
        excluded.write_bytes(b'\x80intentionally omitted reference media')
        policy = {'excluded_inputs': [rel]}
        first = self.bootstrap(policy=policy)
        previous = self.commit(first)
        run = Path(first['run_dir'])
        restored = self.root / 'restored-without-excluded-media'
        bp.restore(run / 'manifest.json', run, restored)
        self.assertFalse((restored / 'DATA' / rel).exists())
        result = bp.prepare(restored / 'SOURCE', restored / 'DATA', self.root / 'restored-state',
                            policy=policy, previous=previous, run_id='restored-unchanged')
        self.assertEqual(result['status'], 'skipped_unchanged')
        audit = bp._load(Path(result['run_dir']) / 'privacy-audit.json')
        self.assertIn({'path': 'DATA/' + rel, 'reason': 'explicit-input-policy-exclusion-not-restorable',
                       'currently_missing': True}, audit['excluded'])
        self.assertFalse((restored / 'DATA' / rel).exists())
        self.assertFalse(list(Path(result['run_dir']).glob('*.zip')))

    def test_missing_excluded_input_is_audited_in_prepared_snapshot(self):
        rel = 'tasks/synthetic/inputs/missing/reference.mp4'
        run = Path(self.bootstrap(policy={'excluded_inputs': [rel]})['run_dir'])
        item = {'path': 'DATA/' + rel, 'reason': 'explicit-input-policy-exclusion-not-restorable',
                'currently_missing': True}
        self.assertIn(item, bp._load(run / 'privacy-audit.json')['excluded'])
        self.assertIn(item, bp._load(run / 'manifest.json')['privacy_exclusions'])
        self.assertFalse((self.data / rel).exists())
        self.assertTrue(bp.verify(run / 'manifest.json', run)['complete_restore_bytes'])

    def test_missing_exclusion_still_rejects_dangling_symlink_parent(self):
        inputs = self.data / 'tasks/synthetic/inputs'
        inputs.rmdir()
        inputs.symlink_to(self.root / 'missing-outside-directory', target_is_directory=True)
        with self.assertRaisesRegex(bp.BackupError, 'Symbolic links'):
            self.bootstrap(policy={'excluded_inputs': ['tasks/synthetic/inputs/absent.mp4']})

    def test_input_exclusions_reject_glob_directory_and_unknown_task(self):
        for path in ('tasks/synthetic/inputs/*.txt', 'tasks/synthetic/outputs/report.txt', '../escape'):
            with self.subTest(path=path), self.assertRaises(bp.BackupError):
                bp._policy({'excluded_inputs': [path]})
        (self.data / 'tasks/synthetic/inputs/subdirectory').mkdir()
        with self.assertRaisesRegex(bp.BackupError, 'existing selected regular file'):
            self.bootstrap(policy={'excluded_inputs': ['tasks/synthetic/inputs/subdirectory']})

    def test_partial_upload_receipts_survive_and_confirmed_cannot_regress(self):
        run = Path(self.bootstrap()['run_dir'])
        verification = bp.verify(run / 'manifest.json', run)
        full = self.uploads(run)
        partial = dict(full, items=full['items'][:1])
        with self.assertRaisesRegex(bp.BackupError, 'Partial or unknown'):
            bp.commit_index(run, partial, expected_current_version='absent', verification=verification)
        saved = bp._load(run / 'upload-receipts.json')
        self.assertEqual(saved['items'][0]['status'], 'confirmed')
        self.assertTrue(all(x['status'] == 'not_reported' for x in saved['items'][1:]))
        downgraded = dict(full, items=[dict(x, status='unknown') for x in full['items']])
        with self.assertRaisesRegex(bp.BackupError, 'cannot change or regress'):
            bp.commit_index(run, downgraded, expected_current_version='absent', verification=verification)
        self.assertEqual(bp._load(run / 'upload-receipts.json'), saved)
        # Reconcile remaining uploads; no need to resubmit the already confirmed item.
        remaining = dict(full, items=full['items'][1:])
        result = bp.commit_index(run, remaining, expected_current_version='absent', verification=verification)
        self.assertEqual(result['status'], 'candidate_ready')
        # A newly generated verification timestamp must not destabilize the candidate.
        another_report = bp.verify(run / 'manifest.json', run)
        self.assertEqual(bp.commit_index(run, full, expected_current_version='absent',
                                       verification=another_report)['status'], 'candidate_ready')

    def test_writer_lock_blocks_same_run_prepare_and_commit(self):
        result = self.bootstrap()
        run = Path(result['run_dir'])
        before = (run / 'manifest.json').read_bytes()
        with bp._writer_lock(self.state):
            with self.assertRaisesRegex(bp.BackupError, 'process is active'):
                self.bootstrap()
            with self.assertRaisesRegex(bp.BackupError, 'process is active'):
                bp.commit_index(run, {}, expected_current_version='absent', verification={})
        self.assertEqual((run / 'manifest.json').read_bytes(), before)

    def test_credential_filenames_are_audited_and_excluded(self):
        config = self.data / 'config'
        config.mkdir()
        (config / 'credentials.json').write_text('{"ordinary": "must not back up"}')
        run = Path(self.bootstrap()['run_dir'])
        audit = bp._load(run / 'privacy-audit.json')
        self.assertIn({'path': 'DATA/config/credentials.json', 'reason': 'credential-file-name'}, audit['excluded'])
        self.assertNotIn('DATA/config/credentials.json', audit['included'])
        names = {x['filename'] for x in bp._load(run / 'upload-plan.json')['items']}
        self.assertTrue({'privacy-audit.json', 'coverage.json'} <= names)

    def test_legacy_commit_locks_index_target_and_preserves_lineage(self):
        legacy = {'index_schema_version': 1, 'latest_available_checkpoint': {'synthetic': True},
                  'validation': {'table_counts': {'tasks': 1, 'runs': 1, 'artifacts': 0}}}
        first = self.bootstrap(previous=legacy)
        run = Path(first['run_dir'])
        verification = bp.verify(run / 'manifest.json', run)
        uploads = self.uploads(run)
        options = {'expected_current_version': 10, 'verification': verification,
                   'previous': legacy, 'index_library_file_id': 'libfile_index_test'}
        bp.commit_index(run, uploads, **options)
        raw = (run / 'candidate-index.json').read_bytes()
        candidate = json.loads(raw)
        receipt = {'status': 'committed', 'expected_current_version': 10,
                   'operation_id': 'run-first:latest', 'file_id': 'file_index_test',
                   'library_file_id': 'libfile_index_test', 'version': 11,
                   'sha256': bp._digest(raw), 'size_bytes': len(raw),
                   'download_path': str(run / 'candidate-index.json')}
        previous = bp.commit_index(run, uploads, platform_receipt=receipt, **options)
        (self.source / 'main.py').write_text('print("new synthetic example")\n')
        second = bp.prepare(self.source, self.data, self.state, previous=previous, run_id='second')
        next_run = Path(second['run_dir'])
        for z in run.glob('*.zip'):
            shutil.copyfile(z, next_run / z.name)
        final = self.commit(second, previous=previous, version=12)
        self.assertEqual(final['candidate']['legacy_previous_index']['content'], legacy)

    def test_runtime_pid_is_not_restorable_even_with_forged_manifest(self):
        run = Path(self.bootstrap()['run_dir'])
        m = bp._load(run / 'manifest.json')
        m['files'][-1]['path'] = 'DATA/run/server.json'
        m['content_sha256'] = bp._logical(m)
        bp._save(run / 'forged.json', m)
        with self.assertRaisesRegex(bp.BackupError, 'forbidden runtime'):
            bp.verify(run / 'forged.json', run)


if __name__ == '__main__':
    unittest.main()
