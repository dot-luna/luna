"""Exercise lock configuration and failures without locking the host session."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[4]


class LockTests(unittest.TestCase):
    def test_theme_configuration_authentication_and_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backend = root / "hyprlock"
            backend.write_text("""#!/usr/bin/python3
import json, os, pathlib, sys
root = pathlib.Path(os.environ["TEST_LOCK_ROOT"])
args = sys.argv[1:]
config = pathlib.Path(args[args.index("--config") + 1])
(root / "capture.json").write_text(json.dumps({"args": args, "config": config.read_text()}))
sys.exit(int(os.environ.get("TEST_LOCK_FAILURE", "0")))
""")
            backend.chmod(0o755)
            env = dict(os.environ, PATH=str(root) + ":" + os.environ["PATH"],
                       XDG_CONFIG_HOME=str(root / "config"), XDG_CACHE_HOME=str(root / "cache"),
                       WAYLAND_DISPLAY="test", TEST_LOCK_ROOT=str(root))
            for failure in ("0", "1"):
                env["TEST_LOCK_FAILURE"] = failure
                result = subprocess.run([str(REPO / "bin/luna"), "lock"], env=env,
                                        text=True, capture_output=True, timeout=10)
                self.assertEqual(result.returncode == 0, failure == "0", result.stderr)
                captured = json.loads((root / "capture.json").read_text())
                self.assertEqual(captured["args"][-2:], ["--grace", "0"])
                self.assertIn("input-field {", captured["config"])
                self.assertIn("rounding = 0", captured["config"])
                self.assertIn("font_family = Outfit", captured["config"])
                self.assertNotIn("pam:enabled = false", captured["config"])
                self.assertEqual(list((root / "cache/luna").glob("hyprlock-*.conf")), [])


if __name__ == "__main__":
    unittest.main()
