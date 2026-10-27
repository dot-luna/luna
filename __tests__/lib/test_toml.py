"""Exercise reusable TOML operations without loading any wallpaper-specific code."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest


REPO = Path(__file__).resolve().parents[2]


class TomlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luna toml ' ")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "app.toml"

    def lua(self, code):
        prelude = '''
local root, path = arg[1], arg[2]
local json = dofile(root .. "/lib/json.lua")
local config = dofile(root .. "/lib/config.lua")(json)
local toml = dofile(root .. "/lib/toml.lua")(dofile(root .. "/lib/common.lua"), json)
'''
        result = subprocess.run(["/usr/bin/lua", "-E", "-", str(REPO), str(self.path)],
                                input=prelude + code, env=dict(os.environ, PATH=""),
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_dotted_reads_and_json_shapes_preserve_false_zero_and_empty_values(self):
        self.path.write_text('[app]\nflag = false\ncount = 0\nitems = [[], {}, { sources = {} }]\n')
        output = self.lua('''
local document = toml.read(path)
assert(config.get(document, "app.flag") == false)
assert(config.get(document, "app.count") == 0)
assert(config.get(document, "app.absent") == nil)
assert(config.get(document, "app..flag") == nil)
assert(config.format(false, "text") == "false")
assert(config.format(0, "text") == "0")
assert(config.format(nil, "text") == "")
print(config.format(config.get(document, "app.items"), "json"))
''')
        self.assertEqual(json.loads(output), [[], {}, {"sources": {}}])

    def test_deep_updates_preserve_siblings_comments_and_replace_arrays(self):
        self.path.write_text('# Personal\n[app.nested]\nfirst = 1 # Keep\nsecond = 2\n'
                             '[app]\nitems = [1, 2, 3]\n')
        self.lua('''
toml.update(path, {app = {nested = {second = 4}, items = {false, 0}}})
toml.update(path, {app = {nested = {third = 5}, sources = {named = "object"}}})
''')
        saved = self.path.read_text()
        self.assertIn("# Personal", saved)
        self.assertIn("first = 1 # Keep", saved)
        self.assertEqual(tomllib.loads(saved)["app"],
                         {"nested": {"first": 1, "second": 4, "third": 5},
                          "items": [False, 0], "sources": {"named": "object"}})

    def test_unchanged_and_null_edits_do_not_rewrite(self):
        self.path.write_text('[app]\nflag = true # Keep\nvalues = [true]\n')
        before = self.path.read_bytes(), self.path.stat().st_mtime_ns
        self.lua('''
toml.update(path, {app = {flag = true}})
toml.update(path, json.decode('{"app":{"flag":null}}'))
toml.update(path, json.decode('{"new":{"nested":{"value":null}}}'))
''')
        self.assertEqual((self.path.read_bytes(), self.path.stat().st_mtime_ns), before)
        self.lua('toml.update(path, {app = {values = {1}}})')
        self.assertIs(type(tomllib.loads(self.path.read_text())["app"]["values"][0]), int)

    def test_missing_reads_and_failed_edits_leave_files_untouched(self):
        self.lua('assert(next(toml.read(path)) == nil); toml.update(path, {}); '
                 'toml.update(path, json.decode(\'{"app":{"nested":{"value":null}}}\'))')
        self.assertFalse(self.path.exists())
        self.path.write_text('[app]\nvalue = "original"\n')
        before = self.path.read_bytes()
        self.lua('''
local ok = pcall(toml.update, path, json.decode('{"app":{"value":[null]}}'))
assert(not ok)
''')
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.glob(".luna-toml-*")), [])

    def test_validator_checks_actual_merged_document_before_any_write(self):
        self.path.write_text('app = "invalid"\n[other]\ncount = 1\n')
        before = self.path.read_bytes(), self.path.stat().st_mtime_ns
        self.lua('''
local options = {validate = {"/usr/bin/python3", "-I", "-c",
    "import json,sys; assert isinstance(json.load(sys.stdin)['app'], dict), 'app must be an object'"}}
-- Empty patches leave existing scalars intact; the validator must see that scalar.
for _, patch in ipairs({{}, {app = {}, other = {count = 2}}}) do
    assert(not pcall(toml.update, path, patch, options))
end
''')
        self.assertEqual((self.path.read_bytes(), self.path.stat().st_mtime_ns), before)
        self.lua('''
toml.update(path, {app = {enabled = true}}, {validate = {"/usr/bin/python3", "-I", "-c",
    "import json,sys; assert json.load(sys.stdin)['app']['enabled'] is True"}})
''')
        self.assertEqual(tomllib.loads(self.path.read_text())['app'], {'enabled': True})


if __name__ == "__main__":
    unittest.main()
