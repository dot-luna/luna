"""Exercise display callbacks without connecting to the running compositor."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[3]
MODULE = REPO / 'apps/hypr/config/bindings/display.lua'
LUA = shutil.which('lua')

API = '''
local binds, changes = {}, {}
local monitor = { name = "DP-1", width = 1920, height = 1080,
    scale = 1, refresh_rate = 143.998, transform = 0, cm = "srgb",
    x = 0, y = 0, is_mirror = false, mirrors = {} }
local monitors = { monitor }
local focused = monitor
local zoom = 1
hl = {
    get_active_monitor = function() return focused end,
    get_monitors = function() return monitors end,
    get_config = function(key) assert(key == "cursor.zoom_factor"); return zoom end,
    config = function(spec) zoom = spec.cursor.zoom_factor end,
    monitor = function(spec)
        table.insert(changes, spec)
        monitor.scale = spec.scale
    end,
}
dofile(arg[1])(function(key, action) binds[key] = action end)
local up = binds["SUPER + slash"]
local down = binds["SUPER + ALT + slash"]
'''


@unittest.skipUnless(LUA, 'Display callbacks require Lua')
class DisplayBindingsTests(unittest.TestCase):
    def lua(self, script):
        result = subprocess.run([LUA, '-E', '-', str(MODULE)], input=API + script,
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_scaling_roundtrip_preserves_physical_mode_and_position(self):
        self.lua('''
monitor.x, monitor.y, monitor.transform = -1080, 50, 1
up()
assert(monitor.scale == 1.25)
down()
assert(monitor.scale == 1)
assert(#changes == 2)
for _, spec in ipairs(changes) do
    assert(spec.mode == "1920x1080@143.998000")
    assert(spec.position == "-1080x50")
    assert(spec.transform == 1 and spec.cm == "srgb")
end
''')

    def test_initial_custom_scale_is_available_on_return(self):
        self.lua('''
monitor.width, monitor.height, monitor.scale = 3840, 2160, 1.2
up()
assert(monitor.scale == 1.25)
down()
assert(monitor.scale == 1.2)
''')

    def test_only_clean_pixel_divisors_are_used(self):
        self.lua('''
monitor.width, monitor.height = 1366, 768
up()
assert(monitor.scale == 2)
assert(#changes == 1)
down()
assert(monitor.scale == 1)
''')

    def test_scaling_cannot_overlap_another_rotated_output(self):
        self.lua('''
monitor.scale, monitor.transform = 1.25, 1
monitors[2] = { name = "DP-2", width = 1920, height = 1080,
    scale = 1, transform = 0, x = 864, y = 0, is_mirror = false }
down()
assert(#changes == 0 and monitor.scale == 1.25)
up()
assert(#changes == 1 and monitor.scale == 1.5)
down()
assert(#changes == 2 and monitor.scale == 1.25)
''')

    def test_mirrors_and_missing_outputs_are_untouched(self):
        self.lua('''
monitor.is_mirror = true
up()
monitor.is_mirror = false
monitor.mirrors = { { name = "HDMI-A-1" } }
down()
focused = nil
up()
down()
assert(#changes == 0)
''')

    def test_zoom_is_bounded_and_resettable_without_an_output(self):
        self.lua('''
for _ = 1, 10 do binds["SUPER + CTRL + Z"]() end
assert(zoom == 3)
focused = nil
binds["SUPER + CTRL + ALT + Z"]()
assert(zoom == 1)
binds["SUPER + CTRL + Z"]()
assert(zoom == 1)
''')

    @unittest.skipUnless(shutil.which('Hyprland'), 'Native verification requires Hyprland')
    def test_callbacks_parse_with_native_hyprland(self):
        executable = shutil.which('Hyprland')
        if '--verify-config' not in subprocess.check_output([executable, '--help'], text=True):
            self.skipTest('Hyprland lacks --verify-config')
        with tempfile.TemporaryDirectory(prefix='luna-display-') as temp:
            config = Path(temp) / 'hyprland.lua'
            module = str(MODULE).replace('\\', '\\\\').replace('"', '\\"')
            config.write_text('''
local bindings = {}
hl.get_active_monitor = function()
    return { name = "LUNA-VERIFY", width = 1920, height = 1080, scale = 1,
        refresh_rate = 60, transform = 0, cm = "srgb", x = 0, y = 0, mirrors = {} }
end
hl.get_monitors = function() return {} end
dofile("''' + module + '''")(function(key, action) bindings[key] = action end)
for _, action in pairs(bindings) do action() end
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
