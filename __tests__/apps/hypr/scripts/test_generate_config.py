"""Validate generated checkout paths without loading compositor configuration."""

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[4]
GENERATOR = REPO / 'apps/hypr/scripts/generate-config.lua'


class GenerateConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luna hypr generator '")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def generate(self, *arguments, script=GENERATOR, ok=True):
        result = subprocess.run(['/usr/bin/lua', '-E', str(script), *arguments],
                                cwd=self.root, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        if not ok:
            self.assertEqual(result.stdout, '')
            self.assertIn('Cannot generate Hyprland configuration:', result.stderr)
            return result

        self.assertEqual(result.stderr, '')
        # Parse emitted Lua in an empty environment: checkout names are data and
        # must never be able to inject calls or additional configuration fields.
        generated = self.root / 'paths.lua'
        generated.write_text(result.stdout)
        decoded = subprocess.run(['/usr/bin/lua', '-E', '-', str(generated), str(REPO)],
                                 input='local file = assert(io.open(arg[1])); '
                                       'local paths = assert(load(file:read("*a"), "generated paths", "t", {}))(); '
                                       'file:close(); print(dofile(arg[2] .. "/lib/theme/json.lua").encode(paths))',
                                 cwd=self.root, text=True, capture_output=True, timeout=10)
        self.assertEqual(decoded.returncode, 0, decoded.stdout + decoded.stderr)
        return json.loads(decoded.stdout)

    def test_checkout_is_resolved_from_another_working_directory_and_ignores_extra_arguments(self):
        self.assertEqual(self.generate('--unused', 'ignored'), {'install_dir': str(REPO)})

    def test_symlink_and_unusual_checkout_characters_roundtrip_without_execution(self):
        checkout = self.root / 'checkout \' " \\ Ω $(touch injected)\nsecond line'
        script = checkout / 'apps/hypr/scripts/generate-config.lua'
        script.parent.mkdir(parents=True)
        shutil.copy2(GENERATOR, script)
        link = self.root / "generator's symlink.lua"
        link.symlink_to(script)
        self.assertEqual(self.generate(script=link), {'install_dir': str(checkout)})
        self.assertFalse((self.root / 'injected').exists())

    def test_generator_outside_expected_layout_fails_without_partial_lua(self):
        script = self.root / 'misplaced.lua'
        shutil.copy2(GENERATOR, script)
        result = self.generate(script=script, ok=False)
        self.assertIn('must remain inside the Luna checkout', result.stderr)


if __name__ == '__main__':
    unittest.main()
