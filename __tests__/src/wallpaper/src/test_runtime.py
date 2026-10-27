"""Exercise shared wallpaper operations with mocked system calls only."""

from pathlib import Path
import subprocess
import os
import tempfile
import time
import unittest


REPO = Path(__file__).resolve().parents[4]


class WallpaperRuntimeTests(unittest.TestCase):
    def test_renderer_session_survives_a_cancelled_caller(self):
        # Fake daemonization leaves a short-lived marker writer in qs's session.
        # Timing out the caller must kill its own children, not this renderer stand-in.
        with tempfile.TemporaryDirectory(prefix="luna runtime '") as temporary:
            root = Path(temporary)
            executable = root / "qs"
            executable.write_text('''#!/usr/bin/python3
import os, pathlib, subprocess, sys
root = pathlib.Path(os.environ["LUNA_RUNTIME_TEST"])
(root / "session").write_text(str(os.getsid(0)))
subprocess.Popen([sys.executable, "-c", "import pathlib,sys,time; time.sleep(0.5); pathlib.Path(sys.argv[1]).touch()", str(root / "alive")],
                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
''')
            executable.chmod(0o755)
            environment = dict(os.environ, PATH=str(root) + ":" + os.environ["PATH"],
                               LUNA_RUNTIME_TEST=str(root), WAYLAND_DISPLAY="test")
            script = '''
local root = arg[1]
local common = dofile(root .. "/lib/common.lua")
local runtime = dofile(root .. "/src/wallpaper/src/runtime.lua")(common, root, "/fake/shell.qml")
runtime.start()
common.run({"sleep", "5"})
'''
            result = subprocess.run(
                ["/usr/bin/timeout", "--signal=KILL", "0.3s", "/usr/bin/lua", "-E", "-", str(REPO)],
                input=script, env=environment, capture_output=True, text=True, timeout=5,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue((root / "session").exists(), result.stderr)
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and not (root / "alive").exists():
                time.sleep(0.02)
            self.assertTrue((root / "alive").exists(), "Caller cancellation killed the detached renderer")

    def test_renderer_deadlines_allow_slow_loading_and_remain_bounded(self):
        # Stub process calls in Lua so the full timeout path takes no wall-clock minute.
        script = '''
local status_calls, sleeps = 0, 0
local mode = "slow"
local common = {
    available = function() return true end,
    succeeds = function() return false end,
    info = function() end,
    run = function(args) if args[1] == "sleep" then sleeps = sleeps + 1 end end,
    capture = function(args)
        if args[1] == "realpath" then return args[4] .. "\\n", true end
        if args[#args] == "status" then
            status_calls = status_calls + 1
            return mode == "slow" and status_calls == 400 and "ready" or "loading", true
        end
        return "", true
    end,
}
local backend = dofile(arg[1] .. "/src/wallpaper/src/runtime.lua")(common, arg[1], "/fake/shell.qml")
backend.reload()
assert(status_calls == 400 and sleeps == 399)
mode, status_calls, sleeps = "timeout", 0, 0
local ok = pcall(backend.reload)
assert(not ok and status_calls == 600 and sleeps == 600)
'''
        result = subprocess.run(['/usr/bin/lua', '-E', '-',
                                 str(REPO)],
                                input=script, env=dict(os.environ, WAYLAND_DISPLAY="test"), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)



if __name__ == "__main__":
    unittest.main()
