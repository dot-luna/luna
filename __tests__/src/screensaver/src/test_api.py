"""Check the public API's passive imports, file semantics, and atomic awake calls."""

import json
import subprocess
import time
import tomllib
import unittest

from test_runtime import REPO, ScreensaverFixture


class ScreensaverApiTests(ScreensaverFixture, unittest.TestCase):
    def test_import_and_disk_edits_never_start_controller(self):
        self.lua('''
for _, method in ipairs({"getConfig", "updateConfig", "getConfigFile", "start", "stop", "restart",
    "reload", "status", "getState", "show", "hide", "setStayAwake", "toggleStayAwake",
    "install", "list", "set", "removalPlan", "remove", "getDirectory"}) do
    assert(type(screensaver[method]) == "function")
end
assert(screensaver.getConfig("idle.lock_seconds") == 600)
screensaver.updateConfig({idle = {screensaver_seconds = 0}, settings = {clock = false}})
assert(screensaver.getConfig("idle.screensaver_seconds") == 0)
assert(screensaver.getConfig("settings.clock") == false)
assert(screensaver.getConfig("missing") == nil)
local file = assert(io.open(screensaver.getConfigFile(), "w"))
file:write('[idle]\\nlock_seconds = 123\\n')
file:close()
assert(screensaver.getConfig("idle.lock_seconds") == 123)
''')
        self.assertFalse(self.calls())

    def test_awake_mutations_are_atomic_boolean_requests_and_return_full_state(self):
        self.lua('''
assert(screensaver.setStayAwake(true).stayAwake)
assert(screensaver.setStayAwake(true).stayAwake)
assert(not screensaver.toggleStayAwake().stayAwake)
assert(screensaver.toggleStayAwake().stayAwake)
assert(not screensaver.setStayAwake(false).stayAwake)
assert(screensaver.getState().running)
''')
        self.assertEqual(len(self.starts()), 1)
        setters = [call[-1] for call in self.calls() if "setStayAwake" in call]
        self.assertEqual(setters, ["true", "true", "false"])
        self.assertEqual(sum(call[-1] == "toggleStayAwake" for call in self.calls()), 2)
        self.assertFalse(self.config.exists())

    def test_bad_awake_input_does_not_launch(self):
        self.lua('assert(not pcall(screensaver.setStayAwake, "false")); '
                 'assert(not pcall(screensaver.setStayAwake, nil))')
        self.assertFalse(self.calls())

    def install_shells(self):
        source = self.root / "source.qml"
        source.write_text("import Quickshell\nShellRoot {}\n")
        self.lua('screensaver.install("source.qml", {name = "stars"}); '
                 'screensaver.install("source.qml", {name = "waves"})')
        return self.root / "data/luna/screensavers"

    def test_library_import_install_and_listing_do_not_start_or_select(self):
        library = self.install_shells()
        self.lua('''
local entries = screensaver.list()
assert(#entries == 5 and entries[1].name == "clock" and entries[1].current)
assert(entries[4].name == "stars" and not entries[4].current)
assert(entries[5].name == "waves" and not entries[5].bundled)
assert(screensaver.getDirectory() == os.getenv("XDG_DATA_HOME") .. "/luna/screensavers")
''')
        self.assertTrue((library / "stars/shell.qml").exists())
        self.assertFalse(self.config.exists())
        self.assertFalse(self.calls())

    def test_saved_and_live_selections_are_protected_until_reloaded(self):
        library = self.install_shells()
        self.lua('''
screensaver.set("stars")
screensaver.updateConfig({renderer = {shell = ""}})
assert(not pcall(screensaver.removalPlan, {"stars"}))
assert(not pcall(screensaver.remove, {"stars"}))
assert(not pcall(screensaver.install, "source.qml", {name = "stars", force = true}))
screensaver.reload()
assert(screensaver.remove({"stars"})[1] == "stars")
screensaver.set("waves")
screensaver.stop()
assert(not pcall(screensaver.remove, {"waves"}))
''')
        self.assertFalse((library / "stars").exists())
        self.assertTrue((library / "waves").exists())

    def test_tilde_and_symlink_selection_marks_current_and_protects_package(self):
        library = self.install_shells()
        (self.root / "alias.qml").symlink_to(library / "stars/shell.qml")
        self.lua('''
screensaver.updateConfig({renderer = {shell = "~/alias.qml"}})
assert(screensaver.list()[4].current)
assert(not pcall(screensaver.remove, {"stars"}))
local result = screensaver.set("~/alias.qml")
assert(result.name == "stars" and result.current)
''')
        self.assertEqual(tomllib.loads(self.config.read_text())["renderer"]["shell"],
                         str(library / "stars/shell.qml"))

    def test_failed_set_restores_only_selection_and_keeps_other_config(self):
        self.install_shells()
        self.lua('screensaver.updateConfig({settings = {message = "hello"}, idle = {lock_seconds = 777}}); '
                 'screensaver.set("stars")')
        self.env["TEST_FAIL_METHOD"] = "configure"
        self.lua('assert(not pcall(screensaver.set, "waves"))')
        saved = tomllib.loads(self.config.read_text())
        applied = json.loads((self.root / "configured").read_text())["config"]
        self.assertEqual(saved["renderer"], applied["renderer"])
        self.assertEqual(saved["settings"]["message"], "hello")
        self.assertEqual(saved["idle"]["lock_seconds"], 777)

    def test_unreadable_live_selection_blocks_destructive_library_operations(self):
        library = self.install_shells()
        self.lua('screensaver.start()')
        self.env["TEST_FAIL_METHOD"] = "getRendererShell"
        self.lua('assert(not pcall(screensaver.remove, {"stars"})); '
                 'assert(not pcall(screensaver.install, "source.qml", {name = "waves", force = true}))')
        self.assertTrue((library / "stars").exists())
        self.assertTrue((library / "waves").exists())

    def test_fast_renderer_failure_rolls_back_even_after_active_is_cleared(self):
        library = self.install_shells()
        self.lua('screensaver.set("stars"); screensaver.show()')
        self.env["TEST_FAIL_SHELL"] = str(library / "waves/shell.qml")
        failure = self.lua('screensaver.set("waves")', ok=False)
        self.assertIn("Broken custom shell", failure.stderr)
        expected = str(library / "stars/shell.qml")
        self.assertEqual(tomllib.loads(self.config.read_text())["renderer"]["shell"], expected)
        self.assertEqual(json.loads((self.root / "configured").read_text())["config"]["renderer"]["shell"], expected)

    def test_concurrent_set_cannot_select_a_package_during_its_removal(self):
        library = self.install_shells()
        self.lua('screensaver.set("stars")')

        def launch(name, code, environment):
            script = self.root / (name + ".lua")
            script.write_text('local screensaver = dofile(arg[1] .. "/lib/luna.lua")(arg[1]).screensaver\n' + code)
            process = subprocess.Popen(["/usr/bin/lua", "-E", str(script), str(REPO)], cwd=self.root,
                                       env=environment, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return process

        removing = launch("remove", 'screensaver.remove({"waves"})',
                          dict(self.env, TEST_HOLD_METHOD="getRendererShell"))
        selecting = None
        try:
            deadline = time.monotonic() + 5
            while not (self.root / "held").exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue((self.root / "held").exists())
            selecting = launch("select", 'screensaver.set("waves")', self.env)
            time.sleep(0.1)
            self.assertIsNone(selecting.poll(), "Selection must wait for the removal transaction")
            (self.root / "release").touch()
            output, error = removing.communicate(timeout=10)
            self.assertEqual(removing.returncode, 0, output + error)
            output, error = selecting.communicate(timeout=10)
            self.assertNotEqual(selecting.returncode, 0)
            self.assertIn("Screensaver not found", error)
        finally:
            (self.root / "release").touch()
            for process in (removing, selecting):
                if process is not None:
                    if process.poll() is None:
                        process.terminate()
                    process.communicate(timeout=15)
        self.assertFalse((library / "waves").exists())
        self.assertEqual(tomllib.loads(self.config.read_text())["renderer"]["shell"],
                         str(library / "stars/shell.qml"))


if __name__ == "__main__":
    unittest.main()
