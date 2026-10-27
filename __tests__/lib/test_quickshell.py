"""Check shared Lua shutdown failures and deadlines without executing any app."""

from pathlib import Path
import subprocess
import unittest


REPO = Path(__file__).resolve().parents[2]


class QuickshellTests(unittest.TestCase):
    def test_scoped_shutdown_errors_races_and_wait_are_bounded(self):
        script = '''
local root, mode = arg[1], arg[2]
local json = dofile(root .. "/lib/json.lua")
local running, lists, kills, sleeps = true, 0, 0, 0
local common = {
    available = function() return true end,
    succeeds = function() return false end,
    run = function(args)
        assert(args[1] == "sleep" and args[2] == "0.1")
        sleeps = sleeps + 1
    end,
    capture = function(args)
        if args[1] == "realpath" then return args[4] .. "\\n", true end
        assert(args[1] == "/usr/bin/timeout" and args[2] == "--kill-after=1s" and args[3] == "5s")
        assert(args[4] == "qs")
        if args[5] == "list" then
            assert(args[6] == "-a" and args[7] == "-j")
            lists = lists + 1
            if mode == "list-failure" then return "", false end
            if mode == "malformed" then return "{}", true end
            if mode == "empty" then return "No running instances.\\n", true end
            if mode == "delayed" and lists >= 3 then running = false end
            local rows = {{pid = 2, config_path = "/other/shell.qml"}}
            if running then table.insert(rows, {pid = 1, config_path = "/app/shell.qml"}) end
            return json.encode(rows), true
        end
        assert(args[5] == "kill" and args[6] == "--pid" and args[7] == "1" and #args == 7)
        kills = kills + 1
        if mode == "kill-failure" then return "", false end
        if mode ~= "stuck" and mode ~= "delayed" then running = false end
        return "", mode ~= "disappeared"
    end,
}
local shell = dofile(root .. "/lib/quickshell.lua")(common, root, "/app/shell.qml", "test", "Test app")
local ok, message = pcall(shell.run, "stop")
if mode == "stuck" then
    assert(not ok and message:find("did not stop", 1, true))
    assert(lists == 31 and sleeps == 30 and kills == 1)
elseif mode == "list-failure" or mode == "malformed" then
    assert(not ok and kills == 0)
elseif mode == "kill-failure" then
    assert(not ok and message:find("could not stop", 1, true) and kills == 1)
else
    assert(ok, message)
    assert(kills == (mode == "empty" and 0 or 1))
    assert(sleeps == (mode == "delayed" and 1 or 0))
end
'''
        for mode in ('normal', 'empty', 'delayed', 'disappeared', 'list-failure',
                     'malformed', 'kill-failure', 'stuck'):
            with self.subTest(mode=mode):
                result = subprocess.run(['/usr/bin/lua', '-E', '-', str(REPO), mode],
                                        input=script, capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
