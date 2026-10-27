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
    readonly property var sections: ["Appearance", "Wallpapers", "Fonts", "Windows", "Keyboard"]
    readonly property var sources: ["pages/Appearance.qml", "pages/Wallpapers.qml", "pages/Fonts.qml", "pages/Windows.qml", "pages/Keyboard.qml"]
    readonly property var descriptions: ["Theme, colors, and application style.", "Background images for your desktop.", "Interface and terminal typography.", "Window layout and visual effects.", "Desktop shortcuts and settings navigation."]

    // Find outer controls only: a spin box's editor is part of its single tab stop.
    function pageControls() {
        const controls = [];
        function visit(item) {
            if (!item || !item.visible || !item.enabled)
                return;
            if (item.focusPolicy !== undefined && (item.focusPolicy & Qt.TabFocus)) {
                controls.push(item);
                return;
            }
            for (const child of item.children)
                visit(child);
        }
        visit(pageLoaders.itemAt(page).item);
        return controls;
    }

    function focusPage(last) {
        const controls = pageControls();
        if (controls.length)
            controls[last ? controls.length - 1 : 0].forceActiveFocus(Qt.TabFocusReason);
        else
            scroll.forceActiveFocus(Qt.TabFocusReason);
    }

    function selectPage(index) {
        page = (index + sections.length) % sections.length;
        navigation.itemAt(page).forceActiveFocus(Qt.TabFocusReason);
    }

    onPageChanged: {
        scroll.contentItem.contentY = 0;
        navigation.itemAt(page).forceActiveFocus(Qt.ShortcutFocusReason);
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
        implicitWidth: 960
        implicitHeight: 760
        minimumSize: Qt.size(760, 540)
        color: Luna.Theme.background
        onClosed: Qt.quit()
        Component.onCompleted: navigation.itemAt(0).forceActiveFocus(Qt.TabFocusReason)

        Shortcut {
            sequence: "Ctrl+Q"
            onActivated: Qt.quit()
        }

        Shortcut {
            sequence: "Ctrl+L"
            onActivated: navigation.itemAt(shell.page).forceActiveFocus(Qt.ShortcutFocusReason)
        }

        Shortcut {
            sequence: "Ctrl+Tab"
            onActivated: shell.selectPage(shell.page + 1)
        }

        Shortcut {
            sequence: "Ctrl+Shift+Tab"
            onActivated: shell.selectPage(shell.page - 1)
        }

        Shortcut {
            sequence: "Alt+1"
            onActivated: shell.page = 0
        }

        Shortcut {
            sequence: "Alt+2"
            onActivated: shell.page = 1
        }

        Shortcut {
            sequence: "Alt+3"
            onActivated: shell.page = 2
        }

        Shortcut {
            sequence: "Alt+4"
            onActivated: shell.page = 3
        }

        Shortcut {
            sequence: "Alt+5"
            onActivated: shell.page = 4
        }

        // Tab navigation reveals focused controls even in a short tiled window.
        Connections {
            function onActiveFocusItemChanged() {
                const item = target.activeFocusItem;
                if (!item)
                    return;

                let ancestor = item;
                while (ancestor && ancestor !== pageContent)
                    ancestor = ancestor.parent;
                if (!ancestor)
                    return;

                const position = item.mapToItem(pageContent, 0, 0);
                const flick = scroll.contentItem;
                if (position.y < flick.contentY)
                    flick.contentY = Math.max(0, position.y - 12);
                else if (position.y + item.height > flick.contentY + flick.height)
                    flick.contentY = Math.min(Math.max(0, scroll.contentHeight - flick.height), position.y + item.height - flick.height + 12);
            }

            target: window.contentItem.Window.window
        }

        // Controls inherit the shared font and palette through every loaded page.
        Control {
            anchors.fill: parent
            padding: 0
            font.family: Luna.Theme.uiFont
            font.pixelSize: 14

            palette {
                window: Luna.Theme.background
                windowText: Luna.Theme.foreground
                base: Luna.Theme.lighterBackground
                alternateBase: Luna.Theme.background
                text: Luna.Theme.foreground
                button: Luna.Theme.lighterBackground
                buttonText: Luna.Theme.foreground
                highlight: Luna.Theme.accent
                highlightedText: Luna.Theme.accentForeground
                light: Luna.Theme.foreground
                mid: Luna.Theme.muted
                dark: Luna.Theme.foreground
                shadow: Luna.Theme.colors.dark_background
                placeholderText: Luna.Theme.foreground
                toolTipBase: Luna.Theme.lighterBackground
                toolTipText: Luna.Theme.foreground
                link: Luna.Theme.colors.link
                linkVisited: Luna.Theme.colors.secondary_accent
            }

            contentItem: RowLayout {
                spacing: 0

                Rectangle {
                    color: Luna.Theme.lighterBackground
                    Layout.preferredWidth: 224
                    Layout.fillHeight: true

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 0

                        Label {
                            text: "Luna Settings"
                            font.bold: true
                            font.pixelSize: 16
                            color: Luna.Theme.brightForeground
                            Layout.fillWidth: true
                            Layout.margins: 22
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            height: 1
                            color: Luna.Theme.muted
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.margins: 12
                            spacing: 4

                            Repeater {
                                id: navigation

                                model: shell.sections

                                delegate: Button {
                                    id: navigationButton

                                    required property int index
                                    required property string modelData

                                    text: modelData
                                    focusPolicy: shell.page === index ? Qt.StrongFocus : Qt.ClickFocus
                                    Layout.fillWidth: true
                                    implicitHeight: 46
                                    Accessible.name: modelData + " settings"
                                    onClicked: shell.selectPage(index)
                                    Keys.onUpPressed: shell.selectPage(index - 1)
                                    Keys.onDownPressed: shell.selectPage(index + 1)
                                    Keys.onRightPressed: shell.focusPage(false)
                                    Keys.onTabPressed: shell.focusPage(false)
                                    Keys.onBacktabPressed: shell.focusPage(true)
                                    Keys.onReturnPressed: shell.focusPage(false)
                                    Keys.onEnterPressed: shell.focusPage(false)

                                    background: Rectangle {
                                        radius: Math.min(Luna.Theme.barRounding, height / 2)
                                        color: shell.page === navigationButton.index || navigationButton.hovered ? Luna.Theme.selection : "transparent"
                                        border.width: navigationButton.visualFocus ? 2 : 0
                                        border.color: Luna.Theme.accent
                                    }

                                    contentItem: Label {
                                        text: navigationButton.text
                                        leftPadding: 14
                                        verticalAlignment: Text.AlignVCenter
                                        font.bold: shell.page === navigationButton.index
                                        color: shell.page === navigationButton.index || navigationButton.hovered ? Luna.Theme.selectionForeground : Luna.Theme.foreground
                                    }

                                }

                            }

                        }

                        Item {
                            Layout.fillHeight: true
                        }

                        Label {
                            text: "Hyprland desktop"
                            font.pixelSize: 12
                            color: Luna.Theme.foreground
                            Layout.margins: 22
                        }

                    }

                }

                Rectangle {
                    Layout.fillHeight: true
                    width: 1
                    color: Luna.Theme.muted
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: 0

                    // The header stays fixed while long settings pages scroll beneath it.
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 68
                        Layout.leftMargin: 28
                        Layout.rightMargin: 16

                        Label {
                            text: shell.sections[shell.page]
                            font.bold: true
                            font.pixelSize: 16
                            color: Luna.Theme.brightForeground
                            Layout.fillWidth: true
                        }

                        Label {
                            text: "Preview"
                            color: Luna.Theme.foreground
                            font.pixelSize: 12
                        }

                        Button {
                            text: "×"
                            font.pixelSize: 22
                            flat: true
                            implicitWidth: 36
                            Accessible.name: "Close settings"
                            onClicked: Qt.quit()
                        }

                    }

                    Rectangle {
                        Layout.fillWidth: true
                        height: 1
                        color: Luna.Theme.muted
                    }

                    ScrollView {
                        id: scroll

                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        contentWidth: availableWidth
                        contentHeight: pageContent.implicitHeight
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                        ColumnLayout {
                            id: pageContent

                            width: scroll.availableWidth
                            height: implicitHeight
                            spacing: 0

                            ColumnLayout {
                                Layout.fillWidth: true
                                Layout.fillHeight: false
                                Layout.maximumWidth: 660
                                Layout.alignment: Qt.AlignHCenter
                                Layout.margins: 28
                                spacing: 12

                                Label {
                                    text: shell.sections[shell.page]
                                    font.pixelSize: 27
                                    font.bold: true
                                    Layout.fillWidth: true
                                }

                                Label {
                                    text: shell.descriptions[shell.page]
                                    color: Luna.Theme.foreground
                                    Layout.fillWidth: true
                                    wrapMode: Text.WordWrap
                                    Layout.bottomMargin: 12
                                }

                                // Keep pages alive so sample selections survive navigation this session.
                                StackLayout {
                                    id: pages

                                    Layout.fillWidth: true
                                    Layout.fillHeight: false
                                    implicitHeight: children[currentIndex] ? children[currentIndex].implicitHeight : 0
                                    currentIndex: shell.page

                                    Repeater {
                                        id: pageLoaders

                                        model: shell.sources

                                        Loader {
                                            required property string modelData

                                            Layout.fillHeight: false
                                            Layout.alignment: Qt.AlignTop
                                            source: modelData
                                        }

                                    }

                                }

                            }

                        }

                    }

                    Rectangle {
                        Layout.fillWidth: true
                        height: 1
                        color: Luna.Theme.muted
                    }

                    Label {
                        text: "Mockup · changes stay in this window"
                        color: Luna.Theme.foreground
                        font.pixelSize: 12
                        Layout.margins: 12
                        Layout.alignment: Qt.AlignHCenter
                    }

                }

            }
        }

    }

}
