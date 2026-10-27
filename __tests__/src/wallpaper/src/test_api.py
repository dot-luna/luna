"""Call the public Lua API directly, with private files and a recording-only qs."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest


REPO = Path(__file__).resolve().parents[4]


class WallpaperApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna-api '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config = self.root / "config/luna/wallpaper.toml"
        self.config.parent.mkdir(parents=True)
        self.tools = self.root / "bin"
        self.tools.mkdir()
        self.env = dict(os.environ, HOME=str(self.root), XDG_CONFIG_HOME=str(self.root / "config"),
                        XDG_DATA_HOME=str(self.root / "data"), LUNA_WALLPAPER_CONFIG="",
                        PATH=str(self.tools) + ":" + os.environ["PATH"],
                        WAYLAND_DISPLAY="test", WALLPAPER_API_TEST=str(self.root))
        # Never contact the desktop. Distinguish a stopped renderer from decode failure.
        mock = self.tools / "qs"
        mock.write_text('''#!/usr/bin/python3
import json, os, pathlib, sys
root = pathlib.Path(os.environ["WALLPAPER_API_TEST"])
with (root / "calls").open("a") as calls:
    calls.write(json.dumps(sys.argv[1:]) + "\\n")
if sys.argv[-1] == "status":
    if (root / "stopped").exists():
        sys.exit(1)
    print("error" if (root / "failed").exists() else "loading" if (root / "loading").exists() else "ready")
elif sys.argv[1] == "-p":
    print("Mock renderer startup output")
''')
        mock.chmod(0o755)

    def lua(self, code):
        # Load from an unrelated cwd, without parsing CLI arguments or invoking bin/luna.
        result = subprocess.run(
            ["/usr/bin/lua", "-E", "-", str(REPO)],
            input='local luna = dofile(arg[1] .. "/lib/luna.lua")(arg[1])\n' + code,
            cwd=self.root, env=self.env, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "", "The wallpaper API must leave output to its caller")
        return result

    def calls(self):
        return [json.loads(line) for line in (self.root / "calls").read_text().splitlines()]

    def test_loading_api_and_editing_config_never_starts_renderer(self):
        self.lua('''
for _, name in ipairs({"getConfig", "updateConfig", "getConfigFile", "reload", "status", "start", "stop", "restart"}) do
    assert(type(luna.wallpaper[name]) == "function")
end
assert(type(luna.wallpapers.add) == "function")
assert(luna.wallpaper.current == nil and luna.wallpaper.setSource == nil)
assert(luna.wallpaper.getConfig().wallpaper.fit == "fill")
assert(luna.wallpaper.getConfig("missing") == nil)
assert(luna.wallpaper.getConfigFile() == os.getenv("XDG_CONFIG_HOME") .. "/luna/wallpaper.toml")
luna.wallpaper.updateConfig({wallpaper = {fit = "fit", background_color = "#123456"}})
assert(luna.wallpaper.getConfig().wallpaper.fit == "fit")
assert(luna.wallpaper.getConfig("wallpaper.source") == "")
''')
        self.assertFalse((self.root / "calls").exists())
        self.assertEqual(tomllib.loads(self.config.read_text())["wallpaper"]["fit"], "fit")

    def test_source_and_clear_use_offline_partial_config_updates(self):
        self.config.write_text('# Personal\n[wallpaper]\nsource = "/old.svg"\nfit = "tile"\n')
        self.lua('''
luna.wallpaper.updateConfig({wallpaper = {source = "/new.svg"}})
assert(luna.wallpaper.getConfig("wallpaper.source") == "/new.svg")
''')
        self.assertEqual(tomllib.loads(self.config.read_text())["wallpaper"]["source"], "/new.svg")
        self.assertIn('# Personal', self.config.read_text())
        self.assertIn('fit = "tile"', self.config.read_text())
        self.lua('luna.wallpaper.updateConfig({wallpaper = {source = ""}})\nassert(luna.wallpaper.getConfig("wallpaper.source") == "")')
        self.assertEqual(tomllib.loads(self.config.read_text())["wallpaper"]["source"], "")

    def test_keyed_reads_preserve_false_zero_and_file_getter_ignores_parse_errors(self):
        self.config.write_text('[playback]\npause_when_output_inactive = false\n[transition]\nduration_ms = 0\n')
        self.lua('assert(luna.wallpaper.getConfig("playback.pause_when_output_inactive") == false); '
                 'assert(luna.wallpaper.getConfig("transition.duration_ms") == 0)')
        self.config.write_text('[broken')
        self.lua('assert(luna.wallpaper.getConfigFile() == os.getenv("XDG_CONFIG_HOME") .. "/luna/wallpaper.toml")')
        self.assertFalse((self.root / "calls").exists())

    def test_config_reads_disk_and_edits_file_in_every_renderer_state_without_reload(self):
        for marker, state in ((None, "ready"), ("loading", "loading"), ("failed", "error"), ("stopped", "stopped")):
            with self.subTest(state=state):
                for name in ("failed", "stopped", "loading"):
                    (self.root / name).unlink(missing_ok=True)
                if marker:
                    (self.root / marker).touch()
                self.lua('assert(luna.wallpaper.status() == "' + state + '")\n' + '''
luna.wallpaper.updateConfig({wallpaper = {fit = "fill"}})
assert(luna.wallpaper.getConfig("wallpaper.fit") == "fill")
-- Simulate a manual edit after creating the API; getters must not reuse a cache.
local file = assert(io.open(luna.wallpaper.getConfigFile(), "w"))
file:write('[wallpaper]\\nsource = "/manual.svg"\\nfit = "tile"\\n')
file:close()
assert(luna.wallpaper.getConfig("wallpaper.fit") == "tile")
luna.wallpaper.updateConfig({wallpaper = {background_color = "#123456"}})
assert(luna.wallpaper.getConfig("wallpaper.source") == "/manual.svg")
''')
                self.assertEqual(tomllib.loads(self.config.read_text())["wallpaper"],
                                 {"source": "/manual.svg", "fit": "tile", "background_color": "#123456"})
        self.assertEqual(len(self.calls()), 4)
        self.assertTrue(all(call[-1] == "status" for call in self.calls()))

    def test_reload_uses_ipc_without_killing_renderer_or_writing_config(self):
        original = '[wallpaper]\nsource = ""\nbackground_color = "#123456"\n'
        self.config.write_text(original)
        self.lua('luna.wallpaper.reload()')
        calls = self.calls()
        self.assertTrue(any(call[-1] == "reload" for call in calls))
        self.assertFalse(any(call[0] in ("kill", "list") for call in calls))
        self.assertEqual(self.config.read_text(), original)
        (self.root / "failed").touch()
        self.lua('local ok = pcall(luna.wallpaper.reload)\nassert(not ok)')
        self.assertEqual(self.config.read_text(), original)

    def test_stopped_status_and_invalid_source_do_not_launch(self):
        (self.root / "stopped").touch()
        self.lua('''
assert(luna.wallpaper.status() == "stopped")
assert(not pcall(luna.wallpaper.updateConfig, {wallpaper = {source = "relative.svg"}}))
''')
        self.assertEqual(len(self.calls()), 1)
        self.assertEqual(self.calls()[0][-1], "status")
        self.assertFalse(self.config.exists())


if __name__ == "__main__":
    unittest.main()
