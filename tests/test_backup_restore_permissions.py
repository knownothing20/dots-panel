"""Synthetic restore privacy regression checks. No production paths or data."""
import os
from pathlib import Path
import stat
import unittest

from dots_panel import backup_protocol as bp
import test_backup_protocol as fixtures


class RestorePermissionTests(unittest.TestCase):
    setUp = fixtures.BackupProtocolTests.setUp
    bootstrap = fixtures.BackupProtocolTests.bootstrap

    def assert_private_directories(self, root):
        for directory in [root, *[p for p in root.rglob('*') if p.is_dir()]]:
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700, directory.name)

    def test_all_intermediate_restore_directories_are_private_under_normal_umask(self):
        nested = self.data / 'tasks/synthetic/inputs/nested/reference.txt'
        nested.parent.mkdir()
        nested.write_text('synthetic input')
        run = Path(self.bootstrap()['run_dir'])
        destination = self.root / 'restored-private'
        old = os.umask(0o022)
        try:
            result = bp.restore(run / 'manifest.json', run, destination)
        finally:
            os.umask(old)
        self.assertTrue(result['complete_restore_bytes'])
        self.assert_private_directories(destination)

    def test_external_dependency_parent_is_private_under_permissive_umask(self):
        raw = b'synthetic external reference'
        path = 'DATA/tasks/synthetic/inputs/external/nested/reference.txt'
        reference = {'file_id': 'file_synthetic', 'library_file_id': 'libfile_synthetic',
                     'version': 0, 'sha256': bp._digest(raw), 'size_bytes': len(raw),
                     'restore_path': path}
        external = self.root / 'external-bytes'
        local = external / path
        local.parent.mkdir(parents=True)
        local.write_bytes(raw)
        run = Path(self.bootstrap(policy={'external_files': [reference]})['run_dir'])
        destination = self.root / 'restored-external-private'
        old = os.umask(0o000)
        try:
            result = bp.restore(run / 'manifest.json', run, destination, external_dir=external)
        finally:
            os.umask(old)
        self.assertTrue(result['complete_restore_bytes'])
        self.assert_private_directories(destination)
        self.assertEqual((destination / path).read_bytes(), raw)
        self.assertEqual(stat.S_IMODE((destination / path).stat().st_mode), 0o600)

    def test_private_parent_helper_rejects_existing_unsafe_directory(self):
        destination = self.root / 'isolated'
        destination.mkdir(mode=0o700)
        unsafe = destination / 'DATA'
        unsafe.mkdir(mode=0o755)
        unsafe.chmod(0o755)
        with self.assertRaisesRegex(bp.BackupError, 'not private'):
            bp._restore_parent(destination, 'DATA/db/example.sqlite3')
        self.assertEqual(stat.S_IMODE(unsafe.stat().st_mode), 0o755)


if __name__ == '__main__':
    unittest.main()
