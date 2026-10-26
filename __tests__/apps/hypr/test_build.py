"""Validate generated checkout paths without loading compositor configuration."""

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[3]
BUILDER = REPO / 'scripts/setup/build-app.lua'


class BuildConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luna hypr generator '")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def generate(self, *arguments, script=BUILDER, checkout=REPO, ok=True):
        output = self.root / 'staging'
        output.mkdir(exist_ok=True)
        generated = output / 'generated/paths.lua'
        generated.unlink(missing_ok=True)
        result = subprocess.run(['/usr/bin/lua', '-E', str(script), str(checkout / 'apps/hypr'),
                                 str(output), str(self.root / 'installed/hypr'),
                                 str(self.root / 'installed'), *arguments],
                                cwd=self.root, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        if not ok:
            self.assertEqual(result.stdout, '')
            self.assertFalse(generated.exists())
            return result

        self.assertEqual(result.stderr, '')
        # Parse emitted Lua in an empty environment: checkout names are data and
        # must never be able to inject calls or additional configuration fields.
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
        script = checkout / 'scripts/setup/build-app.lua'
        script.parent.mkdir(parents=True)
        shutil.copy2(BUILDER, script)
        shutil.copytree(REPO / 'lib', checkout / 'lib')
        shutil.copytree(REPO / 'apps/hypr', checkout / 'apps/hypr')
        link = self.root / "generator's symlink.lua"
        link.symlink_to(script)
        self.assertEqual(self.generate(script=link, checkout=checkout), {'install_dir': str(checkout)})
        self.assertFalse((self.root / 'injected').exists())

    def test_builder_records_final_checkout_without_the_staging_directory(self):
        paths = self.generate()
        self.assertEqual(paths, {'install_dir': str(REPO)})
        self.assertNotIn(str(self.root / 'staging'), str(paths))


if __name__ == '__main__':
    unittest.main()
