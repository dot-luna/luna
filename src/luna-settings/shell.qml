pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Window
import Quickshell
import Quickshell.Io
import Luna 1.0 as Luna

ShellRoot {
    id: shell

    property int page: 0
    readonly property var currentPage: settingsPages.get(page)

    // Keep navigation and page headings together while each section is a placeholder.
    ListModel {
        id: settingsPages

        ListElement {
            group: "Desktop"
            title: "Appearance"
            description: "Themes, colors, fonts, icons, and cursor."
            symbol: "palette"
        }
        ListElement {
            group: "Desktop"
            title: "Wallpaper"
            description: "Background images and how they fit your displays."
            symbol: "sun"
        }
        ListElement {
            group: "Desktop"
            title: "Desktop"
            description: "Your bar, launcher, and desktop behavior."
            symbol: "layout-grid"
        }
        ListElement {
            group: "Desktop"
            title: "Windows"
            description: "Window appearance, tiling, and workspaces."
            symbol: "grid-2x2"
        }
        ListElement {
            group: "Desktop"
            title: "Notifications"
            description: "Alerts, Do Not Disturb, and app preferences."
            symbol: "bell"
        }
        ListElement {
            group: "Devices"
            title: "Displays"
            description: "Monitor arrangement, resolution, and scaling."
            symbol: "monitor"
        }
        ListElement {
            group: "Devices"
            title: "Sound"
            description: "Speakers, microphones, and volume."
            symbol: "volume-2"
        }
        ListElement {
            group: "Devices"
            title: "Connectivity"
            description: "Wi-Fi, wired networks, and Bluetooth devices."
            symbol: "wifi"
        }
        ListElement {
            group: "Devices"
            title: "Keyboard & Mouse"
            description: "Typing, shortcuts, mouse, and touchpad preferences."
            symbol: "type"
        }
        ListElement {
            group: "System"
            title: "Power & Lock"
            description: "Power profiles, idle behavior, and screen locking."
            symbol: "power"
        }
        ListElement {
            group: "System"
            title: "Applications"
            description: "Default apps and what opens at startup."
            symbol: "layout-grid"
        }
        ListElement {
            group: "System"
            title: "System"
            description: "About Luna, updates, and system information."
            symbol: "info"
        }
    }

    function selectPage(index) {
        page = (index + settingsPages.count) % settingsPages.count;
        navigation.positionViewAtIndex(page, ListView.Contain);
        navigation.forceActiveFocus(Qt.ShortcutFocusReason);
    }

    IpcHandler {
        target: "settings"

        function open(): void {
            window.visible = true;
            window.contentItem.Window.window.requestActivate();
        }

        function applyFonts(value: string): void {
            Luna.Theme.applyFonts(JSON.parse(value));
        }

        function ping(): string {
            return "ready";
        }

        function stop(): void {
            Qt.quit();
        }
    }

    FloatingWindow {
        id: window

        title: "Luna Settings"
        visible: true
        implicitWidth: 1000
        implicitHeight: 760
        minimumSize: Qt.size(760, 540)
        color: Luna.Theme.background
        onClosed: Qt.quit()
        Component.onCompleted: navigation.forceActiveFocus(Qt.TabFocusReason)

        Shortcut {
            sequence: "Ctrl+Q"
            onActivated: Qt.quit()
        }

        Shortcut {
            sequence: "Ctrl+L"
            onActivated: shell.selectPage(shell.page)
        }

        Shortcut {
            sequence: "Ctrl+Tab"
            onActivated: shell.selectPage(shell.page + 1)
        }

        Shortcut {
            sequence: "Ctrl+Shift+Tab"
            onActivated: shell.selectPage(shell.page - 1)
        }

        // The current sidebar item is one tab stop; arrow keys move between pages.
        Control {
            anchors.fill: parent
            padding: 0
            font.family: Luna.Theme.uiFont
            font.pixelSize: 14

            palette {
                window: Luna.Theme.background
                windowText: Luna.Theme.foreground
                text: Luna.Theme.foreground
                buttonText: Luna.Theme.foreground
                highlight: Luna.Theme.accent
                highlightedText: Luna.Theme.accentForeground
            }

            contentItem: RowLayout {
                spacing: 0

                Rectangle {
                    Layout.preferredWidth: 248
                    Layout.fillHeight: true
                    color: Luna.Theme.lighterBackground

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 0

                        RowLayout {
                            Layout.fillWidth: true
                            Layout.margins: 24
                            spacing: 12

                            Luna.Icon {
                                name: "sliders-horizontal"
                                ink: Luna.Theme.accent
                                implicitWidth: 20
                                implicitHeight: 20
                            }

                            Label {
                                text: "Luna Settings"
                                font.bold: true
                                font.pixelSize: 17
                                color: Luna.Theme.brightForeground
                            }
                        }

                        ListView {
                            id: navigation

                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Layout.leftMargin: 12
                            Layout.rightMargin: 12
                            Layout.bottomMargin: 12
                            clip: true
                            spacing: 4
                            model: settingsPages
                            currentIndex: shell.page
                            activeFocusOnTab: true
                            keyNavigationEnabled: false
                            boundsBehavior: Flickable.StopAtBounds
                            Accessible.name: "Settings categories"
                            KeyNavigation.tab: pageContent
                            KeyNavigation.backtab: closeButton
                            Keys.onUpPressed: shell.selectPage(shell.page - 1)
                            Keys.onDownPressed: shell.selectPage(shell.page + 1)
                            Keys.onPressed: event => {
                                if (event.key === Qt.Key_Home || event.key === Qt.Key_End) {
                                    shell.selectPage(event.key === Qt.Key_Home ? 0 : settingsPages.count - 1);
                                    event.accepted = true;
                                }
                            }
                            Keys.onRightPressed: pageContent.forceActiveFocus(Qt.TabFocusReason)
                            Keys.onReturnPressed: pageContent.forceActiveFocus(Qt.TabFocusReason)
                            Keys.onEnterPressed: pageContent.forceActiveFocus(Qt.TabFocusReason)

                            ScrollBar.vertical: ScrollBar {
                                policy: ScrollBar.AsNeeded
                            }

                            section.property: "group"
                            section.criteria: ViewSection.FullString
                            section.delegate: Item {
                                required property string section

                                width: navigation.width
                                height: section === "Desktop" ? 30 : 42

                                Label {
                                    anchors.left: parent.left
                                    anchors.leftMargin: 12
                                    anchors.bottom: parent.bottom
                                    anchors.bottomMargin: 8
                                    text: parent.section
                                    font.pixelSize: 12
                                    font.bold: true
                                    color: Luna.Theme.foreground
                                    opacity: 0.65
                                }
                            }

                            delegate: ItemDelegate {
                                id: navigationButton

                                required property int index
                                required property string title
                                required property string symbol

                                width: navigation.width
                                height: 44
                                leftPadding: 14
                                rightPadding: 12
                                text: title
                                focusPolicy: Qt.NoFocus
                                highlighted: shell.page === index
                                Accessible.name: title + " settings"
                                Accessible.role: Accessible.PageTab
                                Accessible.selected: highlighted
                                onClicked: shell.selectPage(index)

                                background: Rectangle {
                                    radius: Math.min(Luna.Theme.barRounding, height / 2)
                                    color: navigationButton.highlighted || navigationButton.hovered ? Luna.Theme.selection : "transparent"
                                    border.width: navigationButton.highlighted && navigation.activeFocus ? 1 : 0
                                    border.color: Luna.Theme.accent
                                }

                                contentItem: RowLayout {
                                    spacing: 12

                                    Luna.Icon {
                                        name: navigationButton.symbol
                                        ink: navigationLabel.color
                                        implicitWidth: 18
                                        implicitHeight: 18
                                    }

                                    Label {
                                        id: navigationLabel

                                        Layout.fillWidth: true
                                        text: navigationButton.title
                                        elide: Text.ElideRight
                                        font.bold: navigationButton.highlighted
                                        color: navigationButton.highlighted || navigationButton.hovered ? Luna.Theme.selectionForeground : Luna.Theme.foreground
                                    }
                                }
                            }
                        }
                    }
                }

                Rectangle {
                    Layout.fillHeight: true
                    implicitWidth: 1
                    color: Luna.Theme.muted
                    opacity: 0.35
                }

                Item {
                    id: pageContent

                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    activeFocusOnTab: true
                    Accessible.role: Accessible.Pane
                    Accessible.name: shell.currentPage.title + ". " + shell.currentPage.description + " Coming soon."
                    KeyNavigation.tab: closeButton
                    KeyNavigation.backtab: navigation
                    Keys.onLeftPressed: shell.selectPage(shell.page)

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 32
                        spacing: 12

                        RowLayout {
                            Layout.fillWidth: true

                            Label {
                                Layout.fillWidth: true
                                text: shell.currentPage.group
                                font.pixelSize: 12
                                color: Luna.Theme.foreground
                                opacity: 0.65
                            }

                            Button {
                                id: closeButton

                                implicitWidth: 32
                                implicitHeight: 32
                                padding: 8
                                Accessible.name: "Close settings"
                                KeyNavigation.tab: navigation
                                KeyNavigation.backtab: pageContent
                                onClicked: Qt.quit()

                                contentItem: Luna.Icon {
                                    name: "x"
                                    ink: Luna.Theme.foreground
                                }

                                background: Rectangle {
                                    radius: Math.min(Luna.Theme.barRounding, height / 2)
                                    color: closeButton.hovered ? Luna.Theme.selection : "transparent"
                                    border.width: closeButton.visualFocus ? 1 : 0
                                    border.color: Luna.Theme.accent
                                }
                            }
                        }

                        Label {
                            Layout.fillWidth: true
                            text: shell.currentPage.title
                            font.pixelSize: 28
                            font.bold: true
                            color: Luna.Theme.brightForeground
                            wrapMode: Text.WordWrap
                        }

                        Label {
                            Layout.fillWidth: true
                            text: shell.currentPage.description
                            color: Luna.Theme.foreground
                            opacity: 0.8
                            wrapMode: Text.WordWrap
                        }

                        Item {
                            Layout.fillWidth: true
                            Layout.fillHeight: true

                            ColumnLayout {
                                anchors.centerIn: parent
                                width: Math.min(parent.width, 360)
                                spacing: 16

                                Rectangle {
                                    Layout.alignment: Qt.AlignHCenter
                                    implicitWidth: 64
                                    implicitHeight: 64
                                    radius: Math.min(Luna.Theme.barRounding, 32)
                                    color: Luna.Theme.lighterBackground

                                    Luna.Icon {
                                        anchors.centerIn: parent
                                        name: shell.currentPage.symbol
                                        ink: Luna.Theme.accent
                                        implicitWidth: 28
                                        implicitHeight: 28
                                    }
                                }

                                Label {
                                    Layout.fillWidth: true
                                    text: "Coming soon"
                                    horizontalAlignment: Text.AlignHCenter
                                    font.pixelSize: 20
                                    font.bold: true
                                    color: Luna.Theme.brightForeground
                                }

                                Label {
                                    Layout.fillWidth: true
                                    text: "Settings for this section will appear here."
                                    horizontalAlignment: Text.AlignHCenter
                                    wrapMode: Text.WordWrap
                                    color: Luna.Theme.foreground
                                    opacity: 0.65
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
