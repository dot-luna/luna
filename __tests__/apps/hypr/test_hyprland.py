"""Check native Lua theme loading without modifying or reloading the running desktop."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[3]


BINDING_API = """
local function binding_api()
    hl.bind = hl.bind or function() end
    hl.monitor = hl.monitor or function() end
    hl.layer_rule = hl.layer_rule or function() end
    hl.window_rule = hl.window_rule or function() end
    hl.on = hl.on or function() end
    hl.timer = hl.timer or function() end
    hl.gesture = hl.gesture or function() end
    hl.config = hl.config or function() end
    hl.get_monitors = hl.get_monitors or function() return {} end
    hl.get_windows = hl.get_windows or function() return {} end
    hl.curve = function() end
    hl.animation = function() end
    hl.dsp = {
        exec_cmd = function(command) return command end,
        window = {},
        group = {},
        workspace = { toggle_special = function(name) return { special = name } end },
        focus = function(options) return options end,
        layout = function(message) return { layout = message } end,
    }
    for _, name in ipairs({ "close", "move", "fullscreen", "fullscreen_state", "float", "pin",
        "swap", "resize", "drag", "cycle_next", "bring_to_top", "pseudo" }) do
        hl.dsp.window[name] = function(options) return options or {} end
    end
    for _, name in ipairs({ "toggle", "next", "prev", "active" }) do
        hl.dsp.group[name] = function(options) return options or {} end
    end
end
"""


WORKSPACE_API = '''
local events, rules, pending = {}, {}, nil
local monitors, workspaces = {}, {}
local active_monitor, active_window
local cursor = { x = 360, y = 220 }

local function monitor(name, x)
    local output = { name = name, x = x, y = 0 }
    table.insert(monitors, output)
    return output
end

local function workspace(output, id, options)
    options = options or {}
    local current = {
        id = id,
        name = options.name or tostring(id),
        monitor = output,
        is_empty = options.is_empty ~= false,
        is_persistent = options.is_persistent == true,
    }
    table.insert(workspaces, current)
    if options.active then output.active_workspace = current end
    return current
end

local function assignment(id)
    local target
    for _, rule in ipairs(rules) do
        if rule.enabled and rule.workspace == tostring(id) then
            assert(not target, "duplicate assignment")
            target = rule.monitor
        end
    end
    return target
end

local function get_workspace(id)
    for _, current in ipairs(workspaces) do
        if current.id == id then return current end
    end
end

local function get_monitor(selector)
    for _, output in ipairs(monitors) do
        if output == selector or output.name == selector then return output end
    end
    error("Unknown monitor")
end

local function show_workspace(current)
    local output = current.monitor
    local previous = output.active_workspace
    output.active_workspace = current
    active_monitor = output
    active_window = current.window
    cursor = { x = output.x + 960, y = 540 }

    -- Hyprland removes an empty, nonpersistent workspace after switching away.
    if previous and previous ~= current and previous.is_empty and not previous.is_persistent then
        for index, candidate in ipairs(workspaces) do
            if candidate == previous then table.remove(workspaces, index); break end
        end
    end
end

hl = {
    get_monitors = function() return monitors end,
    get_workspaces = function() return workspaces end,
    get_active_monitor = function() return active_monitor end,
    get_active_window = function() return active_window end,
    get_cursor_pos = function() return cursor end,
    on = function(event, callback) events[event] = callback end,
    timer = function(callback) pending = callback end,
    workspace_rule = function(spec)
        spec.enabled = true
        function spec:set_enabled(value) self.enabled = value end
        table.insert(rules, spec)
        return spec
    end,
    dsp = {
        workspace = { move = function(options) return { move = options } end },
        focus = function(options) return { focus = options } end,
        cursor = { move = function(options) return { cursor = options } end },
    },
    dispatch = function(action)
        if action.move then
            local current = assert(get_workspace(action.move.workspace))
            current.monitor = get_monitor(action.move.monitor)
        elseif action.cursor then
            cursor = { x = action.cursor.x, y = action.cursor.y }
        elseif action.focus.workspace then
            local id = action.focus.workspace
            local current = get_workspace(id)
            if not current then current = workspace(get_monitor(assignment(id)), id) end
            show_workspace(current)
        elseif action.focus.window then
            local window = action.focus.window
            show_workspace(window.workspace)
            active_window = window
        elseif action.focus.monitor then
            show_workspace(get_monitor(action.focus.monitor).active_workspace)
        else
            error("Unsupported dispatch")
        end
    end,
}

local function flush()
    if pending then
        local callback = pending
        pending = nil
        callback()
    end
end

local function update(event)
    events[event]()
    flush()
end

local function load_workspaces()
    local config_dir = arg[1]:match("^(.*)/[^/]+$")
    dofile(config_dir .. '/workspaces.lua')
end
'''


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
        self.home = self.root / 'home'
        self.home.mkdir()
        self.env = dict(os.environ, HOME=str(self.home), XDG_CONFIG_HOME=str(self.root / 'config'),
                        XDG_DATA_HOME=str(self.root / 'data'), XDG_STATE_HOME=str(self.root / 'state'))
        self.env.pop('LUNA_PATH', None)
        self.env.pop('HYPRLAND_INSTANCE_SIGNATURE', None)
        self.installed = self.root / 'installed hypr'
        shutil.copytree(REPO / 'apps/hypr/config', self.installed)
        (self.installed / 'generated').mkdir()
        subprocess.run(
            ['/usr/bin/lua', '-E', str(REPO / 'scripts/setup/build-app.lua'),
             str(REPO / 'apps/hypr'), str(self.installed), str(self.installed),
             str(self.root / 'config/luna')],
            cwd=self.root, env=self.env, text=True, capture_output=True, check=True,
        )
        self.entry = self.installed / 'hyprland.lua'
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
        result = subprocess.run(['/usr/bin/lua', '-E', '-', str(self.entry),
                                 str(self.config / 'theme'), str(REPO)], env=self.env, cwd=self.root, input=BINDING_API + script.replace("dofile(arg[1])", "binding_api(); dofile(arg[1])"),
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
    config = function(settings)
        if settings.general and settings.general.col then table.insert(calls, settings) end
    end,
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
assert(#monitors == 1)
assert(monitors[1].mode == "preferred" and monitors[1].position == "auto")
assert(monitors[1].scale == 1)
assert(calls[1].general.col.active_border == "#7aa2f7")
assert(calls[1].general.col.inactive_border == "#414868")
assert(calls[1].decoration.blur.size == 10)
assert(calls[1].decoration.blur.passes == 3)
assert(calls[1].decoration.shadow.color == "#13141caa")
local root = arg[3]
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
assert(#monitors == 2 and monitors[2].position == "auto")
''')
        self.assertFalse((self.root / 'config/luna/generated').exists())

    def test_no_selection_and_invalid_selection(self):
        guard = 'hl = { config = function(settings) if settings.decoration then error("Theme must not be applied") end end }; dofile(arg[1])'
        self.lua(guard)
        for name in ('../escape', 'missing'):
            (self.config / 'theme').write_text(name + '\n')
            self.lua(guard, ok=False)
        (self.config / 'theme').write_text('tokyo-night\n')
        output = self.config / 'theme.json'
        output.write_text(output.read_text().replace('"rounding":0', '"rounding":-1'))
        self.lua(guard, ok=False)

    def test_empty_and_unset_xdg_config_read_the_home_theme_selection(self):
        config = self.home / '.config/luna'
        config.mkdir(parents=True)
        shutil.copy2(self.config / 'theme.json', config / 'theme.json')
        (config / 'theme').write_text('tokyo-night\n')
        for value in ('', None):
            with self.subTest(XDG_CONFIG_HOME=value):
                if value is None:
                    self.env.pop('XDG_CONFIG_HOME', None)
                else:
                    self.env['XDG_CONFIG_HOME'] = value
                self.lua('''
local calls = 0
hl = { config = function(settings)
    if not settings.general or not settings.general.col then return end
    calls = calls + 1
    assert(settings.general.col.active_border == "#7aa2f7")
end }
dofile(arg[1])
assert(calls == 1, "Home theme selection was not applied")
''')

    def test_workspace_ranges_follow_monitor_order_and_hotplug(self):
        self.lua('''
local events, rules, pending, moves = {}, {}, nil, {}
local left = { name = "left", x = 0, y = 0 }
local right = { name = "right", x = 1920, y = 0 }
local third = { name = "third", x = 3840, y = 0 }
local monitors = { right, left }
hl = {
    get_monitors = function() return monitors end,
    get_active_monitor = function() return nil end,
    get_active_window = function() return nil end,
    get_cursor_pos = function() return { x = 0, y = 0 } end,
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
local config_dir = arg[1]:match("^(.*)/[^/]+$")
dofile(config_dir .. '/workspaces.lua')
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

    def test_hotplug_replaces_empty_overflow_and_preserves_window_focus(self):
        self.lua(WORKSPACE_API + '''
local left = monitor("left", 0)
local first = workspace(left, 1, { active = true, is_empty = false })
local ninth = workspace(left, 9, { is_empty = false })
local window = { workspace = first, mapped = true, address = '0x1234' }
first.window = window
active_monitor, active_window = left, window
load_workspaces()
update('config.reloaded')
for id = 1, 10 do assert(assignment(id) == 'left') end

-- All ten rules still point left when the delayed monitor callback is queued.
local right = monitor("right", 1920)
workspace(right, 11, { active = true })
update('monitor.added')
assert(right.active_workspace.id == 6, "hotplug left workspace 11 visible")
assert(not get_workspace(11), "temporary workspace should disappear after switching")
assert(ninth.monitor == right, "existing numbered workspaces must still move")
for id = 1, 10 do assert(assignment(id) == (id <= 5 and 'left' or 'right')) end
assert(active_window == window and active_monitor == left, "hotplug stole keyboard focus")
assert(cursor.x == 360 and cursor.y == 220, "hotplug warped the pointer")
''')

    def test_overflow_repair_with_unchanged_topology_and_no_focused_window(self):
        for event in ('config.reloaded', 'monitor.layout_changed'):
            with self.subTest(event=event):
                self.lua(WORKSPACE_API + '''
local left = monitor("left", 0)
local right = monitor("right", 1920)
workspace(left, 1, { active = true })
active_monitor = left
load_workspaces()
update('config.reloaded')
local original_rule_count = #rules

workspace(right, 11, { active = true })
update('EVENT')
assert(right.active_workspace.id == 6, "unchanged topology skipped overflow repair")
assert(#rules == original_rule_count, "unchanged topology duplicated workspace rules")
assert(not get_workspace(11))
assert(active_monitor == left and active_window == nil, "empty desktop lost monitor focus")
assert(cursor.x == 360 and cursor.y == 220, "empty desktop pointer moved")
'''.replace('EVENT', event))

    def test_coalesced_disconnect_reconnect_repairs_same_named_monitor(self):
        self.lua(WORKSPACE_API + '''
local left = monitor("left", 0)
local right = monitor("right", 1920)
workspace(left, 1, { active = true })
active_monitor = left
load_workspaces()
update('config.reloaded')
local original_rule_count = #rules

monitors = { left }
events['monitor.removed']()
right = monitor("right", 1920)
workspace(right, 11, { active = true })
events['monitor.added']()
flush()
assert(right.active_workspace.id == 6, "same-named reconnect left workspace 11 visible")
assert(not get_workspace(11))
assert(#rules == original_rule_count)
assert(active_monitor == left and cursor.x == 360 and cursor.y == 220)
''')

    def test_overflow_uses_first_workspace_in_physical_monitor_range(self):
        for positions, expected in (((0, 1920, 3840), 8), ((1920, 3840, 0), 1)):
            with self.subTest(positions=positions):
                self.lua(WORKSPACE_API + '''
local left = monitor("left", LEFT_X)
local right = monitor("right", RIGHT_X)
local third = monitor("third", THIRD_X)
workspace(left, LEFT_ID, { active = true })
workspace(right, RIGHT_ID, { active = true })
workspace(third, 11, { active = true })
active_monitor = left
load_workspaces()
update('monitor.added')
assert(third.active_workspace.id == EXPECTED, "wrong workspace for physical output order")
assert(not get_workspace(11))
assert(active_monitor == left and cursor.x == 360 and cursor.y == 220)
'''.replace('LEFT_X', str(positions[0]))
                    .replace('RIGHT_X', str(positions[1]))
                    .replace('THIRD_X', str(positions[2]))
                    .replace('LEFT_ID', '1' if expected == 8 else '5')
                    .replace('RIGHT_ID', '5' if expected == 8 else '8')
                    .replace('EXPECTED', str(expected)))

    def test_overflow_repair_preserves_user_workspaces(self):
        cases = (
            (11, '{ is_empty = false, active = true }', False),
            (11, '{ is_persistent = true, active = true }', False),
            (11, '{ name = "project", active = true }', False),
            (-1, '{ name = "special:scratchpad", active = true }', False),
            (8, '{ active = true }', False),
            (11, '{ active = true }', True),
        )
        for workspace_id, options, special in cases:
            with self.subTest(workspace_id=workspace_id, options=options, special=special):
                self.lua(WORKSPACE_API + '''
local left = monitor("left", 0)
local right = monitor("right", 1920)
workspace(left, 1, { active = true })
local original = workspace(right, WORKSPACE_ID, OPTIONS)
if SPECIAL then
    right.active_special_workspace = workspace(right, -2, { name = 'special:overlay' })
end
active_monitor = left
load_workspaces()
update('monitor.added')
assert(right.active_workspace == original, "a user workspace was replaced")
assert(get_workspace(WORKSPACE_ID) == original, "a user workspace was removed")
assert(active_monitor == left and cursor.x == 360 and cursor.y == 220)
'''.replace('WORKSPACE_ID', str(workspace_id)).replace('OPTIONS', options)
                    .replace('SPECIAL', 'true' if special else 'false'))

    def test_global_shortcuts_consume_input_and_bypass_app_inhibitors(self):
        self.lua('''
local bindings = {}
local descriptions = {}
local repeat_flags = {}
local combinations = {}
hl = {
    config = function() end,
    bind = function(keys, action, flags)
        assert(flags.non_consuming == false, keys .. " must consume its input")
        assert(flags.dont_inhibit == true, keys .. " must bypass app shortcut inhibitors")
        assert(not flags.locked, keys .. " must respect the lock screen")
        assert(type(flags.description) == "string" and flags.description:match("%S"),
            keys .. " must describe its Lua action for the keybinding guide")
        assert(not bindings[keys], "Duplicate shortcut: " .. keys)
        local parts = {}
        for part in keys:gmatch("[^+]+") do
            parts[#parts + 1] = part:gsub("%s+", ""):lower()
        end
        table.sort(parts)
        local canonical = table.concat(parts, "+")
        assert(not combinations[canonical], "Duplicate key combination: " .. keys)
        combinations[canonical] = true
        bindings[keys] = action or true
        descriptions[keys] = flags.description
        repeat_flags[keys] = flags.repeating
    end,
}
dofile(arg[1])
assert(bindings["SUPER + T"] and bindings["SUPER + S"])
assert(bindings["SUPER + CTRL + L"] and bindings["SUPER + CTRL + Z"])
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
assert(bindings["Print"]:match(" screenshot region$"))
assert(bindings["SHIFT + Print"]:match(" screenshot screen$"))
assert(bindings["ALT + Print"]:match(" screenshot window$"))
assert(bindings["CTRL + Print"]:match(" screenshot all$"))
assert(bindings["SUPER + N"]:match(" notifications open$"))
assert(bindings["SUPER + SHIFT + N"]:match(" notifications dnd$"))
assert(bindings["SUPER + Print"]:match(" record toggle$"))
assert(bindings["SUPER + SHIFT + Print"]:match(" record stop$"))
assert(bindings["XF86AudioRaiseVolume"]:match(" control volume%-up$"))
assert(bindings["XF86AudioMicMute"]:match(" control mic%-mute$"))
assert(bindings["XF86MonBrightnessDown"]:match(" control brightness%-down$"))
assert(bindings["XF86AudioPlay"]:match(" control play%-pause$"))
assert(repeat_flags["XF86AudioRaiseVolume"] and repeat_flags["XF86MonBrightnessDown"])
assert(not repeat_flags["XF86AudioMute"] and not repeat_flags["XF86AudioPlay"])
''')

    def test_terminal_shortcut_captures_focused_process(self):
        self.lua('''
local binds, commands = {}, {}
local focused = { pid = 4321, class = "luna-dropdown" }
hl = {
    get_active_window = function() return focused end,
    dsp = { exec_cmd = function(command) return command end },
    dispatch = function(command) table.insert(commands, command) end,
}
local config_dir = arg[1]:match("^(.*)/[^/]+$")
local launcher = "'/checkout with spaces/bin/luna'"
dofile(config_dir .. '/bindings/apps.lua')(function(keys, action) binds[keys] = action end, launcher)
binds["SUPER + Return"]()
focused = nil
binds["SUPER + Return"]()
focused = { pid = -1 }
binds["SUPER + Return"]()
assert(commands[1] == launcher .. " terminal --pid=4321")
assert(commands[2] == launcher .. " terminal --pid=0")
assert(commands[3] == launcher .. " terminal --pid=0")
''')

    def test_symlink_entry_point(self):
        (self.config / 'theme').write_text('tokyo-night\n')
        entry = self.root / 'config/hypr/hyprland.lua'
        entry.parent.mkdir()
        entry.symlink_to(self.entry)
        script = 'hl = { config = function(settings) if settings.general then assert(settings.general.border_size == 1) end end, monitor = function(settings) assert(settings.scale == 1) end }; dofile(arg[1])'
        result = subprocess.run(['/usr/bin/lua', '-E', '-', str(entry)], env=self.env,
                                input=BINDING_API + script.replace("dofile(arg[1])", "binding_api(); dofile(arg[1])"), text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_generated_checkout_path_is_authoritative_and_required(self):
        self.env['LUNA_PATH'] = str(self.root / 'wrong checkout')
        self.lua('hl = { config = function() end }; dofile(arg[1])')
        generated = self.installed / 'generated/paths.lua'
        for contents in ('return {}', 'return { install_dir = "relative" }', 'return false'):
            with self.subTest(contents=contents):
                generated.write_text(contents)
                result = self.lua('hl = { config = function() end }; dofile(arg[1])', ok=False)
                self.assertIn('Regenerate Luna', result.stderr)
        generated.unlink()
        result = self.lua('hl = { config = function() end }; dofile(arg[1])', ok=False)
        self.assertIn('generated/paths.lua', result.stderr)

    def test_hyprland_parser(self):
        executable = shutil.which('Hyprland')
        if not executable:
            self.skipTest('Hyprland is needed for its native config parser')
        help_text = subprocess.check_output([executable, '--help'], text=True)
        if '--verify-config' not in help_text:
            self.skipTest('Hyprland config verification is unavailable')
        (self.config / 'theme').write_text('tokyo-night\n')
        runtime = self.root / 'runtime'
        runtime.mkdir(mode=0o700)
        env = dict(self.env, XDG_RUNTIME_DIR=str(runtime))
        for name in ('DISPLAY', 'WAYLAND_DISPLAY', 'HYPRLAND_INSTANCE_SIGNATURE'):
            env.pop(name, None)
        result = subprocess.run([executable, '--verify-config', '-c', str(self.entry)],
                                env=env, text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('config ok', result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
