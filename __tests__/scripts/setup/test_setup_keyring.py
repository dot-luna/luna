"""Check Keyring setup orchestration with no real service or login changes."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[3]


class SetupKeyringTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna keyring '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / 'home'
        self.home.mkdir()
        self.checkout = self.root / 'checkout'
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.calls_file = self.root / 'calls.jsonl'
        self.bash = shutil.which('bash')
        for name in ('scripts/setup/keyring.sh', 'lib/common.sh'):
            destination = self.checkout / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / name, destination)

        # A closed PATH prevents absent mocks from exposing real service tools.
        for name in ('readlink', 'dirname'):
            (self.bin / name).symlink_to(shutil.which(name))
        self.env = {
            'PATH': str(self.bin), 'HOME': str(self.home), 'NO_COLOR': '1',
            'BASH_ENV': '', 'ENV': '', 'TEST_KEYRING_CALLS': str(self.calls_file),
            'XDG_CONFIG_HOME': str(self.root / "config's directory"),
            'XDG_DATA_HOME': str(self.root / 'data directory'),
        }
        backend = f'#!{sys.executable}\n' + '''
import json, os, pathlib, sys
tool = pathlib.Path(sys.argv[0]).name
with open(os.environ['TEST_KEYRING_CALLS'], 'a') as output:
    output.write(json.dumps([tool, *sys.argv[1:]]) + '\\n')
failure = os.environ.get('TEST_HELPER_FAILURE' if tool == 'keyring-config.py'
                         else 'TEST_SYSTEMCTL_FAILURE', '0')
if tool == 'gnome-keyring-daemon':
    sys.exit('Setup must not start, replace or unlock the daemon')
if failure != '0':
    print('Fixture required file write failed' if tool == 'keyring-config.py'
          else 'Fixture service operation failed', file=sys.stderr)
sys.exit(int(failure))
'''
        helper = self.checkout / 'scripts/setup/keyring-config.py'
        helper.write_text(backend)
        for name in ('gnome-keyring-daemon', 'systemctl'):
            tool = self.bin / name
            tool.write_text(backend)
            tool.chmod(0o755)

    def setup(self, *arguments):
        return subprocess.run(
            [self.bash, str(self.checkout / 'scripts/setup/keyring.sh'), *arguments],
            cwd=self.root, env=self.env, input='', capture_output=True, text=True, timeout=10,
        )

    def calls(self):
        if not self.calls_file.exists():
            return []
        return [json.loads(line) for line in self.calls_file.read_text().splitlines()]

    def expected_helper(self, config=None, data=None):
        return ['keyring-config.py', 'configure',
                config or self.env['XDG_CONFIG_HOME'], data or self.env['XDG_DATA_HOME']]

    def test_configures_before_enabling_only_the_socket_and_ignores_extra_arguments(self):
        result = self.setup('--help', '--unknown', 'ignored')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.calls(), [
            self.expected_helper(),
            ['systemctl', '--user', 'enable', 'gnome-keyring-daemon.socket'],
        ])
        self.assertIn('Back up files you want to keep', result.stderr)
        self.assertIn('GNOME Keyring configured.', result.stdout)
        self.assertIn('sign in with your password', result.stdout)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_absent_daemon_warns_and_skips_helper_and_service_work(self):
        (self.bin / 'gnome-keyring-daemon').unlink()
        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Keyring setup skipped', result.stderr)
        self.assertIn('gnome-keyring', result.stderr)
        self.assertEqual(self.calls(), [])
        self.assertNotIn('GNOME Keyring configured.', result.stdout)

    def test_unset_and_empty_xdg_paths_fall_back_to_home(self):
        for value in (None, ''):
            with self.subTest(value=value):
                self.calls_file.unlink(missing_ok=True)
                for variable in ('XDG_CONFIG_HOME', 'XDG_DATA_HOME'):
                    if value is None:
                        self.env.pop(variable, None)
                    else:
                        self.env[variable] = value
                result = self.setup()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(self.calls()[0], self.expected_helper(
                    str(self.home / '.config'), str(self.home / '.local/share')))

    def test_required_helper_write_failure_stops_before_service_configuration(self):
        self.env['TEST_HELPER_FAILURE'] = '23'
        result = self.setup()
        self.assertEqual(result.returncode, 23, result.stdout + result.stderr)
        self.assertEqual(self.calls(), [self.expected_helper()])
        self.assertIn('Fixture required file write failed', result.stderr)
        self.assertNotIn('GNOME Keyring configured.', result.stdout)

    def test_optional_socket_enable_failure_warns_and_keeps_completed_configuration(self):
        self.env['TEST_SYSTEMCTL_FAILURE'] = '17'
        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.calls(), [
            self.expected_helper(),
            ['systemctl', '--user', 'enable', 'gnome-keyring-daemon.socket'],
        ])
        self.assertIn('Could not enable the keyring socket', result.stderr)
        self.assertIn('GNOME Keyring configured.', result.stdout)

    def test_missing_systemctl_warns_without_starting_or_unlocking_daemon(self):
        (self.bin / 'systemctl').unlink()
        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.calls(), [self.expected_helper()])
        self.assertIn('systemctl is unavailable', result.stderr)
        self.assertIn('GNOME Keyring configured.', result.stdout)


if __name__ == '__main__':
    unittest.main()
