"""Exercise the pairing agent against fake BlueZ on a private session bus only."""
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
HELPER = REPO / "src/luna-bar/bluetooth/agent.py"


class BluetoothAgentIsolationTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("dbus-run-session") and importlib.util.find_spec("dbus")
                         and importlib.util.find_spec("gi"), "DBus, python-dbus and PyGObject required")
    def test_agent_on_private_bus(self):
        environment = dict(os.environ, LUNA_PARENT_DBUS_ADDRESS=os.environ.get("DBUS_SESSION_BUS_ADDRESS", ""))
        result = subprocess.run(["dbus-run-session", "--", sys.executable, __file__, "--isolated"],
                                env=environment, capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(shutil.which("qs") and shutil.which("dbus-run-session"), "Quickshell and DBus required")
    def test_pairing_content_loads_offscreen_without_starting_an_agent(self):
        with tempfile.TemporaryDirectory(prefix="luna-pairing-ui-") as directory:
            root = Path(directory)
            (root / "bluetooth").symlink_to(REPO / "src/luna-bar/bluetooth", target_is_directory=True)
            (root / "components").symlink_to(REPO / "src/luna-bar/components", target_is_directory=True)
            (root / "shell.qml").write_text('''import QtQuick
import Quickshell
import "bluetooth"
ShellRoot {
    Window {
        visible: true
        width: 450
        height: 500
        PairingContent { id: card; anchors.centerIn: parent }
    }
    property int index: 0
    property var kinds: ["pin", "passkey", "confirm", "display-pin", "display-passkey", "authorize", "service"]
    Timer {
        interval: 40
        running: true
        repeat: true
        onTriggered: {
            if (index === kinds.length) {
                card.request = null;
                Qt.quit();
                return;
            }
            card.request = {id: index + 1, kind: kinds[index], name: "Test <Keyboard>", code: "000123", entered: 3,
                uuid: "00001124-0000-1000-8000-00805f9b34fb"};
            index++;
        }
    }
}
''')
            colors = {key: "#a0a0a0" for key in ("accent", "accent_foreground", "background", "selection_foreground",
                                                "bright_foreground", "foreground", "lighter_background", "muted", "selection", "error")}
            theme = {"colors": colors, "fonts": {"ui": "Sans Serif", "mono": "Monospace"},
                     "hyprland": {"general": {"border_size": 1, "gaps_out": 8}, "decoration": {"rounding": 10}}}
            runtime = root / "runtime"
            runtime.mkdir(mode=0o700)
            environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", QML_IMPORT_PATH=str(REPO / "src/qml"),
                               LUNA_UI_THEME=json.dumps(theme), XDG_RUNTIME_DIR=str(runtime),
                               DBUS_SYSTEM_BUS_ADDRESS="unix:path=/nonexistent-luna-test-system-bus")
            environment.pop("WAYLAND_DISPLAY", None)
            result = subprocess.run(["dbus-run-session", "--", "qs", "-p", str(root)], env=environment,
                                    capture_output=True, text=True, timeout=10)
            output = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, output)
            for failure in ("ERROR", "TypeError", "ReferenceError", "Unable to assign", "Binding loop", "Bluetooth pairing:"):
                self.assertNotIn(failure, output)


def native_tests():
    import dbus
    import dbus.service
    from dbus.mainloop.glib import DBusGMainLoop
    from gi.repository import GLib

    address = os.environ.get("DBUS_SESSION_BUS_ADDRESS", "")
    assert address and address != os.environ.get("LUNA_PARENT_DBUS_ADDRESS"), "Private DBus required"
    DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    name = dbus.service.BusName("org.bluez", bus)
    device_path = dbus.ObjectPath("/org/bluez/hci0/dev_01_02_03_04_05_06")
    agent_path = "/org/luna/BluetoothAgent"
    agent_interface = "org.bluez.Agent1"

    class Manager(dbus.service.Object):
        def __init__(self):
            super().__init__(bus, "/org/bluez")
            self.sender = ""
            self.capability = ""
            self.default = False

        @dbus.service.method("org.bluez.AgentManager1", in_signature="os", out_signature="", sender_keyword="sender", message_keyword="message")
        def RegisterAgent(self, path, capability, sender, message):
            assert message.get_signature() == "os", "BlueZ requires an object path, not a string"
            self.sender = str(sender)
            self.capability = str(capability)

        @dbus.service.method("org.bluez.AgentManager1", in_signature="o", out_signature="", message_keyword="message")
        def RequestDefaultAgent(self, path, message):
            assert message.get_signature() == "o", "BlueZ requires an object path, not a string"
            self.default = True

        @dbus.service.method("org.bluez.AgentManager1", in_signature="o", out_signature="", message_keyword="message")
        def UnregisterAgent(self, path, message):
            assert message.get_signature() == "o", "BlueZ requires an object path, not a string"
            self.sender = ""
            self.default = False

        @dbus.service.signal("org.freedesktop.DBus.ObjectManager", signature="oas")
        def InterfacesRemoved(self, path, interfaces):
            pass

    class Device(dbus.service.Object):
        def __init__(self):
            super().__init__(bus, device_path)
            self.cancelled = 0

        @dbus.service.method("org.freedesktop.DBus.Properties", in_signature="s", out_signature="a{sv}")
        def GetAll(self, interface):
            return {"Alias": "Test <Keyboard>", "Address": "01:02:03:04:05:06", "Paired": False}

        @dbus.service.method("org.bluez.Device1", in_signature="", out_signature="")
        def CancelPairing(self):
            self.cancelled += 1

        @dbus.service.signal("org.freedesktop.DBus.Properties", signature="sa{sv}as")
        def PropertiesChanged(self, interface, changed, invalidated):
            pass

    manager = Manager()
    device = Device()

    class NativeAgentTests(unittest.TestCase):
        def setUp(self):
            self.events = []
            self.output = b""
            self.log = tempfile.TemporaryFile(mode="w+")
            self.process = subprocess.Popen([sys.executable, "-u", str(HELPER), "--session", "--timeout-ms", "1000"],
                                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log)
            os.set_blocking(self.process.stdout.fileno(), False)
            self.until(lambda: any(event.get("available") for event in self.events))
            self.assertEqual(manager.capability, "KeyboardDisplay")
            self.assertTrue(manager.default)

        def tearDown(self):
            self.process.terminate()
            self.until(lambda: self.process.poll() is not None)
            self.process.stdin.close()
            self.process.stdout.close()
            self.log.seek(0)
            errors = self.log.read()
            self.log.close()
            self.assertNotIn("Traceback", errors)

        def pump(self):
            while GLib.MainContext.default().iteration(False):
                pass
            try:
                chunk = os.read(self.process.stdout.fileno(), 65536)
            except BlockingIOError:
                chunk = b""
            self.output += chunk
            while b"\n" in self.output:
                line, self.output = self.output.split(b"\n", 1)
                self.events.append(json.loads(line))

        def until(self, condition, timeout=3):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                self.pump()
                if condition():
                    return
                time.sleep(0.005)
            self.log.seek(0)
            self.fail("Agent condition timed out: " + repr(self.events) + "\n" + self.log.read())

        def call(self, method, *args, connection=None):
            response = {"done": False}
            interface = dbus.Interface((connection or bus).get_object(manager.sender, agent_path, introspect=False), agent_interface)

            def success(*values):
                response.update(done=True, values=values)

            def failure(error):
                response.update(done=True, error=error.get_dbus_name())

            getattr(interface, method)(*args, reply_handler=success, error_handler=failure)
            return response

        def request(self, method, *args):
            before = len(self.events)
            response = self.call(method, device_path, *args)
            self.until(lambda: any(event["event"] == "request" for event in self.events[before:]))
            prompt = [event for event in self.events[before:] if event["event"] == "request"][-1]
            self.assertEqual(prompt["name"], "Test <Keyboard>")
            return response, prompt

        def decide(self, prompt, action, value=""):
            self.process.stdin.write((json.dumps({"id": prompt["id"], "action": action, "value": value}) + "\n").encode())
            self.process.stdin.flush()

        def test_pin_requires_explicit_valid_response(self):
            response, prompt = self.request("RequestPinCode")
            self.assertFalse(response["done"])
            self.decide(prompt, "accept", "")
            self.until(lambda: any(event["event"] == "validation" for event in self.events))
            self.assertFalse(response["done"])
            self.decide(prompt, "accept", "Ab12")
            self.until(lambda: response["done"])
            self.assertEqual(response["values"], ("Ab12",))

        def test_numeric_passkey_preserves_leading_zero_value(self):
            response, prompt = self.request("RequestPasskey")
            self.decide(prompt, "accept", "12ab")
            self.until(lambda: any(event["event"] == "validation" for event in self.events))
            self.assertFalse(response["done"])
            self.decide(prompt, "accept", "000123")
            self.until(lambda: response["done"])
            self.assertEqual(response["values"], (123,))

        def test_confirmation_and_authorizations_are_never_automatic(self):
            requests = [("RequestConfirmation", (dbus.UInt32(123),)), ("RequestAuthorization", ()),
                        ("AuthorizeService", ("00001124-0000-1000-8000-00805f9b34fb",))]
            for method, arguments in requests:
                with self.subTest(method=method):
                    response, prompt = self.request(method, *arguments)
                    self.assertFalse(response["done"])
                    if method == "RequestConfirmation":
                        self.assertEqual(prompt["code"], "000123")
                    self.decide(prompt, "accept")
                    self.until(lambda: response["done"])
                    self.assertEqual(response["values"], ())

        def test_cancel_rejects_and_requests_pairing_cancellation(self):
            before = device.cancelled
            response, prompt = self.request("RequestConfirmation", dbus.UInt32(123456))
            self.decide(prompt, "cancel")
            self.until(lambda: response["done"] and device.cancelled > before)
            self.assertEqual(response["error"], "org.bluez.Error.Rejected")

        def test_bluez_cancel_closes_pending_request(self):
            response, prompt = self.request("RequestPinCode")
            cancel = self.call("Cancel")
            self.until(lambda: cancel["done"] and response["done"])
            self.assertEqual(response["error"], "org.bluez.Error.Canceled")
            self.assertIn({"event": "closed", "id": prompt["id"]}, self.events)

        def test_display_progress_is_acknowledged_but_not_user_approved(self):
            response, prompt = self.request("DisplayPasskey", dbus.UInt32(42), dbus.UInt16(1))
            self.until(lambda: response["done"])
            self.assertEqual(prompt["code"], "000042")
            self.assertEqual(prompt["entered"], 1)
            update, latest = self.request("DisplayPasskey", dbus.UInt32(42), dbus.UInt16(4))
            self.until(lambda: update["done"])
            self.assertEqual(latest["id"], prompt["id"])
            self.assertEqual(latest["entered"], 4)
            self.decide(prompt, "accept")
            device.PropertiesChanged("org.bluez.Device1", {"Paired": True}, [])
            self.until(lambda: {"event": "closed", "id": prompt["id"]} in self.events)

        def test_display_pin_can_be_cancelled(self):
            response, prompt = self.request("DisplayPinCode", "001234")
            self.until(lambda: response["done"])
            before = device.cancelled
            self.decide(prompt, "cancel")
            self.until(lambda: device.cancelled > before)
            self.assertIn({"event": "closed", "id": prompt["id"]}, self.events)

        def test_disappearing_device_cancels(self):
            response, prompt = self.request("RequestAuthorization")
            manager.InterfacesRemoved(device_path, ["org.bluez.Device1"])
            self.until(lambda: response["done"])
            self.assertEqual(response["error"], "org.bluez.Error.Canceled")

        def test_timeout_cancels_without_authorization(self):
            response, prompt = self.request("RequestAuthorization")
            self.until(lambda: response["done"])
            self.assertEqual(response["error"], "org.bluez.Error.Canceled")

        def test_foreign_sender_cannot_request_or_cancel(self):
            response, prompt = self.request("RequestPinCode")
            foreign = dbus.bus.BusConnection(address)
            spoof = dbus.lowlevel.SignalMessage("/org/freedesktop/DBus", "org.freedesktop.DBus", "NameOwnerChanged")
            spoof.append("org.bluez", bus.get_unique_name(), foreign.get_unique_name(), signature="sss")
            foreign.send_message(spoof)
            for method, args in (("RequestPinCode", (device_path,)), ("Cancel", ())):
                result = self.call(method, *args, connection=foreign)
                self.until(lambda: result["done"])
                self.assertEqual(result["error"], "org.bluez.Error.Rejected")
            self.assertFalse(response["done"])
            foreign.close()
            self.decide(prompt, "cancel")

        def test_bluez_restart_cancels_and_registers_again(self):
            response, prompt = self.request("RequestPinCode")
            before = len(self.events)
            bus.release_name("org.bluez")
            try:
                self.until(lambda: response["done"] and any(event.get("available") is False for event in self.events[before:]))
                self.assertEqual(response["error"], "org.bluez.Error.Canceled")
            finally:
                bus.request_name("org.bluez")
            self.until(lambda: any(event.get("available") is True for event in self.events[before:]))
            response, prompt = self.request("RequestAuthorization")
            self.decide(prompt, "cancel")
            self.until(lambda: response["done"])

        def test_unknown_devices_services_and_methods_are_rejected(self):
            requests = [("RequestPinCode", (dbus.ObjectPath("/unknown"),)),
                        ("RequestPinCode", (dbus.ObjectPath("/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF"),)),
                        ("AuthorizeService", (device_path, "unknown")),
                        ("RequestConfirmation", (device_path, dbus.UInt32(1000000))),
                        ("UnknownMethod", ())]
            for method, arguments in requests:
                result = self.call(method, *arguments)
                self.until(lambda: result["done"])
                self.assertIn("error", result)
            self.assertFalse(any(event["event"] == "request" for event in self.events))

        def test_concurrent_requests_and_stale_decisions_do_not_replace_prompt(self):
            response, prompt = self.request("RequestPinCode")
            other = self.call("RequestAuthorization", device_path)
            self.until(lambda: other["done"])
            self.assertEqual(other["error"], "org.bluez.Error.Rejected")
            self.decide({"id": prompt["id"] + 1}, "accept", "stale")
            self.decide(prompt, "cancel")
            self.until(lambda: response["done"])
            self.assertEqual(response["error"], "org.bluez.Error.Rejected")

        def test_release_and_parent_exit_cancel_requests(self):
            response, prompt = self.request("RequestPinCode")
            release = self.call("Release")
            self.until(lambda: response["done"] and release["done"])
            self.assertEqual(response["error"], "org.bluez.Error.Canceled")
            response, prompt = self.request("RequestPinCode")
            self.process.stdin.close()
            self.until(lambda: response["done"] and self.process.poll() is not None)
            self.assertEqual(response["error"], "org.bluez.Error.Canceled")

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(NativeAgentTests)
    return unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()


if __name__ == "__main__":
    if "--isolated" in sys.argv:
        sys.exit(0 if native_tests() else 1)
    unittest.main()
