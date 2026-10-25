"""Exercise macOS VM setup and console sessions without Docker or guest downloads."""
import fcntl
import json
import os
from pathlib import Path
import pty
import re
import shutil
import signal
import socket
import subprocess
import tempfile
import threading
import time
import unittest

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / 'src/luna-cli/macos'
REAL_TIMEOUT = shutil.which('timeout')


class MacOSTests(unittest.TestCase):
    def setUp(self):
        # Quotes, spaces, and dollars exercise shell quoting and Compose interpolation.
        self.temp = tempfile.TemporaryDirectory(prefix="luna macos '$ ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tools = self.root / 'bin'
        self.tools.mkdir()
        self.env = dict(os.environ, HOME=str(self.root),
                        XDG_CONFIG_HOME=str(self.root / 'config'),
                        XDG_DATA_HOME=str(self.root / 'data'),
                        LUNA_INSTALL_DIR=str(REPO), DISPLAY=':99', WAYLAND_DISPLAY='test',
                        PATH=str(self.tools) + ':' + os.environ['PATH'],
                        TEST_ROOT=str(self.root))
        self.config = self.root / 'config/luna/macos/compose.yml'
        self.prepared = self.config.parent / 'prepared'
        self.storage = self.root / 'data/luna/macos/storage'
        self.shared = self.root / 'macOS'
        self.desktop = self.root / 'data/applications/luna-macos.desktop'
        mock = '''#!/usr/bin/python3
import json
import os
import pathlib
import sys
import time

root = pathlib.Path(os.environ['TEST_ROOT'])
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
# The launcher itself is a Bash script; record only its delegated helpers.
if name != 'bash' or not args or pathlib.Path(args[0]).name != 'luna':
    with (root / 'commands').open('a') as out:
        out.write(json.dumps([name, *args]) + '\\n')

if name == 'docker':
    if args == ['info']:
        sys.exit(int(os.getenv('DOCKER_FAIL', '0')))
    if 'config' in args:
        storage = os.getenv('CUSTOM_STORAGE', str(root / 'data/luna/macos/storage'))
        print(json.dumps({'services': {'macos': {
            'volumes': [{'type': 'bind', 'target': '/storage', 'source': storage}]}}}))
    elif 'pull' in args and '--pull' not in args:
        if os.getenv('DOCKER_PULL_BLOCK'):
            # Let the test attempt deletion while installation is still pulling.
            (root / 'pull-ready').touch()
            deadline = time.monotonic() + 30
            while not (root / 'pull-release').exists():
                if time.monotonic() >= deadline:
                    sys.exit('Timed out waiting for the test to release Docker pull')
                time.sleep(0.05)
        sys.exit(int(os.getenv('DOCKER_PULL_FAIL', '0')))
    elif 'up' in args:
        if os.getenv('DOCKER_UP_FAIL'):
            sys.exit(1)
        (root / 'stopped').unlink(missing_ok=True)
        (root / 'removed').unlink(missing_ok=True)
    elif 'logs' in args:
        print('The macOS installer still needs manual setup.')
    elif args and args[0] == 'inspect':
        print('false false no' if (root / 'stopped').exists() else 'true false no')
    elif 'stop' in args:
        (root / 'stopped').touch()
    elif 'down' in args:
        if os.getenv('DOCKER_DOWN_FAIL'):
            sys.exit(1)
        (root / 'removed').touch()
    elif 'ps' in args:
        if not (root / 'removed').exists() and ('--all' in args or not (root / 'stopped').exists()):
            print('mock-macos-container')
elif name == 'vncviewer':
    if os.getenv('VNC_BLOCK'):
        (root / 'vnc-pid').write_text(str(os.getpid()))
        (root / 'vnc-ready').touch()
        time.sleep(30)
    sys.exit(int(os.getenv('VNC_EXIT', '0')))
elif name == 'timeout':
    # CLI tests never connect to a real VM; socket tests run the real helper separately.
    sys.exit(int(os.getenv('VNC_NOT_READY', '0')))
elif name == 'test':
    if args in (['-c', '/dev/kvm'], ['-c', '/dev/net/tun']):
        sys.exit(int(os.getenv('DEVICE_MISSING') == args[-1]))
    os.execv('/usr/bin/test', ['test', *args])
elif name == 'uname':
    if args == ['-m']:
        print(os.getenv('HOST_ARCH', 'x86_64'))
    else:
        os.execv('/usr/bin/uname', ['uname', *args])
elif name == 'grep':
    if '/proc/cpuinfo' in args:
        sys.exit(int(os.getenv('AVX2_MISSING', '0')))
    os.execv('/usr/bin/grep', ['grep', *args])
elif name == 'bash':
    os.execv('/usr/bin/bash', ['bash', *args])
'''
        for name in ('docker', 'vncviewer', 'timeout', 'test', 'uname', 'grep', 'bash'):
            path = self.tools / name
            path.write_text(mock)
            path.chmod(0o755)

    def cli(self, *args, ok=True, alias='macos'):
        result = subprocess.run([str(REPO / 'bin/luna'), alias, *args], env=self.env,
                                stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, timeout=15)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return result

    def interactive(self, *args, answers=b''):
        master, slave = pty.openpty()
        try:
            if answers:
                os.write(master, answers)
            result = subprocess.run([str(REPO / 'bin/luna'), 'mac', *args],
                                    env=self.env, stdin=slave, capture_output=True,
                                    text=True, timeout=15)
        finally:
            os.close(master)
            os.close(slave)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def commands(self):
        path = self.root / 'commands'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def clear(self):
        (self.root / 'commands').write_text('')

    def assert_resources(self, ram='4G', cpus='2', disk='64G', version='15'):
        content = self.config.read_text()
        for key, value in [('RAM_SIZE', ram), ('CPU_CORES', cpus),
                           ('DISK_SIZE', disk), ('VERSION', version)]:
            self.assertIn(f'{key}: "{value}"', content)

    def prompts(self, result):
        return re.findall(r'(RAM|CPU cores|Disk capacity|macOS version)'
                          r'(?: \([^\n)]*\))? \[[^\n\]]*\]: ', result.stdout)

    def assert_stopped(self):
        self.assertTrue(any(cmd[-4:] == ['stop', '--timeout', '120', 'macos']
                            for cmd in self.commands()), self.commands())

    def wait_for(self, predicate):
        deadline = time.monotonic() + 5
        while not predicate() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(predicate(), 'Timed out waiting for the mocked VM operation')

    def background_cli(self, *args):
        process = subprocess.Popen([str(REPO / 'bin/luna'), 'macos', *args],
                                   env=self.env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   start_new_session=True)

        def cleanup():
            # Reap every process in this test's session even if an assertion fails.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)

        self.addCleanup(cleanup)
        return process

    def blocked_session(self):
        self.env['VNC_BLOCK'] = '1'
        (self.root / 'vnc-ready').unlink(missing_ok=True)
        process = self.background_cli('start')
        self.wait_for(lambda: (self.root / 'vnc-ready').exists())
        self.assertIsNone(process.poll())
        return process

    def test_aliases_help_status_and_missing_install(self):
        for alias in ('macos', 'mac'):
            with self.subTest(alias=alias):
                self.assertIn('logs', self.cli(alias=alias).stdout)
                result = self.cli('status', alias=alias)
                self.assertIn('not', result.stdout.lower())
                self.cli('start', alias=alias, ok=False)
        self.assertEqual(self.commands(), [])
        self.assertFalse(self.config.exists())
        self.assertFalse(self.desktop.exists())

    def test_interactive_defaults_follow_resource_and_version_prompt_order(self):
        result = self.interactive('install', answers=b'\n\n\n\n')
        self.assertEqual(self.prompts(result), ['RAM', 'CPU cores', 'Disk capacity', 'macOS version'])
        self.assert_resources()

    def test_interactive_invalid_resources_retry_the_same_prompt(self):
        result = self.interactive('install',
                                  answers=b'1G\n8\n0\n257\n4\n32G\n128g\n10\n16\n26\n')
        for message in ('minimum 4G', 'CPU', 'minimum 64G'):
            self.assertIn(message, result.stderr)
        self.assert_resources(ram='8G', cpus='4', disk='128G', version='26')
        self.assertEqual(self.prompts(result), ['RAM', 'RAM', 'CPU cores', 'CPU cores',
                                               'CPU cores', 'Disk capacity', 'Disk capacity',
                                               'macOS version', 'macOS version', 'macOS version'])

    def test_explicit_ram_and_disk_skip_only_their_prompts(self):
        result = self.interactive('install', '--ram', '8G', '--disk', '128G',
                                  answers=b'4\n26\n')
        self.assertEqual(self.prompts(result), ['CPU cores', 'macOS version'])
        self.assert_resources(ram='8G', cpus='4', disk='128G', version='26')

    def test_explicit_cpu_and_version_skip_only_their_prompts(self):
        result = self.interactive('install', '--cpus', '4', '--version', '26',
                                  answers=b'8\n128\n')
        self.assertEqual(self.prompts(result), ['RAM', 'Disk capacity'])
        self.assert_resources(ram='8G', cpus='4', disk='128G', version='26')

    def test_yes_skips_interactive_prompts(self):
        result = self.interactive('install', '--yes', '--ram', '8G')
        self.assertNotIn('press Enter', result.stdout)
        self.assertNotIn('RAM (', result.stdout)
        self.assert_resources(ram='8G')

    def test_non_tty_install_uses_defaults_without_prompting(self):
        result = self.cli('install')
        self.assertNotIn('press Enter', result.stdout)
        self.assertNotIn('RAM (', result.stdout)
        self.assert_resources()

    def test_install_resources_permissions_paths_and_project(self):
        self.cli('install', '--ram', '4G', '--cpus', '2', '--disk', '64G',
                 '--version', '15', '--timeout', '7200', '--yes')
        self.assert_resources()
        content = self.config.read_text()
        for value in ('  macos:', 'dockurr/macos:latest', '127.0.0.1:8007:8006',
                      '127.0.0.1:5900:5900/tcp', '/dev/kvm', '/dev/net/tun', 'NET_ADMIN',
                      str(self.storage).replace('$', '$$'), str(self.shared).replace('$', '$$')):
            self.assertIn(value, content)
        self.assertNotIn('127.0.0.1:8006:8006', content)
        self.assertNotIn(':3389:', content)
        self.assertEqual(self.config.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        self.assertTrue(self.storage.is_dir())
        self.assertTrue(self.shared.is_dir())
        commands = self.commands()
        for cmd in commands:
            if cmd[:2] == ['docker', 'compose'] and cmd[2:] != ['version']:
                self.assertEqual(cmd[2:6], ['--project-name', 'luna-macos', '--file', str(self.config)])
        self.assertTrue(any(cmd[-2:] == ['pull', 'macos'] for cmd in commands))
        self.assertTrue(any(cmd[-3:] == ['up', '-d', 'macos'] for cmd in commands))
        self.assertTrue(any(cmd[0] == 'bash' and Path(cmd[1]).name == 'wait-ready.sh'
                            and cmd[-2:] == [str(self.config), '7200'] for cmd in commands))

    def test_reinstall_preserves_configuration_disk_and_skips_prompts(self):
        self.cli('install')
        original = self.config.read_text()
        disk = self.storage / 'disk.img'
        disk.write_text('existing disk')
        result = self.interactive('install', '--ram', '16G', '--version', '26')
        self.assertNotIn('press Enter', result.stdout)
        self.assertEqual(self.prompts(result), [])
        self.assertEqual(self.config.read_text(), original)
        self.assertEqual(disk.read_text(), 'existing disk')

    def test_supported_macos_versions(self):
        for version in ('11', '12', '13', '14', '15', '26'):
            with self.subTest(version=version):
                config_home = self.root / f'version-{version}'
                self.env['XDG_CONFIG_HOME'] = str(config_home)
                self.cli('install', '--version', version)
                content = (config_home / 'luna/macos/compose.yml').read_text()
                self.assertIn(f'VERSION: "{version}"', content)

    def test_supported_cpu_topologies(self):
        for cpus in ('1', '2', '4', '6', '8', '10', '12', '14', '16', '24', '32', '64'):
            with self.subTest(cpus=cpus):
                config_home = self.root / f'cpus-{cpus}'
                self.env['XDG_CONFIG_HOME'] = str(config_home)
                self.cli('install', '--cpus', cpus)
                content = (config_home / 'luna/macos/compose.yml').read_text()
                self.assertIn(f'CPU_CORES: "{cpus}"', content)

    def test_invalid_install_options_do_not_create_configuration(self):
        cases = [('--ram', '3G'), ('--ram', '4.5G'), ('--disk', '63G'),
                 ('--cpus', '0'), ('--cpus', '3'), ('--cpus', '5'), ('--cpus', '7'),
                 ('--cpus', '9'), ('--cpus', '256'), ('--cpus', '257'), ('--cpus', '1.5'),
                 ('--version', '10'), ('--version', '16'), ('--version', '25'),
                 ('--version', '27'), ('--version', 'latest'),
                 ('--timeout', '0'), ('--timeout', '86401'), ('--timeout', '1.5')]
        for args in cases:
            with self.subTest(args=args):
                self.cli('install', *args, ok=False)
                self.assertFalse(self.config.exists())
                self.assertFalse(self.prepared.exists())
                self.assertFalse(self.desktop.exists())
        self.assertFalse(any('pull' in cmd or 'up' in cmd for cmd in self.commands()))

    def test_unavailable_docker_and_host_requirements_fail_before_config_creation(self):
        cases = [('DOCKER_FAIL', '1'), ('DEVICE_MISSING', '/dev/kvm'),
                 ('DEVICE_MISSING', '/dev/net/tun'), ('HOST_ARCH', 'aarch64'),
                 ('AVX2_MISSING', '1')]
        for key, value in cases:
            with self.subTest(requirement=key, value=value):
                self.env[key] = value
                self.cli('install', ok=False)
                self.assertFalse(self.config.exists())
                self.assertFalse(any('pull' in cmd or 'up' in cmd for cmd in self.commands()))
                del self.env[key]
                self.clear()

    def test_failed_pull_or_start_creates_no_prepared_marker_or_launcher(self):
        for variable in ('DOCKER_PULL_FAIL', 'DOCKER_UP_FAIL'):
            with self.subTest(variable=variable):
                self.env[variable] = '1'
                self.cli('install', ok=False)
                self.assertFalse(self.prepared.exists())
                self.assertFalse(self.desktop.exists())
                del self.env[variable]
        self.cli('install')
        self.assertTrue(self.prepared.is_file())
        desktop = self.desktop.read_text()
        for value in ('Name=macOS', 'macos start', 'Terminal=false'):
            self.assertIn(value, desktop)
        self.assertEqual(self.desktop.stat().st_mode & 0o777, 0o644)

    def test_install_waits_only_for_vnc_and_explains_manual_guest_installation(self):
        result = self.cli('install')
        output = (result.stdout + result.stderr).lower()
        self.assertNotIn('macos installed successfully', output)
        self.assertIn('install', output)
        self.assertTrue('manual' in output or 'finish' in output, output)
        self.assertTrue(self.prepared.is_file())
        self.assertFalse((self.config.parent / 'installed').exists())
        commands = self.commands()
        probes = [cmd for cmd in commands if cmd[0] == 'timeout']
        self.assertTrue(probes, commands)
        for probe in probes:
            self.assertGreater(float(probe[1]), 0)
            self.assertLessEqual(float(probe[1]), 5)
            self.assertEqual(probe[2], 'bash')
            self.assertEqual(Path(probe[3]).name, 'vnc-ready.sh')
        self.assertFalse(any(cmd[0] == 'vncviewer' or 'logs' in cmd or 'inspect' in cmd
                             or 'stop' in cmd for cmd in commands))

    def test_install_timeout_keeps_vm_running_without_prepared_marker_or_launcher(self):
        self.env['VNC_NOT_READY'] = '1'
        result = self.cli('install', '--timeout', '1', ok=False)
        self.assertNotIn('installed successfully', result.stdout.lower())
        self.assertTrue(self.config.is_file())
        self.assertFalse(self.prepared.exists())
        self.assertFalse(self.desktop.exists())
        self.assertFalse(any('stop' in cmd or 'down' in cmd for cmd in self.commands()))
        self.clear()
        self.cli('start', ok=False)
        self.assertFalse(any('up' in cmd or cmd[0] == 'vncviewer' for cmd in self.commands()))
        del self.env['VNC_NOT_READY']
        self.cli('install')
        self.assertTrue(self.prepared.exists())

    def test_held_install_lock_prevents_pull_and_start(self):
        self.config.parent.mkdir(parents=True)
        with (self.config.parent / 'install.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.cli('install', '--yes', ok=False)
            self.assertIn('Another macOS install or deletion is active', result.stderr)

            # Configuration may be created before locking, but the VM must not start.
            self.assertTrue(self.config.is_file())
            self.assertFalse(any('pull' in cmd or 'up' in cmd for cmd in self.commands()),
                             self.commands())
            self.assertFalse(self.prepared.exists())
            self.assertFalse(self.desktop.exists())

        self.clear()
        self.cli('install', '--yes')
        self.assertTrue(any(cmd[-2:] == ['pull', 'macos'] for cmd in self.commands()))
        self.assertTrue(any(cmd[-3:] == ['up', '-d', 'macos'] for cmd in self.commands()))
        self.assertTrue(self.prepared.is_file())
        self.assertTrue(self.desktop.is_file())

    def test_delete_refuses_during_pull_and_succeeds_after_install_finishes(self):
        self.env['DOCKER_PULL_BLOCK'] = '1'
        process = self.background_cli('install', '--yes')
        self.wait_for(lambda: (self.root / 'pull-ready').exists())
        self.assertIsNone(process.poll())
        original = self.config.read_text()
        disk = self.storage / 'disk.img'
        disk.write_text('VM disk')
        self.assertTrue(any(cmd[-2:] == ['pull', 'macos'] for cmd in self.commands()))
        self.assertFalse(any('up' in cmd for cmd in self.commands()))

        result = self.cli('delete', '--yes', ok=False)
        self.assertIn('Finish or cancel', result.stderr)
        self.assertIn('installation', result.stderr)
        self.assertIsNone(process.poll())
        self.assertFalse(any('down' in cmd or 'stop' in cmd for cmd in self.commands()),
                         self.commands())
        self.assertFalse((self.root / 'removed').exists())
        self.assertEqual(disk.read_text(), 'VM disk')
        self.assertEqual(self.config.read_text(), original)
        self.assertFalse(self.prepared.exists())
        self.assertFalse(self.desktop.exists())

        (self.root / 'pull-release').touch()
        self.assertEqual(process.wait(timeout=15), 0, self.commands())
        self.assertTrue(any(cmd[-3:] == ['up', '-d', 'macos'] for cmd in self.commands()))
        self.assertEqual(disk.read_text(), 'VM disk')
        self.assertTrue(self.prepared.is_file())
        self.assertEqual(self.prepared.stat().st_mode & 0o777, 0o600)
        self.assertTrue(self.desktop.is_file())

        self.cli('delete', '--yes')
        self.assertTrue(any(cmd[-3:] == ['down', '--timeout', '120'] for cmd in self.commands()))
        self.assertTrue((self.root / 'removed').exists())
        self.assertFalse(self.config.parent.exists())
        self.assertFalse(self.storage.exists())
        self.assertFalse(self.desktop.exists())

    def test_start_attaches_fullscreen_vnc_and_stops_after_viewer_exit(self):
        self.cli('install')
        self.clear()
        self.cli('start')
        commands = self.commands()
        self.assertFalse(any('up' in cmd or 'pull' in cmd or 'build' in cmd for cmd in commands))
        viewer = next(cmd for cmd in commands if cmd[0] == 'vncviewer')
        self.assertIn('-FullScreen', viewer)
        self.assertEqual(viewer[-1], '127.0.0.1::5900')
        self.assert_stopped()
        self.assertTrue(self.prepared.exists())

    def test_start_of_stopped_vm_never_pulls_or_builds(self):
        self.cli('install')
        self.cli('stop')
        self.clear()
        self.cli('start')
        commands = self.commands()
        up = next(cmd for cmd in commands if 'up' in cmd)
        self.assertIn('--no-build', up)
        self.assertEqual(up[up.index('--pull') + 1], 'never')
        self.assertEqual(up[-1], 'macos')
        self.assertFalse(any('pull' in cmd or 'build' in cmd for cmd in commands))
        self.assert_stopped()

    def test_start_requires_display_even_in_a_wayland_session(self):
        self.cli('install')
        self.clear()
        del self.env['DISPLAY']
        self.cli('start', ok=False)
        self.assertFalse(any('up' in cmd or cmd[0] == 'vncviewer' for cmd in self.commands()))

    def test_start_requires_vncviewer_before_starting_vm(self):
        self.cli('install')
        self.clear()
        (self.tools / 'vncviewer').unlink()
        # A restricted PATH prevents an installed host viewer from satisfying this check.
        for name in ('readlink', 'dirname', 'sh', 'env'):
            (self.tools / name).symlink_to(shutil.which(name))
        self.env['PATH'] = str(self.tools)
        result = self.cli('start', ok=False)
        self.assertIn('vncviewer', result.stderr)
        self.assertFalse(any('up' in cmd for cmd in self.commands()))

    def test_invalid_start_timeout_does_not_start_or_attach(self):
        self.cli('install')
        self.clear()
        for timeout in ('0', '3601', '1.5'):
            with self.subTest(timeout=timeout):
                self.cli('start', '--timeout', timeout, ok=False)
        self.assertFalse(any('up' in cmd or cmd[0] == 'vncviewer' for cmd in self.commands()))

    def test_failed_viewer_stops_vm(self):
        self.cli('install')
        self.clear()
        self.env['VNC_EXIT'] = '2'
        self.cli('start', ok=False)
        self.assert_stopped()

    def test_keep_alive_preserves_vm_after_viewer_success_or_failure(self):
        self.cli('install')
        for status in ('0', '2'):
            with self.subTest(viewer_status=status):
                self.clear()
                self.env['VNC_EXIT'] = status
                self.cli('start', '--keep-alive', ok=status == '0')
                self.assertTrue(any(cmd[0] == 'vncviewer' for cmd in self.commands()))
                self.assertFalse(any('stop' in cmd for cmd in self.commands()))

    def test_start_is_foreground_and_rejects_second_session(self):
        self.cli('install')
        self.clear()
        process = self.blocked_session()
        self.cli('start', ok=False)
        self.assertEqual(sum(cmd[0] == 'vncviewer' for cmd in self.commands()), 1)
        self.assertFalse(any('stop' in cmd for cmd in self.commands()))
        os.kill(int((self.root / 'vnc-pid').read_text()), signal.SIGTERM)
        process.wait(timeout=5)
        self.assert_stopped()

    def test_session_signals_stop_vm(self):
        self.cli('install')
        for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            with self.subTest(signal=signum):
                self.clear()
                process = self.blocked_session()
                os.killpg(process.pid, signum)
                process.wait(timeout=5)
                self.wait_for(lambda: any(cmd[-4:] == ['stop', '--timeout', '120', 'macos']
                                         for cmd in self.commands()))

    def test_start_readiness_timeout_leaves_vm_running(self):
        self.cli('install')
        self.clear()
        self.env['VNC_NOT_READY'] = '1'
        self.cli('start', '--timeout', '1', ok=False)
        self.assertFalse(any('stop' in cmd or 'down' in cmd or cmd[0] == 'vncviewer'
                             for cmd in self.commands()))
        self.assertTrue(self.prepared.exists())

    def test_logs_status_and_stop_only_touch_existing_macos_vm(self):
        self.cli('install')
        self.clear()
        self.cli('logs')
        self.cli('logs', '--no-follow', '--tail', '25')
        self.cli('status')
        self.cli('stop')
        commands = self.commands()
        self.assertTrue(any(cmd[-5:] == ['logs', '--tail', '100', '--follow', 'macos']
                            for cmd in commands))
        self.assertTrue(any(cmd[-4:] == ['logs', '--tail', '25', 'macos'] for cmd in commands))
        self.assertTrue(any(cmd[-3:] == ['ps', '--all', 'macos'] for cmd in commands))
        self.assert_stopped()
        self.assertFalse(any('up' in cmd or 'down' in cmd or 'rm' in cmd for cmd in commands))
        self.assertTrue(self.config.exists())

    def test_delete_requires_confirmation_and_preserves_shared_and_windows_files(self):
        self.cli('install')
        disk = self.storage / 'disk.img'
        disk.write_text('VM disk')
        shared = self.shared / 'keep.txt'
        shared.write_text('shared file')
        windows = [self.root / 'config/luna/windows/compose.yml',
                   self.root / 'data/luna/windows/storage/disk.img',
                   self.root / 'data/applications/luna-windows.desktop',
                   self.root / 'Windows/keep.txt']
        for path in windows:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('Windows file')
        self.clear()
        self.cli('delete', ok=False)
        self.assertTrue(disk.exists())
        self.assertFalse(any('down' in cmd for cmd in self.commands()))
        self.cli('remove', '--yes')
        self.assertFalse(self.config.parent.exists())
        self.assertFalse(self.storage.exists())
        self.assertFalse(self.desktop.exists())
        self.assertEqual(shared.read_text(), 'shared file')
        for path in windows:
            self.assertEqual(path.read_text(), 'Windows file')
        self.assertTrue(any(cmd[-3:] == ['down', '--timeout', '120'] for cmd in self.commands()))

    def test_delete_confirmation_can_cancel_or_confirm(self):
        self.cli('install')
        for answer, removed in [(b'no\n', False), (b'delete\n', True)]:
            result = self.interactive('delete', answers=answer)
            self.assertIn('Type delete to confirm', result.stdout)
            self.assertEqual(not self.config.exists(), removed)

    def test_delete_preserves_data_when_docker_removal_fails(self):
        self.cli('install')
        disk = self.storage / 'disk.img'
        disk.write_text('VM disk')
        self.env['DOCKER_DOWN_FAIL'] = '1'
        self.cli('delete', '--yes', ok=False)
        self.assertTrue(self.config.exists())
        self.assertTrue(self.desktop.exists())
        self.assertEqual(disk.read_text(), 'VM disk')

    def test_delete_refuses_custom_storage_without_removing_data(self):
        self.cli('install')
        disk = self.storage / 'disk.img'
        disk.write_text('VM disk')
        shared = self.shared / 'keep.txt'
        shared.write_text('shared file')
        self.env['CUSTOM_STORAGE'] = str(self.shared)
        self.clear()
        self.cli('delete', '--yes', ok=False)
        self.assertTrue(self.config.exists())
        self.assertTrue(self.desktop.exists())
        self.assertEqual(disk.read_text(), 'VM disk')
        self.assertEqual(shared.read_text(), 'shared file')
        self.assertFalse(any('down' in cmd for cmd in self.commands()))

    def test_delete_decodes_literal_compose_dollar_escapes(self):
        self.cli('install')
        self.env['CUSTOM_STORAGE'] = str(self.storage).replace('$', '$$')
        self.clear()
        self.cli('delete', '--yes')
        self.assertFalse(self.config.exists())
        self.assertFalse(self.storage.exists())
        configuration = next(cmd for cmd in self.commands() if 'config' in cmd)
        self.assertIn('--no-interpolate', configuration)

    def test_delete_refuses_dynamic_storage_before_docker_removal(self):
        self.cli('install')
        self.env['CUSTOM_STORAGE'] = '${HOME}/data/luna/macos/storage'
        self.clear()
        result = self.cli('delete', '--yes', ok=False)
        self.assertIn('dynamic storage', result.stderr)
        self.assertTrue(self.config.exists())
        self.assertFalse(any('down' in cmd for cmd in self.commands()))

    def test_delete_refuses_symlink_storage_without_removing_shared_files(self):
        self.cli('install')
        shared = self.shared / 'keep.txt'
        shared.write_text('shared file')
        self.storage.rmdir()
        self.storage.symlink_to(self.shared, target_is_directory=True)
        self.clear()
        self.cli('delete', '--yes', ok=False)
        self.assertTrue(self.config.exists())
        self.assertTrue(self.desktop.exists())
        self.assertTrue(self.storage.is_symlink())
        self.assertEqual(shared.read_text(), 'shared file')
        self.assertFalse(any('down' in cmd for cmd in self.commands()))

    def test_readiness_requires_complete_rfb_banner_not_an_open_port_or_http(self):
        cases = [(None, False), (b'', False), (b'HTTP/1.1 200 OK\r\n', False),
                 (b'RFB invalid\n', False), (b'RFB 003.008', False),
                 (b'RFB 003.003\n', True), (b'RFB 003.008\n', True)]
        for response, ready in cases:
            with self.subTest(response=response), socket.socket() as server:
                server.bind(('127.0.0.1', 0))
                server.listen(1)
                server.settimeout(3)
                finished = threading.Event()
                errors = []

                def respond():
                    try:
                        with server.accept()[0] as client:
                            if response is None:
                                # A listening socket alone is insufficient; force the outer timeout.
                                finished.wait(3)
                            else:
                                client.sendall(response)
                    except OSError as error:
                        errors.append(error)

                thread = threading.Thread(target=respond)
                thread.start()
                try:
                    result = subprocess.run(
                        [REAL_TIMEOUT, '1', '/usr/bin/bash', str(MODULE / 'vnc-ready.sh'),
                         str(server.getsockname()[1])], capture_output=True, timeout=4)
                finally:
                    finished.set()
                    thread.join(timeout=4)
                self.assertFalse(thread.is_alive())
                self.assertEqual(errors, [])
                self.assertEqual(result.returncode == 0, ready, result.stderr)


if __name__ == '__main__':
    unittest.main()
