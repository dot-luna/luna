pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Hyprland
import Luna as Luna
import "Search.js" as Search

ShellRoot {
    id: shell

    readonly property var matches: Search.find(DesktopEntries.applications.values, search.text)

    function launch(entry) {
        if (!entry || !entry.command.length)
            return;
        // Quickshell's execute() currently ignores Terminal=true; wrap those entries.
        if (entry.runInTerminal) {
            Quickshell.execDetached({
                command: ["kitty", "--"].concat(entry.command),
                workingDirectory: entry.workingDirectory
            });
        } else {
            entry.execute();
        }
        panel.visible = false;
    }
    function moveSelection(direction) {
        if (!matches.length)
            return;
        results.currentIndex = (results.currentIndex + direction + matches.length) % matches.length;
        results.positionViewAtIndex(results.currentIndex, ListView.Contain);
    }
    function open() {
        const monitor = Hyprland.focusedMonitor;
        panel.screen = Quickshell.screens.find(screen => monitor && screen.name === monitor.name) || Quickshell.screens[0];
        search.text = "";
        results.currentIndex = matches.length ? 0 : -1;
        panel.visible = true;
        focusDelay.restart();
    }

    onMatchesChanged: {
        results.currentIndex = matches.length ? 0 : -1;
        results.positionViewAtBeginning();
    }

    IpcHandler {
        function open(): void {
            shell.open();
        }
        function ping(): string {
            return "ready";
        }
        function stop(): void {
            Qt.quit();
        }
        function toggle(): void {
            if (panel.visible)
                panel.visible = false;
            else
                shell.open();
        }

        target: "launcher"
    }
    PanelWindow {
        id: panel

        WlrLayershell.keyboardFocus: visible ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.namespace: "luna-launcher"
        color: "transparent"
        exclusionMode: ExclusionMode.Ignore
        visible: false

        anchors {
            bottom: true
            left: true
            right: true
            top: true
        }
        Timer {
            id: focusDelay

            interval: 50

            onTriggered: search.forceActiveFocus(Qt.TabFocusReason)
        }
        Shortcut {
            enabled: panel.visible
            sequence: "Escape"

            onActivated: panel.visible = false
        }
        MouseArea {
            anchors.fill: parent

            onClicked: panel.visible = false
        }
        Rectangle {
            id: card

            anchors.centerIn: parent
            border.color: Luna.Theme.muted
            border.width: Luna.Theme.borderWidth
            color: Luna.Theme.background
            height: body.implicitHeight + 24
            radius: Math.min(Luna.Theme.barRounding, width / 2, height / 2)
            width: Math.min(520, panel.width - 2 * Math.max(12, Luna.Theme.outerGap))

            MouseArea {
                anchors.fill: parent
            }
            ColumnLayout {
                id: body

                anchors.left: parent.left
                anchors.margins: 12
                anchors.right: parent.right
                anchors.top: parent.top
                spacing: 8

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 12

                    Luna.Icon {
                        implicitHeight: 18
                        implicitWidth: 18
                        ink: Luna.Theme.foreground
                        name: "search"
                    }
                    TextField {
                        id: search

                        Accessible.description: shell.matches[results.currentIndex] ? shell.matches[results.currentIndex].name : "No matching applications"
                        Accessible.name: "Search applications"
                        Layout.fillWidth: true
                        color: Luna.Theme.brightForeground
                        font.family: Luna.Theme.uiFont
                        font.pixelSize: 16
                        implicitHeight: 40
                        placeholderText: "Search applications"
                        placeholderTextColor: Luna.Theme.foreground
                        selectByMouse: true
                        selectedTextColor: Luna.Theme.accentForeground
                        selectionColor: Luna.Theme.accent

                        background: Rectangle {
                            color: "transparent"
                        }

                        Keys.onBacktabPressed: shell.moveSelection(-1)
                        Keys.onDownPressed: shell.moveSelection(1)
                        Keys.onEnterPressed: shell.launch(shell.matches[results.currentIndex])
                        Keys.onReturnPressed: shell.launch(shell.matches[results.currentIndex])
                        Keys.onTabPressed: shell.moveSelection(1)
                        Keys.onUpPressed: shell.moveSelection(-1)
                    }
                }
                Rectangle {
                    Layout.fillWidth: true
                    color: Luna.Theme.muted
                    implicitHeight: 1
                }
                ListView {
                    id: results

                    Accessible.name: "Applications"
                    Accessible.role: Accessible.List
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.min(398, Math.max(64, panel.height - 140), Math.max(64, count * 50 - 2))
                    boundsBehavior: Flickable.StopAtBounds
                    clip: true
                    currentIndex: -1
                    model: shell.matches
                    spacing: 2

                    ScrollBar.vertical: ScrollBar {
                        id: scrollbar

                        policy: ScrollBar.AsNeeded
                        implicitWidth: 3
                        contentItem: Rectangle {
                            color: scrollbar.pressed ? Luna.Theme.accent : Luna.Theme.muted
                            radius: Math.min(Luna.Theme.barRounding, width / 2)
                            implicitWidth: 3
                            opacity: scrollbar.size < 1 ? 1 : 0
                        }
                        background: Item {}
                    }
                    delegate: Button {
                        id: result

                        required property int index
                        required property var modelData

                        Accessible.name: modelData.name
                        Accessible.role: Accessible.ListItem
                        focusPolicy: Qt.NoFocus
                        height: 48
                        width: results.width - (scrollbar.size < 1 ? 9 : 0)
                        padding: 10
                        hoverEnabled: true
                        readonly property bool selected: results.currentIndex === index

                        background: Rectangle {
                            color: result.selected ? Luna.Theme.selection : "transparent"
                            radius: Math.min(Luna.Theme.barRounding, width / 2, height / 2)
                        }
                        contentItem: RowLayout {
                            spacing: 12

                            Image {
                                id: appIcon

                                Layout.preferredHeight: 28
                                Layout.preferredWidth: 28
                                fillMode: Image.PreserveAspectFit
                                source: result.modelData.icon.startsWith("/") ? "file://" + result.modelData.icon.split("/").map(encodeURIComponent).join("/") : Quickshell.iconPath(result.modelData.icon, true)
                                sourceSize: Qt.size(28, 28)

                                Luna.Icon {
                                    anchors.centerIn: parent
                                    height: 22
                                    ink: result.selected ? Luna.Theme.selectionForeground : Luna.Theme.foreground
                                    name: "monitor"
                                    visible: appIcon.status !== Image.Ready
                                    width: 22
                                }
                            }
                            Label {
                                Layout.fillWidth: true
                                color: result.selected ? Luna.Theme.selectionForeground : Luna.Theme.brightForeground
                                elide: Text.ElideRight
                                font.family: Luna.Theme.uiFont
                                font.pixelSize: 14
                                text: result.modelData.name
                                textFormat: Text.PlainText
                            }
                        }

                        onClicked: shell.launch(modelData)
                        onHoveredChanged: {
                            if (hovered)
                                results.currentIndex = index;
                        }
                    }

                    Label {
                        anchors.centerIn: parent
                        color: Luna.Theme.foreground
                        font.family: Luna.Theme.uiFont
                        font.pixelSize: 13
                        text: search.text.trim() ? "No matching applications" : "No applications found"
                        visible: results.count === 0
                    }
                }

            }
        }
    }
}
