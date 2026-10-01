"""Independent, synthetic adversarial checks for the offline backup protocol."""
import hashlib
import io
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
import warnings
import zipfile

from dots_panel import backup_protocol as bp


class BackupProtocolIndependentReview(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='backup-review-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, self.data, self.state = [self.root / x for x in ('source', 'data', 'state')]
        self.source.mkdir()
        self.data.mkdir()
        (self.data / 'db').mkdir()
        (self.data / 'config').mkdir()
        (self.source / 'main.py').write_text('print("synthetic")\n')
        with sqlite3.connect(self.data / 'db/panel.sqlite3') as db:
            db.executescript('''
                CREATE TABLE tasks(id TEXT PRIMARY KEY);
                INSERT INTO tasks VALUES ('synthetic-task');
                CREATE TABLE artifacts(id TEXT PRIMARY KEY, task_id TEXT,
                    relative_path TEXT, sha256 TEXT, size INTEGER, library_id TEXT);
            ''')

    def prepare(self, run='first', **kwargs):
        return bp.prepare(self.source, self.data, self.state, run_id=run, **kwargs)

    def bootstrap(self):
        return self.prepare(bootstrap=True, identity='synthetic-installation')

    def commit(self, prepared, version=1):
        run = Path(prepared['run_dir'])
        verification = bp.verify(run / 'manifest.json', run)
        plan = json.loads((run / 'upload-plan.json').read_text())
        receipts = {'schema': bp.RECEIPT_SCHEMA, 'run_id': plan['run_id'], 'items': []}
        for i, item in enumerate(plan['items']):
            receipts['items'].append(dict(item, status='confirmed', version=version,
                file_id='file_synthetic_' + str(i), library_file_id='libfile_synthetic_' + str(i),
                download_path=str(run / item['filename'])))
        bp.commit_index(run, receipts, expected_current_version='absent', verification=verification)
        raw = (run / 'candidate-index.json').read_bytes()
        candidate = json.loads(raw)
        receipt = dict(status='committed', expected_current_version='absent',
                       operation_id=candidate['index_operation_id'],
                       file_id='file_synthetic_index', library_file_id='libfile_synthetic_index',
                       version=version, sha256=hashlib.sha256(raw).hexdigest(), size_bytes=len(raw),
                       download_path=str(run / 'candidate-index.json'))
        return bp.commit_index(run, receipts, expected_current_version='absent',
                               verification=verification, platform_receipt=receipt)

    def test_missing_database_does_not_initialize_or_create_state(self):
        (self.data / 'db/panel.sqlite3').unlink()
        with self.assertRaises(bp.BackupError):
            self.bootstrap()
        self.assertFalse(self.state.exists())
        self.assertFalse((self.data / bp.IDENTITY_PATH).exists())

    def test_empty_database_is_not_a_recovery_point(self):
        with sqlite3.connect(self.data / 'db/panel.sqlite3') as db:
            db.execute('DELETE FROM tasks')
        with self.assertRaises(bp.BackupError):
            self.bootstrap()
        self.assertFalse(self.state.exists())

    def test_selected_symlink_blocks_preparation(self):
        (self.source / 'linked.py').symlink_to(self.source / 'main.py')
        with self.assertRaises(bp.BackupError):
            self.bootstrap()

    def test_relative_path_traversal_is_rejected_before_extracting(self):
        result = self.bootstrap()
        run = Path(result['run_dir'])
        m = json.loads((run / 'manifest.json').read_text())
        m['files'][0]['path'] = 'DATA/../../escaped'
        m['content_sha256'] = bp._logical(m)
        forged = self.root / 'forged.json'
        forged.write_bytes(bp._json_bytes(m))
        with self.assertRaises(bp.BackupError):
            bp.verify(forged, run)
        self.assertFalse((self.root / 'escaped').exists())

    def test_restore_never_overwrites_existing_destination(self):
        result = self.bootstrap()
        run = Path(result['run_dir'])
        destination = self.root / 'restore'
        destination.mkdir()
        marker = destination / 'keep.txt'
        marker.write_text('must survive')
        with self.assertRaises(bp.BackupError):
            bp.restore(run / 'manifest.json', run, destination)
        self.assertEqual(marker.read_text(), 'must survive')

    def test_corrupted_package_is_not_verified(self):
        result = self.bootstrap()
        run = Path(result['run_dir'])
        package = next(run.glob('objects-*.zip'))
        package.write_bytes(package.read_bytes() + b'corruption')
        with self.assertRaises(bp.BackupError):
            bp.verify(run / 'manifest.json', run)

    def test_real_library_zero_version_is_supported(self):
        self.assertEqual(self.commit(self.bootstrap(), version=0)['status'], 'committed')

    def test_committed_same_run_retry_does_not_relock_state(self):
        self.commit(self.bootstrap())
        result = self.prepare(bootstrap=True, identity='synthetic-installation')
        self.assertEqual(result['status'], 'committed')
        self.assertFalse((self.state / 'guard.json').exists())

    def test_unchanged_same_run_retry_does_not_relock_state(self):
        previous = self.commit(self.bootstrap())
        result = self.prepare('unchanged', previous=previous)
        self.assertEqual(result['status'], 'skipped_unchanged')
        repeated = self.prepare('unchanged', previous=previous)
        self.assertEqual(repeated['status'], 'skipped_unchanged')
        self.assertFalse((self.state / 'guard.json').exists())

    def test_reused_object_requires_previous_package_bytes(self):
        previous = self.commit(self.bootstrap())
        (self.source / 'main.py').write_text('print("changed synthetic")\n')
        result = self.prepare('second', previous=previous)
        run = Path(result['run_dir'])
        with self.assertRaises(bp.BackupError):
            bp.verify(run / 'manifest.json', run)
        for package in (self.state / 'first').glob('objects-*.zip'):
            shutil.copyfile(package, run / package.name)
        self.assertTrue(bp.verify(run / 'manifest.json', run)['complete_restore_bytes'])

    def test_reset_identity_never_replaces_previous_point(self):
        previous = self.commit(self.bootstrap())
        marker = self.data / bp.IDENTITY_PATH
        marker.write_text(json.dumps({'schema': bp.SCHEMA, 'identity': 'different-installation'}))
        with self.assertRaises(bp.BackupError):
            self.prepare('after-reset', previous=previous)
        self.assertFalse((self.state / 'after-reset').exists())

    def test_unresolved_upload_blocks_new_run_and_retains_guard(self):
        result = self.bootstrap()
        run = Path(result['run_dir'])
        verification = bp.verify(run / 'manifest.json', run)
        plan = json.loads((run / 'upload-plan.json').read_text())
        receipts = {'schema': bp.RECEIPT_SCHEMA, 'run_id': 'first', 'items':
                    [dict(item, status='unknown') for item in plan['items']]}
        with self.assertRaises(bp.BackupError):
            bp.commit_index(run, receipts, expected_current_version='absent', verification=verification)
        self.assertTrue((self.state / 'guard.json').exists())
        with self.assertRaises(bp.BackupError):
            self.prepare('cannot-blindly-retry', bootstrap=True, identity='synthetic-installation')

    def test_same_run_cannot_silently_change_policy(self):
        self.bootstrap()
        with self.assertRaises(bp.BackupError):
            self.prepare(bootstrap=True, identity='synthetic-installation',
                         policy={'reviewed_binary_sha256': ['a' * 64]})

    def test_source_mass_loss_is_not_hidden_by_many_data_files(self):
        inputs = self.data / 'tasks/synthetic-task/inputs'
        inputs.mkdir(parents=True)
        for i in range(30):
            (inputs / ('input-' + str(i) + '.txt')).write_text('synthetic reference ' + str(i))
        for i in range(9):
            (self.source / ('module-' + str(i) + '.py')).write_text('VALUE = ' + str(i) + '\n')
        previous = self.commit(self.bootstrap())
        for file in self.source.glob('module-*.py'):
            file.unlink()
        with self.assertRaises(bp.BackupError):
            self.prepare('source-partially-reset', previous=previous)

    def test_duplicate_zip_member_is_rejected(self):
        buf = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(buf, 'w') as z:
                z.writestr('objects/' + 'a' * 64, b'first')
                z.writestr('objects/' + 'a' * 64, b'second')
        with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as z:
            with self.assertRaises(bp.BackupError):
                bp._zip_members(z)

    def test_zip_symlink_is_rejected(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            entry = zipfile.ZipInfo('objects/' + 'a' * 64)
            entry.external_attr = 0o120777 << 16
            z.writestr(entry, b'../../outside')
        with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as z:
            with self.assertRaises(bp.BackupError):
                bp._zip_members(z)


if __name__ == '__main__':
    unittest.main()
