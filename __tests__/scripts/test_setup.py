"""Check setup orchestration using harmless child steps in an isolated checkout."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]
STEPS = ("lua", "core", "mise", "aur", "main", "fonts", "git-apps", "src",
         "command", "postinstall", "apps", "session")


@unittest.skipUnless(Path("/usr/bin/lua").is_file(), "The runner requires /usr/bin/lua")
class SetupRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna setup '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.checkout = self.root / "checkout"
        self.steps = self.checkout / "scripts/setup"
        self.steps.mkdir(parents=True)
        (self.checkout / "lib").mkdir()
        shutil.copy2(REPO / "scripts/setup.sh", self.checkout / "scripts/setup.sh")
        shutil.copy2(REPO / "lib/common.sh", self.checkout / "lib/common.sh")
        self.calls = self.root / "calls"
        self.env = dict(os.environ, HOME=str(self.root / "home"),
                        XDG_CONFIG_HOME=str(self.root / "home/.config"),
                        TEST_SETUP_CALLS=str(self.calls))
        self.env.pop("LUNA_CONFIG_DIR", None)
        self.env.pop("TEST_FAIL_STEP", None)

        # No production child script runs: these fixtures only record arguments.
        for name in ("lua", "aur", "src", "command", "postinstall", "apps", "session"):
            (self.steps / f"{name}.sh").write_text('''#!/usr/bin/env bash
set -euo pipefail
step=${0##*/}
step=${step%.sh}
{
    printf '%s' "$step"
    for argument in "$@"; do
        printf '\\t%s' "$argument"
    done
    printf '\\n'
} >> "$TEST_SETUP_CALLS"
if [[ "${TEST_FAIL_STEP:-}" == "$step" ]]; then
    exit 29
fi
''')
        (self.steps / "install-deps.lua").write_text('''
local output = assert(io.open(os.getenv("TEST_SETUP_CALLS"), "a"))
output:write(table.concat(arg, "\\t"), "\\n")
output:close()
if os.getenv("TEST_FAIL_STEP") == arg[1] then
    os.exit(29)
end
''')
        for name in ("mise", "git-apps"):
            (self.steps / f"{name}.lua").write_text(
                f'table.insert(arg, 1, "{name}")\n' + (self.steps / "install-deps.lua").read_text())

    def setup(self, *arguments):
        return subprocess.run(["bash", str(self.checkout / "scripts/setup.sh"), *arguments],
                              env=self.env, cwd=self.root, input="", capture_output=True,
                              text=True, timeout=10)

    def recorded_calls(self):
        if not self.calls.exists():
            return []
        return [line.split("\t") for line in self.calls.read_text().splitlines()]

    def test_steps_run_in_order_then_reload_session(self):
        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.recorded_calls(), [[step] for step in STEPS])
        self.assertIn("Install application configurations", result.stdout)
        self.assertNotIn(["nvidia"], self.recorded_calls())

    def test_failed_critical_steps_stop_later_work_and_propagate_status(self):
        for failed in ("lua", "core", "src", "command", "apps"):
            with self.subTest(failed=failed):
                self.calls.unlink(missing_ok=True)
                self.env["TEST_FAIL_STEP"] = failed
                result = self.setup()
                self.assertEqual(result.returncode, 29, result.stdout + result.stderr)
                self.assertEqual(self.recorded_calls(), [[step] for step in STEPS[:STEPS.index(failed) + 1]])

    def test_failed_optional_steps_continue_to_desktop_deployment_and_reload(self):
        warnings = {
            "mise": "Development tools setup failed; continuing.",
            "aur": "AUR helper setup failed; continuing.",
            "main": "Application setup failed; continuing.",
            "fonts": "Font setup failed; continuing.",
            "git-apps": "Git app setup failed; continuing.",
            "postinstall": "Bundled theme setup failed; continuing.",
            "session": "Session reload failed; log out and back in to apply the configuration.",
        }
        for failed, warning in warnings.items():
            with self.subTest(failed=failed):
                self.calls.unlink(missing_ok=True)
                self.env["TEST_FAIL_STEP"] = failed
                result = self.setup()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(self.recorded_calls(), [[step] for step in STEPS])
                self.assertIn("[WARN] " + warning, result.stderr)

    def test_arguments_are_ignored_and_not_forwarded_to_steps(self):
        result = self.setup("--help", "-h", "--force", "--unknown", "main")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.recorded_calls(), [[step] for step in STEPS])
        self.assertNotIn(["nvidia"], self.recorded_calls())

    def test_skip_lists_accumulate_without_reordering_or_forwarding_arguments(self):
        self.env["TEST_FAIL_STEP"] = "core"
        skipped = {"lua", "core", "mise", "fonts", "git-apps", "apps"}
        result = self.setup("--skip=git-apps,fonts,mise,core,lua,git-apps", "--skip=apps,fonts")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.recorded_calls(), [[step] for step in STEPS if step not in skipped])
        for step in skipped:
            self.assertEqual(result.stdout.count(f"Skipping {step}."), 1)
        self.assertNotIn("setup failed", result.stderr)

    def test_all_steps_can_be_intentionally_skipped(self):
        result = self.setup("--skip=" + ",".join(STEPS))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.recorded_calls(), [])
        for step in STEPS:
            self.assertIn(f"Skipping {step}.", result.stdout)

    def test_invalid_skip_lists_fail_before_any_step(self):
        for argument in ("--skip", "--skip=", "--skip=unknown", "--skip=fonts,",
                         "--skip=,fonts", "--skip=fonts,,mise", "--skip= fonts",
                         "--skip=fonts, mise", "--skip=fonts,\nmise"):
            with self.subTest(argument=argument):
                self.calls.unlink(missing_ok=True)
                result = self.setup("--skip=session", argument)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertEqual(self.recorded_calls(), [])
                self.assertTrue(result.stderr.strip())


if __name__ == "__main__":
    unittest.main()
