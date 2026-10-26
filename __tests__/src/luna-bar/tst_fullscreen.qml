import QtQuick
import QtTest
import "../../../src/luna-bar/Fullscreen.js" as Fullscreen

TestCase {
    id: test
    name: "Fullscreen"

    QtObject {
        id: window
        property var lastIpcObject: ({fullscreen: 0, fullscreenClient: 0})
    }
    QtObject {
        id: windows
        property var values: [window]
    }
    QtObject {
        id: workspace
        property bool hasFullscreen: false
        property var toplevels: windows
    }
    QtObject {
        id: monitor
        property var activeWorkspace: workspace
    }
    // Exercise a real QML binding so mode changes must notify even while the
    // workspace flag stays true when switching between maximized and fullscreen.
    readonly property bool hidden: Fullscreen.isActive(monitor)

    function init() {
        monitor.activeWorkspace = workspace;
        windows.values = [window];
        workspace.hasFullscreen = false;
        window.lastIpcObject = {fullscreen: 0, fullscreenClient: 0};
    }

    function test_window_modes_data() {
        return [
            {tag: "tiled", internal: 0, client: 0, hidden: false},
            {tag: "maximized", internal: 1, client: 1, hidden: false},
            {tag: "fullscreen", internal: 2, client: 2, hidden: true},
            {tag: "client-only fullscreen", internal: 0, client: 2, hidden: false},
            {tag: "maximized with fullscreen client", internal: 1, client: 2, hidden: false},
            {tag: "internal-only fullscreen", internal: 2, client: 0, hidden: true},
        ];
    }
    function test_window_modes(data) {
        workspace.hasFullscreen = data.internal !== 0;
        window.lastIpcObject = {fullscreen: data.internal, fullscreenClient: data.client};
        compare(test.hidden, data.hidden);
    }
    function test_maximized_fullscreen_transitions() {
        workspace.hasFullscreen = true;
        for (const mode of [1, 2, 1, 2, 0]) {
            window.lastIpcObject = {fullscreen: mode, fullscreenClient: mode};
            compare(test.hidden, mode === 2);
        }
    }
    function test_workspace_switch_and_other_monitor() {
        workspace.hasFullscreen = true;
        window.lastIpcObject = {fullscreen: 2};
        verify(test.hidden);

        const emptyWorkspace = {hasFullscreen: false, toplevels: {values: []}};
        verify(!Fullscreen.isActive({activeWorkspace: emptyWorkspace}));
        monitor.activeWorkspace = emptyWorkspace;
        verify(!test.hidden);
        monitor.activeWorkspace = workspace;
        verify(test.hidden);
    }
    function test_window_removed_or_moved_away() {
        workspace.hasFullscreen = true;
        window.lastIpcObject = {fullscreen: 2};
        verify(test.hidden);
        windows.values = [];
        verify(!test.hidden);
        windows.values = [window];
        verify(test.hidden);
    }
    function test_workspace_flag_clears_before_client_snapshot() {
        workspace.hasFullscreen = true;
        window.lastIpcObject = {fullscreen: 2};
        verify(test.hidden);
        workspace.hasFullscreen = false;
        verify(!test.hidden);
    }
    function test_missing_monitor_or_workspace() {
        verify(!Fullscreen.isActive(null));
        monitor.activeWorkspace = null;
        verify(!test.hidden);
    }
}
