"""Exercise the real PolkitAgent against a private D-Bus authority, without PAM.

Run with python3 -m unittest discover -s __tests__/src/luna-polkit/src/shell
-p test_polkit_backend.py -v. PyGObject may come from the system Python when the
test runner uses a virtual environment.
"""

import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys
import tempfile
import time
import unittest


REPO = Path(__file__).resolve().parents[5]
SHELL = REPO / "src/luna-polkit/src/shell/shell.qml"
QUICKSHELL = shutil.which("quickshell")
DBUS_DAEMON = shutil.which("dbus-daemon")
AUTHORITY_NAME = "org.freedesktop.PolicyKit1"
AUTHORITY_PATH = "/org/freedesktop/PolicyKit1/Authority"
AUTHORITY_INTERFACE = "org.freedesktop.PolicyKit1.Authority"


def system_python():
    for executable in dict.fromkeys((sys.executable, "/usr/bin/python3", "/usr/bin/python")):
        if not Path(executable).is_file():
            continue
        probe = subprocess.run(
            [executable, "-c", "import gi; gi.require_version('Polkit', '1.0'); "
             "from gi.repository import Gio, GLib, Polkit"],
            capture_output=True, timeout=5,
        )
        if probe.returncode == 0:
            return executable
    return None


def run_authority(mode, events_path):
    # Only this subprocess imports GI, so normal discovery also works in a venv.
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib

    def record(event, **fields):
        with Path(events_path).open("a") as output:
            output.write(json.dumps({"event": event, **fields}) + "\n")

    connection = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    introspection = Gio.DBusNodeInfo.new_for_xml("""
        <node>
          <interface name="org.freedesktop.PolicyKit1.Authority">
            <method name="RegisterAuthenticationAgent">
              <arg type="(sa{sv})" direction="in"/>
              <arg type="s" direction="in"/>
              <arg type="s" direction="in"/>
            </method>
            <method name="RegisterAuthenticationAgentWithOptions">
              <arg type="(sa{sv})" direction="in"/>
              <arg type="s" direction="in"/>
              <arg type="s" direction="in"/>
              <arg type="a{sv}" direction="in"/>
            </method>
            <method name="UnregisterAuthenticationAgent">
              <arg type="(sa{sv})" direction="in"/>
              <arg type="s" direction="in"/>
            </method>
            <property name="BackendName" type="s" access="read"/>
            <property name="BackendVersion" type="s" access="read"/>
            <property name="BackendFeatures" type="u" access="read"/>
          </interface>
        </node>
    """)

    def unsupported_finished(bus, result, _data):
        try:
            bus.call_finish(result)
            record("unsupported_completed")
        except GLib.Error as error:
            record("unsupported_cancelled", error=str(error))

    def begin_unsupported(sender, path):
        # Quickshell rejects netgroup identities before creating a PAM session.
        # A nonexistent unix-user would still start the privileged PAM helper.
        identities = [("unix-netgroup", {"name": GLib.Variant("s", "luna-test-netgroup")})]
        parameters = GLib.Variant("(sssa{ss}sa(sa{sv}))", (
            "org.luna.test.unsupported", "Unsupported identity test", "", {},
            "luna-test-cookie", identities,
        ))
        connection.call(
            sender, path, "org.freedesktop.PolicyKit1.AuthenticationAgent",
            "BeginAuthentication", parameters, GLib.VariantType.new("()"),
            Gio.DBusCallFlags.NONE, 3000, None, unsupported_finished, None,
        )
        return GLib.SOURCE_REMOVE

    def method_call(_bus, sender, _path, _interface, method, parameters, invocation):
        values = parameters.unpack()
        if method.startswith("RegisterAuthenticationAgent"):
            subject, _locale, path = values[:3]
            record("registration", subject=subject[0], session=subject[1].get("session-id"),
                   path=path, rejected=mode == "reject")
            if mode == "reject":
                invocation.return_dbus_error(
                    "org.freedesktop.PolicyKit1.Error.Failed", "Test authority rejected registration",
                )
                return
            invocation.return_value(GLib.Variant("()", ()))
            if mode == "unsupported":
                GLib.timeout_add(100, begin_unsupported, sender, path)
        elif method == "UnregisterAuthenticationAgent":
            record("unregistration", path=values[1])
            invocation.return_value(GLib.Variant("()", ()))

    def get_property(_bus, _sender, _path, _interface, name):
        if name == "BackendFeatures":
            return GLib.Variant("u", 0)
        return GLib.Variant("s", "luna-test")

    connection.register_object(AUTHORITY_PATH, introspection.interfaces[0],
                               method_call, get_property, None)
    connection.call_sync(
        "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
        "RequestName", GLib.Variant("(su)", (AUTHORITY_NAME, 4)),
        GLib.VariantType.new("(u)"), Gio.DBusCallFlags.NONE, 3000, None,
    )
    record("ready")
    GLib.MainLoop().run()


@unittest.skipUnless(QUICKSHELL and DBUS_DAEMON, "Quickshell and dbus-daemon required")
class PolkitBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.python = system_python()
        if cls.python is None:
            raise unittest.SkipTest("PyGObject and Polkit introspection are required")
        # Quickshell resolves its login session through libsystemd, independently
        # of D-Bus. XDG_SESSION_ID cannot substitute for this in Quickshell 0.3.2.
        probe = subprocess.run(
            [cls.python, "-c", "import os, gi; gi.require_version('Polkit', '1.0'); "
             "from gi.repository import Polkit; "
             "Polkit.UnixSession.new_for_process_sync(os.getpid(), None)"],
            capture_output=True, timeout=5,
        )
        if probe.returncode:
            raise unittest.SkipTest("The real PolkitAgent requires a logind session")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="luna-polkit-backend-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        runtime = self.root / "runtime"
        runtime.mkdir(mode=0o700)
        self.renderer = self.root / "renderer"
        shutil.copytree(SHELL.parent, self.renderer)
        # The real backend and controller remain intact. Qt's offscreen plugin
        # has no layer-shell surface, so only the compositor window is replaced.
        (self.renderer / "AuthDialog.qml").write_text("""import QtQuick
QtObject {
    property var flow
    property var screen
}
""")
        self.events_path = self.root / "events.jsonl"
        self.shell_log_path = self.root / "shell.log"
        self.env = dict(os.environ, HOME=str(self.root), XDG_RUNTIME_DIR=str(runtime),
                        XDG_CONFIG_HOME=str(self.root / "config"),
                        XDG_DATA_HOME=str(self.root / "data"),
                        XDG_CACHE_HOME=str(self.root / "cache"),
                        QT_QPA_PLATFORM="offscreen", QS_NO_RELOAD_POPUP="1")
        for name in ("LUNA_POLKIT_VALIDATE", "HYPRLAND_INSTANCE_SIGNATURE", "WAYLAND_DISPLAY",
                     "DISPLAY", "QML_IMPORT_PATH", "QML2_IMPORT_PATH"):
            self.env.pop(name, None)

        # No service directories: requests cannot activate any real system daemon.
        bus_config = self.root / "bus.conf"
        bus_config.write_text(f"""<busconfig>
            <type>session</type>
            <listen>unix:tmpdir={self.root}</listen>
            <auth>EXTERNAL</auth>
            <policy context="default">
                <allow own="*"/>
                <allow send_destination="*"/>
                <allow receive_sender="*"/>
            </policy>
        </busconfig>""")
        self.bus = subprocess.Popen(
            [DBUS_DAEMON, "--config-file=" + str(bus_config), "--nofork", "--print-address=1"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.addCleanup(self.stop_process, self.bus)
        self.addCleanup(self.bus.stdout.close)
        self.addCleanup(self.bus.stderr.close)
        self.assertTrue(select.select([self.bus.stdout], [], [], 3)[0], "Private bus failed to start")
        address = self.bus.stdout.readline().strip()
        self.assertTrue(address.startswith("unix:"), "Private bus returned no Unix address")
        self.env.update(DBUS_SYSTEM_BUS_ADDRESS=address, DBUS_SESSION_BUS_ADDRESS=address)

    @staticmethod
    def stop_process(process):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)

    def events(self, name):
        if not self.events_path.exists():
            return []
        return [event for line in self.events_path.read_text().splitlines()
                if (event := json.loads(line))["event"] == name]

    def until(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.025)
        logs = "\n".join(path.read_text() for path in self.root.glob("*.log"))
        self.fail("Polkit backend condition failed:\n" + logs)

    def launch(self, mode="accept"):
        authority_log = (self.root / "authority.log").open("w")
        self.addCleanup(authority_log.close)
        authority = subprocess.Popen(
            [self.python, str(Path(__file__).resolve()), "--authority", mode, str(self.events_path)],
            env=self.env, stdout=authority_log, stderr=subprocess.STDOUT,
        )
        self.addCleanup(self.stop_process, authority)
        self.until(lambda: self.events("ready"))

        shell_log = self.shell_log_path.open("w")
        self.addCleanup(shell_log.close)
        self.shell = subprocess.Popen([QUICKSHELL, "-p", str(self.renderer)], env=self.env,
                                      stdout=shell_log, stderr=subprocess.STDOUT)
        self.addCleanup(self.stop_process, self.shell)
        self.until(lambda: self.events("registration"))
        self.until(lambda: self.ipc("status").returncode == 0)

    def ipc(self, method):
        return subprocess.run([QUICKSHELL, "ipc", "-p", str(self.renderer), "call", "auth", method],
                              env=self.env, capture_output=True, text=True, timeout=3)

    def test_registers_real_agent_and_exposes_auth_ipc(self):
        self.launch()
        event = self.events("registration")[0]
        self.assertEqual(event["subject"], "unix-session")
        self.assertTrue(event["session"])
        self.assertEqual(event["path"], "/org/luna/Polkit")
        self.assertEqual(self.ipc("status").stdout.strip(), "running")
        self.assertEqual(self.ipc("ping").stdout.strip(), "true")
        self.assertEqual(self.ipc("stop").returncode, 0)
        self.assertEqual(self.shell.wait(timeout=4), 0)
        self.until(lambda: self.events("unregistration"))

    def test_unsupported_identity_is_cancelled_without_starting_pam(self):
        self.launch("unsupported")
        self.until(lambda: self.events("unsupported_cancelled"))
        error = self.events("unsupported_cancelled")[0]["error"]
        self.assertIn("org.freedesktop.PolicyKit1.Error.Cancelled", error)
        self.assertIn("no supported identities", error)
        self.assertEqual(self.ipc("status").stdout.strip(), "running")
        self.assertEqual(self.ipc("ping").stdout.strip(), "true")

    def test_registration_failure_reports_unavailable_and_exits(self):
        self.launch("reject")
        self.assertEqual(self.ipc("status").stdout.strip(), "unavailable")
        self.assertEqual(self.ipc("ping").stdout.strip(), "false")
        self.assertNotEqual(self.shell.wait(timeout=20), 0)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--authority":
        run_authority(sys.argv[2], sys.argv[3])
    else:
        unittest.main()
