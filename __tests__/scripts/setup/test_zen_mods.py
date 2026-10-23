"""Plan native Zen Mods in temporary profiles; mock all network downloads."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error


REPO = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("zen_mods", REPO / "scripts/setup/zen_mods.py")
MODS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODS)


class ZenModTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna mods ' Ω ")
        self.addCleanup(self.temporary.cleanup)
        self.addCleanup(MODS.release_lock)
        self.root = Path(self.temporary.name)
        self.profile = self.root / "profile"
        self.profile.mkdir()
        self.manifest = {
            "id": MODS.MOD_ID, "name": "Better Find Bar", "version": "1.5.1",
            "author": "RobotoSkunk", "description": "Floating find bar",
            "style": MODS.ASSET_ROOT + "chrome.css",
            "readme": MODS.ASSET_ROOT + "readme.md",
            "preferences": MODS.ASSET_ROOT + "preferences.json",
            "unknown-future-field": {"keep": True},
        }
        self.width = "theme.better_find_bar.textbox_width"
        self.transparent = "theme.better_find_bar.transparent_background"
        self.position = "theme.better_find_bar.horizontal_position"
        self.preferences = [
            {"property": self.width, "type": "string", "defaultValue": "800"},
            {"property": self.transparent, "type": "checkbox", "defaultValue": True},
            {"property": self.position, "type": "dropdown", "defaultValue": "default"},
        ]
        self.payloads = {
            MODS.MANIFEST_URL: json.dumps(self.manifest).encode(),
            MODS.ASSET_ROOT + "chrome.css": b"findbar { width: 90%; }\n",
            MODS.ASSET_ROOT + "readme.md": b"# Better Find Bar\n",
            MODS.ASSET_ROOT + "preferences.json": json.dumps(self.preferences).encode(),
        }
        self.download = self.enterContext(patch.object(MODS, "download", side_effect=lambda url: self.payloads[url]))

    def read_personal(self, path):
        target = path.resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("test profile alias points outside its permitted root")
        try:
            return target, target.read_bytes(), stat.S_IMODE(target.stat().st_mode)
        except FileNotFoundError:
            return target, b"", 0o600

    def prepare(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            writes = MODS.prepare_mod(self.profile, self.read_personal)
        return writes, output.getvalue()

    def apply(self, writes):
        for path, content, mode in writes:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            path.chmod(mode)
        MODS.release_lock()

    def create(self, relative, content):
        path = self.profile / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def registry(self, entries):
        return self.create("zen-themes.json", json.dumps(entries).encode())

    def test_first_install_seeds_native_files_cache_and_editable_defaults(self):
        writes, warning = self.prepare()
        self.assertEqual(warning, "")
        self.assertEqual(len(writes), 6)
        self.assertFalse((self.profile / "zen-themes.json").exists())
        self.assertFalse((self.profile / "chrome").exists())
        self.apply(writes)
        registry = json.loads((self.profile / "zen-themes.json").read_bytes())
        self.assertEqual(registry[MODS.MOD_ID], dict(self.manifest, enabled=True))
        self.assertIn(b"findbar { width: 90%; }", (self.profile / "chrome/zen-themes.css").read_bytes())
        self.assertEqual((self.profile / f"chrome/zen-themes/{MODS.MOD_ID}/preferences.json").read_bytes(),
                         self.payloads[MODS.ASSET_ROOT + "preferences.json"])
        prefs = (self.profile / "prefs.js").read_text()
        self.assertIn(f'user_pref("{self.width}", "800");', prefs)
        self.assertIn(f'user_pref("{self.transparent}", true);', prefs)
        self.assertFalse((self.profile / "user.js").exists())

    def test_preserves_other_mod_metadata_enabled_styles_and_personal_preferences(self):
        original = {
            "other": {"id": "other", "name": "Other", "custom": [1, "kept"]},
            "disabled": {"id": "disabled", "enabled": False, "unknown": "preserved"},
        }
        registry = self.registry(original)
        registry.chmod(0o640)
        other = self.create("chrome/zen-themes/other/chrome.css", b"/* personal mod */\nbody { color: red; }")
        cache = self.create("chrome/zen-themes.css", b"/* previous generated cache */")
        cache.chmod(0o644)
        prefs_content = f'user_pref("{self.width}", "600");\r\nuser_pref("unrelated", 42);\r\n'.encode()
        prefs = self.create("prefs.js", prefs_content)
        prefs.chmod(0o640)
        user = self.create("user.js", f"user_pref('{self.transparent}', false);\n".encode())
        writes, warning = self.prepare()
        self.assertEqual(warning, "")
        self.apply(writes)
        installed = json.loads(registry.read_bytes())
        self.assertEqual({key: installed[key] for key in original}, original)
        self.assertEqual(installed[MODS.MOD_ID]["unknown-future-field"], {"keep": True})
        self.assertIn(other.read_bytes(), cache.read_bytes())
        self.assertLess(cache.read_bytes().index(b"personal mod"), cache.read_bytes().index(b"findbar"))
        self.assertNotIn(b"Mod: disabled", cache.read_bytes())
        self.assertTrue(prefs.read_bytes().startswith(prefs_content))
        self.assertNotIn(f'user_pref("{self.transparent}"'.encode(), prefs.read_bytes())
        self.assertEqual(prefs.read_bytes().count(self.width.encode()), 1)
        self.assertEqual(user.read_bytes(), f"user_pref('{self.transparent}', false);\n".encode())
        self.assertEqual(stat.S_IMODE(registry.stat().st_mode), 0o640)
        self.assertEqual(stat.S_IMODE(cache.stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(prefs.stat().st_mode), 0o640)

    def test_rerun_preserves_user_disabled_state_newer_version_and_settings(self):
        writes, _ = self.prepare()
        self.apply(writes)
        registry = json.loads((self.profile / "zen-themes.json").read_bytes())
        registry[MODS.MOD_ID].update(enabled=False, version="99.0", custom=True)
        self.registry(registry)
        self.create("prefs.js", f'user_pref("{self.width}", "450");\n'.encode())
        snapshot = {path: path.read_bytes() for path in self.profile.rglob("*") if path.is_file()}
        self.download.reset_mock()
        writes, warning = self.prepare()
        self.assertEqual((writes, warning), ([], ""))
        self.download.assert_not_called()
        self.assertEqual(snapshot, {path: path.read_bytes() for path in self.profile.rglob("*") if path.is_file()})

    def test_interrupted_publication_can_retry_without_duplicate_styles_or_defaults(self):
        writes, _ = self.prepare()
        self.assertEqual(writes[-1][0], self.profile / "zen-themes.json")
        self.assertEqual(writes[-2][0], self.profile / "prefs.js")
        # Start with only one published asset, then simulate a failure at the
        # registry commit. Both retry states retain exactly the official bytes.
        self.apply(writes[:1])
        retry, warning = self.prepare()
        self.assertEqual(warning, "")
        self.apply(retry[:-1])
        self.assertFalse((self.profile / "zen-themes.json").exists())
        retry, warning = self.prepare()
        self.assertEqual(warning, "")
        self.apply(retry)
        self.assertEqual((self.profile / "chrome/zen-themes.css").read_bytes().count(b"findbar {"), 1)
        self.assertEqual((self.profile / "prefs.js").read_bytes().count(self.width.encode()), 1)
        self.assertIn(MODS.MOD_ID, json.loads((self.profile / "zen-themes.json").read_bytes()))

    def test_preference_tokenizer_ignores_comments_and_strings_and_decodes_keys(self):
        escaped_width = self.width.replace("width", r"\u0077idth")
        self.create("prefs.js", (
            f'// user_pref("{self.position}", "left");\n'
            f'/* user_pref("{self.transparent}", false); */\n'
            f'user_pref("example", "user_pref(\\\"{self.position}\\\", \\\"left\\\");");\n'
            f'user_pref("{escaped_width}", "600");\n'
        ).encode())
        writes, warning = self.prepare()
        self.assertEqual(warning, "")
        prefs = next(content for path, content, _ in writes if path.name == "prefs.js")
        self.assertNotIn(f'user_pref("{self.width}", "800");'.encode(), prefs)
        self.assertIn(f'user_pref("{self.position}", "default");'.encode(), prefs)
        self.assertIn(f'user_pref("{self.transparent}", true);'.encode(), prefs)

    def test_invalid_registry_is_kept_and_no_installation_is_planned(self):
        for content in (b"", b"{", b"[]", b"null", b'{"same":{},"same":{}}'):
            with self.subTest(content=content):
                path = self.create("zen-themes.json", content)
                writes, warning = self.prepare()
                self.assertEqual(writes, [])
                self.assertIn("Better Find Bar skipped", warning)
                self.assertEqual(path.read_bytes(), content)
                self.assertFalse((self.profile / "chrome").exists())
        self.download.assert_not_called()

    def test_missing_or_unsafe_other_mod_is_not_silently_dropped(self):
        for entry in ({"other": {"id": "other"}}, {"../outside": {"id": "../outside"}}):
            with self.subTest(entry=entry):
                path = self.registry(entry)
                original = path.read_bytes()
                writes, warning = self.prepare()
                self.assertEqual(writes, [])
                self.assertIn("Better Find Bar skipped", warning)
                self.assertEqual(path.read_bytes(), original)
        self.download.assert_not_called()

    def test_network_failure_returns_no_partial_plan_or_asset_files(self):
        def failing_download(url):
            if url.endswith("preferences.json"):
                raise urllib.error.URLError("offline")
            return self.payloads[url]
        self.download.side_effect = failing_download
        writes, warning = self.prepare()
        self.assertEqual(writes, [])
        self.assertIn("offline", warning)
        self.assertFalse((self.profile / "chrome").exists())
        self.assertFalse((self.profile / "zen-themes.json").exists())
        self.assertFalse((self.profile / "prefs.js").exists())

    def test_unexpected_metadata_or_preference_data_is_rejected(self):
        cases = [
            (MODS.MANIFEST_URL, json.dumps(dict(self.manifest, style="https://example.com/evil.css")).encode()),
            (MODS.ASSET_ROOT + "preferences.json", b"{}"),
            (MODS.ASSET_ROOT + "preferences.json", b'[{"property":"browser.evil","type":"checkbox","defaultValue":true}]'),
            (MODS.ASSET_ROOT + "chrome.css", b"<html>findbar download failed</html>"),
        ]
        for url, payload in cases:
            with self.subTest(url=url, payload=payload), patch.dict(self.payloads, {url: payload}):
                writes, warning = self.prepare()
                self.assertEqual(writes, [])
                self.assertIn("Better Find Bar skipped", warning)
                self.assertFalse((self.profile / "chrome").exists())

    def test_symlinked_personal_registry_and_prefs_keep_targets_and_modes(self):
        for name, content in (("zen-themes.json", b"{}"), ("prefs.js", b'// my prefs\n')):
            target = self.root / name
            target.write_bytes(content)
            target.chmod(0o640)
            (self.profile / name).symlink_to(target)
        writes, warning = self.prepare()
        self.assertEqual(warning, "")
        self.apply(writes)
        for name in ("zen-themes.json", "prefs.js"):
            self.assertTrue((self.profile / name).is_symlink())
            self.assertEqual(stat.S_IMODE((self.root / name).stat().st_mode), 0o640)

    def test_conflicting_aliases_and_unregistered_asset_folders_are_preserved(self):
        shared = self.root / "shared"
        shared.write_bytes(b"{}")
        (self.profile / "zen-themes.json").symlink_to(shared)
        (self.profile / "prefs.js").symlink_to(shared)
        writes, warning = self.prepare()
        self.assertEqual(writes, [])
        self.assertIn("separate paths", warning)
        self.assertEqual(shared.read_bytes(), b"{}")
        (self.profile / "zen-themes.json").unlink()
        (self.profile / "prefs.js").unlink()
        existing = self.create(f"chrome/zen-themes/{MODS.MOD_ID}/chrome.css", b"/* user asset */")
        writes, warning = self.prepare()
        self.assertEqual(writes, [])
        self.assertIn("unregistered", warning)
        self.assertEqual(existing.read_bytes(), b"/* user asset */")

    def test_running_profile_lock_skips_downloads_and_all_planned_writes(self):
        # A separate process is necessary because POSIX locks belong to a process.
        program = '''import fcntl, sys
with open(sys.argv[1], "a+b") as lock:
    fcntl.lockf(lock, fcntl.LOCK_EX)
    print("locked", flush=True)
    sys.stdin.read()
'''
        process = subprocess.Popen([sys.executable, "-B", "-c", program, str(self.profile / ".parentlock")],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(), "locked")
            writes, warning = self.prepare()
            self.assertEqual(writes, [])
            self.assertIn("close Zen and rerun setup", warning)
            self.download.assert_not_called()
            self.assertFalse((self.profile / "chrome").exists())
        finally:
            process.communicate(timeout=5)

    def test_success_holds_native_lock_until_caller_releases_it(self):
        writes, _ = self.prepare()
        self.assertTrue(writes)
        program = '''import fcntl, sys
with open(sys.argv[1], "r+b") as lock:
    try:
        fcntl.lockf(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit(23)
'''
        arguments = [sys.executable, "-B", "-c", program, str(self.profile / ".parentlock")]
        self.assertEqual(subprocess.run(arguments, capture_output=True, timeout=5).returncode, 23)
        MODS.release_lock()
        self.assertEqual(subprocess.run(arguments, capture_output=True, timeout=5).returncode, 0)

    def test_obsolete_modern_symlink_lock_is_kept_and_legacy_lock_is_skipped(self):
        old_lock = self.profile / "lock"
        old_lock.symlink_to("127.0.0.1:+123456")
        writes, warning = self.prepare()
        self.assertTrue(writes)
        self.assertEqual(warning, "")
        self.assertEqual(os.readlink(old_lock), "127.0.0.1:+123456")
        MODS.release_lock()
        old_lock.unlink()
        old_lock.symlink_to("192.0.2.1:123456")
        writes, warning = self.prepare()
        self.assertEqual(writes, [])
        self.assertIn("legacy lock", warning)
        self.assertEqual(os.readlink(old_lock), "192.0.2.1:123456")

    def test_symlinked_parentlock_is_not_followed(self):
        target = self.root / "not-a-lock"
        target.write_bytes(b"keep")
        (self.profile / ".parentlock").symlink_to(target)
        writes, warning = self.prepare()
        self.assertEqual(writes, [])
        self.assertIn("profile lock", warning)
        self.assertEqual(target.read_bytes(), b"keep")


class DownloadTests(unittest.TestCase):
    def response(self, content, url):
        class Response(io.BytesIO):
            def geturl(self):
                return url
        return Response(content)

    def test_download_limit_timeout_and_redirect_validation(self):
        for content, url in ((b"x" * (MODS.MAX_DOWNLOAD + 1), MODS.MANIFEST_URL),
                             (b"{}", "https://example.com/redirect"), (b"", MODS.MANIFEST_URL)):
            with self.subTest(size=len(content), url=url), patch.object(
                MODS.urllib.request, "urlopen", return_value=self.response(content, url)
            ) as request:
                with self.assertRaises(ValueError):
                    MODS.download(MODS.MANIFEST_URL)
                request.assert_called_once_with(MODS.MANIFEST_URL, timeout=10)


if __name__ == "__main__":
    unittest.main()
