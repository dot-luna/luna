"""Verify VM shutdown and project isolation using a stateful Docker substitute."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]
INSPECT_FORMAT = '{{.State.Running}} {{.State.Restarting}} {{.HostConfig.RestartPolicy.Name}}'


class VmStopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luna vm stop '$ ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        tools = self.root / 'bin'
        tools.mkdir()
        self.config = self.root / 'compose file.yml'
        self.config.write_text('services: {}\n')
        self.disk = self.root / 'disk.img'
        self.disk.write_text('persistent VM disk')
        self.env = dict(os.environ, PATH=str(tools) + ':' + os.environ['PATH'],
                        TEST_ROOT=str(self.root), TEST_CONFIG=str(self.config))
        self.initial = {
            'windows-vm': self.container('luna-windows', 'windows'),
            'macos-vm': self.container('luna-macos', 'macos'),
            'other-windows': self.container('another-project', 'windows'),
            'other-macos': self.container('another-project', 'macos'),
            'windows-sidecar': self.container('luna-windows', 'sidecar'),
            'macos-sidecar': self.container('luna-macos', 'sidecar'),
        }
        self.write_state(self.initial)
        docker = tools / 'docker'
        docker.write_text('''#!/usr/bin/python3
import json, os, pathlib, sys
root = pathlib.Path(os.environ['TEST_ROOT'])
args = sys.argv[1:]
with (root / 'commands').open('a') as out:
    out.write(json.dumps(args) + '\\n')
state_file = root / 'state.json'
state = json.loads(state_file.read_text())

def save():
    state_file.write_text(json.dumps(state))

def fail(message):
    print(message, file=sys.stderr)
    sys.exit(1)

if args[:2] == ['compose', '--project-name'] and args[3] == '--file':
    assert args[4] == os.environ['TEST_CONFIG'], args
    project = args[2]
    operation = args[5:]
    targets = [key for key, value in state.items()
               if value['project'] == project and value['service'] == operation[-1]]
    if operation == ['ps', '--all', '-q', operation[-1]]:
        for key in targets:
            print(key)
        if os.getenv('TEST_QUERY_FAIL'):
            fail('stub query failure')
    elif operation == ['stop', '--timeout', '120', operation[-1]]:
        if os.getenv('TEST_STOP_FAIL'):
            fail('stub stop failure')
        overrides = json.loads(os.getenv('TEST_STOP_STATES', '{}'))
        for key in targets:
            state[key].update(running=False, restarting=False)
            state[key].update(overrides.get(key, {}))
        save()
    else:
        fail('Unexpected Compose operation: ' + repr(args))
elif args[:2] == ['update', '--restart=no'] and len(args) > 2:
    if os.getenv('TEST_UPDATE_FAIL'):
        fail('stub update failure')
    for key in args[2:]:
        state[key]['restart'] = 'no'
    save()
elif args[:2] == ['inspect', '--format'] and len(args) == 4:
    assert args[2] == '{{.State.Running}} {{.State.Restarting}} {{.HostConfig.RestartPolicy.Name}}'
    if args[3] == os.getenv('TEST_INSPECT_FAIL'):
        fail('stub inspect failure')
    value = state[args[3]]
    print(os.getenv('TEST_INSPECT_OUTPUT',
          str(value['running']).lower() + ' ' + str(value['restarting']).lower()
          + ' ' + value['restart']))
else:
    fail('Unexpected Docker operation: ' + repr(args))
''')
        docker.chmod(0o755)

    def container(self, project, service):
        return dict(project=project, service=service, running=True,
                    restarting=False, restart='always')

    def write_state(self, state):
        (self.root / 'state.json').write_text(json.dumps(state))

    def state(self):
        return json.loads((self.root / 'state.json').read_text())

    def commands(self):
        path = self.root / 'commands'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def compose(self, service, *args):
        return ['compose', '--project-name', 'luna-' + service,
                '--file', str(self.config), *args]

    def run_helper(self, *args):
        return subprocess.run(['/bin/bash', str(REPO / 'lib/vm-stop.sh'), *args],
                              env=self.env, cwd=self.root, capture_output=True,
                              text=True, timeout=5)

    def stop(self, service='windows', *extra, ok=True):
        result = self.run_helper(str(self.config), service, *extra)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        if not ok:
            self.assertNotIn('VM stopped.', result.stdout)
            self.assertIn('luna ' + service + ' stop', result.stderr)
        return result

    def assert_shutdown_sequence(self, service='windows', ids=None):
        ids = ids or [service + '-vm']
        self.assertEqual(self.commands(), [
            self.compose(service, 'ps', '--all', '-q', service),
            ['update', '--restart=no', *ids],
            self.compose(service, 'stop', '--timeout', '120', service),
            *[['inspect', '--format', INSPECT_FORMAT, key] for key in ids],
        ])

    def test_stops_only_selected_vm_and_preserves_data(self):
        for service, label in [('windows', 'Windows'), ('macos', 'macOS')]:
            with self.subTest(service=service):
                self.write_state(self.initial)
                (self.root / 'commands').write_text('')
                result = self.stop(service)
                self.assertIn(label + ' VM stopped.', result.stdout)
                self.assert_shutdown_sequence(service)
                expected = {key: value.copy() for key, value in self.initial.items()}
                expected[service + '-vm'].update(running=False, restarting=False, restart='no')
                self.assertEqual(self.state(), expected)
                self.assertEqual(self.disk.read_text(), 'persistent VM disk')
                self.assertEqual(self.config.read_text(), 'services: {}\n')

    def test_multiple_containers_are_all_updated_and_verified(self):
        state = self.state()
        state['second-vm'] = self.container('luna-windows', 'windows')
        self.write_state(state)
        self.stop()
        self.assert_shutdown_sequence(ids=['windows-vm', 'second-vm'])
        for key in ['windows-vm', 'second-vm']:
            self.assertFalse(self.state()[key]['running'])
            self.assertEqual(self.state()[key]['restart'], 'no')

    def test_existing_stopped_container_has_restart_disabled(self):
        state = self.state()
        state['windows-vm']['running'] = False
        self.write_state(state)
        self.stop()
        self.assert_shutdown_sequence()
        self.assertEqual(self.state()['windows-vm']['restart'], 'no')

    def test_no_container_is_idempotent(self):
        state = self.state()
        del state['windows-vm']
        self.write_state(state)
        for _ in range(2):
            self.assertIn('No Windows VM container', self.stop().stdout)
        self.assertEqual(self.commands(), [self.compose('windows', 'ps', '--all', '-q', 'windows')] * 2)
        self.assertEqual(self.state(), state)
        self.assertEqual(self.disk.read_text(), 'persistent VM disk')

    def test_extra_arguments_are_ignored(self):
        self.stop('windows', '--project-name', 'another-project', '$(exit 99)')
        self.assert_shutdown_sequence()

    def test_update_failure_still_stops_and_fails(self):
        self.env['TEST_UPDATE_FAIL'] = '1'
        result = self.stop(ok=False)
        self.assertIn('Cannot disable automatic restart', result.stderr)
        self.assert_shutdown_sequence()
        self.assertFalse(self.state()['windows-vm']['running'])
        self.assertEqual(self.state()['windows-vm']['restart'], 'always')

    def test_failed_update_is_not_hidden_by_good_final_state(self):
        state = self.state()
        state['windows-vm']['restart'] = 'no'
        self.write_state(state)
        self.env['TEST_UPDATE_FAIL'] = '1'
        self.stop(ok=False)
        self.assert_shutdown_sequence()
        self.assertFalse(self.state()['windows-vm']['running'])

    def test_stop_failure_is_reported_and_still_verified(self):
        self.env['TEST_STOP_FAIL'] = '1'
        result = self.stop(ok=False)
        self.assertIn('Cannot stop Windows', result.stderr)
        self.assert_shutdown_sequence()
        self.assertTrue(self.state()['windows-vm']['running'])

    def test_failed_stop_is_not_hidden_by_good_final_state(self):
        state = self.state()
        state['windows-vm']['running'] = False
        self.write_state(state)
        self.env['TEST_STOP_FAIL'] = '1'
        self.stop(ok=False)
        self.assert_shutdown_sequence()
        self.assertEqual(self.state()['windows-vm']['restart'], 'no')

    def test_running_or_restarting_container_is_rejected(self):
        for running, restarting in [(True, False), (False, True), (True, True)]:
            with self.subTest(running=running, restarting=restarting):
                self.env['TEST_STOP_STATES'] = json.dumps({
                    'windows-vm': dict(running=running, restarting=restarting),
                })
                self.assertIn('shutdown is unverified', self.stop(ok=False).stderr)

    def test_restart_policy_must_stay_disabled(self):
        for policy in ['always', 'unless-stopped', 'on-failure', '']:
            with self.subTest(policy=policy):
                self.env['TEST_STOP_STATES'] = json.dumps({'windows-vm': dict(restart=policy)})
                self.assertIn('shutdown is unverified', self.stop(ok=False).stderr)

    def test_inspect_failure_does_not_skip_remaining_containers(self):
        state = self.state()
        state['second-vm'] = self.container('luna-windows', 'windows')
        self.write_state(state)
        self.env['TEST_INSPECT_FAIL'] = 'windows-vm'
        result = self.stop(ok=False)
        self.assertIn('Cannot verify Windows shutdown', result.stderr)
        self.assert_shutdown_sequence(ids=['windows-vm', 'second-vm'])

    def test_bad_state_does_not_skip_remaining_containers(self):
        state = self.state()
        state['second-vm'] = self.container('luna-windows', 'windows')
        self.write_state(state)
        self.env['TEST_STOP_STATES'] = json.dumps({'windows-vm': dict(running=True)})
        self.stop(ok=False)
        self.assert_shutdown_sequence(ids=['windows-vm', 'second-vm'])

    def test_query_failure_does_not_mutate_containers(self):
        self.env['TEST_QUERY_FAIL'] = '1'
        result = self.stop(ok=False)
        self.assertIn('Check docker info', result.stderr)
        self.assertEqual(self.commands(), [self.compose('windows', 'ps', '--all', '-q', 'windows')])
        self.assertEqual(self.state(), self.initial)

    def test_missing_arguments_and_invalid_service_are_rejected(self):
        for args in [(), (str(self.config),), (str(self.config), 'other'), ('', 'windows')]:
            with self.subTest(args=args):
                result = self.run_helper(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(result.stderr)
                self.assertEqual(self.commands(), [])

    def test_missing_compose_file_is_rejected(self):
        self.config.unlink()
        result = self.run_helper(str(self.config), 'windows')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Restore the Compose file', result.stderr)
        self.assertEqual(self.commands(), [])

    def test_missing_docker_is_actionable(self):
        (self.root / 'bin/docker').unlink()
        self.env['PATH'] = str(self.root / 'bin')
        result = self.run_helper(str(self.config), 'windows')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Docker is required', result.stderr)
        self.assertEqual(self.commands(), [])

    def test_malformed_inspect_output_is_rejected(self):
        for output in ['', 'false false', 'false false no\nfalse false no']:
            with self.subTest(output=output):
                self.env['TEST_INSPECT_OUTPUT'] = output
                self.assertIn('shutdown is unverified', self.stop(ok=False).stderr)


if __name__ == '__main__':
    unittest.main()
