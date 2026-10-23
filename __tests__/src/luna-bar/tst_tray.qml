import QtQuick
import QtTest
import "../../../src/luna-bar/TrayLogic.js" as Tray

TestCase {
    name: "Tray"

    function test_mouse_actions() {
        const item = {onlyMenu: false, hasMenu: true};
        compare(Tray.action(item, "left"), "activate");
        compare(Tray.action(item, "right"), "menu");
        compare(Tray.action(item, "middle"), "secondary");
        compare(Tray.action(item, "unknown"), "");
    }
    function test_menu_only_items_never_receive_primary_activation() {
        const item = {onlyMenu: true, hasMenu: true};
        compare(Tray.action(item, "left"), "menu");
        item.hasMenu = false;
        compare(Tray.action(item, "left"), "");
        compare(Tray.action(item, "right"), "");
    }
    function test_menu_uses_owning_window_and_local_coordinates() {
        const window = {name: "second-monitor-bar"};
        let received;
        const item = {hasMenu: true, display: (parent, x, y) => received = [parent, x, y]};
        verify(Tray.run(item, "menu", window, {x: 325.4, y: 28.8}));
        compare(received[0], window);
        compare(received[1], 325);
        compare(received[2], 29);
    }
    function test_activation_dispatches_once() {
        const calls = [];
        const item = {activate: () => calls.push("primary"), secondaryActivate: () => calls.push("secondary")};
        verify(Tray.run(item, "activate", null, null));
        verify(Tray.run(item, "secondary", null, null));
        compare(calls.join(","), "primary,secondary");
    }
    function test_unavailable_actions_are_safe() {
        verify(!Tray.run(null, "menu", null, null));
        verify(!Tray.run({hasMenu: false}, "menu", null, null));
        verify(!Tray.run({}, "unknown", null, null));
    }
}
