"""Keep optional Zen Mod publication separate from app configuration."""

import importlib.util
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch


REPO = Path(__file__).resolve().parents[3]


class ZenExtrasTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luna zen extras '")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.profile = self.root / "profile"
        self.profile.mkdir()
        self.destination = self.root / "luna/zen"
        self.mods = types.SimpleNamespace(prepare_mod=Mock(return_value=[]), release_lock=Mock())
        spec = importlib.util.spec_from_file_location("zen_extras", REPO / "scripts/setup/zen-extras.py")
        self.extras = importlib.util.module_from_spec(spec)
        with patch.dict("sys.modules", {"zen_mods": self.mods}):
            spec.loader.exec_module(self.extras)
        self.enterContext(patch.dict(os.environ, {
            "HOME": str(self.root), "ZEN_PROFILE_DIR": str(self.profile),
        }))

    def test_mod_writes_publish_only_in_extras_and_release_lock(self):
        registry = self.profile / "zen-themes.json"
        self.mods.prepare_mod.return_value = [(registry, b"{}\n", 0o640)]
        self.extras.install(str(self.destination), True)
        self.assertEqual(registry.read_bytes(), b"{}\n")
        self.assertEqual(registry.stat().st_mode & 0o777, 0o640)
        self.mods.release_lock.assert_called_once_with()
        self.assertFalse(self.destination.exists())

    def test_aliases_to_personal_styles_and_locks_fail_before_publication(self):
        registry = self.profile / "zen-themes.json"
        for relative in ("chrome/userChrome.css", "chrome/userContent.css", "user.js", ".parentlock", "lock"):
            with self.subTest(relative=relative):
                self.mods.prepare_mod.return_value = [
                    (registry, b"{}", 0o600), (self.profile / relative, b"bad", 0o600),
                ]
                with self.assertRaisesRegex(ValueError, "separate files"):
                    self.extras.install(str(self.destination), True)
                self.assertFalse(registry.exists())
        self.assertEqual(self.mods.release_lock.call_count, 5)

    def test_failed_publication_releases_profile_lock(self):
        self.mods.prepare_mod.return_value = [(self.profile / "zen-themes.json", b"{}", 0o600)]
        with patch.object(self.extras.profile_config, "write_file", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                self.extras.install(str(self.destination), True)
        self.mods.release_lock.assert_called_once_with()

    def test_missing_browser_skips_without_explicit_profile(self):
        with patch.dict(os.environ, {"ZEN_PROFILE_DIR": ""}):
            self.extras.install(str(self.destination), False)
        self.mods.prepare_mod.assert_not_called()
        self.extras.install(str(self.destination), False)
        self.mods.prepare_mod.assert_called_once()

    def test_profile_cannot_overlap_luna_output(self):
        with patch.dict(os.environ, {"ZEN_PROFILE_DIR": str(self.destination)}):
            with self.assertRaisesRegex(ValueError, "separate"):
                self.extras.install(str(self.destination), True)
        self.mods.prepare_mod.assert_not_called()

    def test_config_planning_never_installs_mods_or_writes_files(self):
        styles = {"chrome": "/* chrome */", "content": "/* content */",
                  "fonts": {"ui": "UI", "mono": "Mono"}}
        writes = self.extras.profile_config.plan(str(self.destination), True, styles)
        self.assertEqual(len(writes), 3)
        self.assertEqual(list(self.profile.iterdir()), [])
        self.assertFalse(self.destination.exists())
        self.mods.prepare_mod.assert_not_called()


if __name__ == "__main__":
    unittest.main()
