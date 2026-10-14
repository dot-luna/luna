#!/usr/bin/env python3
"""BlueZ Agent1 bridge: newline JSON prompts out, explicit UI decisions in."""
import argparse
import json
import os
import re
import signal
import sys

import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib


BLUEZ = "org.bluez"
AGENT = "org.bluez.Agent1"
MANAGER = "org.bluez.AgentManager1"
DEVICE = "org.bluez.Device1"
PROPERTIES = "org.freedesktop.DBus.Properties"
# Proxies skip introspection, so method arguments must carry their DBus wire types.
PATH = dbus.ObjectPath("/org/luna/BluetoothAgent")
DEVICE_PATH = re.compile(r"/org/bluez/hci[0-9]+/dev_(?:[0-9a-fA-F]{2}_){5}[0-9a-fA-F]{2}")


class Rejected(dbus.DBusException):
    _dbus_error_name = "org.bluez.Error.Rejected"


class Canceled(dbus.DBusException):
    _dbus_error_name = "org.bluez.Error.Canceled"


class Agent(dbus.service.Object):
    def __init__(self, bus, loop, timeout_ms):
        super().__init__(bus, PATH)
        self.bus = bus
        self.loop = loop
        self.timeout_ms = timeout_ms
        self.owner = ""
        self.registered = False
        self.pending = None
        self.sequence = 0
        self.input_buffer = b""
        self.stopping = False
        bus.add_signal_receiver(self.owner_changed, signal_name="NameOwnerChanged",
                                dbus_interface="org.freedesktop.DBus", bus_name="org.freedesktop.DBus", arg0=BLUEZ)
        bus.add_signal_receiver(self.device_removed, signal_name="InterfacesRemoved",
                                dbus_interface="org.freedesktop.DBus.ObjectManager", bus_name=BLUEZ)
        bus.add_signal_receiver(self.properties_changed, signal_name="PropertiesChanged",
                                dbus_interface=PROPERTIES, bus_name=BLUEZ, path_keyword="path")
        GLib.io_add_watch(sys.stdin.fileno(), GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR, self.read_input)
        try:
            self.owner = str(bus.get_name_owner(BLUEZ))
        except dbus.DBusException:
            pass
        self.register()

    def emit(self, event, **values):
        try:
            print(json.dumps(dict(event=event, **values), ensure_ascii=True), flush=True)
        except BrokenPipeError:
            self.stop()

    def manager(self):
        return dbus.Interface(self.bus.get_object(self.owner, "/org/bluez", introspect=False), MANAGER)

    def register(self):
        if not self.owner or self.stopping:
            self.emit("status", available=False)
            return
        owner = self.owner

        def failed(error):
            if self.owner == owner:
                self.emit("status", available=False,
                          error=f"Bluetooth pairing agent could not register: {error.get_dbus_name()}: {error.get_dbus_message()}")

        def default_ready():
            if self.owner == owner:
                self.emit("status", available=True)

        def registered():
            if self.owner == owner:
                self.registered = True
                self.manager().RequestDefaultAgent(PATH, reply_handler=default_ready, error_handler=failed)

        self.manager().RegisterAgent(PATH, "KeyboardDisplay", reply_handler=registered, error_handler=failed)

    def owner_changed(self, name, old_owner, new_owner):
        self.finish(error=Canceled("Bluetooth service changed."))
        self.owner = str(new_owner)
        self.registered = False
        self.register()

    def authenticate(self, sender):
        # Only the current BlueZ owner may request credentials or dismiss its prompt.
        if not self.owner or sender != self.owner:
            raise Rejected("Only BlueZ may request Bluetooth authorization.")

    def begin(self, sender, device, kind, reply, error, **details):
        self.authenticate(sender)
        if not DEVICE_PATH.fullmatch(str(device)):
            raise Rejected("Unknown Bluetooth device.")
        if self.pending:
            if kind == "display-passkey" and self.pending["prompt"]["kind"] == kind and self.pending["device"] == device:
                self.pending["prompt"].update(details)
                self.emit("request", **self.pending["prompt"])
                reply()
                return
            raise Rejected("Another pairing request is already open.")

        self.sequence += 1
        request = {"id": self.sequence, "kind": kind, **details}
        pending = {"device": device, "prompt": request, "reply": reply, "error": error,
                   "timer": GLib.timeout_add(self.timeout_ms, self.timed_out)}
        self.pending = pending

        def loaded(properties):
            if self.pending is not pending:
                return
            if not properties.get("Address"):
                self.finish(error=Rejected("Unknown Bluetooth device."))
                return
            request["name"] = str(properties.get("Alias") or properties.get("Name") or properties["Address"])
            self.emit("request", **request)
            if kind.startswith("display-"):
                # Display methods acknowledge receipt; they do not authorize pairing.
                pending["reply"] = None
                pending["error"] = None
                reply()

        properties = dbus.Interface(self.bus.get_object(self.owner, device, introspect=False), PROPERTIES)
        properties.GetAll(DEVICE, reply_handler=loaded,
                          error_handler=lambda failure: self.finish(error=Rejected("Bluetooth device is unavailable."))
                          if self.pending is pending else None)

    def finish(self, value=None, error=None):
        pending = self.pending
        if not pending:
            return
        self.pending = None
        if pending["timer"]:
            GLib.source_remove(pending["timer"])
        if error is not None and pending["error"]:
            pending["error"](error)
        elif error is None and pending["reply"]:
            if pending["prompt"]["kind"] in ("pin", "passkey"):
                pending["reply"](value)
            else:
                pending["reply"]()
        self.emit("closed", id=pending["prompt"]["id"])

    def cancel_pairing(self):
        if self.pending and self.owner:
            device = dbus.Interface(self.bus.get_object(self.owner, self.pending["device"], introspect=False), DEVICE)
            device.CancelPairing(reply_handler=lambda: None, error_handler=lambda error: None)

    def timed_out(self):
        if self.pending:
            self.pending["timer"] = None
            self.cancel_pairing()
            self.finish(error=Canceled("Pairing request timed out."))
        return GLib.SOURCE_REMOVE

    def device_removed(self, path, interfaces):
        if self.pending and path == self.pending["device"] and DEVICE in interfaces:
            self.finish(error=Canceled("Bluetooth device disappeared."))

    def properties_changed(self, interface, changed, invalidated, path):
        if self.pending and path == self.pending["device"] and interface == DEVICE:
            if changed.get("Paired") and self.pending["prompt"]["kind"].startswith("display-"):
                self.finish()

    def decision(self, message):
        pending = self.pending
        if not isinstance(message, dict) or not pending or message.get("id") != pending["prompt"]["id"]:
            return
        if message.get("action") == "cancel":
            self.cancel_pairing()
            self.finish(error=Rejected("Pairing was declined."))
            return
        if message.get("action") != "accept" or pending["prompt"]["kind"].startswith("display-"):
            return
        kind = pending["prompt"]["kind"]
        value = message.get("value", "")
        if kind == "pin":
            if not isinstance(value, str) or not 1 <= len(value) <= 16 or any(ord(char) < 32 or ord(char) == 127 for char in value):
                self.emit("validation", id=message["id"], error="Enter a PIN of 1–16 characters.")
                return
        elif kind == "passkey":
            if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,6}", value):
                self.emit("validation", id=message["id"], error="Enter a number with up to six digits.")
                return
            value = dbus.UInt32(int(value))
        self.finish(value=value)

    def read_input(self, source, condition):
        chunk = os.read(source, 4096)
        if not chunk:
            self.stop()
            return GLib.SOURCE_REMOVE
        self.input_buffer += chunk
        if len(self.input_buffer) > 16384:
            self.stop()
            return GLib.SOURCE_REMOVE
        while b"\n" in self.input_buffer:
            line, self.input_buffer = self.input_buffer.split(b"\n", 1)
            try:
                self.decision(json.loads(line))
            except (ValueError, UnicodeDecodeError):
                pass
        return GLib.SOURCE_CONTINUE

    def stop(self):
        if self.stopping:
            return
        self.stopping = True
        self.cancel_pairing()
        self.finish(error=Canceled("Pairing agent closed."))
        if self.registered and self.owner:
            self.manager().UnregisterAgent(PATH, reply_handler=self.loop.quit, error_handler=lambda error: self.loop.quit())
            GLib.timeout_add(500, self.loop.quit)
        else:
            self.loop.quit()

    @dbus.service.method(AGENT, in_signature="", out_signature="", sender_keyword="sender")
    def Release(self, sender):
        self.authenticate(sender)
        self.registered = False
        self.finish(error=Canceled("Pairing agent was released."))
        self.emit("status", available=False)

    @dbus.service.method(AGENT, in_signature="", out_signature="", sender_keyword="sender")
    def Cancel(self, sender):
        self.authenticate(sender)
        self.finish(error=Canceled("Pairing was cancelled."))

    @dbus.service.method(AGENT, in_signature="o", out_signature="s", sender_keyword="sender", async_callbacks=("reply", "error"))
    def RequestPinCode(self, device, reply, error, sender):
        self.begin(sender, device, "pin", reply, error)

    @dbus.service.method(AGENT, in_signature="o", out_signature="u", sender_keyword="sender", async_callbacks=("reply", "error"))
    def RequestPasskey(self, device, reply, error, sender):
        self.begin(sender, device, "passkey", reply, error)

    @dbus.service.method(AGENT, in_signature="ou", out_signature="", sender_keyword="sender", async_callbacks=("reply", "error"))
    def RequestConfirmation(self, device, passkey, reply, error, sender):
        if passkey > 999999:
            raise Rejected("Invalid passkey.")
        self.begin(sender, device, "confirm", reply, error, code=f"{passkey:06d}")

    @dbus.service.method(AGENT, in_signature="o", out_signature="", sender_keyword="sender", async_callbacks=("reply", "error"))
    def RequestAuthorization(self, device, reply, error, sender):
        self.begin(sender, device, "authorize", reply, error)

    @dbus.service.method(AGENT, in_signature="os", out_signature="", sender_keyword="sender", async_callbacks=("reply", "error"))
    def AuthorizeService(self, device, uuid, reply, error, sender):
        if not re.fullmatch(r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}", str(uuid)):
            raise Rejected("Unknown Bluetooth service.")
        self.begin(sender, device, "service", reply, error, uuid=str(uuid).lower())

    @dbus.service.method(AGENT, in_signature="os", out_signature="", sender_keyword="sender", async_callbacks=("reply", "error"))
    def DisplayPinCode(self, device, pincode, reply, error, sender):
        if not re.fullmatch(r"[0-9]{6}", str(pincode)):
            raise Rejected("Invalid display PIN.")
        self.begin(sender, device, "display-pin", reply, error, code=str(pincode))

    @dbus.service.method(AGENT, in_signature="ouq", out_signature="", sender_keyword="sender", async_callbacks=("reply", "error"))
    def DisplayPasskey(self, device, passkey, entered, reply, error, sender):
        if passkey > 999999 or entered > 6:
            raise Rejected("Invalid display passkey.")
        self.begin(sender, device, "display-passkey", reply, error, code=f"{passkey:06d}", entered=int(entered))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", action="store_true", help="Use an isolated session bus for tests.")
    parser.add_argument("--timeout-ms", type=int, default=120000)
    options = parser.parse_args()
    DBusGMainLoop(set_as_default=True)
    loop = GLib.MainLoop()
    bus = dbus.SessionBus() if options.session else dbus.SystemBus()
    agent = Agent(bus, loop, max(100, options.timeout_ms))
    for number in (signal.SIGINT, signal.SIGTERM):
        signal.signal(number, lambda signum, frame: GLib.idle_add(agent.stop))
    loop.run()


if __name__ == "__main__":
    main()
