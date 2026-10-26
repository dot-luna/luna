"""Exercise workspace routing and terminal startup without a running compositor."""

from pathlib import Path
import shutil
import subprocess
import unittest


REPO = Path(__file__).resolve().parents[3]
LUA = shutil.which('lua')

API = r'''
local binds, events, timers, commands = {}, {}, {}, {}
local monitors = { { name = 'left' }, { name = 'right' } }
local workspaces, windows = {}, {}
local active_monitor, active_window = monitors[1], nil
local toggles = 0
for _, entry in ipairs({ { 1, 1 }, { 4, 1 }, { 6, 2 }, { 10, 2 } }) do
    local workspace = { id = entry[1], monitor = monitors[entry[2]] }
    workspaces[workspace.id] = workspace
    workspace.monitor.active_workspace = workspace.monitor.active_workspace or workspace
end

local function action(kind)
    return function(value) return { kind = kind, value = value } end
end

local function focus_workspace(workspace)
    local monitor = workspace.monitor
    monitor.previous_workspace = monitor.active_workspace
    monitor.active_workspace = workspace
    active_monitor = monitor
end

hl = {
    get_windows = function() return windows end,
    get_active_monitor = function() return active_monitor end,
    on = function(event, callback) events[event] = callback end,
    timer = function(callback, options)
        assert(options.type == 'oneshot' and options.timeout > 0)
        local timer = { callback = callback, enabled = true }
        function timer:set_enabled(enabled) self.enabled = enabled end
        timers[#timers + 1] = timer
        return timer
    end,
    dsp = {
        focus = action('focus'),
        exec_cmd = action('exec'),
        window = { move = action('move') },
        workspace = { toggle_special = action('special') },
    },
    dispatch = function(dispatcher)
        local value = dispatcher.value
        if dispatcher.kind == 'exec' then
            commands[#commands + 1] = value
        elseif dispatcher.kind == 'special' then
            toggles = toggles + 1
            local current = active_monitor.active_special_workspace
            active_monitor.active_special_workspace = not current and { name = 'special:' .. value } or nil
        elseif dispatcher.kind == 'move' then
            local destination
            if value.monitor then
                destination = monitors[value.monitor == 'r' and 2 or 1].active_workspace
            else
                destination = workspaces[value.workspace] or { name = value.workspace, monitor = active_monitor }
            end
            local target = value.window or active_window
            target.workspace = destination
            if value.follow then focus_workspace(destination) end
        elseif dispatcher.kind == 'focus' then
            if value.window then
                active_window = value.window
            elseif value.monitor then
                active_monitor = active_monitor == monitors[1] and monitors[2] or monitors[1]
            elseif value.workspace == 'previous_per_monitor' then
                focus_workspace(active_monitor.previous_workspace)
            elseif type(value.workspace) == 'string' then
                assert(value.workspace == 'm+1' or value.workspace == 'm-1')
                local ids = active_monitor == monitors[1] and { 1, 4 } or { 6, 10 }
                local next_id = active_monitor.active_workspace.id == ids[1] and ids[2] or ids[1]
                focus_workspace(workspaces[next_id])
            else
                focus_workspace(assert(workspaces[value.workspace]))
            end
        else
            error('Unexpected dispatcher: ' .. dispatcher.kind)
        end
    end,
}

dofile(arg[1])(function(keys, dispatcher, description)
    assert(not binds[keys], 'Duplicate binding: ' .. keys)
    assert(description and description ~= '')
    binds[keys] = dispatcher
end)

local function press(keys)
    local dispatcher = assert(binds[keys], 'Missing binding: ' .. keys)
    if type(dispatcher) == 'function' then dispatcher() else hl.dispatch(dispatcher) end
end

local function opened(class)
    local window = { class = class, mapped = true, workspace = { name = 'special:luna-terminal' } }
    windows[#windows + 1] = window
    events['window.open'](window)
    return window
end

local function expire(timer)
    assert(timer.enabled)
    timer.enabled = false
    timer.callback()
end
'''


@unittest.skipUnless(LUA, 'Lua is unavailable')
class WorkspaceBindingTests(unittest.TestCase):
    def lua(self, script):
        result = subprocess.run(
            [LUA, '-E', '-', str(REPO / 'apps/hypr/config/bindings/workspaces.lua')],
            input=API + script, text=True, capture_output=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_numbered_moves_preserve_global_assignments(self):
        self.lua('''
for number = 1, 10 do
    local key = tostring(number % 10)
    assert(binds['SUPER + ' .. key].value.workspace == number)
    assert(binds['SUPER + SHIFT + ' .. key].value.follow == true)
    assert(binds['SUPER + SHIFT + ALT + ' .. key].value.follow == false)
end
active_window = { workspace = workspaces[1] }
press('SUPER + SHIFT + ALT + 0')
assert(active_window.workspace == workspaces[10])
assert(active_monitor == monitors[1] and monitors[1].active_workspace.id == 1)
assert(workspaces[10].monitor == monitors[2])
press('SUPER + SHIFT + 6')
assert(active_monitor == monitors[2] and active_window.workspace == workspaces[6])
assert(workspaces[1].monitor == monitors[1] and workspaces[6].monitor == monitors[2])
''')

    def test_workspace_cycles_remain_on_current_monitor(self):
        self.lua('''
press('SUPER + Tab')
assert(active_monitor == monitors[1] and active_monitor.active_workspace.id == 4)
press('SUPER + mouse_down')
assert(active_monitor == monitors[1] and active_monitor.active_workspace.id == 1)
press('SUPER + SHIFT + Tab')
assert(active_monitor.active_workspace.id == 4)
press('SUPER + CTRL + Tab')
assert(active_monitor.active_workspace.id == 1)
press('CTRL + ALT + Tab')
press('SUPER + mouse_up')
assert(active_monitor == monitors[2] and active_monitor.active_workspace.id == 10)
press('CTRL + ALT + SHIFT + Tab')
assert(active_monitor == monitors[1] and active_monitor.active_workspace.id == 1)
''')

    def test_monitor_moves_only_transfer_the_window(self):
        self.lua('''
active_window = { workspace = workspaces[1] }
press('SUPER + CTRL + SHIFT + right')
assert(active_window.workspace == workspaces[6] and active_monitor == monitors[2])
press('SUPER + CTRL + SHIFT + left')
assert(active_window.workspace == workspaces[1] and active_monitor == monitors[1])
assert(workspaces[1].monitor == monitors[1] and workspaces[6].monitor == monitors[2])
assert(binds['SUPER + CTRL + SHIFT + up'].value.monitor == 'u')
assert(binds['SUPER + CTRL + SHIFT + down'].value.monitor == 'd')
''')

    def test_scratchpad_is_separate_and_moves_silently(self):
        self.lua('''
active_window = { workspace = workspaces[1] }
press('SUPER + ALT + S')
assert(active_window.workspace.name == 'special:luna-scratchpad')
assert(active_monitor.active_workspace.id == 1 and not active_monitor.active_special_workspace)
press('SUPER + S')
assert(active_monitor.active_special_workspace.name == 'special:luna-scratchpad')
assert(#commands == 0)
''')

    def test_dropdown_is_lazy_reuses_window_and_relaunches_after_exit(self):
        self.lua('''
assert(#commands == 0 and #timers == 0)
press('SUPER + grave')
assert(#commands == 1 and #timers == 1)
assert(commands[1]:find('flock -n "${XDG_RUNTIME_DIR:?}/luna-dropdown-${HYPRLAND_INSTANCE_SIGNATURE:?}.lock"', 1, true))
local terminal = opened('luna-dropdown')
assert(not timers[1].enabled and active_window == terminal)
assert(active_monitor.active_special_workspace.name == 'special:luna-terminal')
press('SUPER + grave')
assert(not active_monitor.active_special_workspace and #commands == 1)
press('SUPER + grave')
assert(active_monitor.active_special_workspace and #commands == 1)
windows, active_monitor.active_special_workspace = {}, nil
press('SUPER + grave')
assert(#commands == 2 and #timers == 2)
''')

    def test_rapid_presses_can_cancel_or_restore_pending_visibility(self):
        for count in (2, 3, 20, 21):
            with self.subTest(presses=count):
                self.lua(f'''
for i = 1, {count} do press('SUPER + grave') end
assert(#commands == 1 and #timers == 1)
opened('luna-dropdown')
assert(toggles == {count % 2})
assert(not timers[1].enabled)
''')

    def test_dropdown_recovers_a_terminal_moved_to_another_workspace(self):
        self.lua('''
local terminal = opened('luna-dropdown')
terminal.workspace = workspaces[6]
active_window = { workspace = workspaces[1] }
press('SUPER + grave')
assert(terminal.workspace.name == 'special:luna-terminal')
assert(active_window.workspace == workspaces[1])
assert(active_monitor.active_special_workspace.name == 'special:luna-terminal')
assert(#commands == 0)
''')

    def test_failed_or_slow_launch_allows_retry_without_polling(self):
        self.lua('''
press('SUPER + grave')
opened('another-terminal')
assert(timers[1].enabled and toggles == 0)
expire(timers[1])
assert(#commands == 1 and #timers == 1)
press('SUPER + grave')
assert(#commands == 2 and #timers == 2)
opened('luna-dropdown')
assert(toggles == 1 and not timers[2].enabled)
press('SUPER + grave')
assert(#commands == 2 and not active_monitor.active_special_workspace)
''')


if __name__ == '__main__':
    unittest.main()
