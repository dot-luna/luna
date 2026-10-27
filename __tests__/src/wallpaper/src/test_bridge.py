"""Exercise QML's Lua JSON transport with private configs and a recording-only qs."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest


REPO = Path(__file__).resolve().parents[4]
BRIDGE = REPO / "src/wallpaper/src/bridge.lua"


class WallpaperBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna bridge '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bridge = BRIDGE
        self.config = self.root / "config/luna/wallpaper.toml"
        self.config.parent.mkdir(parents=True)
        self.tools = self.root / "bin"
        self.tools.mkdir()
        self.env = dict(os.environ, HOME=str(self.root),
                        XDG_CONFIG_HOME=str(self.root / "config"),
                        XDG_DATA_HOME=str(self.root / "data"),
                        LUNA_WALLPAPER_CONFIG="", WAYLAND_DISPLAY="bridge-test",
                        PATH=str(self.tools) + ":" + os.environ["PATH"],
                        WALLPAPER_BRIDGE_TEST=str(self.root))

        # Every renderer call resolves to this mock; no test contacts the desktop.
        mock = self.tools / "qs"
        mock.write_text('''#!/usr/bin/python3
import json, os, pathlib, sys
root = pathlib.Path(os.environ["WALLPAPER_BRIDGE_TEST"])
with (root / "calls").open("a") as calls:
    calls.write(json.dumps(sys.argv[1:]) + "\\n")
if sys.argv[-1] == "status":
    if (root / "stopped").exists():
        sys.exit(1)
    print("error" if (root / "failed").exists() else "ready")
elif sys.argv[1:4] == ["list", "-a", "-j"]:
    path = root / "instances"
    print(path.read_text() if path.exists() else "No running instances.")
elif sys.argv[1:3] == ["kill", "--pid"]:
    if (root / "stop-failed").exists():
        sys.exit(1)
    path = root / "instances"
    remaining = [item for item in json.loads(path.read_text()) if str(item["pid"]) != sys.argv[3]]
    path.write_text(json.dumps(remaining))
elif sys.argv[1] == "-p":
    print("Mock startup output must not leak into JSON")
''')
        mock.chmod(0o755)

    def raw_request(self, request, *, ok=True):
        """Require one complete JSON reply, including when the process fails."""
        result = subprocess.run(
            ["/usr/bin/lua", "-E", str(self.bridge), request],
            cwd=self.root, env=self.env, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 1, result.stdout)
        response = json.loads(result.stdout)
        self.assertIs(response["ok"], ok)
        if ok:
            self.assertIn("result", response)
            self.assertEqual(response["configPath"], self.env["LUNA_WALLPAPER_CONFIG"] or str(self.config))
        else:
            self.assertIsInstance(response["error"], str)
            self.assertTrue(response["error"])
            self.assertNotIn("result", response)
        return response

    def request(self, method, argument=None, *, ok=True):
        return self.raw_request(json.dumps({"method": method, "argument": argument}), ok=ok)

    def calls(self):
        path = self.root / "calls"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_get_and_update_preserve_unknown_document_shapes_and_comments(self):
        self.config.write_text('''# Personal settings
unknown = [[], {}, [1, "two", true], { inner = [] }]
special = [nan, 2026-01-02, { value = inf }]
not_a_number = nan
infinite = inf
negative_infinite = -inf
day = 2026-01-02
moment = 2026-01-02T03:04:05Z
[wallpaper]
source = "/old.svg" # Keep my source note
fit = "tile"
[custom]
[custom.empty]
''')
        before = self.config.read_text()
        document = self.request("getConfig")["result"]
        self.assertEqual(document["unknown"], [[], {}, [1, "two", True], {"inner": []}])
        self.assertEqual(document["special"], [None, None, {"value": None}])
        self.assertEqual(document["custom"], {"empty": {}})
        for key in ("not_a_number", "infinite", "negative_infinite", "day", "moment"):
            self.assertIn(key, document)
            self.assertIsNone(document[key])
        self.assertEqual(self.config.read_text(), before)

        updated = self.request("updateConfig", {"wallpaper": {"fit": "fill"}})["result"]
        document["wallpaper"]["fit"] = "fill"
        self.assertEqual(updated, document)
        self.assertEqual(self.request("getConfig")["result"], document)
        self.assertIn("# Personal settings", self.config.read_text())
        self.assertIn('# Keep my source note', self.config.read_text())
        self.assertIn("not_a_number = nan", self.config.read_text())
        self.assertIn("day = 2026-01-02", self.config.read_text())
        self.assertEqual(self.calls(), [])

    def test_offline_edits_reject_invalid_values_without_creating_or_rewriting(self):
        self.assertEqual(self.request("getConfig")["result"]["wallpaper"]["fit"], "fill")
        self.request("updateConfig", {"wallpaper": {"fit": "invalid"}}, ok=False)
        self.assertFalse(self.config.exists())
        expected = {
            "wallpaper": {"source": "", "fit": "fit", "background_color": "#123456"},
            "playback": {"pause_when_output_inactive": False},
            "transition": {"type": "none", "duration_ms": 0},
        }
        self.assertEqual(self.request("updateConfig", expected)["result"], expected)
        original = self.config.read_bytes()
        modified = self.config.stat().st_mtime_ns
        invalid = {
            "wallpaper": {"fit": "unsupported", "source": "relative.svg", "background_color": "red"},
            "playback": {"pause_when_output_inactive": "false"},
            "transition": {"type": "slide", "duration_ms": -1},
        }
        for changes in (invalid, None, "wrong", [], {"wallpaper": []}):
            with self.subTest(changes=changes):
                self.request("updateConfig", changes, ok=False)
                self.assertEqual(self.config.read_bytes(), original)
                self.assertEqual(self.config.stat().st_mtime_ns, modified)
        self.assertEqual(self.calls(), [])

    def test_source_updates_preserve_quoted_paths_and_clear_explicitly(self):
        source = str(self.root / "quote ' $(touch INJECTED); `touch ALSO_INJECTED` 🖼.svg")
        self.config.write_text('# Keep\n[wallpaper]\nsource = "/old.svg"\nfit = "tile"\n')
        self.assertEqual(self.request("updateConfig", {"wallpaper": {"source": source}})["result"]["wallpaper"]["source"], source)
        self.assertEqual(tomllib.loads(self.config.read_text())["wallpaper"]["source"], source)
        self.assertEqual(self.calls(), [])
        self.assertIn("# Keep", self.config.read_text())
        self.assertFalse((self.root / "INJECTED").exists())
        self.assertFalse((self.root / "ALSO_INJECTED").exists())
        self.assertEqual(self.request("updateConfig", {"wallpaper": {"source": ""}})["result"]["wallpaper"]["source"], "")
        self.assertEqual(self.request("getConfig", "wallpaper.source")["result"], "")

    def test_newlines_in_config_path_are_data_and_media_controls_are_rejected(self):
        custom = self.root / "config ' $(touch INJECTED)\nwallpaper.toml"
        self.env["LUNA_WALLPAPER_CONFIG"] = str(custom)
        self.request("updateConfig", {"wallpaper": {"fit": "center"}})
        self.assertTrue(custom.is_file())
        self.assertFalse((self.root / "INJECTED").exists())
        for source in ("/image\n.svg", "/image\x00.svg", "relative.svg", None, {}):
            with self.subTest(source=source):
                self.request("updateConfig", {"wallpaper": {"source": source}}, ok=False)
        self.assertEqual(self.calls(), [])

    def test_reload_replies_null_without_restarting_or_saving(self):
        original = '[wallpaper]\nsource = ""\nbackground_color = "#123456"\n'
        self.config.write_text(original)
        self.assertIsNone(self.request("reload")["result"])
        self.assertTrue(any(call[-1] == "reload" for call in self.calls()))
        self.assertFalse(any(call[0] in ("list", "kill") for call in self.calls()))
        self.assertEqual(self.config.read_text(), original)
        (self.root / "failed").touch()
        self.request("reload", ok=False)
        self.assertEqual(self.config.read_text(), original)

    def test_status_reports_ready_or_stopped_without_launching(self):
        self.assertEqual(self.request("status")["result"], "ready")
        (self.root / "stopped").touch()
        self.assertEqual(self.request("status")["result"], "stopped")
        self.assertEqual(len(self.calls()), 2)
        self.assertTrue(all(call[0] == "ipc" and call[-1] == "status" for call in self.calls()))
        self.assertFalse(self.config.exists())

    def test_start_leaves_config_untouched_and_keeps_renderer_output_out_of_json(self):
        self.assertIsNone(self.request("start")["result"])
        self.assertFalse(self.config.exists())
        calls = self.calls()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "-p")
        self.assertEqual(Path(calls[0][1]).resolve(), REPO / "src/wallpaper/src/shell/shell.qml")
        self.assertEqual(calls[0][2:], ["--daemonize", "--no-duplicate"])

    def test_restart_only_stops_exact_wallpaper_path(self):
        instances = [
            {"id": "current", "pid": 101, "config_path": str(REPO / "src/wallpaper/src/shell/shell.qml")},
            {"id": "bar", "pid": 203, "config_path": str(REPO / "src/luna-bar/shell.qml")},
            {"id": "other", "pid": 204, "config_path": "/other/src/wallpaper/src/shell/shell.qml"},
        ]
        state = self.root / "instances"
        state.write_text(json.dumps(instances))
        self.assertIsNone(self.request("restart")["result"])
        self.assertEqual([call for call in self.calls() if call[0] == "kill"],
                         [["kill", "--pid", "101"]])
        self.assertEqual(json.loads(state.read_text()), instances[1:])
        self.assertEqual(self.calls()[-1][0], "-p")
        self.assertEqual(Path(self.calls()[-1][1]).resolve(), REPO / "src/wallpaper/src/shell/shell.qml")

    def test_installed_link_and_checkout_use_the_same_renderer_identity(self):
        alias = self.root / "installed ' luna"
        alias.symlink_to(REPO, target_is_directory=True)
        self.request("start")
        self.bridge = alias / "src/wallpaper/src/bridge.lua"
        self.request("start")
        self.request("status")
        self.request("reload")

        # Exact path strings determine qs identity; resolving only in this assertion
        # would hide duplicate launches and IPC aimed at the wrong shell.
        renderer = str(REPO / "src/wallpaper/src/shell/shell.qml")
        calls = self.calls()
        self.assertGreaterEqual(len(calls), 5)
        self.assertTrue(all(call[call.index("-p") + 1] == renderer for call in calls), calls)

    def test_stop_is_scoped_repeatable_and_independent_of_config_or_wayland(self):
        self.assertIsNone(self.request("stop")["result"])
        self.assertFalse(self.config.exists())
        alias = self.root / "installed ' wallpaper.qml"
        alias.symlink_to(REPO / "src/wallpaper/src/shell/shell.qml")
        instances = [
            {"id": "wallpaper-1", "pid": 201, "config_path": str(REPO / "src/wallpaper/src/shell/shell.qml")},
            {"id": "wallpaper-2", "pid": 202, "config_path": str(alias)},
            {"id": "bar", "pid": 203, "config_path": str(REPO / "src/luna-bar/shell.qml")},
            {"id": "other", "pid": 204, "config_path": "/other/src/wallpaper/src/shell/shell.qml"},
        ]
        state = self.root / "instances"
        state.write_text(json.dumps(instances))
        self.env["WAYLAND_DISPLAY"] = ""
        original = "# Unfinished user edit\n[wallpaper\n"
        self.config.write_text(original)
        for _ in range(2):
            self.assertIsNone(self.request("stop")["result"])
            self.assertEqual(self.config.read_text(), original)
        self.assertEqual(json.loads(state.read_text()), instances[2:])
        self.assertEqual([call for call in self.calls() if call[0] == "kill"],
                         [["kill", "--pid", "201"], ["kill", "--pid", "202"]])
        self.assertTrue(all(call[0] in ("list", "kill") for call in self.calls()))
        self.config.unlink()
        self.request("stop")
        self.assertFalse(self.config.exists())

    def test_stop_failure_reports_error_and_restart_does_not_launch(self):
        instances = [{"id": "wallpaper", "pid": 201, "config_path": str(REPO / "src/wallpaper/src/shell/shell.qml")}]
        state = self.root / "instances"
        state.write_text(json.dumps(instances))
        (self.root / "stop-failed").touch()
        self.request("stop", ok=False)
        self.request("restart", ok=False)
        self.assertEqual(json.loads(state.read_text()), instances)
        self.assertFalse(any(call[0] == "-p" for call in self.calls()))

    def test_invalid_requests_return_errors_without_reusing_a_previous_edit(self):
        self.request("updateConfig", {"wallpaper": {"fit": "tile"}})
        original = self.config.read_bytes()
        for raw in ('', '{', '{"method":"getConfig",}', 'null', '[]',
                    '{"method":"getConfig"} trailing',
                    '{"method":"os.execute", "argument":"touch INJECTED"}',
                    '{"method":"getConfig","method":"start"}'):
            with self.subTest(raw=raw):
                self.raw_request(raw, ok=False)
                self.assertEqual(self.config.read_bytes(), original)
        self.assertFalse((self.root / "INJECTED").exists())
        self.assertEqual(self.calls(), [])

    def test_malformed_toml_errors_before_any_renderer_request(self):
        original = '[wallpaper\nsource = "broken"\n'
        self.config.write_text(original)
        for method, argument in (("getConfig", None), ("getConfig", "wallpaper.source"),
                                 ("updateConfig", {"wallpaper": {"fit": "fit"}}),
                                 ("updateConfig", {"wallpaper": {"source": "/new.svg"}})):
            with self.subTest(method=method):
                self.request(method, argument, ok=False)
                self.assertEqual(self.config.read_text(), original)
        self.assertEqual(self.calls(), [])

    def test_config_write_failure_preserves_file_without_renderer_calls(self):
        # Copy the small API into a private checkout: even a broken protection check
        # must never let this regression test modify the real repository's reference.
        checkout = self.root / "checkout"
        for relative in ("src/wallpaper/src/bridge.lua", "src/wallpaper/src/api.lua",
                         "src/wallpaper/src/config.lua", "src/wallpaper/src/read.lua", "src/wallpaper/src/runtime.lua",
                         "lib/common.lua", "lib/json.lua", "lib/quickshell.lua", "lib/config.lua", "lib/toml.lua",
                         "lib/validation.lua", "lib/vendor/tableshape/init.lua",
                         "apps/luna-wallpaper/config/wallpaper.toml"):
            target = checkout / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / relative, target)
        self.bridge = checkout / "src/wallpaper/src/bridge.lua"
        reference = checkout / "src/wallpaper/config.toml"
        reference.write_text('[wallpaper]\nsource = "/reference.svg"\nfit = "center"\n')
        original = reference.read_bytes()
        self.config.symlink_to(reference)
        self.request("updateConfig", {"wallpaper": {"fit": "stretch"}}, ok=False)
        self.assertEqual(self.calls(), [])
        self.request("updateConfig", {"wallpaper": {"source": "/new-bridge-test.svg"}}, ok=False)
        self.assertEqual(self.calls(), [])
        self.assertTrue(self.config.is_symlink())
        self.assertEqual(reference.read_bytes(), original)

    def test_saved_edits_do_not_depend_on_media_readiness(self):
        self.config.write_text('# Personal\n[wallpaper]\nsource = "/old.svg"\n')
        (self.root / "failed").touch()
        self.request("updateConfig", {"wallpaper": {"source": "/later.svg"}})
        self.assertEqual(self.calls(), [])
        saved = self.config.read_bytes()
        self.request("reload", ok=False)
        self.assertEqual(self.config.read_bytes(), saved)

    def test_keyed_get_returns_scalars_tables_arrays_or_null(self):
        self.request("updateConfig", {"playback": {"pause_when_output_inactive": False},
                                     "transition": {"duration_ms": 0}, "custom": {"values": [[], {}]}})
        self.assertIs(self.request("getConfig", "playback.pause_when_output_inactive")["result"], False)
        self.assertEqual(self.request("getConfig", "transition.duration_ms")["result"], 0)
        self.assertEqual(self.request("getConfig", "custom.values")["result"], [[], {}])
        self.assertEqual(self.request("getConfig", "custom")["result"], {"values": [[], {}]})
        self.assertIsNone(self.request("getConfig", "custom.absent")["result"])
        self.config.write_text('[broken')
        self.assertEqual(self.request("getConfigFile")["result"], str(self.config))
        self.assertEqual(self.calls(), [])
        for method in ("current", "setSource"):
            self.request(method, ok=False)


if __name__ == "__main__":
    unittest.main()
