"""Check shared Lua config resolution without a renderer or filesystem writes."""

import os
from pathlib import Path
import subprocess
import unittest


REPO = Path(__file__).resolve().parents[2]


class ConfigTests(unittest.TestCase):
    def lua(self, code):
        result = subprocess.run(
            ["/usr/bin/lua", "-E", "-", str(REPO)],
            input='local json = dofile(arg[1] .. "/lib/json.lua")\n'
                  'local config = dofile(arg[1] .. "/lib/config.lua")(json)\n' + code,
            env=dict(os.environ, PATH=""), capture_output=True, text=True, timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_deep_merge_replaces_arrays_and_does_not_mutate_inputs(self):
        self.lua('''
local defaults = {app = {count = 5, flag = true, nested = {first = 1}, items = {1, 2, 3}}}
local edits = {app = {count = 0, flag = false, nested = {second = 2}, items = {4}}}
local result = config.merge(defaults, edits)
assert(result.app.count == 0 and result.app.flag == false)
assert(result.app.nested.first == 1 and result.app.nested.second == 2)
assert(#result.app.items == 1 and result.app.items[1] == 4)
result.app.nested.first = 99
result.app.items[1] = 99
assert(defaults.app.nested.first == 1 and defaults.app.nested.second == nil)
assert(defaults.app.flag == true and #defaults.app.items == 3)
assert(edits.app.items[1] == 4 and edits.app.nested.first == nil)
''')

    def test_empty_arrays_objects_and_null_keep_their_shapes(self):
        self.lua('''
local value = config.merge({items = {1, 2}, nested = {keep = true}},
    json.decode('{"items":[],"nested":{},"empty":{},"missing":null}'))
assert(json.encode(value) == '{"empty":{},"items":[],"missing":null,"nested":{"keep":true}}')
assert(value.missing == json.null)
local replaced = config.merge({value = false}, {value = {nested = true}})
assert(replaced.value.nested == true)
assert(#config.merge({items = {1}}, {items = json.array({})}).items == 0)
''')

    def test_dotted_lookup_and_output_preserve_false_zero_and_absence(self):
        self.lua('''
local document = {app = {flag = false, count = 0}}
assert(config.get(document) == document)
assert(config.get(document, "app.flag") == false)
assert(config.get(document, "app.count") == 0)
assert(config.get(document, "app.missing") == nil)
assert(config.get(document, "app.flag.child") == nil)
assert(config.get(document, "app..flag") == nil)
assert(config.format(false, "text") == "false")
assert(config.format(0, "text") == "0")
assert(config.format(nil, "text") == "")
assert(config.format(nil, "json") == "null")
''')


if __name__ == "__main__":
    unittest.main()
