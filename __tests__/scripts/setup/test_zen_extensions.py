"""Exercise native Zen policies with temporary installs and mocked privilege calls."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("zen_extensions", REPO / "scripts/setup/zen-extensions.py")
HELPER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HELPER)


class ZenExtensionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna zen extensions '")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.install = self.root / "native Zen"
        self.install.mkdir()
        (self.install / "application.ini").write_text("[App]\nName=Zen\n")
        executable = self.install / "zen-bin"
        executable.write_text("#!/bin/sh\nexit 99\n")
        executable.chmod(0o755)
        self.distribution = self.install / "distribution/policies.json"
        self.write_json(self.distribution, {"policies": {"DisableAppUpdate": True}})
        self.policy = self.root / "etc/zen/policies/policies.json"
        self.manifest = self.root / "extensions.json"
        shutil.copyfile(REPO / "apps/zen/extensions.json", self.manifest)
        self.extensions = json.loads(self.manifest.read_text())
        self.ids = list(self.extensions)
        self.urls = list(self.extensions.values())
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(HELPER, "POLICY_FILE", self.policy).start()
        mock.patch.object(HELPER.os, "geteuid", return_value=1000).start()
        self.run = mock.patch.object(HELPER.subprocess, "run").start()
        self.which = mock.patch.object(HELPER.shutil, "which", return_value="/fixture/sudo").start()
        self.error = io.StringIO()
        self.output = io.StringIO()

    def write_json(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value) + "\n")

    def apply(self):
        HELPER.apply(str(self.install), str(self.manifest))

    def configure(self):
        with contextlib.redirect_stderr(self.error), contextlib.redirect_stdout(self.output):
            HELPER.configure(str(self.install), str(self.manifest))

    def read_policy(self):
        return json.loads(self.policy.read_text())

    def test_first_policy_seeds_packaged_settings_and_installs_removable_addons(self):
        original = self.distribution.read_bytes()
        self.apply()
        self.assertEqual(self.read_policy(), {"policies": {
            "DisableAppUpdate": True, "Extensions": {"Install": self.urls},
        }})
        self.assertEqual(self.distribution.read_bytes(), original)
        self.assertEqual(stat.S_IMODE(self.policy.stat().st_mode), 0o644)
        self.assertEqual(set(self.extensions), {
            "uBlock0@raymondhill.net", "addon@darkreader.org",
            "{446900e4-71c2-419f-a6a7-df9c091e268b}",
        })
        self.run.assert_not_called()

    def test_existing_system_policy_is_authoritative_and_duplicate_urls_are_removed(self):
        other = "https://example.org/other.xpi"
        self.write_json(self.policy, {"custom": True, "policies": {
            "Homepage": {"URL": "https://example.org"},
            "Extensions": {"Install": [other, self.urls[0], other], "Locked": ["other@example.org"]},
        }})
        self.policy.chmod(0o640)
        self.distribution.write_text("This shadowed file is deliberately invalid")
        self.apply()
        self.assertEqual(self.read_policy(), {"custom": True, "policies": {
            "Homepage": {"URL": "https://example.org"},
            "Extensions": {"Install": [other, *self.urls], "Locked": ["other@example.org"]},
        }})
        self.assertEqual(stat.S_IMODE(self.policy.stat().st_mode), 0o640)

    def test_unchanged_policy_preserves_original_bytes_and_needs_no_sudo(self):
        document = {"policies": {"Extensions": {"Install": self.urls}, "DisableAppUpdate": True}}
        self.policy.parent.mkdir(parents=True)
        content = ("\ufeff" + json.dumps(document, indent=2) + "\r\n").encode()
        self.policy.write_bytes(content)
        self.configure()
        self.apply()
        self.assertEqual(self.policy.read_bytes(), content)
        self.distribution.write_bytes(content)
        self.policy.unlink()
        self.policy.symlink_to(self.distribution)
        self.configure()
        self.apply()
        self.assertTrue(self.policy.is_symlink())
        self.assertEqual(self.distribution.read_bytes(), content)
        self.which.assert_not_called()
        self.run.assert_not_called()
        self.assertEqual(self.error.getvalue(), "")

    def test_existing_policy_symlink_is_detached_without_changing_its_target(self):
        self.policy.parent.mkdir(parents=True)
        self.policy.symlink_to(self.distribution)
        original = self.distribution.read_bytes()
        self.apply()
        self.assertFalse(self.policy.is_symlink())
        self.assertEqual(self.distribution.read_bytes(), original)
        self.assertEqual(self.read_policy()["policies"]["Extensions"]["Install"], self.urls)

    def test_missing_distribution_and_profile_still_allow_system_policy(self):
        self.distribution.unlink()
        self.apply()
        self.assertEqual(self.read_policy(), {"policies": {"Extensions": {"Install": self.urls}}})
        self.assertEqual(sorted(path.name for path in self.root.iterdir()),
                         ["etc", "extensions.json", "native Zen"])

    def test_manifest_changes_control_installs_and_empty_manifest_is_a_noop(self):
        self.write_json(self.manifest, {"different@example.org": "https://example.org/new.xpi"})
        self.apply()
        self.assertEqual(self.read_policy()["policies"]["Extensions"]["Install"],
                         ["https://example.org/new.xpi"])
        before = self.policy.read_bytes()
        self.write_json(self.manifest, {})
        self.configure()
        self.assertEqual(self.policy.read_bytes(), before)
        self.run.assert_not_called()

    def test_invalid_policy_warns_and_leaves_all_files_unchanged(self):
        cases = (
            "{bad", "[]", '{"policies": {}, "policies": {}}', '{"policies": {"unknown": NaN}}',
            '{"policies": null}', '{"policies": {"Extensions": []}}',
            '{"policies": {"Extensions": {"Install": "https://example.org/a.xpi"}}}',
            '{"policies": {"Extensions": {"Locked": [1]}}}',
            '{"policies": {"ExtensionSettings": []}}',
        )
        self.policy.parent.mkdir(parents=True)
        for content in cases:
            with self.subTest(content=content):
                self.policy.write_text(content)
                self.configure()
                self.assertEqual(self.policy.read_text(), content)
                self.run.assert_not_called()
        self.assertIn("Skipped", self.error.getvalue())

    def test_invalid_distribution_or_manifest_does_not_create_system_policy(self):
        self.distribution.write_text("{broken")
        self.configure()
        self.assertFalse(self.policy.parent.exists())
        self.write_json(self.distribution, {"policies": {}})
        for manifest in ({"": "https://example.org/a.xpi"}, {"id": 1},
                         {"id": "http://example.org/a.xpi"}, {"id": "https://user:pass@example.org/a.xpi"}):
            with self.subTest(manifest=manifest):
                self.write_json(self.manifest, manifest)
                self.configure()
                self.assertFalse(self.policy.parent.exists())
        self.run.assert_not_called()

    def test_conflicting_removal_lock_or_extension_mode_preserves_policy(self):
        conflicts = [
            {"Extensions": {"Uninstall": [self.ids[0]]}},
            {"Extensions": {"Locked": [self.ids[1]]}},
            {"ExtensionSettings": {"*": {"installation_mode": "blocked"}}},
            *({"ExtensionSettings": {self.ids[0]: {"installation_mode": mode}}}
              for mode in ("blocked", "removed", "normal_installed", "force_installed")),
        ]
        for policies in conflicts:
            with self.subTest(policies=policies):
                self.write_json(self.policy, {"policies": policies})
                before = self.policy.read_bytes()
                self.configure()
                self.assertEqual(self.policy.read_bytes(), before)
                self.run.assert_not_called()
        self.assertIn("conflicts", self.error.getvalue())

    def test_explicit_allowed_modes_override_default_block_without_rewriting_settings(self):
        settings = {"*": {"installation_mode": "blocked"}}
        settings.update({extension: {"installation_mode": "allowed"} for extension in self.ids})
        self.write_json(self.policy, {"policies": {"ExtensionSettings": settings}})
        self.apply()
        self.assertEqual(self.read_policy()["policies"]["ExtensionSettings"], settings)
        self.assertEqual(self.read_policy()["policies"]["Extensions"], {"Install": self.urls})

    def test_missing_wrong_or_nonexecutable_native_install_skips_before_sudo(self):
        for value in ("relative", str(self.root / "missing")):
            with contextlib.redirect_stderr(self.error):
                HELPER.configure(value, str(self.manifest))
        (self.install / "application.ini").write_text("[App]\nName=Firefox\n")
        self.configure()
        (self.install / "application.ini").write_text("[App]\nName=Zen\n")
        (self.install / "zen-bin").chmod(0o644)
        self.configure()
        self.assertFalse(self.policy.parent.exists())
        self.run.assert_not_called()
        self.which.assert_not_called()

    def test_optional_missing_or_failing_sudo_does_not_write_or_report_success(self):
        self.which.return_value = None
        self.configure()
        self.assertIn("sudo is unavailable", self.error.getvalue())
        self.run.assert_not_called()
        self.which.return_value = "/fixture/sudo"
        for outcome in (subprocess.CompletedProcess([], 1), OSError("sudo denied")):
            with self.subTest(outcome=outcome):
                self.run.side_effect = outcome if isinstance(outcome, OSError) else None
                self.run.return_value = outcome
                self.configure()
        self.assertFalse(self.policy.parent.exists())
        self.assertNotIn("policy configured", self.output.getvalue())
        self.assertIn("Policy setup failed", self.error.getvalue())

    def test_sudo_invokes_only_the_helper_apply_mode_and_keeps_paths_as_arguments(self):
        self.run.return_value = subprocess.CompletedProcess([], 0)
        self.configure()
        self.run.assert_called_once_with([
            "/fixture/sudo", "/usr/bin/python3", str(REPO / "scripts/setup/zen-extensions.py"),
            "apply", str(self.install), str(self.manifest),
        ], check=False)
        self.assertIn("Back up policies", self.error.getvalue())
        self.assertIn("restart Zen", self.output.getvalue())
        self.assertFalse(self.policy.parent.exists())

    def test_privileged_apply_revalidates_existing_policy_before_writing(self):
        HELPER.prepare(str(self.install), str(self.manifest))
        self.write_json(self.policy, {"policies": {"Extensions": {"Locked": [self.ids[0]]}}})
        before = self.policy.read_bytes()
        with self.assertRaisesRegex(ValueError, "conflicts"):
            self.apply()
        self.assertEqual(self.policy.read_bytes(), before)

    def test_atomic_failure_keeps_existing_policy_and_removes_temporary_file(self):
        self.write_json(self.policy, {"policies": {"Homepage": {"URL": "https://example.org"}}})
        before = self.policy.read_bytes()
        with mock.patch.object(HELPER.os, "replace", side_effect=OSError("read-only filesystem")):
            with self.assertRaisesRegex(OSError, "read-only"):
                self.apply()
        self.assertEqual(self.policy.read_bytes(), before)
        self.assertEqual(list(self.policy.parent.iterdir()), [self.policy])

    def test_directory_or_dangling_policy_and_package_directory_alias_are_rejected(self):
        self.policy.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "regular JSON file"):
            self.apply()
        self.policy.rmdir()
        self.policy.symlink_to(self.root / "missing-policy")
        with self.assertRaises(FileNotFoundError):
            self.apply()
        self.policy.unlink()
        self.policy.parent.rmdir()
        self.policy.parent.symlink_to(self.install / "distribution", target_is_directory=True)
        before = self.distribution.read_bytes()
        with self.assertRaisesRegex(ValueError, "outside Luna"):
            self.apply()
        self.assertEqual(self.distribution.read_bytes(), before)


class ZenExtensionShellTests(unittest.TestCase):
    def test_shell_uses_manifest_and_absolute_install_override_while_ignoring_extra_arguments(self):
        with tempfile.TemporaryDirectory(prefix="luna zen shell '") as temporary:
            root = Path(temporary)
            for name in ("scripts/setup/zen-extensions.sh", "lib/common.sh"):
                destination = root / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO / name, destination)
            helper = root / "scripts/setup/zen-extensions.py"
            helper.write_text("import json, sys\nprint(json.dumps(sys.argv[1:]))\n")
            binary = root / "bin"
            binary.mkdir()
            for name in ("readlink", "dirname"):
                (binary / name).symlink_to(shutil.which(name))
            env = {"PATH": str(binary), "HOME": str(root / "home"), "NO_COLOR": "1",
                   "BASH_ENV": "", "ENV": "", "ZEN_INSTALL_DIR": str(root / "native Zen '")}
            command = [shutil.which("bash"), str(root / "scripts/setup/zen-extensions.sh"),
                       "--help", "ignored"]
            result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), [
                "configure", env["ZEN_INSTALL_DIR"], str(root / "apps/zen/extensions.json"),
            ])
            env["ZEN_INSTALL_DIR"] = ""
            result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)[1], "/opt/zen-browser-bin")


if __name__ == "__main__":
    unittest.main()
