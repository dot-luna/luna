"""Run the streamed installer against local Git fixtures and fake package tools."""

import fcntl
import json
import os
from pathlib import Path
import pty
import re
import shutil
import subprocess
import sys
import tempfile
import termios
import unittest


REPO = Path(__file__).resolve().parents[1]
INSTALLER = REPO / "scripts/install.sh"
ORIGIN = "https://github.com/dot-luna/luna.git"


@unittest.skipIf(os.geteuid() == 0, "The installer requires a real non-root user")
class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.git = shutil.which("git")
        self.bash = shutil.which("bash")
        if not self.git or not self.bash:
            self.skipTest("Git and Bash are needed")

        self.temporary = tempfile.TemporaryDirectory(prefix="luna installer '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home with spaces"
        self.home.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.remote = self.root / "remote"
        self.destination = self.home / ".local/src/luna"
        self.calls_file = self.root / "calls.jsonl"
        self.setup_file = self.root / "setup.jsonl"
        self.env = dict(
            os.environ,
            HOME=str(self.home),
            PATH=str(self.bin) + ":" + os.environ["PATH"],
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL=str(self.root / "gitconfig"),
            GIT_TERMINAL_PROMPT="0",
            TEST_ROOT=str(self.root),
            TEST_GIT=self.git,
            TEST_PYTHON=sys.executable,
            BASH_ENV=str(self.root / "bash-env"),
            NO_COLOR="1",
        )
        for name in ("XDG_STATE_HOME", "TEST_BOOTSTRAP_GIT", "TEST_SETUP_STATUS", "TEST_SETUP_COLOR",
                     "TEST_TOOL_LOCALE"):
            self.env.pop(name, None)

        # Override only OS discovery and Git availability; never mutate the host.
        (self.root / "bash-env").write_text('''
source() {
    if [[ "$1" == /etc/os-release ]]; then
        ID=arch
    else
        builtin source "$@"
    fi
}
command() {
    if [[ "$1" == -v && "${2:-}" == git && "${TEST_BOOTSTRAP_GIT:-}" == 1 && ! -f "$TEST_ROOT/git-installed" ]]; then
        return 1
    fi
    builtin command "$@"
}
''')

        backend = f"#!{sys.executable}\n" + '''
import json, os, pathlib, sys
root = pathlib.Path(os.environ["TEST_ROOT"])
tool = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with (root / "calls.jsonl").open("a") as output:
    output.write(json.dumps([tool, *args]) + "\\n")
if tool == "git":
    if args and args[0] == "clone" and os.environ.get("TEST_TOOL_LOCALE") == "1":
        print("Fixture clone locale: " + os.environ["LC_ALL"], flush=True)
        print("\\x1b[31mFixture Unicode café — काठमाडौं\\x1b[0m", flush=True)
    os.execv(os.environ["TEST_GIT"], ["git", *args])
elif tool == "sudo":
    if args == ["-v"]:
        sys.exit(0)
    if not args or args[0] != "pacman":
        sys.exit("Unexpected sudo command: " + repr(args))
    os.execv(str(root / "bin/pacman"), ["pacman", *args[1:]])
elif tool == "pacman":
    if args != ["-Syu", "--needed", "--noconfirm", "--", "git"]:
        sys.exit("Unexpected pacman command: " + repr(args))
    (root / "git-installed").touch()
'''
        for name in ("sudo", "pacman", "git"):
            path = self.bin / name
            path.write_text(backend)
            path.chmod(0o755)

        (self.root / "setup-probe.py").write_text('''
import json, os, pathlib, sys
print("Fixture setup prompt: ", end="", flush=True)
answer = sys.stdin.readline().strip()
with (pathlib.Path(os.environ["TEST_ROOT"]) / "setup.jsonl").open("a") as output:
    output.write(json.dumps({"cwd": os.getcwd(), "args": sys.argv[1:],
                             "tty": sys.stdin.isatty(), "answer": answer}) + "\\n")
if answer != "yes" or not sys.stdin.isatty():
    sys.exit("Setup did not receive terminal input")
print("Fixture setup stdout")
print("Fixture setup stderr", file=sys.stderr)
if os.environ.get("TEST_TOOL_LOCALE") == "1":
    print("Fixture setup locale: " + os.environ["LC_ALL"], flush=True)
if os.environ.get("TEST_SETUP_COLOR") == "1":
    print("\\x1b[31mFixture colored output\\x1b[0m")
    print("\\x1b[32mFixture colored tail\\x1b[0m", end="", flush=True)
sys.exit(int(os.environ.get("TEST_SETUP_STATUS", "0")))
''')

        self.git_run("init", "--quiet", "--initial-branch=master", str(self.remote))
        self.git_run("-C", str(self.remote), "config", "user.name", "Installer Test")
        self.git_run("-C", str(self.remote), "config", "user.email", "installer@example.invalid")
        (self.remote / "scripts").mkdir()
        (self.remote / "scripts/setup.sh").write_text(
            '#!/usr/bin/env bash\nexec "$TEST_PYTHON" "$TEST_ROOT/setup-probe.py" "$@"\n')
        self.git_run("-C", str(self.remote), "add", ".")
        self.git_run("-C", str(self.remote), "commit", "--quiet", "-m", "Fixture setup")
        self.git_run("-C", str(self.remote), "branch", "feature/installer")
        self.git_run("-C", str(self.remote), "tag", "v1.2.3")

        # Git performs real cloning locally while retaining the production origin URL.
        self.git_run("config", "--global", f"url.{self.remote.as_uri()}.insteadOf", ORIGIN)

    def git_run(self, *args):
        result = subprocess.run([self.git, *args], env=self.env, cwd=self.root,
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def run_installer(self, *args, terminal=True):
        master = slave = None
        options = {"start_new_session": True}
        if terminal:
            master, slave = pty.openpty()

            def attach_terminal():
                os.setsid()
                fcntl.ioctl(slave, termios.TIOCSCTTY, 0)

            options = {"preexec_fn": attach_terminal, "pass_fds": (slave,)}

        # The script arrives through a pipe, exactly as in curl ... | bash -s -- ... .
        try:
            with subprocess.Popen([self.bash, "-s", "--", *args], env=self.env,
                                  cwd=self.root, stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  **options) as process:
                if master is not None:
                    os.write(master, b"yes\nyes\nyes\nyes\n")
                try:
                    output, _ = process.communicate(INSTALLER.read_bytes(), timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    output, _ = process.communicate()
                    self.fail("Installer timed out:\n" + output.decode(errors="replace"))
                return subprocess.CompletedProcess(process.args, process.returncode,
                                                   output.decode(errors="replace"))
        finally:
            for descriptor in (master, slave):
                if descriptor is not None:
                    os.close(descriptor)

    def calls(self, tool):
        if not self.calls_file.exists():
            return []
        return [entry for line in self.calls_file.read_text().splitlines()
                if (entry := json.loads(line))[0] == tool]

    def setups(self):
        if not self.setup_file.exists():
            return []
        return [json.loads(line) for line in self.setup_file.read_text().splitlines()]

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("[OK] Luna setup completed.", result.stdout)
        self.assertEqual(list(self.destination.parent.glob("luna.luna-backup*")), [])

    def assert_refused(self, result):
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("[OK] Luna setup completed.", result.stdout)

    def test_default_clone_and_logs_preserve_terminal_input(self):
        self.assert_success(self.run_installer())
        self.assertEqual(self.git_run("-C", str(self.destination), "branch", "--show-current"), "master")
        self.assertEqual(self.git_run("-C", str(self.destination), "config", "remote.origin.url"), ORIGIN)
        self.assertEqual(self.setups(), [{"cwd": str(self.destination), "args": [],
                                         "tty": True, "answer": "yes"}])
        self.assertEqual(self.calls("pacman"), [])
        logs = list((self.home / ".local/state/luna").glob("install-*.log"))
        self.assertEqual(len(logs), 1)
        log = logs[0].read_text()
        self.assertIn("Fixture setup stdout", log)
        self.assertIn("Fixture setup stderr", log)

    def test_selected_branch(self):
        self.assert_success(self.run_installer("--ref", "feature/installer"))
        self.assertEqual(self.git_run("-C", str(self.destination), "branch", "--show-current"),
                         "feature/installer")

    def test_selected_tag_replaces_detached_checkout(self):
        self.assert_success(self.run_installer("--ref", "v1.2.3"))
        self.assertEqual(self.git_run("-C", str(self.destination), "branch", "--show-current"), "")
        self.assertEqual(self.git_run("-C", str(self.destination), "describe", "--tags", "--exact-match"),
                         "v1.2.3")
        self.assert_success(self.run_installer("--ref", "v1.2.3"))
        self.assertEqual(len(self.setups()), 2)
        self.assertEqual(len([call for call in self.calls("git") if "clone" in call]), 2)
        self.assertEqual(self.git_run("-C", str(self.destination), "describe", "--tags", "--exact-match"),
                         "v1.2.3")

    def test_annotated_tag_replaces_checkout_with_its_commit(self):
        self.git_run("-C", str(self.remote), "tag", "-a", "v2.0.0", "-m", "Release fixture")
        self.assert_success(self.run_installer("--ref", "v2.0.0"))
        self.assertEqual(self.git_run("-C", str(self.destination), "rev-parse", "HEAD"),
                         self.git_run("-C", str(self.remote), "rev-parse", "v2.0.0^{commit}"))
        self.assert_success(self.run_installer("--ref", "v2.0.0"))
        self.assertEqual(len(self.setups()), 2)
        self.assertEqual(self.git_run("-C", str(self.destination), "rev-parse", "HEAD"),
                         self.git_run("-C", str(self.remote), "rev-parse", "v2.0.0^{commit}"))

    def test_unknown_ref_stops_before_setup(self):
        self.assert_refused(self.run_installer("--ref", "missing-version"))
        self.assertFalse(self.destination.exists())
        self.assertEqual(self.setups(), [])

    def test_repeated_install_clones_latest_version(self):
        self.assert_success(self.run_installer())
        head = self.git_run("-C", str(self.destination), "rev-parse", "HEAD")
        (self.remote / "new-version").write_text("A later remote commit\n")
        self.git_run("-C", str(self.remote), "add", ".")
        self.git_run("-C", str(self.remote), "commit", "--quiet", "-m", "Advance remote")
        self.assert_success(self.run_installer())
        self.assertNotEqual(self.git_run("-C", str(self.destination), "rev-parse", "HEAD"), head)
        self.assertEqual((self.destination / "new-version").read_text(), "A later remote commit\n")
        self.assertEqual(len(self.setups()), 2)
        self.assertEqual(len([call for call in self.calls("git") if "clone" in call]), 2)
        self.assertFalse(any(action in call for call in self.calls("git")
                             for action in ("pull", "fetch", "reset")))

    def test_dirty_checkout_is_replaced_with_clean_clone(self):
        self.assert_success(self.run_installer())
        changed = self.destination / "scripts/setup.sh"
        contents = changed.read_text() + "# Personal modification\n"
        changed.write_text(contents)
        (self.destination / "untracked-file").write_text("Keep untracked\n")
        (self.destination / "staged-file").write_text("Keep staged\n")
        self.git_run("-C", str(self.destination), "add", "staged-file")
        self.assert_success(self.run_installer())
        self.assertFalse((self.destination / "untracked-file").exists())
        self.assertFalse((self.destination / "staged-file").exists())
        self.assertEqual(self.git_run("-C", str(self.destination), "status", "--porcelain"), "")
        self.assertNotIn("# Personal modification", changed.read_text())
        self.assertEqual(len(self.setups()), 2)

    def test_different_origin_is_replaced_with_luna_clone(self):
        self.assert_success(self.run_installer())
        self.git_run("-C", str(self.destination), "remote", "set-url", "origin", "https://example.invalid/other.git")
        self.assert_success(self.run_installer())
        self.assertEqual(self.git_run("-C", str(self.destination), "config", "remote.origin.url"), ORIGIN)
        self.assertEqual(len(self.setups()), 2)

    def test_different_branch_is_replaced_with_requested_branch(self):
        self.assert_success(self.run_installer())
        self.assert_success(self.run_installer("--ref", "feature/installer"))
        self.assertEqual(self.git_run("-C", str(self.destination), "branch", "--show-current"),
                         "feature/installer")
        self.assertEqual(len(self.setups()), 2)

    def test_branch_can_be_replaced_with_requested_tag(self):
        self.assert_success(self.run_installer())
        self.assert_success(self.run_installer("--ref", "v1.2.3"))
        self.assertEqual(self.git_run("-C", str(self.destination), "branch", "--show-current"), "")
        self.assertEqual(self.git_run("-C", str(self.destination), "describe", "--tags", "--exact-match"),
                         "v1.2.3")

    def test_nonrepository_directory_is_replaced(self):
        self.destination.mkdir(parents=True)
        personal = self.destination / "personal-file"
        personal.write_text("Keep me\n")
        self.assert_success(self.run_installer())
        self.assertFalse(personal.exists())
        self.assertTrue((self.destination / ".git").is_dir())
        self.assertEqual(len(self.setups()), 1)

    def test_nonrepository_file_is_replaced(self):
        self.destination.parent.mkdir(parents=True)
        self.destination.write_text("Keep my file\n")
        self.assert_success(self.run_installer())
        self.assertTrue((self.destination / ".git").is_dir())

    def test_symlink_is_replaced_without_touching_external_target(self):
        external = self.root / "external target"
        external.mkdir()
        (external / "personal-file").write_text("Keep external\n")
        self.destination.parent.mkdir(parents=True)
        target = os.path.relpath(external, self.destination.parent)
        self.destination.symlink_to(target, target_is_directory=True)
        self.assert_success(self.run_installer())
        self.assertFalse(self.destination.is_symlink())
        self.assertTrue((self.destination / ".git").is_dir())
        self.assertEqual((external / "personal-file").read_text(), "Keep external\n")
        self.assertEqual([path.name for path in external.iterdir()], ["personal-file"])

    def test_dangling_symlink_is_replaced(self):
        self.destination.parent.mkdir(parents=True)
        self.destination.symlink_to("missing-target")
        self.assert_success(self.run_installer())
        self.assertFalse(self.destination.is_symlink())
        self.assertTrue((self.destination / ".git").is_dir())
        self.assertFalse((self.destination.parent / "missing-target").exists())

    def test_unknown_ref_does_not_run_setup_again(self):
        self.assert_success(self.run_installer())
        self.assert_refused(self.run_installer("--ref", "missing-version"))
        self.assertEqual(len(self.setups()), 1)

    def test_selected_version_missing_setup_stops_before_running_setup(self):
        self.assert_success(self.run_installer())
        self.git_run("-C", str(self.remote), "rm", "scripts/setup.sh")
        self.git_run("-C", str(self.remote), "commit", "--quiet", "-m", "Version without setup")
        result = self.run_installer()
        self.assert_refused(result)
        self.assertIn("scripts/setup.sh", result.stdout)
        self.assertEqual(len(self.setups()), 1)

    def test_setup_failure_propagates_after_replacing_existing_checkout(self):
        self.assert_success(self.run_installer())
        (self.destination / "personal-file").write_text("Old checkout\n")
        self.env["TEST_SETUP_STATUS"] = "37"
        result = self.run_installer("--ref", "feature/installer")
        self.assert_refused(result)
        self.assertEqual(result.returncode, 37, result.stdout)
        self.assertEqual(self.git_run("-C", str(self.destination), "branch", "--show-current"),
                         "feature/installer")
        self.assertFalse((self.destination / "personal-file").exists())
        self.assertEqual(len(self.setups()), 2)

    def test_setup_failure_propagates_and_is_logged(self):
        self.env["TEST_SETUP_STATUS"] = "37"
        self.env["XDG_STATE_HOME"] = str(self.root / "custom state")
        result = self.run_installer()
        self.assert_refused(result)
        self.assertEqual(result.returncode, 37, result.stdout)
        logs = list((self.root / "custom state/luna").glob("install-*.log"))
        self.assertEqual(len(logs), 1)
        self.assertIn("Fixture setup stderr", logs[0].read_text())

    def test_missing_git_bootstraps_without_package_prompt(self):
        self.env["TEST_BOOTSTRAP_GIT"] = "1"
        self.assert_success(self.run_installer())
        self.assertEqual(self.calls("pacman"), [["pacman", "-Syu", "--needed", "--noconfirm", "--", "git"]])
        self.assertTrue((self.root / "git-installed").exists())
        self.assertEqual(self.setups()[0]["answer"], "yes")

    def test_forced_color_console_keeps_complete_plain_log(self):
        self.env.pop("NO_COLOR", None)
        self.env["LUNA_COLOR"] = "1"
        self.env["TEST_SETUP_COLOR"] = "1"
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("\x1b[", result.stdout)
        plain_console = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", result.stdout)
        self.assertIn("[OK] Luna setup completed.", plain_console)
        self.assertEqual(self.setups()[0]["answer"], "yes")

        logs = list((self.home / ".local/state/luna").glob("install-*.log"))
        self.assertEqual(len(logs), 1)
        contents = logs[0].read_text()
        self.assertNotIn("\x1b", contents)
        self.assertIn("Fixture setup prompt:", contents)
        self.assertIn("Fixture colored output", contents)
        self.assertIn("Fixture colored tail", contents)
        self.assertIn("[OK] Luna setup completed.", contents)
        self.assertIn("Install log:", contents)

    def test_english_locale_keeps_console_and_log_free_of_regex_errors(self):
        if not shutil.which("locale"):
            self.skipTest("locale is needed to find an English UTF-8 locale")
        available = subprocess.run(["locale", "-a"], capture_output=True, text=True,
                                   check=True, timeout=5).stdout.splitlines()
        locale_name = next((name for name in available
                            if name.lower().replace("-", "") == "en_us.utf8"), None)
        if locale_name is None:
            self.skipTest("An en_US UTF-8 locale is not installed")

        self.env.pop("NO_COLOR", None)
        self.env.update(LC_ALL=locale_name, LANG=locale_name, TEST_TOOL_LOCALE="1")
        log_dir = self.home / ".local/state/luna"
        for color in ("0", "1"):
            with self.subTest(color=color):
                self.env["LUNA_COLOR"] = color
                previous_logs = set(log_dir.glob("install-*.log"))
                result = self.run_installer()
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertNotRegex(result.stdout, r"invalid regex|Invalid range end")
                self.assertNotIn("\x1b[31m", result.stdout)
                self.assertEqual("\x1b[90m" in result.stdout, color == "1")
                if color == "0":
                    self.assertNotIn("\x1b", result.stdout)
                plain_console = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", result.stdout)

                logs = set(log_dir.glob("install-*.log")) - previous_logs
                self.assertEqual(len(logs), 1)
                contents = logs.pop().read_text()
                self.assertNotIn("\x1b", contents)
                self.assertNotRegex(contents, r"invalid regex|Invalid range end")
                for output in (plain_console, contents):
                    self.assertIn("Fixture Unicode café — काठमाडौं", output)
                    self.assertIn("Fixture clone locale: " + locale_name, output)
                    self.assertIn("Fixture setup locale: " + locale_name, output)
                    self.assertIn("[OK] Luna setup completed.", output)

    def test_no_terminal_stops_before_package_or_clone_writes(self):
        self.env["TEST_BOOTSTRAP_GIT"] = "1"
        result = self.run_installer(terminal=False)
        self.assert_refused(result)
        self.assertIn("interactive terminal", result.stdout)
        self.assertEqual(self.calls("sudo"), [])
        self.assertEqual(self.calls("pacman"), [])
        self.assertFalse(self.destination.exists())
        self.assertEqual(self.setups(), [])

    def test_help_and_invalid_arguments_have_no_side_effects(self):
        for args in (("--help",), ("-h",)):
            with self.subTest(args=args):
                result = self.run_installer(*args, terminal=False)
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertIn("--ref", result.stdout)
        for args in (("--ref",), ("--unknown",), ("--ref", ""),
                     ("--ref", "-bad"), ("--ref", "bad..ref"), ("--ref", "refs/heads/master")):
            with self.subTest(args=args):
                self.assert_refused(self.run_installer(*args, terminal=False))
        self.assertEqual(list(self.home.iterdir()), [])
        self.assertEqual(self.calls("sudo"), [])
        self.assertEqual(self.calls("git"), [])


if __name__ == "__main__":
    unittest.main()
