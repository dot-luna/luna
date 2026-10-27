"""Check reusable Tableshape object schemas without files or desktop processes."""

from pathlib import Path
import subprocess
import unittest


REPO = Path(__file__).resolve().parents[2]


class ValidationTests(unittest.TestCase):
    def test_nested_objects_validate_without_filtering_or_changing_values(self):
        result = subprocess.run(["/usr/bin/lua", "-E", "-", str(REPO)], input='''
local json = dofile(arg[1] .. "/lib/json.lua")
local validation = dofile(arg[1] .. "/lib/validation.lua")(arg[1])
local types = validation.types
local schema = validation.object({
    app = validation.object({
        mode = types.one_of({"light", "dark"}),
        enabled = types.boolean:is_optional(),
    }),
})
local value = json.decode('{"app":{"mode":"dark","enabled":false},"future":[1,2]}')
local before = json.encode(value)
assert(schema:check_value(value))
assert(json.encode(value) == before)
assert(schema:check_value({app = {mode = "light"}}))

-- Neither empty arrays nor JSON null may masquerade as config objects.
for _, raw in ipairs({'[]', 'null', '{"app":[]}', '{"app":null}',
    '{"app":{"mode":"wrong"}}', '{"app":{"mode":"dark","enabled":"false"}}'}) do
    local invalid = json.decode(raw)
    local original = json.encode(invalid)
    local ok, message = schema:check_value(invalid)
    assert(not ok and type(message) == "string")
    assert(json.encode(invalid) == original)
end
''', capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
