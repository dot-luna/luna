"""Exercise shared wallpaper operations with mocked system calls only."""

from pathlib import Path
import subprocess
import unittest


REPO = Path(__file__).resolve().parents[3]


class WallpaperDownloadTests(unittest.TestCase):
    def test_missing_curl_bootstrap(self):
        # Inject availability and install calls so bootstrap never invokes host pacman.
        script = '''
local installed = false
local calls = {}
local common = {
    available = function(name)
        return name ~= "curl" or installed
    end,
    is_root = function() return false end,
    info = function() end,
    run = function(args)
        table.insert(calls, table.concat(args, " "))
        installed = true
    end,
}
local download = dofile(arg[1])(common)
download.prepare()
assert(calls[1] == "sudo pacman -Syu --needed curl")
download.prepare()
assert(#calls == 1)
'''
        result = subprocess.run(['/usr/bin/lua', '-E', '-',
                                 str(REPO / 'lib/wallpapers/download.lua')],
                                input=script, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)



if __name__ == "__main__":
    unittest.main()
