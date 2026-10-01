"""Synthetic private read-only backup status. No live Library or production DATA."""
import copy
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from dots_panel import backup_status as status, backup_protocol as bp
import test_backup_protocol as fixtures


class BackupStatusTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.BackupProtocolTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.data, self.state, self.source = self.fixture.data, self.fixture.state, self.fixture.source
        for path in [self.data, *self.data.rglob('*')]:
            if path.is_dir():
                path.chmod(0o700)
        self.prepared = self.fixture.bootstrap()
        self.envelope = self.fixture.commit(self.prepared, version=1)
        self.write(self.state/'latest-committed.json', self.envelope)
        self.config = {'schema': status.CONFIG_SCHEMA, 'state_dir': str(self.state),
                       'destination_label': 'Synthetic private backups', 'destination_path': '/Synthetic private backups',
                       'index_library_file_id': 'libfile_index_test', 'stale_after_seconds': 7200}
        self.write(self.data/'config/backup-status.json', self.config)
        # Match the microsecond precision of the serialized observation timestamp.
        self.now = datetime.fromtimestamp(time.time() + 2, timezone.utc).timestamp()

    def write(self, path, value):
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        path.chmod(0o600)

    def load(self, **kwargs):
        return status.load(self.data, source=self.source, now=kwargs.get('now', self.now))

    def observe(self, result='failed', checked_at=None):
        value = {'schema': status.OBSERVATION_SCHEMA, 'checked_at': checked_at or datetime.fromtimestamp(self.now, timezone.utc).isoformat(),
                 'result': result, 'stage': 'prepare', 'error_type': 'source_busy' if result == 'failed' else None,
                 'recovery_point_sha256': self.envelope['candidate']['snapshot_sha256']}
        self.write(self.state/'operations/backup-observation.json', value)
        return value

    def test_verified_history_with_counts_not_remote_live(self):
        value = self.load()
        self.assertEqual(value['status'], 'verified')
        self.assertFalse(value['remote_live'])
        self.assertEqual(value['last_verified']['index_version'], 1)
        self.assertGreater(value['last_verified']['file_count'], 0)
        self.assertEqual(value['last_verified']['evidence'], 'local_committed_receipt')
        self.assertIsNone(value['last_attempt'])
        self.assertNotIn('manifest', json.dumps(value))
        self.assertNotIn('operation_id', json.dumps(value))

    def test_missing_config_is_unknown_and_read_only(self):
        (self.data/'config/backup-status.json').unlink()
        self.assertEqual(self.load()['status'], 'unconfigured')
        self.assertFalse((self.data/'config/backup-status.json').exists())

    def test_missing_data_never_created(self):
        missing = self.fixture.root/'missing'
        self.assertEqual(status.load(missing)['status'], 'unavailable')
        self.assertFalse(missing.exists())

    def test_missing_state_does_not_fall_back(self):
        self.config['state_dir'] = str(self.fixture.root/'missing-state')
        self.write(self.data/'config/backup-status.json', self.config)
        self.assertEqual(self.load()['status'], 'unavailable')
        self.assertFalse(Path(self.config['state_dir']).exists())

    def test_no_envelope_cannot_promote_observation_to_success(self):
        (self.state/'latest-committed.json').unlink()
        self.observe('committed')
        self.assertEqual(self.load()['status'], 'unverified')
        self.assertIsNone(self.load()['last_verified'])

    def test_failed_observation_retains_last_good_point(self):
        self.observe()
        value = self.load()
        self.assertEqual(value['status'], 'failed')
        self.assertEqual(value['last_verified']['index_version'], 1)
        self.assertEqual(value['last_attempt']['error_type'], 'source_busy')

    def test_stale_without_claiming_failure(self):
        value = self.load(now=self.now+7201)
        self.assertEqual(value['status'], 'stale')
        self.assertIsNotNone(value['last_verified'])
        self.assertNotEqual(value['status'], 'failed')

    def test_hydrated_is_explicit_not_historical_cas_proof(self):
        self.envelope['hydration_evidence'] = 'Synthetic current readback only'
        self.write(self.state/'latest-committed.json', self.envelope)
        value = self.load()
        self.assertTrue(value['last_verified']['hydrated'])
        self.assertIn('not independently proven', status.presentation(value, 'en')['note'])

    def test_older_failure_does_not_override_newer_verification(self):
        self.observe(checked_at='2000-01-01T00:00:00Z')
        self.assertEqual(self.load()['status'], 'verified')

    def test_pending_is_observation_not_live(self):
        self.observe('running')
        self.assertEqual(self.load()['status'], 'pending')
        self.assertFalse(self.load()['remote_live'])

    def test_noncommitted_and_candidate_only_rejected(self):
        for value in [self.envelope['candidate'], {**self.envelope, 'status': 'candidate_ready'}, {**self.envelope, 'status': 'prepared'}]:
            with self.subTest(value=value.get('status')):
                self.write(self.state/'latest-committed.json', value)
                self.assertIsNone(self.load()['last_verified'])

    def test_receipt_tamper_rejected(self):
        self.envelope['platform_receipt']['sha256'] = '0'*64
        self.write(self.state/'latest-committed.json', self.envelope)
        self.assertIsNone(self.load()['last_verified'])

    def test_receipt_and_restore_verification_both_required(self):
        self.envelope['candidate']['verified']['complete_restore_bytes'] = False
        candidate = bp._json_bytes(self.envelope['candidate'])
        self.envelope['platform_receipt'].update(sha256=bp._digest(candidate), size_bytes=len(candidate))
        self.write(self.state/'latest-committed.json', self.envelope)
        self.assertIsNone(self.load()['last_verified'])

    def test_wrong_installation_identity_rejected(self):
        self.write(self.data/'config/backup-identity.json', {'schema':bp.SCHEMA,'identity':'other-installation'})
        self.assertIsNone(self.load()['last_verified'])

    def test_wrong_pinned_index_rejected(self):
        self.config['index_library_file_id'] = 'libfile_other'
        self.write(self.data/'config/backup-status.json', self.config)
        self.assertIsNone(self.load()['last_verified'])

    def test_invalid_observation_does_not_hide_verified_history(self):
        value = self.observe()
        value.update(error_type='secret token in arbitrary message', checked_at='2099-01-01T00:00:00Z')
        self.write(self.state/'operations/backup-observation.json', value)
        result = self.load()
        self.assertEqual(result['observation_state'], 'invalid')
        self.assertEqual(result['status'], 'verified')
        self.assertNotIn('secret token', json.dumps(result))

    def test_extra_config_fields_rejected(self):
        self.config['download_path'] = '/unrelated/private/file'
        self.write(self.data/'config/backup-status.json', self.config)
        self.assertEqual(self.load()['reason'], 'invalid_config')

    def test_symlink_config_rejected(self):
        target = self.fixture.root/'config-outside'
        path = self.data/'config/backup-status.json'
        path.rename(target)
        path.symlink_to(target)
        self.assertIsNone(self.load()['last_verified'])

    def test_symlink_state_ancestor_rejected(self):
        link = self.fixture.root/'linked'
        link.symlink_to(self.fixture.root, target_is_directory=True)
        self.config['state_dir'] = str(link/'state')
        self.write(self.data/'config/backup-status.json', self.config)
        self.assertEqual(self.load()['status'], 'unavailable')

    def test_symlink_committed_file_rejected(self):
        target = self.fixture.root/'outside-envelope'
        path = self.state/'latest-committed.json'
        path.rename(target)
        path.symlink_to(target)
        self.assertIsNone(self.load()['last_verified'])

    def test_unsafe_permissions_rejected(self):
        (self.state/'latest-committed.json').chmod(0o644)
        self.assertIsNone(self.load()['last_verified'])

    def test_nested_state_rejected(self):
        for root in (self.data, self.source):
            self.config['state_dir'] = str(root/'nested-state')
            self.write(self.data/'config/backup-status.json', self.config)
            self.assertEqual(self.load()['reason'], 'invalid_config')

    def test_duplicate_json_keys_rejected(self):
        path = self.data/'config/backup-status.json'
        path.write_text('{"schema":"first","schema":"second"}')
        self.assertIsNone(self.load()['last_verified'])

    def test_oversized_envelope_rejected_without_full_read(self):
        with patch.object(status, 'MAX_ENVELOPE', 10):
            self.assertIsNone(self.load()['last_verified'])

    def test_fifo_rejected_without_block(self):
        path = self.state/'latest-committed.json'
        path.unlink()
        os.mkfifo(path, 0o600)
        self.assertIsNone(self.load()['last_verified'])

    def test_load_no_network_no_writes(self):
        files = list(self.fixture.root.rglob('*'))
        before = {str(p):(p.stat().st_size,p.stat().st_mtime_ns) for p in files if p.is_file()}
        with patch('urllib.request.urlopen', side_effect=AssertionError('No network')), patch.object(bp, 'prepare', side_effect=AssertionError('No prepare')), patch.object(bp, 'restore', side_effect=AssertionError('No restore')):
            self.assertEqual(self.load()['status'], 'verified')
        after = {str(p):(p.stat().st_size,p.stat().st_mtime_ns) for p in self.fixture.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_bilingual_timezone_display_and_boundaries(self):
        value = self.load()
        for lang in ('zh','en'):
            view = status.presentation(value, lang, lambda epoch: 'LOCAL_TIME')
            self.assertIn('LOCAL_TIME',view['compact'])
            self.assertIn('Last verified snapshot: ' if lang == 'en' else '最后核验快照：', view['compact'])
            self.assertIn('/Synthetic private backups',str(view['rows']))
            self.assertNotIn('restore_now',str(view))
        self.assertIn('not platform sessions', str(status.presentation(value, 'en')['rows']))

    def watch(self, state='checked', last_success=None, **changes):
        stamp = datetime.fromtimestamp(self.now, timezone.utc).isoformat()
        value = {'schema': status.WATCH_SCHEMA, 'status': state, 'checked_at': stamp,
                 'last_success_at': stamp if state == 'checked' else last_success,
                 'error_type': None if state == 'checked' else 'data_unavailable'}
        value.update(changes)
        self.write(self.state/'operations/task-watch-observation.json', value)
        return value

    def test_missing_task_watch_is_unverified_not_backup_success(self):
        value = self.load()
        self.assertEqual(value['status'], 'verified')
        self.assertEqual(value['task_watch']['status'], 'unverified')
        self.assertIsNone(value['task_watch']['last_success_at'])

    def test_task_watch_success_uses_real_recorded_time_not_ui_refresh(self):
        self.watch()
        value = self.load(now=self.now+60)['task_watch']
        self.assertEqual(value['status'], 'checked')
        self.assertEqual(value['checked_at'], self.now)
        self.assertEqual(value['last_success_at'], self.now)

    def test_task_watch_unavailable_is_independent_and_retains_success(self):
        self.watch('unavailable', last_success='2000-01-01T00:00:00Z')
        value = self.load()
        self.assertEqual(value['status'], 'verified')
        self.assertEqual(value['task_watch']['status'], 'unavailable')
        self.assertEqual(value['task_watch']['last_success_at'], 946684800)
        self.assertIn('Task checks unavailable', status.presentation(value, 'en')['watch_compact'])

    def test_task_watch_old_success_is_stale_not_live_success(self):
        self.watch()
        self.assertEqual(self.load(now=self.now+7201)['task_watch']['status'], 'stale')

    def test_task_watch_claimed_success_requires_matching_last_success(self):
        self.watch(last_success_at=None)
        value = self.load()['task_watch']
        self.assertEqual(value['status'], 'invalid')
        self.assertIsNone(value['last_success_at'])

    def test_task_watch_rejects_future_or_private_text(self):
        for changes in [{'checked_at':'2099-01-01T00:00:00Z'}, {'task_text':'private conversation'}, {'error_type':'raw private path /tmp/private'}]:
            with self.subTest(changes=changes):
                self.watch(**changes)
                value = self.load()['task_watch']
                self.assertEqual(value['status'], 'invalid')
                self.assertNotIn('private', json.dumps(value))

    def test_task_watch_last_success_cannot_follow_failed_attempt(self):
        self.watch('failed', checked_at='2000-01-01T00:00:00Z', last_success_at='2001-01-01T00:00:00Z')
        self.assertEqual(self.load()['task_watch']['status'], 'invalid')

    def test_task_watch_symlink_rejected_independent_of_backup(self):
        self.watch()
        path = self.state/'operations/task-watch-observation.json'
        target = self.fixture.root/'outside-watch'
        path.rename(target);path.symlink_to(target)
        value = self.load()
        self.assertEqual(value['task_watch']['status'], 'invalid')
        self.assertEqual(value['status'], 'verified')

    def test_existing_store_snapshot_includes_unknown_no_creation(self):
        from dots_panel.app import Store
        from dots_panel.desktop_view import ReadOnlyStore
        isolated = self.fixture.root/'standalone'
        Store(isolated)
        value = ReadOnlyStore(isolated).snapshot()
        self.assertEqual(value['backup']['status'], 'unconfigured')
        self.assertFalse((isolated/'config/backup-status.json').exists())
