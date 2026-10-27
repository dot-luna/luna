import QtQuick
import QtQuick.Window
import QtTest
import Luna as Luna

TestCase {
    id: tests
    name: "ScreensaverSurface"
    visible: true
    property var surface
    property var input
    property var failedTests: []

    function init() {
        Luna.ScreensaverSession.readyCount = 0;
        Luna.ScreensaverSession.dismissCount = 0;
        Luna.ScreensaverSession.focusedScreen = "primary";
        surface.monitor = null;
        surface.outputScreen = {name: "primary"};
        surface.visible = true;
        surface.visualClicks = 0;
        surface.requestActivate();
        input = findChild(surface.contentItem, "screensaverWakeInput");
        verify(input !== null);
        input.forceActiveFocus();
        tryCompare(input, "activeFocus", true, 1000);
        wait(10);
        surface.inputReady = true;
        Luna.ScreensaverSession.dismissCount = 0;
    }

    function cleanup() {
        if (qtest_results.failed)
            failedTests = failedTests.concat([qtest_results.functionName]);
    }

    function cleanupTestCase() {
        console.log("LUNA_SCREENSAVER_SURFACE_TEST_RESULT " + JSON.stringify({
            passed: qtest_results.passCount,
            failed: qtest_results.failCount,
            skipped: qtest_results.skipCount,
            failedTests: failedTests
        }));
    }

    function test_ready_requires_visible_window_and_output() {
        surface.reportReady();
        verify(Luna.ScreensaverSession.readyCount > 0);
        Luna.ScreensaverSession.readyCount = 0;
        surface.visible = false;
        surface.reportReady();
        compare(Luna.ScreensaverSession.readyCount, 0);
        surface.outputScreen = null;
        surface.visible = true;
        surface.reportReady();
        compare(Luna.ScreensaverSession.readyCount, 0);
        surface.outputScreen = {name: "primary"};
        surface.reportReady();
        verify(Luna.ScreensaverSession.readyCount > 0);
    }

    function test_keys_dismiss_immediately_during_pointer_grace() {
        surface.windowChanged();
        verify(!surface.inputReady);
        keyClick(Qt.Key_Escape);
        keyClick(Qt.Key_Return);
        compare(Luna.ScreensaverSession.dismissCount, 2);
    }

    function test_escape_enter_space_tab_and_typing_dismiss() {
        const keys = [Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space,
            Qt.Key_Tab, Qt.Key_Left, Qt.Key_A];
        for (let index = 0; index < keys.length; index++) {
            keyClick(keys[index]);
            compare(Luna.ScreensaverSession.dismissCount, index + 1);
        }
    }

    function test_mouse_buttons_dismiss_and_cover_custom_content() {
        const buttons = [Qt.LeftButton, Qt.RightButton, Qt.MiddleButton, Qt.BackButton];
        for (let index = 0; index < buttons.length; index++) {
            Luna.ScreensaverSession.dismissCount = 0;
            mouseClick(input, 100, 100, buttons[index]);
            verify(Luna.ScreensaverSession.dismissCount > 0);
        }
        compare(surface.visualClicks, 0);
    }

    function test_wheel_dismisses() {
        mouseWheel(input, 100, 100, 0, 120);
        verify(Luna.ScreensaverSession.dismissCount > 0);
    }

    function test_pointer_motion_obeys_opening_grace() {
        surface.windowChanged();
        mouseMove(input, 40, 40);
        compare(Luna.ScreensaverSession.dismissCount, 0);
        tryCompare(surface, "inputReady", true, 1000);
        mouseMove(input, 120, 120);
        verify(Luna.ScreensaverSession.dismissCount > 0);
    }

    function test_output_and_visibility_control_rendering() {
        verify(surface.renderingActive);
        surface.monitor = {lastIpcObject: {dpmsStatus: false}};
        verify(!surface.outputActive);
        verify(!surface.renderingActive);
        surface.monitor = {lastIpcObject: {dpmsStatus: true, disabled: true}};
        verify(!surface.renderingActive);
        surface.monitor = {lastIpcObject: {dpmsStatus: true, disabled: false}};
        verify(surface.renderingActive);
        surface.visible = false;
        verify(!surface.renderingActive);
    }

    function test_focused_output_updates_without_recreating_surface() {
        verify(surface.keyboardFocused);
        Luna.ScreensaverSession.focusedScreen = "secondary";
        verify(!surface.keyboardFocused);
        surface.outputScreen = {name: "secondary"};
        verify(surface.keyboardFocused);
    }

    function test_theme_and_custom_settings_are_available_to_content() {
        compare(surface.color, Luna.Theme.background);
        compare(surface.settings.orbit_seconds, 42);
        compare(surface.contentData[0].objectName, "customVisual");
    }
}
