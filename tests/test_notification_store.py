"""Run the native Quickshell notification service on a private DBus with no windows."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest


REPO = Path(__file__).resolve().parents[1]


class NotificationStoreIsolationTests(unittest.TestCase):
    @unittest.skipUnless(all(shutil.which(tool) for tool in ("qs", "dbus-run-session"))
                         and importlib.util.find_spec("dbus") and importlib.util.find_spec("gi"),
                         "Quickshell, DBus, python-dbus and PyGObject required")
    def test_native_notification_lifecycle_on_private_bus(self):
        environment = dict(os.environ, LUNA_PARENT_DBUS_ADDRESS=os.environ.get("DBUS_SESSION_BUS_ADDRESS", ""))
        result = subprocess.run(["dbus-run-session", "--", sys.executable, __file__, "--isolated"],
                                env=environment, capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


def native_tests():
    import dbus
    from dbus.mainloop.glib import DBusGMainLoop
    from gi.repository import GLib

    address = os.environ.get("DBUS_SESSION_BUS_ADDRESS", "")
    assert address and address != os.environ.get("LUNA_PARENT_DBUS_ADDRESS"), "Private DBus required"
    DBusGMainLoop(set_as_default=True)

    class NativeNotificationTests(unittest.TestCase):
        @classmethod
        def setUpClass(cls):
            cls.temporary = tempfile.TemporaryDirectory(prefix="luna-notification-test-")
            cls.root = Path(cls.temporary.name)
            (cls.root / "notifications").symlink_to(REPO / "src/luna-bar/notifications", target_is_directory=True)
            (cls.root / "shell.qml").write_text('''import QtQuick
import Quickshell
import Quickshell.Io
import "notifications"
ShellRoot {
    id: fixture
    property var sounds: []
    NotificationStore {
        id: store
        onSoundRequested: urgency => fixture.sounds = fixture.sounds.concat([urgency])
    }
    IpcHandler {
        target: "test"
        function state(): string { return JSON.stringify({entries:store.entries, popups:store.popupEntries, unread:store.unreadCount, dnd:store.dnd, sounds:fixture.sounds}); }
        function clearSounds(): void { fixture.sounds = []; }
        function clear(): void { store.clear(); }
        function dismiss(id: int): void { store.dismiss(id); }
        function remove(id: int): void { store.remove(id); }
        function read(): void { store.markRead(); }
        function dnd(value: bool): void { store.dnd = value; }
        function panel(value: bool): void { store.panelOpen = value; }
        function invoke(id: int, action: string): void { store.invoke(id, action); }
        function open(id: int): bool { return store.open(id); }
        function hover(id: int, value: bool): void { store.setHovered(id, value); }
        function reload(): void { Qt.callLater(function() { Quickshell.reload(false); }); }
    }
}
''')
            runtime = cls.root / "runtime"
            runtime.mkdir(mode=0o700)
            config = cls.root / "config"
            (config / "luna").mkdir(parents=True)
            home = cls.root / "home"
            home.mkdir()
            tools = cls.root / "tools"
            tools.mkdir()
            opener = tools / "xdg-open"
            opener.write_text("#!/usr/bin/env python3\nimport json, os, sys\nwith open(os.environ['LUNA_TEST_OPEN_LOG'], 'a') as log:\n    log.write(json.dumps(sys.argv[1:]) + '\\n')\n")
            opener.chmod(0o755)
            application = tools / "luna-notification-test-app"
            application.write_text("#!/usr/bin/env python3\nimport json, os, sys\nwith open(os.environ['LUNA_TEST_APP_LOG'], 'a') as log:\n    log.write(json.dumps(sys.argv[1:]) + '\\n')\n")
            application.chmod(0o755)
            data = cls.root / "data"
            (data / "applications").mkdir(parents=True)
            (data / "applications/luna-notification-test.desktop").write_text("[Desktop Entry]\nType=Application\nName=Notification test\nIcon=luna-notification-test-icon\nExec=luna-notification-test-app --opened\n")
            cls.environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", XDG_RUNTIME_DIR=str(runtime),
                                   HOME=str(home), XDG_CONFIG_HOME=str(config), QS_NO_RELOAD_POPUP="1",
                                   XDG_DATA_HOME=str(data), XDG_DATA_DIRS=str(cls.root / "empty-data"),
                                   PATH=str(tools) + ":" + os.environ["PATH"], LUNA_TEST_OPEN_LOG=str(cls.root / "opened"),
                                   LUNA_TEST_APP_LOG=str(cls.root / "app-opened"))
            cls.environment.pop("WAYLAND_DISPLAY", None)
            cls.log = (cls.root / "service.log").open("w+")
            cls.process = subprocess.Popen(["qs", "-p", str(cls.root)], env=cls.environment,
                                           stdout=cls.log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 6
            while time.monotonic() < deadline:
                probe = cls.ipc("state", check=False)
                if probe.returncode == 0:
                    break
                if cls.process.poll() is not None:
                    break
                time.sleep(0.05)
            else:
                raise AssertionError("Notification fixture did not start")
            cls.log.flush()
            if cls.process.poll() is not None:
                cls.log.seek(0)
                raise AssertionError(cls.log.read())
            cls.bus = dbus.SessionBus()
            cls.service = dbus.Interface(cls.bus.get_object("org.freedesktop.Notifications", "/org/freedesktop/Notifications"),
                                         "org.freedesktop.Notifications")
            cls.signals = []
            cls.bus.add_signal_receiver(lambda identity, action: cls.signals.append(("action", int(identity), str(action))),
                                        signal_name="ActionInvoked", dbus_interface="org.freedesktop.Notifications")
            cls.bus.add_signal_receiver(lambda identity, reason: cls.signals.append(("closed", int(identity), int(reason))),
                                        signal_name="NotificationClosed", dbus_interface="org.freedesktop.Notifications")

        @classmethod
        def tearDownClass(cls):
            cls.process.terminate()
            cls.process.wait(timeout=5)
            cls.log.seek(0)
            output = cls.log.read()
            if "ERROR" in output or "TypeError" in output:
                print(output, file=sys.stderr)
            cls.log.close()
            cls.temporary.cleanup()

        @classmethod
        def ipc(cls, action, *args, check=True):
            return subprocess.run(["qs", "ipc", "-p", str(cls.root), "call", "test", action, *map(str, args)],
                                  env=cls.environment, capture_output=True, text=True, timeout=3, check=check)

        @classmethod
        def state(cls):
            return json.loads(cls.ipc("state").stdout)

        def setUp(self):
            self.ipc("clear")
            self.ipc("dnd", "false")
            self.ipc("panel", "false")
            self.ipc("clearSounds")
            self.signals.clear()
            for name in ("opened", "app-opened"):
                (self.root / name).unlink(missing_ok=True)

        def notify(self, summary="Message", timeout=0, hints=None, actions=None, replace=0, app="Example", body="Body", app_icon=""):
            return int(self.service.Notify(app, dbus.UInt32(replace), app_icon, summary, body,
                                           dbus.Array(actions or [], signature="s"),
                                           dbus.Dictionary(hints or {}, signature="sv"), dbus.Int32(timeout)))

        def until(self, predicate, timeout=2):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                while GLib.MainContext.default().iteration(False):
                    pass
                try:
                    if predicate():
                        return
                except (subprocess.CalledProcessError, json.JSONDecodeError):
                    pass
                time.sleep(0.02)
            self.fail("Notification condition did not become true")

        def test_capabilities_plain_text_and_unread_history(self):
            capabilities = list(self.service.GetCapabilities())
            self.assertIn("persistence", capabilities)
            self.assertIn("actions", capabilities)
            self.assertNotIn("body-markup", capabilities)
            first = self.notify("<b>First</b>", body="<img src='https://example.test/image'>")
            second = self.notify("Second")
            state = self.state()
            self.assertEqual([entry["id"] for entry in state["entries"]], [second, first])
            self.assertEqual(state["entries"][1]["summary"], "<b>First</b>")
            self.assertEqual(state["unread"], 2)
            self.ipc("read")
            self.assertEqual(self.state()["unread"], 0)

        def test_popup_timeout_keeps_actions_live_in_history(self):
            identity = self.notify(timeout=120, actions=["open", "Open"])
            self.until(lambda: not self.state()["popups"])
            entry = self.state()["entries"][0]
            self.assertTrue(entry["live"])
            self.assertEqual(entry["actions"], [{"identifier": "open", "text": "Open"}])
            self.ipc("invoke", identity, "open")
            self.until(lambda: ("action", identity, "open") in self.signals)
            self.assertFalse(self.state()["entries"][0]["live"])
            self.assertEqual(self.state()["entries"][0]["actions"], [])

        def test_open_invokes_default_instead_of_a_destructive_first_action(self):
            identity = self.notify(actions=["delete", "Delete", "default", "Open"])
            self.assertEqual(self.ipc("open", identity).stdout.strip(), "true")
            self.until(lambda: ("action", identity, "default") in self.signals)
            self.assertNotIn(("action", identity, "delete"), self.signals)
            self.assertFalse(self.state()["entries"][0]["unread"])
            self.assertEqual(self.state()["popups"], [])

        def test_open_without_a_safe_target_never_invokes_arbitrary_actions(self):
            identity = self.notify(actions=["delete", "Delete"], hints={"desktop-entry": "../unsafe.desktop"})
            self.assertEqual(self.ipc("open", identity).stdout.strip(), "false")
            self.assertEqual(self.state()["entries"][0]["actions"][0]["identifier"], "delete")
            self.assertTrue(self.state()["entries"][0]["live"])
            self.assertEqual(self.state()["unread"], 0)
            self.assertEqual(self.state()["popups"], [])

        def test_sound_signal_respects_suppression_and_does_not_repeat_for_replacements(self):
            identity = self.notify("First", hints={"urgency": dbus.Byte(2)})
            self.assertEqual(self.state()["sounds"], [2])
            self.notify("Replacement", replace=identity)
            self.notify("Quiet hint", hints={"suppress-sound": dbus.Boolean(True)})
            self.notify("Quiet integer hint", hints={"suppress-sound": dbus.Int32(1)})
            self.assertEqual(self.state()["sounds"], [2])
            self.ipc("dnd", "true")
            self.notify("DND")
            self.ipc("dnd", "false")
            self.ipc("panel", "true")
            self.notify("Reading")
            self.ipc("panel", "false")
            self.assertEqual(self.state()["sounds"], [2])
            self.notify("New")
            self.assertEqual(self.state()["sounds"], [2, 1])

        def test_open_can_launch_the_exact_installed_desktop_entry(self):
            identity = self.notify(hints={"desktop-entry": "luna-notification-test.desktop"})
            self.until(lambda: self.state()["entries"][0]["appIcon"] == "luna-notification-test-icon")
            self.assertEqual(self.state()["entries"][0]["appIcon"], "luna-notification-test-icon")
            self.assertEqual(self.ipc("open", identity).stdout.strip(), "true")
            self.until(lambda: (self.root / "app-opened").exists())
            self.assertEqual(json.loads((self.root / "app-opened").read_text().splitlines()[-1]), ["--opened"])
            self.assertFalse(self.state()["entries"][0]["live"])

        def test_libnotify_named_image_hints_supply_sender_icons(self):
            for hint, icon in (("image-path", "kitty"), ("image_path", "zen-browser")):
                with self.subTest(hint=hint):
                    self.notify(hints={hint: icon})
                    self.assertEqual(self.state()["entries"][0]["appIcon"], icon)
            self.notify(hints={"image-path": str(self.root / "photo.png")})
            self.assertEqual(self.state()["entries"][0]["appIcon"], "")

        def test_sender_and_desktop_icons_take_priority_over_named_image_hints(self):
            hints = {"image-path": "kitty", "desktop-entry": "luna-notification-test.desktop"}
            self.notify(hints=hints)
            self.until(lambda: self.state()["entries"][0]["appIcon"] == "luna-notification-test-icon")
            self.notify(hints=hints, app_icon="sender-icon")
            self.assertEqual(self.state()["entries"][0]["appIcon"], "sender-icon")

        def test_critical_and_explicit_zero_stay_while_transient_expires(self):
            permanent = self.notify("Permanent", timeout=0)
            critical = self.notify("Critical", timeout=40, hints={"urgency": dbus.Byte(2)})
            transient = self.notify("Transient", timeout=100, hints={"transient": dbus.Boolean(True)})
            self.until(lambda: ("closed", transient, 1) in self.signals)
            state = self.state()
            self.assertEqual([entry["id"] for entry in state["popups"]], [critical, permanent])
            self.assertEqual(len(state["entries"]), 2)

        def test_maximum_three_popups_prioritizes_critical(self):
            critical = self.notify("Critical", hints={"urgency": dbus.Byte(2)})
            others = [self.notify(str(index)) for index in range(5)]
            self.assertEqual([entry["id"] for entry in self.state()["popups"]], [critical, others[-1], others[-2]])

        def test_dnd_and_panel_suppress_without_replaying_backlog(self):
            self.notify("Old")
            self.ipc("dnd", "true")
            self.notify("Quiet")
            transient = self.notify("Transient", hints={"transient": dbus.Boolean(True)})
            self.assertEqual(self.state()["popups"], [])
            self.assertEqual(len(self.state()["entries"]), 2)
            self.until(lambda: ("closed", transient, 1) in self.signals)
            self.ipc("dnd", "false")
            self.assertEqual(self.state()["popups"], [])
            self.ipc("panel", "true")
            self.notify("While reading")
            self.assertEqual(self.state()["unread"], 0)
            self.ipc("panel", "false")
            self.assertEqual(self.state()["popups"], [])
            self.notify("New")
            self.assertEqual(len(self.state()["popups"]), 1)

        def test_dnd_survives_process_restart_without_persisting_message_content(self):
            self.ipc("dnd", "true")
            self.notify("Private message that must not be persisted")
            preferences = self.root / "config/luna/notifications.json"
            self.assertEqual(json.loads(preferences.read_text()), {"dnd": True})
            self.process.terminate()
            self.process.wait(timeout=5)
            type(self).process = subprocess.Popen(["qs", "-p", str(self.root)], env=self.environment,
                                                  stdout=self.log, stderr=subprocess.STDOUT)
            self.until(lambda: self.state()["dnd"] is True)
            self.assertEqual(self.state()["entries"], [])
            self.assertEqual(json.loads(preferences.read_text()), {"dnd": True})
            type(self).service = dbus.Interface(self.bus.get_object("org.freedesktop.Notifications", "/org/freedesktop/Notifications"),
                                                "org.freedesktop.Notifications")
            self.notify("Still quiet")
            self.assertEqual(self.state()["popups"], [])

        def test_replacement_updates_in_place_and_action_label_changes(self):
            identity = self.notify("Before", actions=["open", "Open"])
            replacement = self.notify("After", replace=identity, actions=["open", "New label"])
            self.assertEqual(replacement, identity)
            self.until(lambda: self.state()["entries"][0]["summary"] == "After")
            self.assertEqual(len(self.state()["entries"]), 1)
            self.assertEqual(self.state()["entries"][0]["actions"][0]["text"], "New label")
            self.notify("After", replace=identity, actions=["open", "Label only"])
            self.until(lambda: self.state()["entries"][0]["actions"][0]["text"] == "Label only")

        def test_client_close_dismiss_remove_and_clear(self):
            identity = self.notify(actions=["open", "Open"])
            self.service.CloseNotification(dbus.UInt32(identity))
            self.until(lambda: not self.state()["entries"][0]["live"])
            self.assertEqual(self.state()["popups"], [])
            self.assertEqual(self.state()["entries"][0]["actions"], [])
            second = self.notify("Dismiss me")
            self.ipc("dismiss", second)
            self.assertEqual(len(self.state()["entries"]), 2)
            self.ipc("remove", second)
            self.assertEqual(len(self.state()["entries"]), 1)
            self.ipc("clear")
            self.assertEqual(self.state()["entries"], [])

        def test_hover_pauses_popup_timeout(self):
            identity = self.notify(timeout=180)
            self.ipc("hover", identity, "true")
            time.sleep(0.3)
            self.assertEqual(len(self.state()["popups"]), 1)
            self.ipc("hover", identity, "false")
            self.until(lambda: not self.state()["popups"])

        def test_history_bounded_to_one_hundred(self):
            identities = [self.notify(str(index)) for index in range(105)]
            entries = self.state()["entries"]
            self.assertEqual(len(entries), 100)
            self.assertEqual([entry["id"] for entry in entries], list(reversed(identities[-100:])))

        def test_pending_critical_is_not_expired_by_history_pruning(self):
            critical = self.notify("Critical", timeout=20, hints={"urgency": dbus.Byte(2)})
            for index in range(105):
                self.notify(str(index))
            self.assertEqual(len(self.state()["entries"]), 100)
            self.assertEqual(self.state()["popups"][0]["id"], critical)
            self.assertNotIn(("closed", critical, 1), self.signals)

        def test_reload_keeps_live_history_without_replaying_popups(self):
            identity = self.notify("Before reload")
            self.ipc("reload")
            self.until(lambda: len(self.state()["entries"]) == 1 and not self.state()["popups"])
            self.assertEqual(self.state()["entries"][0]["id"], identity)
            self.assertEqual(self.state()["unread"], 0)

        def test_reload_restores_critical_even_with_a_positive_sender_timeout(self):
            critical = self.notify("Critical", timeout=20, hints={"urgency": dbus.Byte(2)})
            self.notify("Normal", timeout=0)
            self.ipc("reload")
            self.until(lambda: [entry["id"] for entry in self.state()["popups"]] == [critical])
            time.sleep(0.15)
            self.assertEqual([entry["id"] for entry in self.state()["popups"]], [critical])
            self.assertEqual(self.state()["sounds"], [])

        def test_screenshot_open_action_survives_close_and_uses_exact_path(self):
            path = self.root / "image with ' spaces.png"
            path.write_bytes(b"test")
            identity = self.notify("Saved", app="Luna Screenshot", hints={"image-path": str(path)})
            self.assertEqual(self.state()["entries"][0]["image"], str(path))
            self.service.CloseNotification(dbus.UInt32(identity))
            self.until(lambda: not self.state()["entries"][0]["live"])
            self.assertEqual(self.state()["entries"][0]["actions"], [{"identifier": "luna-open-image", "text": "Open image"}])
            self.assertEqual(self.ipc("open", identity).stdout.strip(), "true")
            self.until(lambda: (self.root / "opened").exists())
            self.assertEqual(json.loads((self.root / "opened").read_text().splitlines()[-1]), [str(path)])

        def test_recording_default_open_uses_local_mp4_and_survives_client_close(self):
            path = self.root / "recording with ' spaces.mp4"
            path.write_bytes(b"test")
            opened = self.root / "opened"
            for archived in (False, True):
                with self.subTest(archived=archived):
                    before = len(opened.read_text().splitlines()) if opened.exists() else 0
                    identity = self.notify("Recorded", app="Luna Recording", hints={"x-luna-recording": path.as_uri()})
                    self.assertEqual(self.state()["entries"][0]["recordingFile"], str(path))
                    if archived:
                        self.service.CloseNotification(dbus.UInt32(identity))
                        self.until(lambda: not self.state()["entries"][0]["live"])
                    self.assertEqual(self.state()["entries"][0]["actions"], [{"identifier": "luna-open-recording", "text": "Open recording"}])
                    self.assertEqual(self.ipc("open", identity).stdout.strip(), "true")
                    self.until(lambda: opened.exists() and len(opened.read_text().splitlines()) > before)
                    self.assertEqual(json.loads(opened.read_text().splitlines()[-1]), [str(path)])
                    self.assertFalse(self.state()["entries"][0]["unread"])

        def test_recording_open_rejects_remote_files_and_non_recording_senders(self):
            for app, path in (("Luna Recording", "https://example.test/video.mp4"),
                              ("Luna Recording", "file://host/tmp/video.mp4"),
                              ("Luna Recording", "/tmp/program.desktop"), ("Other", "/tmp/video.mp4")):
                with self.subTest(app=app, path=path):
                    identity = self.notify(app=app, hints={"x-luna-recording": path})
                    self.assertEqual(self.state()["entries"][0]["actions"], [])
                    self.assertEqual(self.ipc("open", identity).stdout.strip(), "false")

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(NativeNotificationTests)
    return unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()


if __name__ == "__main__":
    if "--isolated" in sys.argv:
        sys.exit(0 if native_tests() else 1)
    unittest.main()
