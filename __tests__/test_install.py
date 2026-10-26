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
INSTALLER = REPO / "install.sh"
ORIGIN = "https://github.com/dot-luna/luna.git"
RELEASES = "https://github.com/dot-luna/luna/releases"
SETUP_STEPS = ("lua", "core", "mise", "aur", "main", "fonts", "git-apps", "src",
               "command", "postinstall", "apps", "keyring", "defaults", "session")


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
        for name in ("XDG_STATE_HOME", "LUNA_INSTALL_DIR", "TEST_BOOTSTRAP_GIT", "TEST_SETUP_STATUS",
                     "TEST_SETUP_COLOR", "TEST_TOOL_LOCALE", "TEST_RELEASE_URL",
                     "TEST_CURL_STATUS", "TEST_MISSING_CURL", "TEST_INTERRUPT_SLEEP"):
            self.env.pop(name, None)

        # Override only OS discovery and tool availability; never mutate the host.
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
    if [[ "$1" == -v && "${2:-}" == curl && "${TEST_MISSING_CURL:-}" == 1 ]]; then
        return 1
    fi
    builtin command "$@"
}
''')

        backend = f"#!{sys.executable}\n" + '''
import json, os, pathlib, signal, sys
root = pathlib.Path(os.environ["TEST_ROOT"])
tool = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with (root / "calls.jsonl").open("a") as output:
    output.write(json.dumps([tool, *args]) + "\\n")
if tool == "git":
    transfer = next((value for value in ("clone", "fetch") if value in args), None)
    if transfer and os.environ.get("TEST_TOOL_LOCALE") == "1":
        print("Fixture " + transfer + " locale: " + os.environ["LC_ALL"], flush=True)
        print("\\x1b[31mFixture Unicode café — काठमाडौं\\x1b[0m", flush=True)
    os.execv(os.environ["TEST_GIT"], ["git", *args])
elif tool == "curl":
    if args != ["-fsSL", "-o", "/dev/null", "-w", "%{url_effective}",
                "https://github.com/dot-luna/luna/releases/latest"]:
        sys.exit("Unexpected curl command: " + repr(args))
    status = int(os.environ.get("TEST_CURL_STATUS", "0"))
    if status:
        print("Fixture release request failed", file=sys.stderr)
        sys.exit(status)
    print(os.environ.get("TEST_RELEASE_URL", "https://github.com/dot-luna/luna/releases/tag/v1.2.3"), end="")
elif tool == "sleep":
    if args != ["5"]:
        sys.exit("Unexpected sleep command: " + repr(args))
    print("Fixture installer pause", flush=True)
    if os.environ.get("TEST_INTERRUPT_SLEEP") == "1":
        os.kill(os.getppid(), signal.SIGINT)
        sys.exit(130)
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
        for name in ("sudo", "pacman", "git", "curl", "sleep"):
            path = self.bin / name
            path.write_text(backend)
            path.chmod(0o755)

        (self.root / "setup-probe.py").write_text('''
import json, os, pathlib, sys
print("Fixture setup prompt: ", end="", flush=True)
answer = sys.stdin.readline().strip()
with (pathlib.Path(os.environ["TEST_ROOT"]) / "setup.jsonl").open("a") as output:
    output.write(json.dumps({"cwd": os.getcwd(), "args": sys.argv[1:],
                             "tty": sys.stdin.isatty(), "answer": answer,
                             "luna_install_dir": os.environ.get("LUNA_INSTALL_DIR")}) + "\\n")
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

    def commit_file(self, repository, name, contents):
        path = repository / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)
        self.git_run("-C", str(repository), "add", "--", name)
        self.git_run("-C", str(repository), "-c", "user.name=Installer Test",
                     "-c", "user.email=installer@example.invalid", "commit", "--quiet", "-m", "Update " + name)
        return self.git_run("-C", str(repository), "rev-parse", "HEAD")

    def run_installer(self, *args, terminal=True, cwd=None):
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
                                  cwd=self.root if cwd is None else cwd, stdin=subprocess.PIPE,
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
        self.commit_file(self.remote, "unreleased-file", "Only on master\n")
        self.assert_success(self.run_installer())
        self.assertEqual(self.git_run("-C", str(self.destination), "branch", "--show-current"), "")
        self.assertEqual(self.git_run("-C", str(self.destination), "describe", "--tags", "--exact-match"),
                         "v1.2.3")
        self.assertFalse((self.destination / "unreleased-file").exists())
        self.assertEqual(len(self.calls("curl")), 1)
        self.assertEqual(self.git_run("-C", str(self.destination), "config", "remote.origin.url"), ORIGIN)
        self.assertEqual(self.setups(), [{"cwd": str(self.destination), "args": [],
                                         "tty": True, "answer": "yes",
                                         "luna_install_dir": str(self.destination)}])
        self.assertEqual(self.calls("pacman"), [])
        logs = list((self.home / ".local/state/luna").glob("install-*.log"))
        self.assertEqual(len(logs), 1)
        log = logs[0].read_text()
        self.assertIn("Fixture setup stdout", log)
        self.assertIn("Fixture setup stderr", log)

    def test_explicit_latest_selects_release_instead_of_newer_master(self):
        self.commit_file(self.remote, "unreleased-file", "Only on master\n")
        self.assert_success(self.run_installer("--ref", "latest"))
        self.assertEqual(self.git_run("-C", str(self.destination), "describe", "--tags", "--exact-match"),
                         "v1.2.3")
        self.assertFalse((self.destination / "unreleased-file").exists())
        self.assertEqual(len(self.calls("curl")), 1)

    def test_startup_warnings_and_pause_precede_install_actions(self):
        self.env["TEST_BOOTSTRAP_GIT"] = "1"
        result = self.run_installer()
        self.assert_success(result)
        backup_warning = "Back up files you want to keep; no automatic backups are created."
        pause_notice = "Continuing in 5 seconds... Press Ctrl+C to cancel."
        self.assertLess(result.stdout.index(backup_warning), result.stdout.index(pause_notice))
        for notice in ("Packages may be installed or upgraded", "reload the active Hyprland session"):
            self.assertLess(result.stdout.index(notice), result.stdout.index(pause_notice))
        self.assertNotIn("Cleanup may remove", result.stdout)
        self.assertLess(result.stdout.index(pause_notice), result.stdout.index("Fixture installer pause"))
        self.assertEqual(self.calls("sleep"), [["sleep", "5"]])
        calls = [json.loads(line)[0] for line in self.calls_file.read_text().splitlines()]
        for tool in ("curl", "sudo", "pacman", "git"):
            self.assertLess(calls.index("sleep"), calls.index(tool))

    def test_interrupting_startup_pause_preserves_destination_before_install_actions(self):
        self.destination.mkdir(parents=True)
        (self.destination / "personal-file").write_text("Keep existing directory\n")
        self.env.update(TEST_BOOTSTRAP_GIT="1", TEST_INTERRUPT_SLEEP="1")
        result = self.run_installer()
        self.assert_refused(result)
        self.assertEqual(result.returncode, 130, result.stdout)
        self.assertIn("Back up files you want to keep", result.stdout)
        self.assertEqual((self.destination / "personal-file").read_text(), "Keep existing directory\n")
        self.assertFalse((self.destination / ".git").exists())
        self.assertFalse((self.root / "git-installed").exists())
        self.assertEqual(self.calls("sleep"), [["sleep", "5"]])
        for tool in ("curl", "sudo", "pacman", "git"):
            self.assertEqual(self.calls(tool), [])
        self.assertEqual(self.setups(), [])

    def test_skipped_session_omits_only_its_startup_notice(self):
        result = self.run_installer("--skip=session")
        self.assert_success(result)
        self.assertNotIn("reload the active Hyprland session", result.stdout)
        self.assertIn("Packages may be installed or upgraded", result.stdout)
        self.assertIn("Back up files you want to keep", result.stdout)

    def test_latest_rerun_updates_to_new_release_and_preserves_local_files_and_config(self):
        self.assert_success(self.run_installer())
        self.git_run("-C", str(self.destination), "config", "luna.fixture", "Keep local configuration")
        (self.destination / "personal-file").write_text("Keep local file\n")
        head = self.commit_file(self.remote, "release-update", "New release contents\n")
        self.git_run("-C", str(self.remote), "tag", "-a", "v1.3.0", "-m", "Next release")
        self.commit_file(self.remote, "unreleased-file", "Only on master\n")
        self.env["TEST_RELEASE_URL"] = RELEASES + "/tag/v1.3.0"

        self.assert_success(self.run_installer())
        self.assertEqual(self.git_run("-C", str(self.destination), "rev-parse", "HEAD"), head)
        self.assertEqual(self.git_run("-C", str(self.destination), "branch", "--show-current"), "")
        self.assertEqual((self.destination / "personal-file").read_text(), "Keep local file\n")
        self.assertFalse((self.destination / "unreleased-file").exists())
        self.assertEqual(self.git_run("-C", str(self.destination), "config", "luna.fixture"), "Keep local configuration")
        self.assertEqual(len(self.setups()), 2)
        self.assertEqual(len(self.calls("curl")), 2)
        self.assertEqual(len([call for call in self.calls("git") if "clone" in call]), 1)

    def test_latest_release_tag_wins_over_same_named_branch_on_clone_and_rerun(self):
        released = self.git_run("-C", str(self.remote), "rev-parse", "refs/tags/v1.2.3")
        setup_script = (self.remote / "scripts/setup.sh").read_text()

        # An unrelated branch keeps clone from fetching the release tag implicitly.
        self.git_run("-C", str(self.remote), "switch", "--orphan", "v1.2.3")
        self.commit_file(self.remote, "scripts/setup.sh", setup_script)
        self.commit_file(self.remote, "branch-only", "Not part of the release\n")

        for _ in range(2):
            self.assert_success(self.run_installer())
            self.assertEqual(self.git_run("-C", str(self.destination), "rev-parse", "HEAD"), released)
            self.assertEqual(self.git_run("-C", str(self.destination), "branch", "--show-current"), "")
            self.assertFalse((self.destination / "branch-only").exists())
        self.assertEqual(len(self.setups()), 2)
        self.assertEqual(len([call for call in self.calls("git") if "clone" in call]), 1)

    def test_latest_switches_existing_same_named_branch_to_release_tag(self):
        released = self.git_run("-C", str(self.remote), "rev-parse", "refs/tags/v1.2.3")
        self.git_run("-C", str(self.remote), "switch", "-c", "v1.2.3")
        branch_head = self.commit_file(self.remote, "branch-only", "Not part of the release\n")
        self.assert_success(self.run_installer("--ref", "v1.2.3"))
        self.assertEqual(self.git_run("-C", str(self.destination), "rev-parse", "HEAD"), branch_head)

        self.assert_success(self.run_installer())
        self.assertEqual(self.git_run("-C", str(self.destination), "rev-parse", "HEAD"), released)
        self.assertEqual(self.git_run("-C", str(self.destination), "branch", "--show-current"), "")
        self.assertEqual(self.git_run("-C", str(self.destination), "rev-parse", "refs/heads/v1.2.3"), branch_head)
        self.assertFalse((self.destination / "branch-only").exists())
        self.assertEqual(len(self.setups()), 2)
        self.assertEqual(len([call for call in self.calls("git") if "clone" in call]), 1)

    def test_latest_decodes_percent_encoded_release_tag_on_clone_and_rerun(self):
        tag = "release/v1.2.3+test%build"
        released = self.commit_file(self.remote, "release-update", "Encoded tag contents\n")
        self.git_run("-C", str(self.remote), "tag", "-a", tag, "-m", "Encoded release fixture")
        self.commit_file(self.remote, "unreleased-file", "Only on master\n")
        self.env["TEST_RELEASE_URL"] = RELEASES + "/tag/release%2Fv1.2.3%2Btest%25build"

        for _ in range(2):
            self.assert_success(self.run_installer())
            self.assertEqual(self.git_run("-C", str(self.destination), "rev-parse", "HEAD"), released)
            self.assertEqual(self.git_run("-C", str(self.destination), "branch", "--show-current"), "")
            self.assertEqual(self.git_run("-C", str(self.destination), "describe", "--tags", "--exact-match"), tag)
            self.assertFalse((self.destination / "unreleased-file").exists())
        self.assertEqual(len(self.setups()), 2)
        self.assertEqual(len([call for call in self.calls("git") if "clone" in call]), 1)

    def test_no_release_falls_back_to_master_and_updates_existing_checkout(self):
        for suffix in ("", "/"):
            with self.subTest(suffix=suffix):
                self.env["TEST_RELEASE_URL"] = RELEASES + suffix
                head = self.commit_file(self.remote, "master-update", "Current master" + suffix + "\n")
                result = self.run_installer()
                self.assert_success(result)
                self.assertIn("[WARN] No release found; using master.", result.stdout)
                self.assertEqual(self.git_run("-C", str(self.destination), "branch", "--show-current"), "master")
                self.assertEqual(self.git_run("-C", str(self.destination), "rev-parse", "HEAD"), head)
        self.assertEqual(len(self.setups()), 2)
        self.assertEqual(len([call for call in self.calls("git") if "clone" in call]), 1)

    def test_release_lookup_errors_preserve_checkout_before_authentication_or_bootstrap(self):
        self.assert_success(self.run_installer("--ref", "master"))
        (self.destination / "personal-file").write_text("Keep local file\n")
        head = self.git_run("-C", str(self.destination), "rev-parse", "HEAD")
        before = self.git_run("-C", str(self.destination), "status", "--porcelain")
        self.env["TEST_BOOTSTRAP_GIT"] = "1"
        scenarios = (
            ({"TEST_MISSING_CURL": "1"}, "Install curl"),
            ({"TEST_CURL_STATUS": "22"}, "Could not fetch the latest release"),
            ({"TEST_RELEASE_URL": ""}, "Could not determine the latest release tag"),
            ({"TEST_RELEASE_URL": RELEASES + "/latest"}, "Could not determine the latest release tag"),
            ({"TEST_RELEASE_URL": RELEASES + "/tag/"}, "Could not determine the latest release tag"),
            ({"TEST_RELEASE_URL": RELEASES + "/tag/v1.2.3%"}, "Could not determine the latest release tag"),
            ({"TEST_RELEASE_URL": RELEASES + "/tag/v1.2.3%2"}, "Could not determine the latest release tag"),
            ({"TEST_RELEASE_URL": RELEASES + "/tag/v1.2.3%GG"}, "Could not determine the latest release tag"),
            ({"TEST_RELEASE_URL": RELEASES + "/tag/v1.2.3%00"}, "Could not determine the latest release tag"),
            ({"TEST_RELEASE_URL": "https://example.invalid/releases/tag/v1.2.3"},
             "Could not determine the latest release tag"),
        )
        for overrides, message in scenarios:
            with self.subTest(overrides=overrides):
                for name in ("TEST_MISSING_CURL", "TEST_CURL_STATUS", "TEST_RELEASE_URL"):
                    self.env.pop(name, None)
                self.env.update(overrides)
                self.calls_file.write_text("")
                result = self.run_installer()
                self.assert_refused(result)
                self.assertIn(message, result.stdout)
                self.assertEqual(self.git_run("-C", str(self.destination), "rev-parse", "HEAD"), head)
                self.assertEqual(self.git_run("-C", str(self.destination), "status", "--porcelain"), before)
                self.assertEqual((self.destination / "personal-file").read_text(), "Keep local file\n")
                self.assertEqual(self.calls("sudo"), [])
                self.assertEqual(self.calls("pacman"), [])
                self.assertEqual(self.calls("git"), [])
                self.assertFalse((self.root / "git-installed").exists())
                self.assertEqual(len(self.setups()), 1)

    def test_release_request_failure_preserves_nonrepository_destination(self):
        self.destination.mkdir(parents=True)
        (self.destination / "personal-file").write_text("Keep existing directory\n")
        self.env["TEST_CURL_STATUS"] = "7"
        self.assert_refused(self.run_installer())
        self.assertEqual((self.destination / "personal-file").read_text(), "Keep existing directory\n")
        self.assertFalse((self.destination / ".git").exists())
        self.assertEqual(self.calls("sudo"), [])
        self.assertEqual(self.calls("pacman"), [])
        self.assertEqual(self.calls("git"), [])
        self.assertEqual(self.setups(), [])

    def test_empty_luna_install_dir_uses_and_exports_default_checkout(self):
        self.env["LUNA_INSTALL_DIR"] = ""
        self.assert_success(self.run_installer())
        self.assertTrue((self.destination / ".git").is_dir())
        self.assertEqual(self.setups()[0]["cwd"], str(self.destination))
        self.assertEqual(self.setups()[0]["luna_install_dir"], str(self.destination))

    def test_single_skip_is_forwarded_without_adding_dependency_skips(self):
        result = self.run_installer("--skip=git-apps")
        self.assert_success(result)
        self.assertEqual(self.setups()[0]["args"], ["--skip=git-apps"])
        self.assertIn("Run luna --version to check the installation.", result.stdout)
        self.assertTrue(any("clone" in call for call in self.calls("git")))

    def test_repeated_skip_lists_are_forwarded_unchanged_in_order(self):
        result = self.run_installer("--skip=git-apps,fonts", "--ref", "feature/installer",
                                    "--skip=fonts,mise,git-apps", "--skip=apps,mise,keyring,defaults,keyring")
        self.assert_success(result)
        self.assertEqual(self.setups()[0]["args"], ["--skip=git-apps,fonts", "--skip=fonts,mise,git-apps",
                                                  "--skip=apps,mise,keyring,defaults,keyring"])
        self.assertEqual(self.git_run("-C", str(self.destination), "branch", "--show-current"),
                         "feature/installer")

    def test_future_and_malformed_skip_values_are_forwarded_to_selected_setup(self):
        arguments = ("--skip=future-step", "--skip=", "--skip=,fonts", "--skip=fonts,",
                     "--skip=fonts,,mise", "--skip=fonts,unknown", "--skip=fonts mise",
                     "--skip=fonts\nmise", "--skip=FONTS", "--skip=../main",
                     "--skip=git", "--skip=all", "--skip=git-apps=1")
        self.assert_success(self.run_installer(*arguments))
        self.assertEqual(self.setups()[0]["args"], list(arguments))

    def test_selected_setup_validates_skip_values_before_running_children(self):
        # Use the real selected runner without any child scripts, so this cannot
        # perform setup work even if validation unexpectedly lets a value through.
        self.commit_file(self.remote, "scripts/setup.sh", (REPO / "scripts/setup.sh").read_text())
        self.commit_file(self.remote, "lib/common.sh", (REPO / "lib/common.sh").read_text())

        for argument in ("--skip=future-step", "--skip=fonts,,mise", "--skip=cleanup"):
            with self.subTest(argument=argument):
                result = self.run_installer("--ref", "master", argument)
                self.assert_refused(result)
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn("Invalid step in --skip", result.stdout)
                self.assertNotIn("1/14 — Prepare Lua", result.stdout)
                self.assertNotIn("No such file or directory", result.stdout)
                self.assertEqual((self.destination / "scripts/setup.sh").read_text(),
                                 (REPO / "scripts/setup.sh").read_text())
                self.assertEqual(self.setups(), [])
        self.assertEqual(len([call for call in self.calls("git") if "clone" in call]), 1)

    def test_skipping_every_setup_step_keeps_bootstrap_and_avoids_command_advice(self):
        self.env["TEST_BOOTSTRAP_GIT"] = "1"
        selected = "--skip=" + ",".join(SETUP_STEPS)
        result = self.run_installer(selected)
        self.assert_success(result)
        self.assertEqual(self.setups()[0]["args"], [selected])
        self.assertEqual(self.calls("pacman"), [["pacman", "-Syu", "--needed", "--noconfirm", "--", "git"]])
        self.assertIn(["sudo", "-v"], self.calls("sudo"))
        self.assertTrue(any("clone" in call for call in self.calls("git")))
        self.assertNotIn("Run luna --version to check the installation.", result.stdout)

    def test_custom_luna_install_dir_creates_parents_and_preserves_default_checkout(self):
        self.assert_success(self.run_installer())
        personal = self.destination / "personal-file"
        personal.write_text("Keep the default checkout\n")
        before = self.git_run("-C", str(self.destination), "status", "--porcelain")
        head = self.git_run("-C", str(self.destination), "rev-parse", "HEAD")
        custom = self.root / "coding with spaces/new parent/luna"
        self.assertFalse(custom.parent.exists())

        self.env["LUNA_INSTALL_DIR"] = str(custom)
        self.assert_success(self.run_installer())
        self.assertTrue((custom / ".git").is_dir())
        self.assertEqual(self.setups()[-1]["cwd"], str(custom))
        self.assertEqual(self.setups()[-1]["luna_install_dir"], str(custom))
        self.assertEqual(self.git_run("-C", str(custom), "config", "remote.origin.url"), ORIGIN)
        self.assertEqual(personal.read_text(), "Keep the default checkout\n")
        self.assertEqual(self.git_run("-C", str(self.destination), "status", "--porcelain"), before)
        self.assertEqual(self.git_run("-C", str(self.destination), "rev-parse", "HEAD"), head)

    def test_custom_existing_checkout_is_reused_without_losing_local_files(self):
        custom = self.root / "coding checkout/luna"
        self.env["LUNA_INSTALL_DIR"] = str(custom)
        self.assert_success(self.run_installer("--ref", "master"))
        (custom / "personal-file").write_text("Old checkout\n")
        head = self.commit_file(self.remote, "remote-update", "Updated upstream\n")

        self.assert_success(self.run_installer("--ref", "master"))
        self.assertEqual((custom / "personal-file").read_text(), "Old checkout\n")
        self.assertEqual(self.git_run("-C", str(custom), "rev-parse", "HEAD"), head)
        self.assertEqual(len(self.setups()), 2)
        self.assertEqual(len([call for call in self.calls("git") if "clone" in call]), 1)
        self.assertFalse(self.destination.exists())

    def test_custom_symlink_to_git_checkout_is_reused_and_updates_its_target(self):
        external = self.root / "external Git checkout"
        self.git_run("clone", "--branch", "master", "--single-branch", ORIGIN, str(external))
        (external / "personal-file").write_text("Keep external edits\n")
        custom = self.root / "custom checkout"
        custom.symlink_to(external, target_is_directory=True)
        self.env["LUNA_INSTALL_DIR"] = str(custom) + "/"
        head = self.commit_file(self.remote, "remote-update", "Updated upstream\n")

        self.assert_success(self.run_installer("--ref", "master"))
        self.assertTrue(custom.is_symlink())
        self.assertEqual(self.git_run("-C", str(external), "rev-parse", "HEAD"), head)
        self.assertEqual((external / "personal-file").read_text(), "Keep external edits\n")
        self.assertEqual(self.setups()[0]["cwd"], str(external))
        self.assertEqual(self.setups()[0]["luna_install_dir"], str(custom))
        self.assertFalse(any("clone" in call for call in self.calls("git")))
        self.assertFalse(self.destination.exists())

    def test_custom_symlink_with_trailing_slash_preserves_its_external_target(self):
        external = self.root / "external checkout"
        external.mkdir()
        (external / "personal-file").write_text("Keep external\n")
        custom = self.root / "custom checkout"
        custom.symlink_to(external, target_is_directory=True)
        self.env["LUNA_INSTALL_DIR"] = str(custom) + "/"

        self.assert_success(self.run_installer())
        self.assertFalse(custom.is_symlink())
        self.assertTrue((custom / ".git").is_dir())
        self.assertEqual(self.setups()[0]["luna_install_dir"], str(custom))
        self.assertEqual((external / "personal-file").read_text(), "Keep external\n")
        self.assertEqual([path.name for path in external.iterdir()], ["personal-file"])
        self.assertFalse(self.destination.exists())

    def test_install_from_inside_nonrepository_destination_survives_replacement(self):
        for relative in (".", "nested/folder"):
            with self.subTest(relative=relative):
                directory = self.root / ("install-from-root" if relative == "." else "install-from-descendant")
                working_directory = directory / relative
                working_directory.mkdir(parents=True)
                (directory / "old-file").write_text("Replace this non-Git directory\n")
                self.env["LUNA_INSTALL_DIR"] = str(directory)

                self.assert_success(self.run_installer(cwd=working_directory))
                self.assertTrue((directory / ".git").is_dir())
                self.assertFalse((directory / "old-file").exists())
                self.assertEqual(self.setups()[-1]["cwd"], str(directory))
                self.assertEqual(self.git_run("-C", str(directory), "describe", "--tags", "--exact-match"),
                                 "v1.2.3")
        self.assertEqual(len(self.setups()), 2)

    def test_custom_linked_worktree_updates_without_changing_the_main_checkout(self):
        self.assert_success(self.run_installer("--ref", "master"))
        original = self.git_run("-C", str(self.destination), "rev-parse", "HEAD")
        worktree = self.root / "coding worktree"
        self.git_run("-C", str(self.destination), "worktree", "add", "-b", "feature/installer", str(worktree))
        metadata = (worktree / ".git").read_text()
        (worktree / "personal-file").write_text("Keep worktree edits\n")
        self.git_run("-C", str(self.remote), "switch", "feature/installer")
        updated = self.commit_file(self.remote, "remote-update", "Updated feature branch\n")
        self.env["LUNA_INSTALL_DIR"] = str(worktree)

        self.assert_success(self.run_installer("--ref", "feature/installer"))
        self.assertEqual((worktree / ".git").read_text(), metadata)
        self.assertEqual((worktree / "personal-file").read_text(), "Keep worktree edits\n")
        self.assertEqual(self.git_run("-C", str(worktree), "rev-parse", "HEAD"), updated)
        self.assertEqual(self.git_run("-C", str(self.destination), "rev-parse", "HEAD"), original)
        self.assertEqual(self.git_run("-C", str(self.destination), "branch", "--show-current"), "master")
        self.assertEqual(self.setups()[-1]["cwd"], str(worktree))
        self.assertEqual(len([call for call in self.calls("git") if "clone" in call]), 1)

    def test_invalid_luna_install_dir_stops_before_authentication_or_writes(self):
        # Block filesystem mutations as well as asserting their absence: a broken
        # path validator must never let this test remove a real root directory.
        environment = self.root / "bash-env"
        environment.write_text(environment.read_text() + '''
mkdir() {
    builtin printf 'mkdir\\n' >> "$TEST_ROOT/blocked-write"
    return 97
}
rm() {
    builtin printf 'rm\\n' >> "$TEST_ROOT/blocked-write"
    return 97
}
mv() {
    builtin printf 'mv\\n' >> "$TEST_ROOT/blocked-write"
    return 97
}
''')
        for value in ("relative/luna", ".", "/", str(self.home), str(self.home) + "/.", str(self.home.parent)):
            with self.subTest(value=value):
                self.env["LUNA_INSTALL_DIR"] = value
                result = self.run_installer()
                self.assert_refused(result)
                self.assertIn("LUNA_INSTALL_DIR", result.stdout)
                self.assertEqual(self.calls("sudo"), [])
                self.assertEqual(self.calls("git"), [])
                self.assertEqual(list(self.home.iterdir()), [])
                self.assertFalse((self.root / "blocked-write").exists())
                self.assertEqual(self.setups(), [])

    def test_selected_branch(self):
        self.env["TEST_MISSING_CURL"] = "1"
        self.assert_success(self.run_installer("--ref", "feature/installer"))
        self.assertEqual(self.git_run("-C", str(self.destination), "branch", "--show-current"),
                         "feature/installer")
        self.assertEqual(self.calls("curl"), [])

    def test_selected_tag_reuses_detached_checkout(self):
        self.env["TEST_MISSING_CURL"] = "1"
        self.assert_success(self.run_installer("--ref", "v1.2.3"))
        self.assertEqual(self.git_run("-C", str(self.destination), "branch", "--show-current"), "")
        self.assertEqual(self.git_run("-C", str(self.destination), "describe", "--tags", "--exact-match"),
                         "v1.2.3")
        self.assertEqual(self.calls("curl"), [])
        self.assert_success(self.run_installer("--ref", "v1.2.3"))
        self.assertEqual(len(self.setups()), 2)
        self.assertEqual(len([call for call in self.calls("git") if "clone" in call]), 1)
        self.assertEqual(self.git_run("-C", str(self.destination), "describe", "--tags", "--exact-match"),
                         "v1.2.3")

    def test_annotated_tag_reuses_checkout_at_its_commit(self):
        self.git_run("-C", str(self.remote), "tag", "-a", "v2.0.0", "-m", "Release fixture")
        self.assert_success(self.run_installer("--ref", "v2.0.0"))
        self.assertEqual(self.git_run("-C", str(self.destination), "rev-parse", "HEAD"),
                         self.git_run("-C", str(self.remote), "rev-parse", "v2.0.0^{commit}"))
        self.assert_success(self.run_installer("--ref", "v2.0.0"))
        self.assertEqual(len(self.setups()), 2)
        self.assertEqual(self.git_run("-C", str(self.destination), "rev-parse", "HEAD"),
                         self.git_run("-C", str(self.remote), "rev-parse", "v2.0.0^{commit}"))
        self.assertEqual(len([call for call in self.calls("git") if "clone" in call]), 1)

    def test_moved_remote_tag_updates_existing_detached_checkout(self):
        self.assert_success(self.run_installer("--ref", "v1.2.3"))
        head = self.commit_file(self.remote, "retagged-file", "New release contents\n")
        self.git_run("-C", str(self.remote), "tag", "-f", "v1.2.3")

        self.assert_success(self.run_installer("--ref", "v1.2.3"))
        self.assertEqual(self.git_run("-C", str(self.destination), "rev-parse", "HEAD"), head)
        self.assertEqual(self.git_run("-C", str(self.destination), "rev-parse", "refs/tags/v1.2.3"), head)
        self.assertEqual(self.git_run("-C", str(self.destination), "branch", "--show-current"), "")
        self.assertEqual(len([call for call in self.calls("git") if "clone" in call]), 1)

    def test_branch_takes_precedence_over_same_named_tag(self):
        self.git_run("-C", str(self.remote), "tag", "shared-name")
        self.git_run("-C", str(self.remote), "checkout", "-b", "shared-name")
        head = self.commit_file(self.remote, "branch-only", "The branch is newer than the tag\n")
        for _ in range(2):
            self.assert_success(self.run_installer("--ref", "shared-name"))
            self.assertEqual(self.git_run("-C", str(self.destination), "branch", "--show-current"), "shared-name")
            self.assertEqual(self.git_run("-C", str(self.destination), "rev-parse", "HEAD"), head)

    def test_unknown_ref_stops_before_setup(self):
        self.assert_refused(self.run_installer("--ref", "missing-version"))
        self.assertFalse(self.destination.exists())
        self.assertEqual(self.setups(), [])

    def test_repeated_install_fast_forwards_without_recloning_or_losing_config(self):
        self.assert_success(self.run_installer("--ref", "master"))
        head = self.git_run("-C", str(self.destination), "rev-parse", "HEAD")
        self.git_run("-C", str(self.destination), "config", "luna.fixture", "Keep local configuration")
        (self.remote / "new-version").write_text("A later remote commit\n")
        self.git_run("-C", str(self.remote), "add", ".")
        self.git_run("-C", str(self.remote), "commit", "--quiet", "-m", "Advance remote")
        self.assert_success(self.run_installer("--ref", "master"))
        self.assertNotEqual(self.git_run("-C", str(self.destination), "rev-parse", "HEAD"), head)
        self.assertEqual((self.destination / "new-version").read_text(), "A later remote commit\n")
        self.assertEqual(len(self.setups()), 2)
        self.assertEqual(len([call for call in self.calls("git") if "clone" in call]), 1)
        self.assertTrue(any("fetch" in call for call in self.calls("git")))
        self.assertEqual(self.git_run("-C", str(self.destination), "config", "luna.fixture"), "Keep local configuration")
        self.assertFalse(any(action in call for call in self.calls("git")
                             for action in ("reset", "clean", "stash")))

    def test_nonconflicting_tracked_staged_and_untracked_edits_survive_update(self):
        self.assert_success(self.run_installer("--ref", "master"))
        changed = self.destination / "scripts/setup.sh"
        contents = changed.read_text() + "# Personal modification\n"
        changed.write_text(contents)
        (self.destination / "untracked-file").write_text("Keep untracked\n")
        (self.destination / "staged-file").write_text("Keep staged\n")
        self.git_run("-C", str(self.destination), "add", "staged-file")
        before = self.git_run("-C", str(self.destination), "status", "--porcelain")
        head = self.commit_file(self.remote, "new-version", "Unrelated upstream addition\n")
        self.assert_success(self.run_installer("--ref", "master"))
        self.assertEqual((self.destination / "untracked-file").read_text(), "Keep untracked\n")
        self.assertEqual((self.destination / "staged-file").read_text(), "Keep staged\n")
        self.assertEqual(self.git_run("-C", str(self.destination), "status", "--porcelain"), before)
        self.assertEqual(self.git_run("-C", str(self.destination), "rev-parse", "HEAD"), head)
        self.assertEqual(changed.read_text(), contents)
        self.assertEqual(len(self.setups()), 2)

    def test_conflicting_tracked_edits_refuse_update_without_losing_changes(self):
        self.commit_file(self.remote, "settings", "Original\n")
        self.assert_success(self.run_installer("--ref", "master"))
        head = self.git_run("-C", str(self.destination), "rev-parse", "HEAD")
        (self.destination / "settings").write_text("Local changes\n")
        self.commit_file(self.remote, "settings", "Upstream changes\n")

        for staged in (False, True):
            with self.subTest(staged=staged):
                if staged:
                    self.git_run("-C", str(self.destination), "add", "settings")
                before = self.git_run("-C", str(self.destination), "status", "--porcelain")
                self.assert_refused(self.run_installer("--ref", "master"))
                self.assertEqual((self.destination / "settings").read_text(), "Local changes\n")
                self.assertEqual(self.git_run("-C", str(self.destination), "rev-parse", "HEAD"), head)
                self.assertEqual(self.git_run("-C", str(self.destination), "status", "--porcelain"), before)
                self.assertEqual(len(self.setups()), 1)

    def test_untracked_collision_refuses_update_without_removing_local_file(self):
        self.assert_success(self.run_installer("--ref", "master"))
        head = self.git_run("-C", str(self.destination), "rev-parse", "HEAD")
        (self.destination / "collision").write_text("Keep local file\n")
        self.commit_file(self.remote, "collision", "Upstream file\n")

        self.assert_refused(self.run_installer("--ref", "master"))
        self.assertEqual((self.destination / "collision").read_text(), "Keep local file\n")
        self.assertEqual(self.git_run("-C", str(self.destination), "rev-parse", "HEAD"), head)
        self.assertEqual(len(self.setups()), 1)

    def test_ignored_collision_refuses_fast_forward_without_removing_local_file(self):
        self.assert_success(self.run_installer("--ref", "master"))
        head = self.git_run("-C", str(self.destination), "rev-parse", "HEAD")
        with (self.destination / ".git/info/exclude").open("a") as excludes:
            excludes.write("\nignored-settings\n")
        (self.destination / "ignored-settings").write_text("Keep ignored local settings\n")
        self.commit_file(self.remote, "ignored-settings", "Upstream settings\n")

        self.assert_refused(self.run_installer("--ref", "master"))
        self.assertEqual((self.destination / "ignored-settings").read_text(), "Keep ignored local settings\n")
        self.assertEqual(self.git_run("-C", str(self.destination), "rev-parse", "HEAD"), head)
        self.assertEqual(len(self.setups()), 1)

    def test_ignored_collision_refuses_branch_and_tag_switches(self):
        self.git_run("-C", str(self.remote), "switch", "feature/installer")
        self.commit_file(self.remote, "ignored-settings", "Upstream settings\n")
        self.git_run("-C", str(self.remote), "branch", "existing-feature")
        self.git_run("-C", str(self.remote), "tag", "release-with-settings")
        self.assert_success(self.run_installer("--ref", "master"))
        self.git_run("-C", str(self.destination), "fetch", "--no-tags", "origin",
                     "refs/heads/existing-feature:refs/heads/existing-feature")
        head = self.git_run("-C", str(self.destination), "rev-parse", "HEAD")
        with (self.destination / ".git/info/exclude").open("a") as excludes:
            excludes.write("\nignored-settings\n")
        (self.destination / "ignored-settings").write_text("Keep ignored local settings\n")

        for ref in ("feature/installer", "existing-feature", "release-with-settings"):
            with self.subTest(ref=ref):
                self.assert_refused(self.run_installer("--ref", ref))
                self.assertEqual((self.destination / "ignored-settings").read_text(), "Keep ignored local settings\n")
                self.assertEqual(self.git_run("-C", str(self.destination), "rev-parse", "HEAD"), head)
                self.assertEqual(self.git_run("-C", str(self.destination), "branch", "--show-current"), "master")
                self.assertEqual(len(self.setups()), 1)

    def test_branch_autostash_config_does_not_hide_conflicting_edits(self):
        self.commit_file(self.remote, "settings", "Original\n")
        self.assert_success(self.run_installer("--ref", "master"))
        head = self.git_run("-C", str(self.destination), "rev-parse", "HEAD")
        self.git_run("-C", str(self.destination), "config", "branch.master.mergeoptions", "--autostash")
        (self.destination / "settings").write_text("Keep local changes\n")
        before = self.git_run("-C", str(self.destination), "status", "--porcelain")
        self.commit_file(self.remote, "settings", "Upstream changes\n")

        self.assert_refused(self.run_installer("--ref", "master"))
        self.assertEqual((self.destination / "settings").read_text(), "Keep local changes\n")
        self.assertEqual(self.git_run("-C", str(self.destination), "rev-parse", "HEAD"), head)
        self.assertEqual(self.git_run("-C", str(self.destination), "status", "--porcelain"), before)
        self.assertEqual(self.git_run("-C", str(self.destination), "stash", "list"), "")
        self.assertEqual(len(self.setups()), 1)

    def test_local_commits_are_preserved_when_already_ahead_of_remote(self):
        self.assert_success(self.run_installer("--ref", "master"))
        head = self.commit_file(self.destination, "local-commit", "Local work\n")
        self.assert_success(self.run_installer("--ref", "master"))
        self.assertEqual(self.git_run("-C", str(self.destination), "rev-parse", "HEAD"), head)
        self.assertEqual((self.destination / "local-commit").read_text(), "Local work\n")
        self.assertEqual(len(self.setups()), 2)

    def test_diverged_history_refuses_update_and_preserves_local_commits_and_config(self):
        self.assert_success(self.run_installer("--ref", "master"))
        head = self.commit_file(self.destination, "local-commit", "Local work\n")
        self.git_run("-C", str(self.destination), "config", "luna.fixture", "Keep local configuration")
        self.commit_file(self.remote, "remote-commit", "Remote work\n")

        self.assert_refused(self.run_installer("--ref", "master"))
        self.assertEqual(self.git_run("-C", str(self.destination), "rev-parse", "HEAD"), head)
        self.assertEqual((self.destination / "local-commit").read_text(), "Local work\n")
        self.assertFalse((self.destination / "remote-commit").exists())
        self.assertEqual(self.git_run("-C", str(self.destination), "config", "luna.fixture"), "Keep local configuration")
        self.assertEqual(len(self.setups()), 1)

    def test_different_origin_is_refused_without_replacing_checkout(self):
        self.assert_success(self.run_installer())
        self.git_run("-C", str(self.destination), "remote", "set-url", "origin", "https://example.invalid/other.git")
        (self.destination / "personal-file").write_text("Keep unrelated checkout\n")
        self.assert_refused(self.run_installer())
        self.assertEqual(self.git_run("-C", str(self.destination), "config", "remote.origin.url"), "https://example.invalid/other.git")
        self.assertEqual((self.destination / "personal-file").read_text(), "Keep unrelated checkout\n")
        self.assertEqual(len(self.setups()), 1)

    def test_missing_origin_is_refused_without_replacing_checkout(self):
        self.assert_success(self.run_installer())
        self.git_run("-C", str(self.destination), "remote", "remove", "origin")
        head = self.git_run("-C", str(self.destination), "rev-parse", "HEAD")
        self.assert_refused(self.run_installer())
        self.assertEqual(self.git_run("-C", str(self.destination), "rev-parse", "HEAD"), head)
        self.assertEqual(self.git_run("-C", str(self.destination), "remote"), "")
        self.assertEqual(len(self.setups()), 1)

    def test_github_ssh_origins_are_preserved_and_updated(self):
        self.assert_success(self.run_installer("--ref", "master"))
        for origin in ("git@github.com:dot-luna/luna.git", "ssh://git@github.com/dot-luna/luna.git"):
            with self.subTest(origin=origin):
                self.git_run("config", "--global", "--add", f"url.{self.remote.as_uri()}.insteadOf", origin)
                self.git_run("-C", str(self.destination), "remote", "set-url", "origin", origin)
                head = self.commit_file(self.remote, "remote-origin", origin + "\n")
                self.assert_success(self.run_installer("--ref", "master"))
                self.assertEqual(self.git_run("-C", str(self.destination), "config", "remote.origin.url"), origin)
                self.assertEqual(self.git_run("-C", str(self.destination), "rev-parse", "HEAD"), head)
        self.assertEqual(len([call for call in self.calls("git") if "clone" in call]), 1)

    def test_corrupt_git_metadata_is_refused_and_preserved(self):
        self.destination.mkdir(parents=True)
        (self.destination / "personal-file").write_text("Keep damaged checkout\n")
        metadata = self.destination / ".git"
        metadata.write_text("gitdir: " + str(self.root / "missing-git-dir") + "\n")
        before = metadata.read_text()
        self.assert_refused(self.run_installer())
        self.assertEqual(metadata.read_text(), before)
        self.assertEqual((self.destination / "personal-file").read_text(), "Keep damaged checkout\n")
        self.assertEqual(self.setups(), [])
        self.assertFalse(any("clone" in call for call in self.calls("git")))

    def test_different_branch_is_fetched_despite_single_branch_clone(self):
        self.assert_success(self.run_installer("--ref", "master"))
        self.git_run("-C", str(self.remote), "checkout", "feature/installer")
        head = self.commit_file(self.remote, "feature-file", "Branch-specific content\n")
        self.assert_success(self.run_installer("--ref", "feature/installer"))
        self.assertEqual(self.git_run("-C", str(self.destination), "branch", "--show-current"),
                         "feature/installer")
        self.assertEqual(self.git_run("-C", str(self.destination), "rev-parse", "HEAD"), head)
        self.assertEqual((self.destination / "feature-file").read_text(), "Branch-specific content\n")
        self.assertEqual(len(self.setups()), 2)
        self.assertEqual(len([call for call in self.calls("git") if "clone" in call]), 1)

    def test_checkout_switches_from_branch_to_tag_and_back(self):
        head = self.commit_file(self.remote, "latest-master", "After tagged release\n")
        self.assert_success(self.run_installer("--ref", "master"))
        self.assert_success(self.run_installer("--ref", "v1.2.3"))
        self.assertEqual(self.git_run("-C", str(self.destination), "branch", "--show-current"), "")
        self.assertEqual(self.git_run("-C", str(self.destination), "describe", "--tags", "--exact-match"),
                         "v1.2.3")
        self.assert_success(self.run_installer("--ref", "master"))
        self.assertEqual(self.git_run("-C", str(self.destination), "branch", "--show-current"), "master")
        self.assertEqual(self.git_run("-C", str(self.destination), "rev-parse", "HEAD"), head)
        self.assertEqual(len([call for call in self.calls("git") if "clone" in call]), 1)

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

    def test_unknown_ref_preserves_checkout_and_does_not_run_setup_again(self):
        self.assert_success(self.run_installer())
        head = self.git_run("-C", str(self.destination), "rev-parse", "HEAD")
        (self.destination / "personal-file").write_text("Keep local file\n")
        self.assert_refused(self.run_installer("--ref", "missing-version"))
        self.assertEqual(self.git_run("-C", str(self.destination), "rev-parse", "HEAD"), head)
        self.assertEqual((self.destination / "personal-file").read_text(), "Keep local file\n")
        self.assertEqual(len(self.setups()), 1)

    def test_selected_version_missing_setup_stops_before_running_setup(self):
        self.assert_success(self.run_installer("--ref", "master"))
        self.git_run("-C", str(self.remote), "rm", "scripts/setup.sh")
        self.git_run("-C", str(self.remote), "commit", "--quiet", "-m", "Version without setup")
        result = self.run_installer("--ref", "master")
        self.assert_refused(result)
        self.assertIn("scripts/setup.sh", result.stdout)
        self.assertEqual(len(self.setups()), 1)

    def test_setup_failure_propagates_after_switching_existing_checkout(self):
        self.assert_success(self.run_installer())
        (self.destination / "personal-file").write_text("Old checkout\n")
        self.env["TEST_SETUP_STATUS"] = "37"
        result = self.run_installer("--ref", "feature/installer")
        self.assert_refused(result)
        self.assertEqual(result.returncode, 37, result.stdout)
        self.assertEqual(self.git_run("-C", str(self.destination), "branch", "--show-current"),
                         "feature/installer")
        self.assertEqual((self.destination / "personal-file").read_text(), "Old checkout\n")
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
                    transfer = "clone" if color == "0" else "fetch"
                    self.assertIn("Fixture " + transfer + " locale: " + locale_name, output)
                    self.assertIn("Fixture setup locale: " + locale_name, output)
                    self.assertIn("[OK] Luna setup completed.", output)

    def test_no_terminal_stops_before_package_or_clone_writes(self):
        self.env["TEST_BOOTSTRAP_GIT"] = "1"
        result = self.run_installer(terminal=False)
        self.assert_refused(result)
        self.assertIn("interactive terminal", result.stdout)
        self.assertEqual(self.calls("sleep"), [])
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
                self.assertIn("--skip=git-apps,fonts,mise", result.stdout)
                self.assertIn("scripts/setup.sh", result.stdout)
        for args in (("--ref",), ("--unknown",), ("--ref", ""),
                     ("--ref", "-bad"), ("--ref", "bad..ref"), ("--ref", "refs/heads/master"),
                     ("--skip-git-apps",), ("--skip-fonts",)):
            with self.subTest(args=args):
                result = self.run_installer(*args, terminal=False)
                self.assert_refused(result)
                self.assertEqual(result.returncode, 2, result.stdout)
        self.assertEqual(list(self.home.iterdir()), [])
        self.assertEqual(self.calls("sleep"), [])
        self.assertEqual(self.calls("curl"), [])
        self.assertEqual(self.calls("sudo"), [])
        self.assertEqual(self.calls("git"), [])

    def test_bare_skip_fails_before_system_checks_or_authentication(self):
        # A valid call would fail HOME validation; invalid flags must fail earlier.
        self.env["HOME"] = "relative home"
        self.env["TEST_BOOTSTRAP_GIT"] = "1"
        for args in (("--skip",), ("--skip", "git-apps")):
            with self.subTest(args=args):
                result = self.run_installer(*args, terminal=False)
                self.assert_refused(result)
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertNotIn("HOME must", result.stdout)
                self.assertIn("Use --skip=", result.stdout)
        self.assertEqual(list(self.home.iterdir()), [])
        self.assertFalse((self.root / "relative home").exists())
        self.assertEqual(self.calls("sleep"), [])
        self.assertEqual(self.calls("sudo"), [])
        self.assertEqual(self.calls("pacman"), [])
        self.assertEqual(self.calls("git"), [])
        self.assertEqual(self.setups(), [])


if __name__ == "__main__":
    unittest.main()
