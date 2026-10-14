"""Check native Lua theme loading without modifying or reloading the running desktop."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]


BINDING_API = """
local function binding_api()
    hl.bind = hl.bind or function() end
    hl.monitor = hl.monitor or function() end
    hl.layer_rule = hl.layer_rule or function() end
    hl.window_rule = hl.window_rule or function() end
    hl.on = hl.on or function() end
    hl.timer = hl.timer or function() end
    hl.curve = function() end
    hl.animation = function() end
    hl.dsp = {
        exec_cmd = function() end,
        window = { close = function() end, move = function(options) return options end, fullscreen = function(options) return options end },
        focus = function() end,
    }
end
"""


class HyprlandThemeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luna hypr '")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / 'config/luna'
        self.config.mkdir(parents=True)
        self.library = self.root / 'data/luna/themes'
        self.library.mkdir(parents=True)
        self.theme = self.library / 'tokyo-night'
        shutil.copytree(REPO / 'themes/bundled/tokyo-night', self.theme)
        self.env = dict(os.environ, XDG_CONFIG_HOME=str(self.root / 'config'),
                        XDG_DATA_HOME=str(self.root / 'data'), XDG_STATE_HOME=str(self.root / 'state'))
        self.env.pop('LUNA_PATH', None)
        self.publish()

    def publish(self):
        subprocess.run(['lua', '-E', '-', str(REPO), str(self.theme), str(self.config / 'theme.json')],
                       input="""
local resolved = dofile(arg[1] .. '/lib/theme/resolved.lua')(arg[1])
local validate = dofile(arg[1] .. '/lib/theme/validate.lua')()
local file = assert(io.open(arg[3], 'w'))
file:write(resolved.encode(resolved.resolve(validate.load(arg[2]), 'tokyo-night')))
file:close()
""", env=self.env, text=True, capture_output=True, check=True)

    def lua(self, script, ok=True):
        result = subprocess.run(['/usr/bin/lua', '-E', '-', str(REPO / 'config/hypr/.config/hypr/hyprland.lua'),
                                 str(self.config / 'theme')], env=self.env, input=BINDING_API + script.replace("dofile(arg[1])", "binding_api(); dofile(arg[1])"),
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return result

    def test_native_mapping_and_fresh_selection(self):
        (self.config / 'theme').write_text('tokyo-night\n')
        other = self.library / 'other'
        other.mkdir()
        colors = (self.theme / 'colors.lua').read_text().replace('#7aa2f7', '#82aaff')
        (other / 'colors.lua').write_text(colors)
        self.lua('''
local calls = {}
local monitors = {}
hl = {
    config = function(settings) table.insert(calls, settings) end,
    monitor = function(settings) table.insert(monitors, settings) end,
}
dofile(arg[1])
assert(#calls == 1)
assert(calls[1].general.gaps_in == 5)
assert(calls[1].general.gaps_out == 5)
assert(calls[1].general.border_size == 1)
assert(calls[1].decoration.rounding == 0)
assert(calls[1].decoration.active_opacity == 0.90)
assert(calls[1].decoration.inactive_opacity == 0.85)
assert(calls[1].monitor == nil)
assert(#monitors == 2)
assert(monitors[1].mode == "preferred" and monitors[1].position == "auto")
assert(monitors[1].scale == 1)
assert(monitors[2].mode == "1920x1080@60")
assert(monitors[2].output == "desc:LG Electronics 2D HD LG TV 0x01010101")
assert(calls[1].general.col.active_border == "#7aa2f7")
assert(calls[1].general.col.inactive_border == "#414868")
assert(calls[1].decoration.blur.size == 10)
assert(calls[1].decoration.blur.passes == 3)
assert(calls[1].decoration.shadow.color == "#13141caa")
local root = arg[1]:match("^(.*)/config/hypr/")
local resolved = dofile(root .. '/lib/theme/resolved.lua')(root)
local output = assert(io.open(resolved.path, 'w'))
output:write(resolved.encode(resolved.resolve({ colors = { accent = '#82aaff' } }, 'other')))
output:close()
local file = assert(io.open(arg[2], "w")); file:write("other\\n"); file:close()
dofile(arg[1])
assert(#calls == 2)
assert(calls[2].general.col.active_border == "#82aaff")
assert(calls[2].general.gaps_in == 5)
assert(calls[2].decoration.rounding == 0)
assert(#monitors == 4 and monitors[3].position == "auto")
''')
        self.assertFalse((self.root / 'config/luna/generated').exists())

    def test_no_selection_and_invalid_selection(self):
        self.lua('hl = { config = function() error("No theme should be applied") end }; dofile(arg[1])')
        for name in ('../escape', 'missing'):
            (self.config / 'theme').write_text(name + '\n')
            self.lua('hl = { config = function() error("Invalid theme must not be applied") end }; dofile(arg[1])', ok=False)
        (self.config / 'theme').write_text('tokyo-night\n')
        output = self.config / 'theme.json'
        output.write_text(output.read_text().replace('"rounding":0', '"rounding":-1'))
        self.lua('hl = { config = function() error("Invalid settings must not be applied") end }; dofile(arg[1])', ok=False)

    def test_workspace_ranges_follow_monitor_order_and_hotplug(self):
        self.lua('''
local events, rules, pending, moves = {}, {}, nil, {}
local left = { name = "left", x = 0, y = 0 }
local right = { name = "right", x = 1920, y = 0 }
local third = { name = "third", x = 3840, y = 0 }
local monitors = { right, left }
hl = {
    get_monitors = function() return monitors end,
    get_workspaces = function() return {
        { id = 2, monitor = right }, { id = 9, monitor = left }, { id = -1, monitor = left },
    } end,
    on = function(event, callback) events[event] = callback end,
    timer = function(callback) pending = callback end,
    workspace_rule = function(spec)
        spec.enabled = true
        function spec:set_enabled(value) self.enabled = value end
        table.insert(rules, spec)
        return spec
    end,
    dsp = { workspace = { move = function(options) return options end } },
    dispatch = function(options) table.insert(moves, options) end,
}
local root = arg[1]:match("^(.*)/config/hypr/")
dofile(root .. '/default/hypr/workspaces.lua')
local function update(event)
    events[event]()
    if pending then local callback = pending; pending = nil; callback() end
end
local function assignment(id)
    local result
    for _, rule in ipairs(rules) do
        if rule.enabled and rule.workspace == tostring(id) then
            assert(not result, "duplicate assignment")
            result = rule.monitor
        end
    end
    return result
end
update('config.reloaded')
for id = 1, 10 do assert(assignment(id) == (id <= 5 and 'left' or 'right')) end
assert(#moves == 2 and moves[1].workspace == 2 and moves[1].monitor == 'left')
update('monitor.layout_changed')
assert(#rules == 10 and #moves == 2)
monitors = { third, right, left }
update('monitor.added')
for id = 1, 10 do assert(assignment(id) == (id <= 4 and 'left' or id <= 7 and 'right' or 'third')) end
monitors = { left }
update('monitor.removed')
for id = 1, 10 do assert(assignment(id) == 'left') end
monitors = { right, left }
left.x = 3000
update('monitor.layout_changed')
for id = 1, 10 do assert(assignment(id) == (id <= 5 and 'right' or 'left')) end
''')

    def test_global_shortcuts_consume_input_and_bypass_app_inhibitors(self):
        self.lua('''
local bindings = {}
local descriptions = {}
hl = {
    config = function() end,
    bind = function(keys, action, flags)
        assert(flags.non_consuming == false, keys .. " must consume its input")
        assert(flags.dont_inhibit == true, keys .. " must bypass app shortcut inhibitors")
        assert(not flags.locked, keys .. " must respect the lock screen")
        assert(type(flags.description) == "string" and flags.description:match("%S"),
            keys .. " must describe its Lua action for the keybinding guide")
        assert(not bindings[keys], "Duplicate shortcut: " .. keys)
        bindings[keys] = action or true
        descriptions[keys] = flags.description
    end,
}
dofile(arg[1])
local count = 0
for _ in pairs(bindings) do count = count + 1 end
assert(count == 28)
assert(bindings["SUPER + F"].action == "toggle")
assert(bindings["SUPER + F"].mode == "fullscreen")
assert(bindings["SUPER + F"].layout_aware == false)
for workspace = 1, 10 do
    local move = bindings["SUPER + SHIFT + " .. tostring(workspace % 10)]
    assert(move.workspace == workspace)
    assert(move.follow == true)
    assert(descriptions["SUPER + " .. tostring(workspace % 10)]:find(tostring(workspace), 1, true))
    assert(descriptions["SUPER + SHIFT + " .. tostring(workspace % 10)]:find(tostring(workspace), 1, true))
end
assert(bindings["SUPER + 0"])
assert(bindings["SUPER + CTRL + Space"])
assert(bindings["SUPER + Space"])
assert(bindings["SUPER + L"])
''')

    def test_symlink_entry_point(self):
        (self.config / 'theme').write_text('tokyo-night\n')
        entry = self.root / 'config/hypr/hyprland.lua'
        entry.parent.mkdir()
        entry.symlink_to(REPO / 'config/hypr/.config/hypr/hyprland.lua')
        script = 'hl = { config = function(settings) assert(settings.general.border_size == 1) end, monitor = function(settings) assert(settings.scale == 1) end }; dofile(arg[1])'
        result = subprocess.run(['/usr/bin/lua', '-E', '-', str(entry)], env=self.env,
                                input=BINDING_API + script.replace("dofile(arg[1])", "binding_api(); dofile(arg[1])"), text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_hyprland_parser(self):
        executable = shutil.which('Hyprland')
        if not executable:
            self.skipTest('Hyprland is needed for its native config parser')
        help_text = subprocess.check_output([executable, '--help'], text=True)
        if '--verify-config' not in help_text:
            self.skipTest('Hyprland config verification is unavailable')
        (self.config / 'theme').write_text('tokyo-night\n')
        result = subprocess.run([executable, '--verify-config', '-c', str(REPO / 'config/hypr/.config/hypr/hyprland.lua')],
                                env=self.env, text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('config ok', result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
