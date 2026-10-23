import QtQuick
import QtTest
import "../../../src/launcher/System.js" as System

TestCase {
    name: "MenuSystem"

    // Check routing only: never execute session or power commands in tests.
    function test_lock_uses_checkout_cli() {
        compare(System.command("lock", "/checkout/bin/luna"), ["/checkout/bin/luna", "lock"]);
        compare(System.command("screensaver", "/luna"), ["/luna", "screensaver"]);
    }

    function test_sleep_uses_lock_aware_cli() {
        compare(System.command("suspend", "/luna"), ["/luna", "suspend"]);
        compare(System.command("hibernate", "/luna"), ["/luna", "hibernate"]);
    }

    function test_logout_targets_compositor() {
        compare(System.command("logout"), ["hyprctl", "eval", "hl.dispatch(hl.dsp.exit())"]);
    }

    function test_power_requests_do_not_force_or_bypass_inhibitors() {
        compare(System.command("reboot"), ["systemctl", "reboot"]);
        compare(System.command("shutdown"), ["systemctl", "poweroff"]);
    }

    function test_placeholders_and_unknown_actions_do_nothing() {
        for (const action of ["lock", "suspend", "hibernate", "screensaver", "", "reboot --force"])
            compare(System.command(action), []);
    }
}
