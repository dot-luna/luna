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
    hl.bind = function() end
    hl.dsp = {
        exec_cmd = function() end,
        window = { close = function() end },
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
assert(#monitors == 1 and monitors[1].scale == 1)
assert(calls[1].general.col.active_border == "#7aa2f7")
assert(calls[1].general.col.inactive_border == "#414868")
assert(calls[1].decoration.blur.size == 10)
assert(calls[1].decoration.blur.passes == 3)
assert(calls[1].decoration.shadow.color == "#13141caa")
local file = assert(io.open(arg[2], "w")); file:write("other\\n"); file:close()
dofile(arg[1])
assert(#calls == 2)
assert(calls[2].general.col.active_border == "#82aaff")
assert(calls[2].general.gaps_in == nil)
assert(calls[2].decoration == nil)
assert(#monitors == 1)
''')
        self.assertFalse((self.root / 'config/luna/generated').exists())

    def test_no_selection_and_invalid_selection(self):
        self.lua('hl = { config = function() error("No theme should be applied") end }; dofile(arg[1])')
        for name in ('../escape', 'missing'):
            (self.config / 'theme').write_text(name + '\n')
            self.lua('hl = { config = function() error("Invalid theme must not be applied") end }; dofile(arg[1])', ok=False)
        (self.config / 'theme').write_text('tokyo-night\n')
        (self.theme / 'hyprland.lua').write_text('return { decoration = { rounding = -1 } }')
        self.lua('hl = { config = function() error("Invalid settings must not be applied") end }; dofile(arg[1])', ok=False)

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
