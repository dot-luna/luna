"""Verify sleep ordering with every system command mocked."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location("luna_sleep", ROOT / "src/luna-cli/sleep/sleep.py")
sleep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sleep)


class SleepTests(unittest.TestCase):
    def test_unsupported_hibernate_never_locks_or_sleeps(self):
        with patch.dict(os.environ, WAYLAND_DISPLAY="test"),              patch.object(sleep.subprocess, "run", return_value=Mock(stdout='s "na"')) as run,              patch.object(sleep.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(RuntimeError, "disk-backed"):
                sleep.sleep_session("hibernate", "/luna")
            launch.assert_not_called()
            self.assertEqual(run.call_count, 1)

    def test_sleep_waits_for_compositor_lock(self):
        with tempfile.TemporaryDirectory() as cache,              patch.dict(os.environ, WAYLAND_DISPLAY="test", XDG_CACHE_HOME=cache),              patch.object(sleep.subprocess, "run", return_value=Mock(stdout='s "yes"')) as run,              patch.object(sleep.subprocess, "Popen", return_value=Mock(poll=lambda: None)) as launch,              patch.object(sleep, "locked", side_effect=[False, False, True, True]),              patch.object(sleep.time, "sleep"):
            sleep.sleep_session("suspend", "/luna")
            self.assertEqual(launch.call_args.args[0], ["/luna", "lock"])
            self.assertTrue(launch.call_args.kwargs["start_new_session"])
            self.assertEqual(run.call_args.args[0], ["systemctl", "suspend"])

    def test_existing_lock_is_reused_for_hibernate(self):
        with patch.dict(os.environ, WAYLAND_DISPLAY="test"),              patch.object(sleep.subprocess, "run", return_value=Mock(stdout='s "challenge"')) as run,              patch.object(sleep.subprocess, "Popen") as launch,              patch.object(sleep, "locked", return_value=True):
            sleep.sleep_session("hibernate", "/luna")
            launch.assert_not_called()
            self.assertEqual(run.call_args.args[0], ["systemctl", "hibernate"])

    def test_failed_locker_cancels_sleep(self):
        with tempfile.TemporaryDirectory() as cache,              patch.dict(os.environ, WAYLAND_DISPLAY="test", XDG_CACHE_HOME=cache),              patch.object(sleep.subprocess, "run", return_value=Mock(stdout='s "yes"')) as run,              patch.object(sleep.subprocess, "Popen", return_value=Mock(poll=lambda: 1)),              patch.object(sleep, "locked", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "cancelled"):
                sleep.sleep_session("suspend", "/luna")
            self.assertEqual(run.call_count, 1)

    def test_lock_timeout_cancels_sleep(self):
        with tempfile.TemporaryDirectory() as cache,              patch.dict(os.environ, WAYLAND_DISPLAY="test", XDG_CACHE_HOME=cache),              patch.object(sleep.subprocess, "run", return_value=Mock(stdout='s "yes"')) as run,              patch.object(sleep.subprocess, "Popen", return_value=Mock(poll=lambda: None)),              patch.object(sleep, "locked", return_value=False),              patch.object(sleep.time, "monotonic", side_effect=[0, 11]):
            with self.assertRaisesRegex(RuntimeError, "not ready"):
                sleep.sleep_session("suspend", "/luna")
            self.assertEqual(run.call_count, 1)
