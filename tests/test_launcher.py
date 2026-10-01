import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('desktop_launcher', Path(__file__).resolve().parents[1] / 'scripts/desktop.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class LauncherTests(unittest.TestCase):
    def test_native_python_prefers_compatible_system(self):
        with patch.object(launcher.shutil, 'which', side_effect=lambda value: value), patch.object(launcher.subprocess, 'run') as probe:
            probe.return_value.returncode = 0
            self.assertEqual(launcher.native_python(), '/usr/bin/python3')
            self.assertEqual(launcher.native_python('/custom/python3'), '/custom/python3')

    def test_native_python_rejects_missing_tk(self):
        with patch.object(launcher.shutil, 'which', side_effect=lambda value: value), patch.object(launcher.subprocess, 'run') as probe:
            probe.return_value.returncode = 1
            with self.assertRaises(SystemExit): launcher.native_python('/custom/python3')

    def test_private_runtime_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'record'
            with launcher.private_file(path, 'w') as file: file.write('private')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            linked = Path(temp) / 'linked'
            linked.symlink_to(path)
            with self.assertRaises(ValueError): launcher.private_file(linked, 'w')
            path.chmod(0o644)
            with self.assertRaises(ValueError): launcher.private_file(path, 'w')
            self.assertEqual(path.read_text(), 'private')

    def test_health_ignores_environment_proxies(self):
        with patch.object(launcher.urllib.request, 'ProxyHandler') as proxy, patch.object(launcher.urllib.request, 'build_opener') as builder:
            builder.return_value.open.side_effect = OSError('offline')
            launcher.health(1)
            proxy.assert_called_once_with({})

    def test_startup_timeout_terminates_child(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(launcher.sys, 'argv', ['desktop.py', 'start', '--data-dir', temp]), patch.object(launcher, 'health', return_value=False), patch.object(launcher.subprocess, 'Popen') as spawn, patch.object(launcher.time, 'sleep'):
            spawn.return_value.poll.return_value = None
            with self.assertRaises(RuntimeError): launcher.main()
            spawn.return_value.terminate.assert_called_once()
            spawn.return_value.wait.assert_called_once_with(timeout=3)

    def test_different_runtime_service_is_not_reused(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(launcher.sys, 'argv', ['desktop.py', 'start', '--data-dir', temp]), patch.object(launcher, 'health', return_value=True), patch.object(launcher.subprocess, 'Popen') as spawn:
            with self.assertRaises(SystemExit): launcher.main()
            spawn.assert_not_called()

    def test_native_open_is_network_free(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(launcher.sys, 'argv', ['desktop.py', 'open', '--data-dir', temp]), patch.object(launcher.os, 'execvpe', side_effect=SystemExit) as execute, patch.object(launcher, 'health') as health, patch.object(launcher.os, 'dup2') as redirect:
            with self.assertRaises(SystemExit): launcher.main()
            health.assert_not_called()
            self.assertIn('dots_panel.desktop_view', execute.call_args[0][1])
            self.assertEqual(redirect.call_count, 2)
            self.assertEqual((Path(temp) / 'logs/desktop.log').stat().st_mode & 0o777, 0o600)


if __name__ == '__main__': unittest.main()
