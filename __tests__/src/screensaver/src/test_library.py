"""Run Lua package storage against real file tools and isolated user directories."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[4]


class ScreensaverLibraryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="luna library ' ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.env = dict(os.environ, HOME=str(self.root), XDG_DATA_HOME=str(self.root / "data space"))
        self.directory = self.root / "data space/luna/screensavers"

    def package(self, name, content="import QtQuick\nItem {}\n"):
        source = self.root / "sources" / name
        source.mkdir(parents=True, exist_ok=True)
        (source / "shell.qml").write_text(content)
        return source

    def lua(self, code, ok=True, request=None):
        program = '''
local root = arg[1]
local common = dofile(root .. "/lib/common.lua")
local json = dofile(root .. "/lib/json.lua")
local library = dofile(root .. "/src/screensaver/src/library.lua")(common, root)
local request = json.decode(os.getenv("TEST_REQUEST"))
''' + code
        result = subprocess.run(["/usr/bin/lua", "-E", "-", str(REPO)], input=program,
                                cwd=self.root, env=dict(self.env, TEST_REQUEST=json.dumps(request)),
                                text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        if ok:
            self.assertEqual(result.stderr, "")
        return result

    def invoke(self, method, argument=None, ok=True):
        result = self.lua('''
local result
if request.method == "install" then
    result = library.install(request.argument.source, request.argument.options)
elseif request.method == "remove" or request.method == "removalPlan" then
    result = library[request.method](request.argument.names, request.argument.protectedPaths)
else
    result = library[request.method](request.argument)
end
print(json.encode(result))
''', ok=ok, request={"method": method, "argument": argument})
        return json.loads(result.stdout) if ok else result.stderr

    def install(self, source, **options):
        return self.invoke("install", {"source": str(source), "options": options})

    def assert_unstaged(self):
        self.assertEqual(list(self.directory.glob(".install-*")), [])

    def test_discovery_is_passive_and_bundled_order_is_stable(self):
        self.assertEqual(self.invoke("getDirectory"), str(self.directory))
        entries = self.invoke("list")
        self.assertEqual([entry["name"] for entry in entries], ["clock", "blank", "orbit"])
        self.assertTrue(all(entry["bundled"] and Path(entry["path"]).is_file() for entry in entries))
        self.assertEqual(self.invoke("resolve", "clock")["selection"], "")
        self.assertEqual(self.invoke("resolve", "blank")["selection"], entries[1]["path"])
        self.assertFalse(self.directory.parent.exists())
        result = self.lua('local unused = library.getDirectory(); library.list(); library.resolve("clock")')
        self.assertEqual(result.stdout, "")

    def test_home_default_and_absolute_xdg_validation(self):
        self.env["XDG_DATA_HOME"] = ""
        self.assertEqual(self.invoke("getDirectory"), str(self.root / ".local/share/luna/screensavers"))
        self.env["XDG_DATA_HOME"] = "relative/path"
        self.assertIn("absolute", self.invoke("getDirectory", ok=False))
        self.assertFalse(self.directory.exists())

    def test_install_two_packages_preserves_assets_and_ignores_only_git(self):
        source = self.package("zulu", 'Item { Component.onCompleted: throw "never execute" }')
        (source / "assets/.hidden").mkdir(parents=True)
        (source / "assets/.hidden/data").write_bytes(b"\x00\x01assets")
        (source / ".settings").write_text("personal")
        (source / ".git").mkdir()
        (source / ".git/config").write_text("not a resource")
        (source / "assets/.git").mkdir()
        (source / "assets/.git/config").write_text("nested metadata")
        first = self.install(source)
        second = self.install(self.package("alpha"))
        self.assertFalse(first["bundled"])
        self.assertEqual(Path(first["path"]), self.directory / "zulu/shell.qml")
        self.assertEqual((self.directory / "zulu/assets/.hidden/data").read_bytes(), b"\x00\x01assets")
        self.assertEqual((self.directory / "zulu/.settings").read_text(), "personal")
        self.assertFalse((self.directory / "zulu/.git").exists())
        self.assertFalse((self.directory / "zulu/assets/.git").exists())
        self.assertEqual([entry["name"] for entry in self.invoke("list")],
                         ["clock", "blank", "orbit", "alpha", "zulu"])
        self.assertEqual(second["path"], self.invoke("resolve", "alpha")["selection"])
        self.assert_unstaged()

    def test_standalone_qml_copies_one_file_and_uses_stem_or_parent_name(self):
        source = self.package("folder")
        (source / "unused.txt").write_text("only folder installs include this")
        entry = self.install(source / "shell.qml")
        self.assertEqual(entry["name"], "folder")
        self.assertEqual([path.name for path in (self.directory / "folder").iterdir()], ["shell.qml"])
        standalone = self.root / "stars.qml"
        standalone.write_text("Item {}")
        self.assertEqual(self.install(standalone)["name"], "stars")

    def test_names_are_validated_and_bundled_names_are_reserved(self):
        source = self.package("source with spaces")
        for name in ("", ".", "..", "../escape", "folder/name", "two words", "-flag", "a\nname", False):
            with self.subTest(name=name):
                self.invoke("install", {"source": str(source), "options": {"name": name}}, ok=False)
        for name in ("clock", "blank", "orbit"):
            with self.subTest(name=name):
                self.assertIn("--name", self.invoke("install", {"source": str(source), "options": {"name": name}}, ok=False))
        self.assertIn("Install options must be an object", self.invoke("install",
            {"source": str(source), "options": False}, ok=False))
        self.assertFalse(self.directory.exists())
        self.assertEqual(self.install(source, name="My.Clock_v2-test")["name"], "My.Clock_v2-test")

    def test_existing_packages_require_force_and_replacement_removes_old_assets(self):
        source = self.package("stable", "old")
        (source / "old.txt").write_text("old asset")
        self.install(source)
        (source / "shell.qml").write_text("new")
        (source / "old.txt").unlink()
        self.assertIn("--force", self.invoke("install", {"source": str(source)}, ok=False))
        self.assertEqual((self.directory / "stable/shell.qml").read_text(), "old")
        self.install(source, force=True)
        self.assertEqual((self.directory / "stable/shell.qml").read_text(), "new")
        self.assertFalse((self.directory / "stable/old.txt").exists())
        self.assert_unstaged()

    def test_copy_failure_preserves_old_package_and_cleans_staging(self):
        source = self.package("stable", "old")
        self.install(source)
        (source / "shell.qml").write_text("new")
        self.lua('''
local capture = common.capture
common.capture = function(arguments, quiet)
    if arguments[1] == "cp" then return "", false end
    return capture(arguments, quiet)
end
assert(not pcall(library.install, request.source, {force = true}))
''', request={"source": str(source)})
        self.assertEqual((self.directory / "stable/shell.qml").read_text(), "old")
        self.assert_unstaged()

    def test_commit_failure_restores_old_package(self):
        source = self.package("stable", "old")
        self.install(source)
        (source / "shell.qml").write_text("new")
        self.lua('''
local rename = os.rename
os.rename = function(source, destination)
    if source:match("/package$") then return nil, "rename failed" end
    return rename(source, destination)
end
assert(not pcall(library.install, request.source, {force = true}))
''', request={"source": str(source)})
        self.assertEqual((self.directory / "stable/shell.qml").read_text(), "old")
        self.assert_unstaged()

    def test_invalid_resources_never_replace_existing_package(self):
        source = self.package("stable", "old")
        self.install(source)
        (source / "shell.qml").write_text("new")
        outside = self.root / "outside.txt"
        outside.write_text("untouched")
        for kind in ("external link", "internal link", "fifo"):
            resource = source / "resource"
            if kind == "fifo":
                os.mkfifo(resource)
            else:
                resource.symlink_to(outside if kind == "external link" else "shell.qml")
            with self.subTest(kind=kind):
                self.invoke("install", {"source": str(source), "options": {"force": True}}, ok=False)
            resource.unlink()
            self.assertEqual((self.directory / "stable/shell.qml").read_text(), "old")
            self.assertEqual(outside.read_text(), "untouched")
            self.assert_unstaged()

    def test_symlinked_sources_and_non_qml_files_are_rejected(self):
        source = self.package("real")
        alias = self.root / "alias"
        alias.symlink_to(source, target_is_directory=True)
        self.assertIn("symlink", self.invoke("install", {"source": str(alias)}, ok=False))
        (source / "link.qml").symlink_to("shell.qml")
        self.assertIn("symlink", self.invoke("install", {"source": str(source / "link.qml")}, ok=False))
        self.invoke("install", {"source": str(self.root / "missing.qml")}, ok=False)
        invalid = self.root / "script.sh"
        invalid.write_text("exit 0")
        self.invoke("install", {"source": str(invalid)}, ok=False)

    def test_source_and_destination_cannot_overlap(self):
        self.install(self.package("same"))
        for source in (self.directory / "same", self.directory / "same/shell.qml"):
            with self.subTest(source=source):
                self.assertIn("overlap", self.invoke("install", {"source": str(source),
                    "options": {"name": "same", "force": True}}, ok=False))
        (self.directory / "shell.qml").write_text("Item {}")
        self.assertIn("overlap", self.invoke("install", {"source": str(self.directory),
            "options": {"name": "nested"}}, ok=False))
        self.assertEqual((self.directory / "same/shell.qml").read_text(), "import QtQuick\nItem {}\n")

    def test_resolve_names_absolute_relative_and_home_paths(self):
        source = self.package("custom")
        installed = self.install(source)
        self.assertEqual(self.invoke("resolve", "custom")["path"], installed["path"])
        self.assertEqual(self.invoke("resolve", installed["path"])["name"], "custom")
        self.assertEqual(self.invoke("resolve", str(source / "shell.qml"))["selection"], str(source / "shell.qml"))
        self.assertEqual(self.invoke("resolve", "~/sources/custom/shell.qml")["path"], str(source / "shell.qml"))
        self.assertEqual(self.invoke("resolve", "sources/custom/shell.qml")["path"], str(source / "shell.qml"))
        clock = self.invoke("resolve", str(REPO / "src/screensaver/src/shell/shell.qml"))
        self.assertEqual((clock["name"], clock["selection"]), ("clock", ""))
        for invalid in ("missing", "../missing.qml", "", "~someone/file.qml", "x\n.qml"):
            with self.subTest(invalid=invalid):
                self.invoke("resolve", invalid, ok=False)

    def test_selected_or_live_package_cannot_be_replaced_or_removed(self):
        source = self.package("selected")
        entry = self.install(source)
        alias = self.root / "selected-alias.qml"
        alias.symlink_to(entry["path"])
        for protected in ([entry["path"]], [str(alias)], [str(self.directory / "selected/assets/missing")]):
            with self.subTest(protected=protected):
                self.assertIn("another screensaver", self.invoke("install", {"source": str(source),
                    "options": {"force": True, "protectedPaths": protected}}, ok=False))
                for method in ("removalPlan", "remove"):
                    self.assertIn("another screensaver", self.invoke(method,
                        {"names": ["selected"], "protectedPaths": protected}, ok=False))
        self.assertTrue(Path(entry["path"]).exists())

    def test_batch_removal_validates_every_name_before_deleting(self):
        for name in ("first", "second"):
            self.install(self.package(name))
        for names in (["first", "missing"], ["first", "clock"], ["first", "../second"]):
            with self.subTest(names=names):
                self.invoke("remove", {"names": names}, ok=False)
            self.assertTrue((self.directory / "first/shell.qml").exists())
            self.assertTrue((self.directory / "second/shell.qml").exists())
        self.invoke("remove", {"names": ["first", "second"],
            "protectedPaths": [str(self.directory / "second/shell.qml")]}, ok=False)
        plan = self.invoke("removalPlan", {"names": ["second", "first", "second"]})
        self.assertEqual([entry["name"] for entry in plan], ["second", "first"])
        self.assertTrue((self.directory / "first").exists())
        self.assertEqual(self.invoke("remove", {"names": ["second", "first", "second"]}), ["second", "first"])
        self.assertEqual(len(self.invoke("list")), 3)

    def test_remove_revalidates_previous_plan_and_refuses_external_paths(self):
        self.install(self.package("first"))
        self.install(self.package("second"))
        self.invoke("removalPlan", {"names": ["first", "second"]})
        (self.directory / "second/shell.qml").unlink()
        self.invoke("remove", {"names": ["first", "second"]}, ok=False)
        self.assertTrue((self.directory / "first/shell.qml").exists())
        self.invoke("remove", {"names": [str(self.root / "sources/first/shell.qml")]}, ok=False)
        self.assertTrue((self.root / "sources/first/shell.qml").exists())

    def test_library_entry_symlinks_never_redirect_operations(self):
        source = self.package("outside")
        self.directory.mkdir(parents=True)
        (self.directory / "alias").symlink_to(source, target_is_directory=True)
        self.invoke("list", ok=False)
        self.invoke("resolve", "alias", ok=False)
        self.invoke("remove", {"names": ["alias"]}, ok=False)
        self.invoke("install", {"source": str(source), "options": {"name": "alias", "force": True}}, ok=False)
        self.assertTrue((source / "shell.qml").is_file())

    def test_library_root_symlinks_never_redirect_operations(self):
        outside = self.root / "outside"
        outside.mkdir()
        self.directory.parent.mkdir(parents=True)
        self.directory.symlink_to(outside, target_is_directory=True)
        source = self.package("source")
        self.assertIn("real directory", self.invoke("list", ok=False))
        self.assertIn("real directory", self.invoke("remove", {"names": ["missing"]}, ok=False))
        self.assertIn("real directory", self.invoke("install", {"source": str(source)}, ok=False))
        self.assertEqual(list(outside.iterdir()), [])

    def test_resource_symlink_added_after_install_is_unlinked_without_following_it(self):
        self.install(self.package("first"))
        outside = self.package("outside", "keep")
        (self.directory / "first/escape").symlink_to(outside, target_is_directory=True)
        self.invoke("remove", {"names": ["first"]})
        self.assertEqual((outside / "shell.qml").read_text(), "keep")

    def test_api_is_silent_preserves_arrays_and_never_executes_paths(self):
        source = self.package("my ' $(touch BAD); `touch ALSO` shell")
        result = self.lua('''
local entry = library.install(request.source, {name = "safe"})
assert(library.resolve("safe").path == entry.path)
assert(#library.removalPlan({"safe"}) == 1)
assert(json.encode(library.remove({"safe"})) == '["safe"]')
assert(not pcall(library.install, request.source, {force = "yes"}))
assert(not pcall(library.remove, {"missing", extra = "bad"}))
''', request={"source": str(source)})
        self.assertEqual(result.stdout, "")
        self.assertFalse((self.root / "BAD").exists())
        self.assertFalse((self.root / "ALSO").exists())


if __name__ == "__main__":
    unittest.main()
