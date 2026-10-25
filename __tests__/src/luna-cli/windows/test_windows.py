"""Exercise VM setup and foreground session cleanup without Docker or a Windows download."""
import json
import os
import pty
import signal
import socket
import threading
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

REPO = Path(__file__).resolve().parents[4]
STOP_INSPECT_FORMAT = '{{.State.Running}} {{.State.Restarting}} {{.HostConfig.RestartPolicy.Name}}'


class WindowsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luna windows '$ ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        tools = self.root / 'bin'
        tools.mkdir()
        self.env = dict(os.environ, HOME=str(self.root),
                        XDG_CONFIG_HOME=str(self.root / 'config'),
                        XDG_DATA_HOME=str(self.root / 'data'),
                        LUNA_INSTALL_DIR=str(REPO),
                        PATH=str(tools) + ':' + os.environ['PATH'],
                        WAYLAND_DISPLAY='test', TEST_ROOT=str(self.root))
        self.config = self.root / 'config/luna/windows/compose.yml'
        mock = '''#!/usr/bin/python3
import json, os, pathlib, sys, time
root = pathlib.Path(os.environ['TEST_ROOT'])
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with (root / 'commands').open('a') as out:
    out.write(json.dumps([name, *args]) + '\\n')
if name == 'docker':
    if args == ['info']:
        sys.exit(int(os.getenv('DOCKER_FAIL', '0')))
    if 'config' in args:
        # Compose resolves $$ in user paths; credentials stay inside the mocked pipe.
        print(json.dumps({'services': {'windows': {'command': None, 'entrypoint': None,
            'networks': {'default': None},
            'volumes': [{'type': 'bind', 'target': '/storage', 'source': str(root / 'data/luna/windows/storage')}],
            'environment': {'USERNAME': 'luna', 'PASSWORD': 'private-test-secret'}}}}))
    elif 'up' in args and os.getenv('DOCKER_UP_FAIL'):
        sys.exit(1)
    elif 'stop' in args and os.getenv('DOCKER_STOP_FAIL'):
        sys.exit(1)
    elif args[:1] == ['update']:
        sys.exit(int(os.getenv('DOCKER_UPDATE_FAIL', '0')))
    elif args and args[0] == 'inspect':
        if args[2] == '{{.State.StartedAt}}':
            print('2026-10-13T00:00:00Z')
        elif args[2] == '{{.State.Running}} {{.State.Restarting}} {{.HostConfig.RestartPolicy.Name}}':
            if os.getenv('DOCKER_STOP_INSPECT_FAIL'): sys.exit(1)
            print(os.getenv('DOCKER_STOP_STATE', 'false false no'))
        else:
            sys.exit(1)
    elif 'logs' in args:
        print('Windows started successfully')
    elif 'down' in args:
        if os.getenv('DOCKER_DOWN_FAIL'): sys.exit(1)
        (root / 'removed').touch()
    elif 'ps' in args:
        if not (root / 'removed').exists(): print('mock-container')
elif name == 'xfreerdp3':
    data = sys.stdin.read()
    (root / 'rdp-stdin').write_text(data)
    if os.getenv('RDP_BLOCK'):
        (root / 'rdp-pid').write_text(str(os.getpid()))
        (root / 'rdp-ready').touch()
        time.sleep(30)
    sys.exit(int(os.getenv('RDP_EXIT', '0')))
elif name == 'timeout':
    sys.exit(int(os.getenv('RDP_NOT_READY', '0')))
elif name == 'hyprctl':
    print('[{"focused":true,"scale":1.5}]')
'''
        for name in ('docker', 'xfreerdp3', 'timeout', 'hyprctl', 'test'):
            path = tools / name
            path.write_text(mock)
            path.chmod(0o755)

    def cli(self, *args, ok=True, alias='win'):
        result = subprocess.run([str(REPO / 'bin/luna'), alias, *args], env=self.env,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        self.assertNotIn('private-test-secret', result.stdout + result.stderr)
        return result

    def commands(self):
        file = self.root / 'commands'
        return [json.loads(line) for line in file.read_text().splitlines()] if file.exists() else []

    def clear(self):
        (self.root / 'commands').write_text('')

    def assert_verified_stop(self):
        compose = ['docker', 'compose', '--project-name', 'luna-windows', '--file', str(self.config)]
        self.assertEqual(self.commands()[-4:], [
            [*compose, 'ps', '--all', '-q', 'windows'],
            ['docker', 'update', '--restart=no', 'mock-container'],
            [*compose, 'stop', '--timeout', '120', 'windows'],
            ['docker', 'inspect', '--format', STOP_INSPECT_FORMAT, 'mock-container'],
        ])

    def test_help_status_and_missing_install(self):
        self.assertIn('logs', self.cli().stdout)
        self.assertIn('not installed', self.cli('status', alias='windows').stdout)
        self.cli('start', ok=False)
        self.assertEqual(self.commands(), [])
        self.assertFalse((self.root / 'data/applications/luna-windows.desktop').exists())

    def test_interactive_install_prompts_and_retries_invalid_resources(self):
        master, slave = pty.openpty()
        try:
            os.write(master, b'1G\n8\n4\n128g\ntester\n')
            result = subprocess.run([str(REPO / 'bin/luna'), 'win', 'install'],
                                    env=self.env, stdin=slave, capture_output=True,
                                    text=True, timeout=15)
        finally:
            os.close(master)
            os.close(slave)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('minimum 2G', result.stderr)
        self.assertIn('RAM (GiB', result.stdout)
        config = self.config.read_text()
        for value in ('RAM_SIZE: "8G"', 'CPU_CORES: "4"', 'DISK_SIZE: "128G"', 'USERNAME: "tester"'):
            self.assertIn(value, config)

    def test_interactive_install_yes_skips_prompts(self):
        master, slave = pty.openpty()
        try:
            result = subprocess.run([str(REPO / 'bin/luna'), 'win', 'install', '--yes', '--ram', '8G'],
                                    env=self.env, stdin=slave, capture_output=True,
                                    text=True, timeout=15)
        finally:
            os.close(master)
            os.close(slave)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('press Enter', result.stdout)
        self.assertIn('RAM_SIZE: "8G"', self.config.read_text())
        self.assertIn('DISK_SIZE: "64G"', self.config.read_text())

    def test_install_resources_permissions_and_preservation(self):
        self.cli('install', '--ram', '8G', '--cpus', '4', '--disk', '128G')
        original = self.config.read_text()
        for value in ('RAM_SIZE: "8G"', 'CPU_CORES: "4"', 'DISK_SIZE: "128G"',
                      '127.0.0.1:3389:3389/tcp', '127.0.0.1:8006:8006', '$$'):
            self.assertIn(value, original)
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.config.parent.stat().st_mode & 0o777, 0o700)
        self.assertTrue((self.root / 'Windows').is_dir())
        self.cli('install', '--ram', '16G')
        self.assertEqual(self.config.read_text(), original)
        self.assertTrue(any(cmd[-3:] == ['up', '-d', 'windows'] for cmd in self.commands()))

    def test_desktop_entry_is_created_only_after_successful_install(self):
        entry = self.root / 'data/applications/luna-windows.desktop'
        self.env['DOCKER_UP_FAIL'] = '1'
        self.cli('install', ok=False)
        self.assertFalse(entry.exists())
        del self.env['DOCKER_UP_FAIL']
        self.cli('install')
        desktop = entry.read_text()
        self.assertIn('Name=Windows', desktop)
        self.assertIn('windows start', desktop)
        self.assertIn('Terminal=false', desktop)
        self.assertEqual(entry.stat().st_mode & 0o777, 0o644)

    def test_invalid_install_and_unavailable_docker_do_not_create_config(self):
        for args in [('--ram', '1G'), ('--cpus', '0'), ('--disk', '32G'), ('--username', 'bad\nname')]:
            self.cli('install', *args, ok=False)
            self.assertFalse(self.config.exists())
        self.env['DOCKER_FAIL'] = '1'
        self.cli('install', ok=False)
        self.assertFalse(self.config.exists())

    def test_install_waits_for_guest_before_success_and_launcher(self):
        self.env['RDP_NOT_READY'] = '1'
        result = self.cli('install', '--timeout', '1', ok=False)
        self.assertNotIn('installed successfully', result.stdout)
        self.assertFalse((self.config.parent / 'installed').exists())
        self.assertFalse((self.root / 'data/applications/luna-windows.desktop').exists())
        self.clear()
        result = self.cli('start', ok=False)
        self.assertIn('installation is not complete', result.stderr)
        self.assertFalse(any('up' in cmd for cmd in self.commands()))
        del self.env['RDP_NOT_READY']
        self.assertIn('installed successfully', self.cli('install').stdout)
        self.assertTrue((self.config.parent / 'installed').exists())

    def test_start_uses_private_stdin_and_stops_after_rdp(self):
        self.cli('install')
        self.clear()
        self.cli('start')
        commands = self.commands()
        self.assertFalse(any('up' in cmd or 'pull' in cmd for cmd in commands))
        self.assertTrue(any('--since' in cmd for cmd in commands))
        rdp = next(cmd for cmd in commands if cmd[0] == 'xfreerdp3')
        self.assertEqual(rdp, ['xfreerdp3', '/args-from:stdin'])
        arguments = (self.root / 'rdp-stdin').read_text().splitlines()
        for flag in ('-grab-keyboard', '/f', '/clipboard', '/scale:140', '/p:private-test-secret'):
            self.assertIn(flag, arguments)
        self.assertTrue(any(cmd[-4:] == ['stop', '--timeout', '120', 'windows'] for cmd in commands))
        self.assert_verified_stop()
        self.assertEqual(list(self.config.parent.glob('.rdp-*')), [])
        self.assertNotIn('private-test-secret', (self.root / 'commands').read_text())

    def test_keep_alive_and_failed_rdp(self):
        self.cli('install')
        self.clear()
        self.cli('start', '--keep-alive')
        self.assertFalse(any('stop' in cmd for cmd in self.commands()))
        self.assertFalse(any('update' in cmd for cmd in self.commands()))
        self.clear()
        self.env['RDP_EXIT'] = '2'
        self.cli('start', ok=False)
        self.assertTrue(any('stop' in cmd for cmd in self.commands()))
        self.assertEqual(list(self.config.parent.glob('.rdp-*')), [])

    def test_logs_status_and_stop_only_touch_existing_vm(self):
        self.cli('install')
        self.clear()
        self.cli('logs')
        self.cli('logs', '--no-follow', '--tail', '25')
        self.cli('status')
        self.cli('stop')
        commands = self.commands()
        self.assertTrue(any(cmd[-5:] == ['logs', '--tail', '100', '--follow', 'windows'] for cmd in commands))
        self.assertTrue(any(cmd[-4:] == ['logs', '--tail', '25', 'windows'] for cmd in commands))
        self.assertFalse(any('up' in cmd or 'down' in cmd or 'rm' in cmd for cmd in commands))
        self.assert_verified_stop()
        self.assertTrue(self.config.exists())

    def test_stop_and_session_cleanup_propagate_stop_failure(self):
        self.cli('install')
        self.env['DOCKER_STOP_FAIL'] = '1'
        for command in ['stop', 'start']:
            with self.subTest(command=command):
                self.clear()
                result = self.cli(command, ok=False)
                self.assertIn('Cannot stop Windows', result.stderr)
                self.assertNotIn('VM stopped.', result.stdout)
                self.assert_verified_stop()
                self.assertEqual(list(self.config.parent.glob('.rdp-*')), [])

    def test_stop_and_session_cleanup_reject_running_or_restarting_vm(self):
        self.cli('install')
        for state in ['true false no', 'false true no', 'false false always']:
            for command in ['stop', 'start']:
                with self.subTest(command=command, state=state):
                    self.clear()
                    self.env['DOCKER_STOP_STATE'] = state
                    result = self.cli(command, ok=False)
                    self.assertIn('shutdown is unverified', result.stderr)
                    self.assertNotIn('VM stopped.', result.stdout)
                    self.assert_verified_stop()
                    self.assertEqual(list(self.config.parent.glob('.rdp-*')), [])

    def test_stop_and_session_cleanup_still_stop_after_policy_update_failure(self):
        self.cli('install')
        self.env['DOCKER_UPDATE_FAIL'] = '1'
        for command in ['stop', 'start']:
            with self.subTest(command=command):
                self.clear()
                result = self.cli(command, ok=False)
                self.assertIn('Cannot disable automatic restart', result.stderr)
                self.assertNotIn('VM stopped.', result.stdout)
                self.assert_verified_stop()
                self.assertEqual(list(self.config.parent.glob('.rdp-*')), [])

    def test_stop_and_session_cleanup_propagate_inspect_failure(self):
        self.cli('install')
        self.env['DOCKER_STOP_INSPECT_FAIL'] = '1'
        for command in ['stop', 'start']:
            with self.subTest(command=command):
                self.clear()
                result = self.cli(command, ok=False)
                self.assertIn('Cannot verify Windows shutdown', result.stderr)
                self.assertNotIn('VM stopped.', result.stdout)
                self.assert_verified_stop()
                self.assertEqual(list(self.config.parent.glob('.rdp-*')), [])

    def test_start_is_foreground_and_second_session_is_rejected(self):
        self.cli('install')
        self.env['RDP_BLOCK'] = '1'
        process = subprocess.Popen([str(REPO / 'bin/luna'), 'win', 'start'], env=self.env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 5
            while not (self.root / 'rdp-ready').exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue((self.root / 'rdp-ready').exists())
            self.assertIsNone(process.poll())
            self.cli('start', ok=False)
            rdp = next(cmd for cmd in self.commands() if cmd[0] == 'xfreerdp3')
            self.assertEqual(rdp[-1], '/args-from:stdin')
        finally:
            # End only the mocked FreeRDP child; normal session cleanup then stops Docker.
            pid_file = self.root / 'rdp-pid'
            if pid_file.exists():
                os.kill(int(pid_file.read_text()), signal.SIGTERM)
            process.wait(timeout=5)
        self.assertTrue(any('stop' in cmd for cmd in self.commands()))

    def test_delete_removes_vm_data_but_preserves_shared_files(self):
        self.cli('install')
        disk = self.root / 'data/luna/windows/storage/disk.img'
        disk.write_text('VM disk')
        shared = self.root / 'Windows/keep.txt'
        shared.write_text('keep')
        self.clear()
        self.cli('delete', ok=False)
        self.assertTrue(disk.exists())
        self.assertFalse(any('down' in cmd for cmd in self.commands()))
        self.cli('delete', '--yes')
        self.assertFalse(self.config.parent.exists())
        self.assertFalse(disk.parent.exists())
        self.assertFalse((self.root / 'data/applications/luna-windows.desktop').exists())
        self.assertEqual(shared.read_text(), 'keep')
        self.assertTrue(any('down' in cmd for cmd in self.commands()))

    def test_delete_confirmation_can_cancel_or_confirm(self):
        self.cli('install')
        for answer, removed in [(b'no\n', False), (b'delete\n', True)]:
            master, slave = pty.openpty()
            try:
                os.write(master, answer)
                result = subprocess.run([str(REPO / 'bin/luna'), 'win', 'delete'],
                                        env=self.env, stdin=slave, capture_output=True,
                                        text=True, timeout=15)
            finally:
                os.close(master)
                os.close(slave)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('Type delete to confirm', result.stdout)
            self.assertEqual(not self.config.exists(), removed)

    def test_delete_preserves_data_when_docker_removal_fails(self):
        self.cli('install')
        self.env['DOCKER_DOWN_FAIL'] = '1'
        self.cli('delete', '--yes', ok=False)
        self.assertTrue(self.config.exists())
        self.assertTrue((self.root / 'data/luna/windows/storage').exists())
        self.assertTrue((self.root / 'data/applications/luna-windows.desktop').exists())

    def test_delete_refuses_symlink_storage(self):
        self.cli('install')
        storage = self.root / 'data/luna/windows/storage'
        storage.rmdir()
        storage.symlink_to(self.root / 'Windows', target_is_directory=True)
        self.clear()
        self.cli('delete', '--yes', ok=False)
        self.assertTrue(self.config.exists())
        self.assertFalse(any('down' in cmd for cmd in self.commands()))

    def test_readiness_requires_rdp_response_not_just_open_tcp(self):
        for response, ready in [(b'', False), (b'HTTP/1.1 200 OK', False),
                                (bytes.fromhex('030000130ed000001234000200080003000000'), True)]:
            with self.subTest(response=response), socket.socket() as server:
                server.bind(('127.0.0.1', 0))
                server.listen(1)
                server.settimeout(3)
                requests = []

                def respond():
                    with server.accept()[0] as client:
                        client.settimeout(3)
                        requests.append(client.recv(1024))
                        client.sendall(response)

                thread = threading.Thread(target=respond)
                thread.start()
                try:
                    result = subprocess.run(
                        ['timeout', '2', 'bash', str(REPO / 'src/luna-cli/windows/rdp-ready.sh'),
                         str(server.getsockname()[1])], capture_output=True, timeout=4)
                finally:
                    thread.join(timeout=4)
                self.assertEqual(result.returncode == 0, ready)
                self.assertEqual(requests, [bytes.fromhex('030000130ee000000000000100080003000000')])

    def test_rdp_timeout_leaves_setup_running_and_cleans_credentials(self):
        self.cli('install')
        self.clear()
        self.env['RDP_NOT_READY'] = '1'
        self.cli('start', '--timeout', '1', ok=False)
        self.assertFalse(any('stop' in cmd for cmd in self.commands()))
        self.assertEqual(list(self.config.parent.glob('.rdp-*')), [])


if __name__ == '__main__':
    unittest.main()
