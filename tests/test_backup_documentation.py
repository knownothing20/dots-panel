"""Public onboarding guidance must retain opt-in and privacy boundaries."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BackupDocumentationTests(unittest.TestCase):
    def test_public_template_keeps_explicit_opt_in_and_no_duplicate_plan_checks(self):
        text = (ROOT / 'docs/hourly-backup-agent-template.md').read_text()
        for required in ('安装或运行本地测试不代表同意持续数据共享', '读取现有计划',
                         '确认不存在后才按授权创建一个计划', '首次实际周期执行',
                         '普通每小时调用永远不带 bootstrap', 'expected_current_version'):
            self.assertIn(required, text)

    def test_template_uses_placeholders_instead_of_private_identifiers_or_roots(self):
        files = ('docs/hourly-backup-agent-template.md', 'docs/private-backup-protocol.md',
                 'docs/agent-setup.md', 'docs/install.md', 'docs/privacy.md', 'docs/restoration.md')
        private = re.compile(r'(?:libfile_[0-9a-f]{16,}|file_[0-9a-f]{16,}|'
                             r'/workspace/(?:shared|scratch)/|/home/[^\s]+|'
                             r'jawbone_id\s*[:=]\s*[\"\'][^\"\']+[\"\'])')
        for name in files:
            self.assertIsNone(private.search((ROOT / name).read_text()), name)
        template = (ROOT / files[0]).read_text()
        for placeholder in ('[SOURCE_ROOT]', '[DATA_ROOT]', '[STATE_ROOT]',
                            '[PRIVATE_LIBRARY_FOLDER_ID]', '[LATEST_INDEX_LIBRARY_ID]',
                            '[PLATFORM_AUTOMATION_ID]', '[TASK_SCOPE]'):
            self.assertIn(placeholder, template)

    def test_capture_and_restore_limits_are_documented(self):
        text = (ROOT / 'docs/private-backup-protocol.md').read_text()
        for required in ('strict-live', 'database-snapshot-cutoff', 'cutoff upper bound',
                         'not a promise that every transaction', '0700',
                         'same-mode retry', 'a source candidate does not install it'):
            self.assertIn(required, text)

    def test_recovery_guide_does_not_publish_personal_historical_verification(self):
        text = (ROOT / 'docs/restoration.md').read_text()
        for stale in ('172 Python tests', '207-test suite', 'lost checkout', 'This installation combines'):
            self.assertNotIn(stale, text)
        for required in ('private-backup-protocol.md', 'do not infer a daily reset',
                         'explicitly approves', 'Never initialize empty DATA'):
            self.assertIn(required, text)


if __name__ == '__main__':
    unittest.main()
