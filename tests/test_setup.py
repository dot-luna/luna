"""Check setup orchestration using harmless child steps in an isolated checkout."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]


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
        self.env = dict(os.environ, HOME=str(self.root / "home"), TEST_SETUP_CALLS=str(self.calls))
        self.env.pop("TEST_FAIL_STEP", None)

        # No production child script runs: these fixtures only record arguments.
        for name in ("lua", "aur", "config", "src", "nvidia"):
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

    def setup(self, *arguments):
        return subprocess.run(["bash", str(self.checkout / "scripts/setup.sh"), *arguments],
                              env=self.env, cwd=self.root, input="", capture_output=True,
                              text=True, timeout=10)

    def recorded_calls(self):
        if not self.calls.exists():
            return []
        return [line.split("\t") for line in self.calls.read_text().splitlines()]

    def test_steps_run_in_order_with_nvidia_last(self):
        result = self.setup()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.recorded_calls(), [[step] for step in
                         ("lua", "core", "aur", "main", "fonts", "config", "src", "nvidia")])

    def test_force_is_forwarded_except_to_aur_and_nvidia(self):
        result = self.setup("--force")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.recorded_calls(), [
            ["lua", "--force"], ["core", "--force"], ["aur"], ["main", "--force"],
            ["fonts", "--force"], ["config", "--force"], ["src", "--force"], ["nvidia"],
        ])

    def test_failed_step_stops_later_work_and_propagates_status(self):
        self.env["TEST_FAIL_STEP"] = "main"
        result = self.setup()
        self.assertEqual(result.returncode, 29, result.stdout + result.stderr)
        self.assertEqual(self.recorded_calls(), [[step] for step in ("lua", "core", "aur", "main")])

    def test_help_and_unknown_options_do_not_run_steps(self):
        result = self.setup("--help")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("NVIDIA", result.stdout)
        self.assertEqual(self.setup("--unknown").returncode, 2)
        self.assertEqual(self.recorded_calls(), [])


if __name__ == "__main__":
    unittest.main()
