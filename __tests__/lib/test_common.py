"""Check shared setup helpers without touching personal configuration."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]


class ConfigBlockTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna config block '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config = self.root / ".bashrc"
        self.original = "# Personal config without a final newline"
        self.config.write_text(self.original)
        self.config.chmod(0o640)
        self.env = dict(os.environ, TEST_CONFIG=str(self.config),
                        TEST_CALLER_TRAP=str(self.root / "caller-trap"))
        self.env.pop("BASH_ENV", None)

    def append(self, prelude=""):
        # A conditional intentionally disables errexit inside the helper: each
        # failed staging operation must still prevent replacement of the file.
        source = '''set -euo pipefail
source "$1"
trap 'printf caller > "$TEST_CALLER_TRAP"' EXIT
''' + prelude + '''
if luna_append_config_block "$TEST_CONFIG" '# START' '# END'; then
    exit 0
else
    exit "$?"
fi
'''
        return subprocess.run(["bash", "-c", source, "config-test", str(REPO / "lib/common.sh")],
                              input="export EXAMPLE='literal $HOME'\n", env=self.env,
                              text=True, capture_output=True, timeout=10)

    def test_success_preserves_contents_mode_and_caller_trap(self):
        result = self.append()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.config.read_text(), self.original +
                         "\n# START\nexport EXAMPLE='literal $HOME'\n# END\n")
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o640)
        self.assertEqual((self.root / "caller-trap").read_text(), "caller")
        self.assertEqual(list(self.root.glob(".bashrc.luna.*")), [])

    def test_staging_failures_preserve_original_and_clean_temporary_files(self):
        for operation, prelude in (
                ("copy", "cat() { return 67; }"),
                ("mode", "chmod() { return 67; }"),
                ("body", '''cat() {
    if (( $# == 0 )); then
        printf 'partial body'
        return 67
    fi
    command cat "$@"
}'''),
                ("replace", "mv() { return 67; }")):
            with self.subTest(operation=operation):
                result = self.append(prelude)
                self.assertEqual(result.returncode, 67, result.stdout + result.stderr)
                self.assertEqual(self.config.read_text(), self.original)
                self.assertEqual(self.config.stat().st_mode & 0o777, 0o640)
                self.assertEqual(list(self.root.glob(".bashrc.luna.*")), [])
                self.assertEqual((self.root / "caller-trap").read_text(), "caller")

    def test_symlink_is_replaced_without_modifying_its_external_target(self):
        target = self.root / "personal-config"
        self.config.rename(target)
        self.config.symlink_to(target)

        result = self.append()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.config.is_symlink())
        self.assertIn("# START", self.config.read_text())
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o640)
        self.assertEqual(target.read_text(), self.original)


@unittest.skipUnless(shutil.which("lua"), "Lua is required")
class ManifestListTests(unittest.TestCase):
    def test_lists_cannot_silently_drop_malformed_entries(self):
        source = '''local common = dofile(arg[1])
for _, list in ipairs({ {}, { false, "tool", {} } }) do
    common.assert_list(list, "Tools")
end
for _, value in ipairs({ false, "tool", 1, { [0] = "tool" },
    { [1] = "tool", [3] = "hidden" }, { tool = "hidden" },
    { "tool", hidden = true }, { [1.5] = "hidden" } }) do
    local ok, message = pcall(common.assert_list, value, "Tools")
    assert(not ok and message:find("Tools must be a", 1, true), tostring(message))
end
'''
        # Execute the source on stdin so arg[1] is an ordinary filename argument.
        result = subprocess.run([shutil.which("lua"), "-E", "-", str(REPO / "lib/common.lua")],
                                input=source, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


@unittest.skipUnless(Path("/usr/bin/lua").is_file(), "Lua is required")
class StagedFileTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna staged file '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / "settings"
        self.path.write_text("Original contents\n")
        self.env = {"HOME": str(self.root), "PATH": "/usr/bin:/bin"}

    def lua(self, source):
        result = subprocess.run(["/usr/bin/lua", "-E", "-", str(REPO / "lib/common.lua"), str(self.path)],
                                input="local common = dofile(arg[1])\nlocal path = arg[2]\n" + source,
                                env=self.env, cwd=self.root, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_staging_is_private_and_unique_without_publishing_early(self):
        output = self.lua('''
print(common.stage_file(path, "First contents"))
print(common.stage_file(path, "Second contents"))
''')
        first, second = map(Path, output.splitlines())
        self.assertNotEqual(first, second)
        for temporary in (first, second):
            self.assertEqual(temporary.parent, self.path.parent)
            self.assertEqual(temporary.stat().st_mode & 0o777, 0o600)
        self.assertEqual(first.read_text(), "First contents")
        self.assertEqual(second.read_text(), "Second contents")
        self.assertEqual(self.path.read_text(), "Original contents\n")

    def test_replace_does_not_follow_destination_symlink(self):
        personal = self.root / "personal"
        self.path.rename(personal)
        self.path.symlink_to(personal)

        self.lua('common.replace_file(path, "Replacement contents")')

        self.assertFalse(self.path.is_symlink())
        self.assertEqual(self.path.read_text(), "Replacement contents")
        self.assertEqual(personal.read_text(), "Original contents\n")
        self.assertEqual(list(self.root.glob("*.luna-*")), [])

    def test_write_failure_removes_only_its_own_partial_stage(self):
        unrelated = self.root / "settings.luna-existing"
        unrelated.write_text("Keep this file\n")
        self.lua('''
local original_open = io.open
io.open = function(name, mode)
    local file = assert(original_open(name, mode))
    return {
        write = function()
            assert(file:write("Partial contents"))
            return nil, "Fixture write failure"
        end,
        close = function() return file:close() end,
    }
end
local ok, message = pcall(common.stage_file, path, "Replacement contents")
assert(not ok and message:find("Fixture write failure", 1, true), tostring(message))
''')
        self.assertEqual(self.path.read_text(), "Original contents\n")
        self.assertEqual(unrelated.read_text(), "Keep this file\n")
        self.assertEqual(list(self.root.glob("*.luna-*")), [unrelated])

    def test_failed_replace_cleans_stage_and_preserves_destination(self):
        self.path.unlink()
        self.path.mkdir()
        marker = self.path / "keep"
        marker.write_text("Original contents\n")

        self.lua('assert(not pcall(common.replace_file, path, "Replacement contents"))')

        self.assertEqual(marker.read_text(), "Original contents\n")
        self.assertEqual(list(self.root.glob("*.luna-*")), [])


if __name__ == "__main__":
    unittest.main()
