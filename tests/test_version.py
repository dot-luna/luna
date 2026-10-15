"""Version reporting must work without loading optional CLI dependencies."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]


@unittest.skipUnless(Path("/usr/bin/lua").exists(), "System Lua is required")
class VersionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna version '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.checkout = self.root / "checkout"
        # Intentionally omit common.lua, argparse, and every desktop module.
        for name in ("bin/luna", "src/luna-cli/main.lua", "VERSION"):
            destination = self.checkout / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / name, destination)
        self.launcher = self.root / "luna"
        self.launcher.symlink_to(self.checkout / "bin/luna")
        self.env = dict(os.environ, HOME=str(self.root), LUA_PATH="/missing/?.lua")

    def run_version(self, option):
        return subprocess.run([str(self.launcher), option], env=self.env, cwd=self.root,
                              capture_output=True, text=True, timeout=10)

    def test_both_flags_resolve_version_through_launcher_symlink(self):
        expected = "luna " + (REPO / "VERSION").read_text().strip() + "\n"
        for option in ("--version", "-v"):
            with self.subTest(option=option):
                result = self.run_version(option)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, expected)
                self.assertEqual(result.stderr, "")

    def test_version_is_read_from_current_checkout_file(self):
        (self.checkout / "VERSION").write_text("2.3.4-test\n")
        result = self.run_version("--version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "luna 2.3.4-test\n")

    def test_missing_and_empty_version_fail_without_loading_modules(self):
        version = self.checkout / "VERSION"
        for content in (None, "", "  \n"):
            with self.subTest(content=content):
                if content is None:
                    version.unlink()
                else:
                    version.write_text(content)
                result = self.run_version("--version")
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertIn("version", result.stderr.lower())
                self.assertNotIn("stack traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
