"""Verify reversible appearance changes and independent workspace overrides."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[3]
MODULE = REPO / 'apps/hypr/config/bindings/appearance.lua'
LUA = shutil.which('lua')

API = '''
local binds, rules = {}, {}
local workspace = { id = 1, tiled_layout = "dwindle", special = false }
local special = nil
local values = {
    ["general.gaps_in"] = { top = 3, right = 4, bottom = 5, left = 6 },
    ["general.gaps_out"] = { top = 7, right = 8, bottom = 9, left = 10 },
    ["decoration.active_opacity"] = 0.83,
    ["decoration.inactive_opacity"] = 0.72,
    ["decoration.fullscreen_opacity"] = 0.97,
    ["layout.single_window_aspect_ratio"] = { 16, 9 },
}
hl = {
    get_active_workspace = function() return workspace end,
    get_active_special_workspace = function() return special end,
    get_config = function(key) return values[key] end,
    config = function(spec)
        for key, value in pairs(spec) do values[key] = value end
    end,
    workspace_rule = function(spec)
        -- Match the native merge behavior so selector collisions are observable.
        local rule
        for _, candidate in ipairs(rules) do
            if candidate.enabled and candidate.workspace == spec.workspace then rule = candidate end
        end
        if not rule then
            rule = { enabled = true }
            function rule:is_enabled() return self.enabled end
            function rule:set_enabled(enabled) self.enabled = enabled end
            table.insert(rules, rule)
        end
        for key, value in pairs(spec) do rule[key] = value end
        return rule
    end,
}
dofile(arg[1])(function(key, action) binds[key] = action end)
'''


@unittest.skipUnless(LUA, 'Appearance callbacks require Lua')
class AppearanceBindingsTests(unittest.TestCase):
    def lua(self, script):
        result = subprocess.run([LUA, '-E', '-', str(MODULE)], input=API + script,
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_gaps_restore_each_custom_edge_and_recapture_later_settings(self):
        self.lua('''
local toggle = binds["SUPER + SHIFT + BackSpace"]
toggle()
assert(values["general.gaps_in"] == 0 and values["general.gaps_out"] == 0)
toggle()
assert(values["general.gaps_in"].left == 6 and values["general.gaps_out"].bottom == 9)
values["general.gaps_in"] = { top = 11, right = 12, bottom = 13, left = 14 }
toggle()
toggle()
assert(values["general.gaps_in"].right == 12)
''')

    def test_transparency_roundtrip_restores_all_three_opacities(self):
        self.lua('''
local toggle = binds["SUPER + BackSpace"]
toggle()
assert(values["decoration.active_opacity"] == 1)
assert(values["decoration.inactive_opacity"] == 1)
assert(values["decoration.fullscreen_opacity"] == 1)
toggle()
assert(values["decoration.active_opacity"] == 0.83)
assert(values["decoration.inactive_opacity"] == 0.72)
assert(values["decoration.fullscreen_opacity"] == 0.97)
''')

    def test_opaque_default_can_enable_transparency(self):
        self.lua('''
values["decoration.active_opacity"] = 1
values["decoration.inactive_opacity"] = 1
values["decoration.fullscreen_opacity"] = 1
binds["SUPER + BackSpace"]()
assert(values["decoration.active_opacity"] == 0.9)
assert(values["decoration.fullscreen_opacity"] == 1)
binds["SUPER + BackSpace"]()
assert(values["decoration.active_opacity"] == 1)
''')

    def test_square_mode_restores_custom_ratio(self):
        self.lua('''
local toggle = binds["SUPER + CTRL + BackSpace"]
toggle()
assert(values["layout.single_window_aspect_ratio"][1] == 1)
assert(values["layout.single_window_aspect_ratio"][2] == 1)
toggle()
assert(values["layout.single_window_aspect_ratio"][1] == 16)
assert(values["layout.single_window_aspect_ratio"][2] == 9)
values["layout.single_window_aspect_ratio"] = { 1, 1 }
toggle()
assert(values["layout.single_window_aspect_ratio"][1] == 0)
toggle()
assert(values["layout.single_window_aspect_ratio"][1] == 1)
''')

    def test_layout_handles_do_not_mutate_or_disable_monitor_rules(self):
        self.lua('''
local assignment = hl.workspace_rule({ workspace = "1", monitor = "DP-1", layout = "dwindle" })
local toggle = binds["SUPER + CTRL + L"]
toggle()
assert(#rules == 2)
local override = rules[2]
assert(override.workspace == "r[1-1] s[false]" and override.layout == "scrolling")
for _ = 1, 10 do toggle() end
assert(#rules == 2 and override.enabled)
toggle()
assert(not override.enabled)
assert(assignment.enabled and assignment.monitor == "DP-1" and assignment.layout == "dwindle")
-- Hotplug can disable and replace assignments without affecting the layout handle.
assignment:set_enabled(false)
local replacement = hl.workspace_rule({ workspace = "1", monitor = "DP-2" })
toggle()
assert(override.enabled and replacement.enabled and replacement.monitor == "DP-2")
''')

    def test_layout_changes_are_local_and_preserve_scrolling_defaults(self):
        self.lua('''
local toggle = binds["SUPER + CTRL + L"]
toggle()
workspace = { id = 2, tiled_layout = "scrolling", special = false }
toggle()
assert(#rules == 2 and rules[2].layout == "dwindle")
toggle()
assert(not rules[2].enabled and rules[1].enabled)
''')

    def test_missing_special_named_and_other_layouts_are_untouched(self):
        self.lua('''
local toggle = binds["SUPER + CTRL + L"]
workspace = nil
toggle()
workspace = { id = -99, special = true }
toggle()
workspace = { id = -1337, special = false, tiled_layout = "dwindle" }
toggle()
workspace = { id = 1, special = false, tiled_layout = "master" }
toggle()
workspace.tiled_layout = "dwindle"
special = { id = -99 }
toggle()
assert(#rules == 0)
''')

    @unittest.skipUnless(shutil.which('Hyprland'), 'Native verification requires Hyprland')
    def test_callbacks_parse_with_native_hyprland(self):
        executable = shutil.which('Hyprland')
        if '--verify-config' not in subprocess.check_output([executable, '--help'], text=True):
            self.skipTest('Hyprland lacks --verify-config')
        with tempfile.TemporaryDirectory(prefix='luna-appearance-') as temp:
            config = Path(temp) / 'hyprland.lua'
            module = str(MODULE).replace('\\', '\\\\').replace('"', '\\"')
            config.write_text('''
local bindings = {}
hl.get_active_workspace = function() return { id = 1, tiled_layout = "dwindle" } end
hl.get_active_special_workspace = function() return nil end
dofile("''' + module + '''")(function(key, action) bindings[key] = action end)
for _, action in pairs(bindings) do action(); action(); action() end
''')
            env = os.environ.copy()
            env['XDG_RUNTIME_DIR'] = temp
            for name in ('HYPRLAND_INSTANCE_SIGNATURE', 'WAYLAND_DISPLAY', 'DISPLAY'):
                env.pop(name, None)
            result = subprocess.run([executable, '--verify-config', '--config', str(config)],
                                    env=env, text=True, capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('config ok', result.stdout)


if __name__ == '__main__':
    unittest.main()
