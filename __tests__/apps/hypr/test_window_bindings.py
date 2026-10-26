"""Exercise window shortcuts with compositor state held entirely in Lua fixtures."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[3]
MODULE = REPO / "apps/hypr/config/bindings/windows.lua"


API = r'''
local bindings, dispatched = {}, {}
local windows, focused, after_dispatch = {}, nil, nil

local function dispatcher(kind)
    return function(options) return { kind = kind, options = options or {} } end
end

hl = {
    get_active_window = function() return focused end,
    dsp = { window = {}, group = {}, focus = dispatcher("focus"), layout = dispatcher("layout") },
}
for _, name in ipairs({ "close", "fullscreen", "fullscreen_state", "float", "pseudo", "swap", "move",
    "cycle_next", "bring_to_top", "drag", "resize", "pin", "alter_zorder" }) do
    hl.dsp.window[name] = dispatcher(name)
end
for _, name in ipairs({ "toggle", "next", "prev", "active" }) do
    hl.dsp.group[name] = dispatcher("group." .. name)
end

function hl.dispatch(action)
    table.insert(dispatched, action)
    local options = action.options
    local window = options.window or focused
    if action.kind == "cycle_next" then
        local candidates, index = {}, nil
        for _, candidate in ipairs(windows) do
            if (not options.tiled or not candidate.floating) and (not options.floating or candidate.floating) then
                table.insert(candidates, candidate)
                if candidate == focused then index = #candidates end
            end
        end
        if #candidates > 0 then
            local offset = options.next == false and -1 or 1
            focused = candidates[index and ((index - 1 + offset) % #candidates + 1) or 1]
        end
    elseif window then
        if action.kind == "fullscreen_state" then
            if options.action == "toggle" then
                window.fullscreen = window.fullscreen == options.internal and 0 or options.internal
                window.fullscreen_client = window.fullscreen_client == options.client and 0 or options.client
            else
                window.fullscreen, window.fullscreen_client = options.internal, options.client
            end
        elseif action.kind == "pin" then
            assert(window.floating and window.fullscreen == 0, "Hyprland cannot pin a tiled or fullscreen window")
            window.pinned = options.action == "on"
        elseif action.kind == "float" then
            assert(window.fullscreen == 0, "Exit fullscreen before changing floating state")
            assert(options.action ~= "off" or not window.pinned, "Unpin before returning to tiling")
            window.floating = options.action == "toggle" and not window.floating or options.action == "on"
        elseif action.kind == "bring_to_top" or action.kind == "alter_zorder" then
            window.raised = true
        elseif action.kind == "resize" and options.x then
            window.width = options.relative and window.width + options.x or options.x
            window.height = options.relative and window.height + options.y or options.y
        end
    end
    if after_dispatch then after_dispatch(action) end
end

dofile(arg[1])(function(keys, action, description, options)
    assert(not bindings[keys], "Duplicate window binding: " .. keys)
    assert(type(description) == "string" and description:match("%S"))
    bindings[keys] = { action = action, options = options or {} }
end)

local function press(keys)
    local action = assert(bindings[keys], "Missing binding: " .. keys).action
    if type(action) == "function" then action() else hl.dispatch(action) end
end

local function window(floating, pinned, fullscreen, client)
    return { floating = floating or false, pinned = pinned or false,
        fullscreen = fullscreen or 0, fullscreen_client = client or 0, width = 800, height = 600 }
end
'''


class WindowBindingTests(unittest.TestCase):
    def lua(self, script):
        with tempfile.TemporaryDirectory(prefix="luna-window-bindings-") as directory:
            env = {key: value for key, value in os.environ.items()
                   if not key.startswith(("LUNA_", "XDG_", "HYPRLAND_"))}
            env.update(HOME=directory, XDG_CONFIG_HOME=directory)
            result = subprocess.run(["/usr/bin/lua", "-E", "-", str(MODULE)], input=API + script,
                                    cwd=directory, env=env, text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_sticky_toggle_handles_empty_desktop_and_existing_window_states(self):
        self.lua('''
press("SUPER + O")
assert(#dispatched == 0, "Empty desktop should do nothing")
for _, floating in ipairs({ false, true }) do
    for _, fullscreen in ipairs({ 0, 1, 2 }) do
        focused = window(floating, false, fullscreen, fullscreen)
        press("SUPER + O")
        assert(focused.pinned and focused.floating and focused.raised)
        assert(focused.fullscreen == 0 and focused.fullscreen_client == 0)
        press("SUPER + O")
        assert(not focused.pinned and not focused.floating)
    end
end
-- An already pinned window may have been fullscreened by a user override.
focused = window(true, true, 2, 2)
press("SUPER + O")
assert(not focused.pinned and not focused.floating and focused.fullscreen == 0)
''')

    def test_sticky_operation_stays_on_the_original_window_if_focus_changes(self):
        self.lua('''
local original, other = window(false, false, 2, 2), window()
focused = original
after_dispatch = function() focused = other end
press("SUPER + O")
assert(original.pinned and original.floating and original.raised)
assert(not other.pinned and not other.floating and not other.raised)
''')

    def test_alt_tab_cycles_both_window_types_in_both_directions_and_raises_selection(self):
        self.lua('''
press("ALT + TAB")
assert(focused == nil)
windows = { window(), window(true), window() }
press("ALT + TAB")
assert(focused == windows[1] and focused.raised)
press("ALT + TAB")
assert(focused == windows[2] and focused.raised, "Floating windows must participate")
press("ALT + TAB")
assert(focused == windows[3] and focused.raised)
press("ALT + TAB")
assert(focused == windows[1])
press("ALT + SHIFT + TAB")
assert(focused == windows[3], "Reverse cycling must wrap backwards")
press("ALT + SHIFT + TAB")
assert(focused == windows[2])
''')

    def test_client_fullscreen_keeps_window_geometry_and_never_requests_monitor_fullscreen(self):
        self.lua('''
for _, internal in ipairs({ 0, 1, 2 }) do
    focused = window(false, false, internal, 0)
    press("SUPER + CTRL + F")
    assert(focused.fullscreen == 0 and focused.fullscreen_client == 2)
    assert(focused.width == 800 and focused.height == 600)
    press("SUPER + CTRL + F")
    assert(focused.fullscreen == 0 and focused.fullscreen_client == 0)
end
assert(bindings["SUPER + F"].action.options.mode == "fullscreen")
assert(bindings["SUPER + F"].action.options.layout_aware == false)
assert(bindings["SUPER + ALT + F"].action.options.mode == "maximized")
assert(bindings["SUPER + ALT + F"].action.options.layout_aware == false)
''')

    def test_mouse_drag_flags_and_repeating_keyboard_resize_steps(self):
        self.lua('''
assert(bindings["SUPER + mouse:272"].options.mouse == true)
assert(bindings["SUPER + mouse:273"].options.mouse == true)
focused = window(true)
press("SUPER + code:21")
assert(focused.width == 900 and focused.height == 600)
press("SUPER + ALT + code:20")
assert(focused.width == 875 and focused.height == 600)
press("SUPER + SHIFT + code:20")
assert(focused.width == 875 and focused.height == 500)
press("SUPER + SHIFT + ALT + code:21")
assert(focused.width == 875 and focused.height == 525)
for key, binding in pairs(bindings) do
    if key:find("code:", 1, true) then
        assert(binding.options.repeating == true, "Held resize keys should repeat")
    end
end
''')


if __name__ == "__main__":
    unittest.main()
