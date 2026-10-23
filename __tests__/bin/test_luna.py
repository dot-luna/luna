"""The launcher selects a checkout while preserving arguments and working directory."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]


@unittest.skipUnless(Path("/usr/bin/lua").exists(), "System Lua is required")
class LunaLauncherTests(unittest.TestCase):
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
        self.env.pop("LUNA_INSTALL_DIR", None)
        self.env.pop("BASH_ENV", None)

    def run_launcher(self, *arguments, cwd=None):
        return subprocess.run([str(self.launcher), *arguments], env=self.env,
                              cwd=cwd or self.root,
                              capture_output=True, text=True, timeout=10)

    def run_version(self, option):
        return self.run_launcher(option)

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

    def test_explicit_install_directory_selects_another_checkout_through_symlink(self):
        selected = self.root / "coding checkout's directory"
        main = selected / "src/luna-cli/main.lua"
        main.parent.mkdir(parents=True)
        shutil.copy2(REPO / "src/luna-cli/main.lua", main)
        (selected / "VERSION").write_text("9.8.7-selected\n")
        self.env["LUNA_INSTALL_DIR"] = str(selected)

        result = self.run_version("--version")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "luna 9.8.7-selected\n")
        self.assertEqual(result.stderr, "")

    def test_selected_directory_is_exported_and_arguments_and_cwd_are_preserved(self):
        caller = self.root / "caller's working directory"
        caller.mkdir()
        (caller / "caller-marker").write_text("caller directory")
        explicit = self.root / "coding checkout's directory"
        arguments = ("--unknown", "", "argument with spaces", "apostrophe's", "$(literal)")

        # The probe needs only Lua itself and uses a relative file to verify cwd.
        probe = """local marker = assert(io.open("caller-marker", "r"))
io.write(os.getenv("LUNA_INSTALL_DIR") or "UNSET", "\\0", arg[0], "\\0")
io.write(marker:read("*a"), "\\0")
marker:close()
for index = 1, #arg do
    io.write(arg[index], "\\0")
end
"""
        for configured in (None, "", str(explicit)):
            with self.subTest(install_dir=configured):
                if configured is None:
                    self.env.pop("LUNA_INSTALL_DIR", None)
                else:
                    self.env["LUNA_INSTALL_DIR"] = configured
                selected = explicit if configured else self.checkout
                main = selected / "src/luna-cli/main.lua"
                main.parent.mkdir(parents=True, exist_ok=True)
                main.write_text(probe)

                result = self.run_launcher(*arguments, cwd=caller)

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "")
                self.assertEqual(result.stdout.split("\0"), [
                    str(selected), str(main), "caller directory", *arguments, "",
                ])

    def test_relative_install_directory_is_rejected_even_when_checkout_exists(self):
        self.env["LUNA_INSTALL_DIR"] = "checkout"

        result = self.run_version("--version")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("absolute", result.stderr.lower())
        self.assertEqual(len(result.stderr.splitlines()), 1)

    def test_missing_selected_cli_fails_without_falling_back(self):
        empty_checkout = self.root / "empty checkout"
        empty_checkout.mkdir()
        for selected in (self.root / "missing checkout", empty_checkout):
            with self.subTest(install_dir=selected):
                self.env["LUNA_INSTALL_DIR"] = str(selected)

                result = self.run_version("--version")

                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertIn(str(selected / "src/luna-cli/main.lua"), result.stderr)
                self.assertEqual(len(result.stderr.splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
