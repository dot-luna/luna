"""Exercise setup log formatting with local commands, pipes, and terminal output."""

import errno
import json
import os
from pathlib import Path
import pty
import re
import select
import shutil
import subprocess
import sys
import tempfile
import time
import unittest


REPO = Path(__file__).resolve().parents[1]
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
STAMP = r"\[\d{2}:\d{2}:\d{2}\]"
ARGUMENTS = ["space value", "O'Reilly", "$HOME; $(echo unsafe)"]


class LoggingTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna logging '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.env = dict(os.environ, TERM="xterm-256color", HOME=str(self.root),
                        TEST_PYTHON=sys.executable,
                        TEST_COMMON_LUA=str(REPO / "lib/common.lua"))
        for name in ("LUNA_COLOR", "NO_COLOR", "BASH_ENV", "ENV", "LUA_INIT",
                     "TEST_TOOL_COLOR", "TEST_TOOL_STATUS", "TEST_TOOL_READ_STDIN"):
            self.env.pop(name, None)
        self.command = self.root / "command probe.py"
        self.env["TEST_COMMAND"] = str(self.command)
        self.command.write_text('''
import json, os, sys
if os.environ.get("TEST_TOOL_READ_STDIN") == "1":
    print("ready for input", flush=True)
    print("answer: " + sys.stdin.readline().rstrip("\\n"), flush=True)
print("arguments: " + json.dumps(sys.argv[1:]), flush=True)
diagnostic = "tool diagnostic"
if os.environ.get("TEST_TOOL_COLOR") == "1":
    diagnostic = "\\x1b[31m" + diagnostic + "\\x1b[0m"
print(diagnostic, file=sys.stderr, flush=True)
print("partial final line", end="", flush=True)
sys.exit(int(os.environ.get("TEST_TOOL_STATUS", "0")))
''')

    def run_code(self, source, *, terminal=False, input=""):
        arguments = self.interpreter_arguments(source)
        if not terminal:
            return subprocess.run(arguments, env=self.env, cwd=self.root,
                                  input=input, text=True, capture_output=True,
                                  timeout=10)

        # A small output fixture makes terminal color detection testable without
        # a real user session, package manager, or additional browser/process tool.
        master, slave = pty.openpty()
        try:
            result = subprocess.run(arguments, env=self.env, cwd=self.root,
                                    input=input, text=True, stdout=slave,
                                    stderr=slave, timeout=10)
            os.close(slave)
            slave = None
            chunks = []
            while True:
                try:
                    chunk = os.read(master, 65536)
                except OSError as error:
                    if error.errno != errno.EIO:
                        raise
                    break
                if not chunk:
                    break
                chunks.append(chunk)
            output = b"".join(chunks).decode().replace("\r\n", "\n")
            return subprocess.CompletedProcess(arguments, result.returncode, output, "")
        finally:
            os.close(master)
            if slave is not None:
                os.close(slave)

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def assert_streaming_stdin(self, source):
        self.env["TEST_TOOL_READ_STDIN"] = "1"
        with subprocess.Popen(self.interpreter_arguments(source), env=self.env,
                              cwd=self.root, stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as process:
            prefix = b""
            try:
                # Do not answer until the child's flushed line reaches the caller.
                # A formatter buffering until exit would deadlock this exchange.
                deadline = time.monotonic() + 5
                while b"ready for input\n" not in prefix:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not select.select([process.stdout], [], [], remaining)[0]:
                        self.fail("Command output was buffered while waiting for input: " + repr(prefix))
                    chunk = os.read(process.stdout.fileno(), 4096)
                    self.assertTrue(chunk, "Command stopped before requesting input: " + repr(prefix))
                    prefix += chunk
                self.assertIsNone(process.poll())
                tail, _ = process.communicate(b"answer with spaces\n", timeout=5)
                output = (prefix + tail).decode()
                self.assertEqual(process.returncode, 0, output)
                self.assertIn("answer: answer with spaces", output)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()

    def assert_wrapped_command(self, output):
        plain = ANSI.sub("", output)
        self.assertRegex(plain, r"before\n\n[ \t]+arguments: ")
        self.assertRegex(plain, r"(?m)^[ \t]+tool diagnostic$")
        self.assertRegex(plain, r"partial final line\n\n" + STAMP + r" \[INFO\] after")
        argument_line = next(line.strip() for line in plain.splitlines()
                             if line.strip().startswith("arguments: "))
        self.assertEqual(json.loads(argument_line.removeprefix("arguments: ")), ARGUMENTS)


@unittest.skipUnless(shutil.which("bash"), "Bash is required")
class BashLoggingTests(LoggingTestCase):
    def interpreter_arguments(self, source):
        return ["bash", "-c", 'set -euo pipefail\nsource "$1"\n' + source,
                "logging-test", str(REPO / "lib/common.sh")]

    def command_source(self):
        return '''luna_run "$TEST_PYTHON" "$TEST_COMMAND" "space value" "O'Reilly" '$HOME; $(echo unsafe)' '''

    def test_labels_have_timestamps_and_literal_messages(self):
        result = self.run_code('''
luna_info 'ordinary 100% $HOME'
luna_success 'completed'
luna_warn 'review this'
luna_error 'failed'
luna_step 'next step'
''')
        self.assert_success(result)
        for label, message in (("INFO", "ordinary 100% $HOME"), ("OK", "completed"),
                               ("WARN", "review this"), ("STEP", "next step")):
            self.assertRegex(result.stdout + result.stderr,
                             STAMP + r" \[" + label + r"\] " + re.escape(message))
        self.assertRegex(result.stderr, STAMP + r" \[ERROR\] failed")
        self.assertNotIn("\x1b", result.stdout + result.stderr)

    def test_command_combines_streams_and_preserves_arguments_and_partial_line(self):
        result = self.run_code('luna_info before\n' + self.command_source() + '\nluna_info after')
        self.assert_success(result)
        self.assert_wrapped_command(result.stdout)
        self.assertEqual(result.stderr, "")

    def test_command_streams_output_and_preserves_stdin(self):
        self.assert_streaming_stdin(self.command_source())

    def test_command_failure_propagates_exact_status(self):
        self.env["TEST_TOOL_STATUS"] = "37"
        result = self.run_code(self.command_source() + '\nprintf "must not run\\n"')
        self.assertEqual(result.returncode, 37, result.stdout + result.stderr)
        self.assertIn("partial final line", result.stdout)
        self.assertNotIn("must not run", result.stdout)

        # Conditionals disable errexit inside shell functions; their explicit
        # return status must still represent the failed child command.
        result = self.run_code('if ' + self.command_source() + '; then\nexit 99\nelse\nexit "$?"\nfi')
        self.assertEqual(result.returncode, 37, result.stdout + result.stderr)

    def test_color_modes(self):
        for overrides, terminal, colored in (
                ({}, False, False), ({}, True, True),
                ({"LUNA_COLOR": "1"}, False, True),
                ({"LUNA_COLOR": "0"}, True, False),
                ({"LUNA_COLOR": "1", "NO_COLOR": "yes"}, True, False),
                ({"TERM": "dumb"}, True, False)):
            with self.subTest(overrides=overrides, terminal=terminal):
                original = self.env.copy()
                self.env.update(overrides)
                try:
                    result = self.run_code("luna_info color-check", terminal=terminal)
                    self.assert_success(result)
                    self.assertEqual("\x1b[" in result.stdout, colored, result.stdout)
                finally:
                    self.env = original

    def test_tool_color_is_replaced_with_gray_without_leaking(self):
        self.env.update(LUNA_COLOR="1", TEST_TOOL_COLOR="1")
        result = self.run_code('luna_info before\n' + self.command_source() + '\nluna_info after')
        self.assert_success(result)
        self.assert_wrapped_command(result.stdout)
        self.assertIn("\x1b[90m", result.stdout)
        self.assertNotIn("\x1b[31m", result.stdout)
        diagnostic = next(line for line in result.stdout.splitlines() if "tool diagnostic" in line)
        self.assertIn("\x1b[0m", diagnostic)


@unittest.skipUnless(Path("/usr/bin/lua").is_file(), "System Lua is required")
class LuaLoggingTests(LoggingTestCase):
    def interpreter_arguments(self, source):
        return ["/usr/bin/lua", "-E", "-e",
                'local common = dofile(os.getenv("TEST_COMMON_LUA"))\n' + source]

    def command_source(self):
        return '''common.run({ os.getenv("TEST_PYTHON"), os.getenv("TEST_COMMAND"), "space value", "O'Reilly", "$HOME; $(echo unsafe)" })'''

    def test_defaults_remain_plain(self):
        self.env["LUNA_COLOR"] = "1"
        result = self.run_code('common.info("ordinary")\ncommon.error("failure")')
        self.assert_success(result)
        self.assertEqual(result.stdout, "ordinary\n")
        self.assertEqual(result.stderr, "failure\n")

    def test_setup_logging_opts_in_to_labels_and_command_formatting(self):
        result = self.run_code('common.setup_logging()\ncommon.info("before")\n'
                               + self.command_source() + '\ncommon.info("after")\ncommon.error("failed")')
        self.assert_success(result)
        self.assertRegex(result.stdout, STAMP + r" \[INFO\] before")
        self.assertRegex(result.stderr, STAMP + r" \[ERROR\] failed")
        self.assert_wrapped_command(result.stdout)

    def test_command_streams_output_and_preserves_stdin(self):
        self.assert_streaming_stdin('common.setup_logging()\n' + self.command_source())

    def test_command_failure_is_not_hidden_by_formatter(self):
        self.env["TEST_TOOL_STATUS"] = "37"
        result = self.run_code('common.setup_logging()\n' + self.command_source()
                               + '\ncommon.info("must not run")')
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("partial final line", result.stdout)
        self.assertNotIn("must not run", result.stdout)
        self.assertIn("Command failed", result.stderr)

    def test_capture_and_quiet_probes_remain_unformatted(self):
        result = self.run_code('''
common.setup_logging()
local output, ok, code = common.capture({ "sh", "-c", "printf 'raw output'; exit 23" }, true)
assert(output == "raw output", output)
assert(not ok and code == 23)
assert(common.succeeds({ "sh", "-c", "printf ignored; printf ignored >&2; exit 0" }))
assert(not common.succeeds({ "sh", "-c", "printf ignored; exit 17" }))
io.stdout:write("verified\\n")
''')
        self.assert_success(result)
        self.assertEqual(result.stdout, "verified\n")
        self.assertEqual(result.stderr, "")

    def test_color_modes(self):
        for overrides, terminal, colored in (
                ({}, False, False), ({}, True, True),
                ({"LUNA_COLOR": "1"}, False, True),
                ({"LUNA_COLOR": "0"}, True, False),
                ({"LUNA_COLOR": "1", "NO_COLOR": "yes"}, True, False),
                ({"TERM": "dumb"}, True, False)):
            with self.subTest(overrides=overrides, terminal=terminal):
                original = self.env.copy()
                self.env.update(overrides)
                try:
                    result = self.run_code('common.setup_logging()\ncommon.info("color-check")',
                                           terminal=terminal)
                    self.assert_success(result)
                    self.assertEqual("\x1b[" in result.stdout, colored, result.stdout)
                finally:
                    self.env = original

    def test_tool_color_is_replaced_with_gray_without_leaking(self):
        self.env.update(LUNA_COLOR="1", TEST_TOOL_COLOR="1")
        result = self.run_code('common.setup_logging()\ncommon.info("before")\n'
                               + self.command_source() + '\ncommon.info("after")')
        self.assert_success(result)
        self.assert_wrapped_command(result.stdout)
        self.assertIn("\x1b[90m", result.stdout)
        self.assertNotIn("\x1b[31m", result.stdout)
        diagnostic = next(line for line in result.stdout.splitlines() if "tool diagnostic" in line)
        self.assertIn("\x1b[0m", diagnostic)


if __name__ == "__main__":
    unittest.main()
