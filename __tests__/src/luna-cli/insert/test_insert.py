import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class InsertTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.env = {**os.environ, "HOME": str(self.home), "XDG_CONFIG_HOME": str(self.home / "config"), "GIPHY_API_KEY": "", "XDG_RUNTIME_DIR": str(self.home)}

    def cli(self, *args):
        return subprocess.run([str(ROOT / "bin/luna"), "insert", *args], env=self.env, capture_output=True, text=True)

    def test_offline_unicode_data(self):
        result = self.cli("emoji")
        self.assertEqual(result.returncode, 0, result.stderr)
        entries = json.loads(result.stdout)["results"]
        self.assertGreater(len(entries), 3500)
        glyphs = [entry["emoji"] for entry in entries]
        self.assertEqual(len(glyphs), len(set(glyphs)))
        self.assertIn("🇳🇵", glyphs)
        self.assertIn("👍🏽", glyphs)
        self.assertIn("👩‍💻", glyphs)

    def test_missing_key(self):
        result = json.loads(self.cli("gifs", "hello").stdout)
        self.assertTrue(result["needsKey"])
        self.assertEqual(result["results"], [])

    def test_paste_rejects_invalid_inputs_before_touching_clipboard(self):
        for args in [("paste-emoji", "not an emoji", "0x1"),
                     ("paste-giphy", "https://giphy.com.evil.test/gif", "0x1")]:
            with self.subTest(args=args):
                self.assertNotEqual(self.cli(*args).returncode, 0)

    def test_giphy_normalization_and_key_not_in_argv(self):
        response = {"data": [{"title": "Happy", "username": "artist", "url": "https://giphy.com/gifs/abc",
                             "images": {"fixed_width_small_still": {"url": "https://media.giphy.com/a.jpg"},
                                        "downsized": {"url": "https://media.giphy.com/a.gif"}}}],
                    "pagination": {"total_count": 30}}
        fixture = self.home / "response.json"
        fixture.write_text(json.dumps(response))
        # Mock the HTTP transport, retaining real JSON parsing and result mapping.
        script = r'''
local common = dofile(arg[1] .. "/lib/common.lua")
local real_capture = common.capture
common.capture = function(command, quiet)
    if command[1] ~= "curl" then return real_capture(command, quiet) end
    for _, value in ipairs(command) do assert(not value:find("test-secret", 1, true)) end
    local config = assert(io.open(command[#command])):read("*a")
    assert(config:find("api_key=test-secret", 1, true))
    assert(config:find("q=happy%20cat", 1, true))
    return assert(io.open(arg[2])):read("*a"), true
end
dofile(arg[1] .. "/src/luna-cli/insert/backend.lua")(common, arg[1] .. "/src/luna-cli/insert").giphy("happy cat", 0)
'''
        script_path = self.home / "mock.lua"
        script_path.write_text(script)
        result = subprocess.run(["lua", str(script_path), str(ROOT), str(fixture)],
                                env={**self.env, "GIPHY_API_KEY": "test-secret"}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data["hasMore"])
        self.assertEqual(data["results"][0]["creator"], "artist")
        self.assertEqual(data["results"][0]["animation"], "https://media.giphy.com/a.gif")

    def test_paste_keeps_unicode_and_uses_terminal_shortcut(self):
        script = r'''
local common = dofile(arg[1] .. "/lib/common.lua")
local capture = common.capture
local commands = {}
common.capture = function(command, quiet)
    if command[1] == "hyprctl" then return '{"address":"0x1","class":"kitty"}', true end
    return capture(command, quiet)
end
common.run = function(command) table.insert(commands, table.concat(command, " ")) end
os.execute = function(command)
    local path = command:match(" < '([^']+)'")
    assert(path)
    assert(assert(io.open(path, "rb")):read("*a") == "👍🏽👍🏽🇳🇵")
    return true
end
dofile(arg[1] .. "/src/luna-cli/insert/backend.lua")(common, arg[1] .. "/src/luna-cli/insert").paste_emoji('["👍🏽","👍🏽","🇳🇵"]', "0x1")
assert(commands[#commands] == "wtype -M ctrl -M shift -k v -m shift -m ctrl")
'''
        path = self.home / "paste.lua"
        path.write_text(script)
        result = subprocess.run(["lua", str(path), str(ROOT)], env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_giphy_pastes_binary_gif_and_rejects_non_image_response(self):
        script = r'''
local common = dofile(arg[1] .. "/lib/common.lua")
local capture = common.capture
local data = "GIF89a" .. string.char(1, 0, 1, 0, 0, 0, 0) .. ";"
local copied, pasted = false, false
local real_run = common.run
common.capture = function(command, quiet)
    if command[1] == "curl" then return data, true end
    if command[1] == "hyprctl" then return '{"address":"0x1","class":"browser"}', true end
    return capture(command, quiet)
end
common.run = function(command)
    if command[1] == "mkdir" then return real_run(command) end
    if command[1] == "wtype" then pasted = true end
end
local real_execute = os.execute
os.execute = function(command)
    if command:find("mkdir", 1, true) then return real_execute(command) end
    local path = command:match(" < '([^']+)'")
    local bytes = assert(io.open(path, "rb")):read("*a")
    if command:find("wl-copy", 1, true) then
        assert(command:find("text/uri-list", 1, true))
        local gif_path = assert(bytes:match("^file://(.-)\r\n$"))
        assert(assert(io.open(gif_path, "rb")):read("*a") == data)
        copied = true
    else
        assert(bytes == data)
    end
    return true
end
local backend = dofile(arg[1] .. "/src/luna-cli/insert/backend.lua")(common, arg[1] .. "/src/luna-cli/insert")
backend.paste_giphy("https://media.giphy.com/media/example/giphy.gif", "0x1")
assert(copied and pasted)
data = "<html>not a GIF</html>"
copied, pasted = false, false
assert(not pcall(backend.paste_giphy, "https://media.giphy.com/error", "0x1"))
assert(not copied and not pasted)
'''
        path = self.home / "gif.lua"
        path.write_text(script)
        result = subprocess.run(["lua", str(path), str(ROOT)], env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
