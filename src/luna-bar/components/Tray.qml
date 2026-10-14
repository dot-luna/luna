pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import Quickshell.Services.SystemTray
import Luna as Luna
import "../TrayLogic.js" as Logic

Item {
    id: tray

    required property var panelWindow
    property var items: SystemTray.items.values
    readonly property var activeItems: items.filter(item => item.status !== Status.Passive)
    signal beforeAction()

    implicitWidth: icons.implicitWidth
    implicitHeight: Luna.Theme.barHeight - 4
    visible: activeItems.length > 0

    function controls() {
        const result = [];
        if (!visible || width <= 0) return result;
        for (let i = 0; i < buttons.count; i++) {
            const button = buttons.itemAt(i);
            if (button && button.visible && button.enabled) result.push(button);
        }
        return result;
    }
    function reveal(button) {
        const x = button.mapToItem(icons, 0, 0).x;
        if (x < viewport.contentX) viewport.contentX = x;
        else if (x + button.width > viewport.contentX + viewport.width)
            viewport.contentX = x + button.width - viewport.width;
    }
    function activate(button, mouseButton) {
        const action = Logic.action(button.item, mouseButton);
        if (!action) return;
        const point = button.mapToItem(panelWindow.contentItem, 0, button.height);
        beforeAction();
        Logic.run(button.item, action, panelWindow, point);
    }

    // A crowded tray can scroll without overlapping the centered clock.
    Flickable {
        id: viewport
        anchors.fill: parent
        contentWidth: icons.implicitWidth
        contentHeight: height
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.HorizontalFlick
        interactive: contentWidth > width
        clip: true

        Row {
            id: icons
            spacing: 2
            height: tray.height
            Repeater {
                id: buttons
                model: tray.activeItems
                delegate: Button {
                    id: button
                    required property var modelData
                    readonly property var item: modelData
                    width: 26
                    height: tray.height
                    focusPolicy: Qt.StrongFocus
                    enabled: !item.onlyMenu || item.hasMenu
                    Accessible.name: item.title || item.tooltipTitle || item.id || "Application"
                    ToolTip.visible: hovered
                    ToolTip.delay: 600
                    ToolTip.text: Accessible.name.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
                    onClicked: tray.activate(button, "left")
                    onActiveFocusChanged: if (activeFocus) tray.reveal(button)
                    background: Rectangle {
                        color: button.hovered ? Luna.Theme.selection : "transparent"
                        radius: Math.min(5, Luna.Theme.barRounding)
                        border.width: button.visualFocus || button.item.status === Status.NeedsAttention ? 1 : 0
                        border.color: button.visualFocus ? Luna.Theme.brightForeground : Luna.Theme.accent
                    }
                    contentItem: Item {
                        Image {
                            id: icon
                            anchors.centerIn: parent
                            width: 17
                            height: 17
                            source: button.item.icon
                            sourceSize: Qt.size(34, 34)
                            fillMode: Image.PreserveAspectFit
                            asynchronous: true
                        }
                        Luna.Icon {
                            anchors.centerIn: parent
                            implicitWidth: 15
                            implicitHeight: 15
                            visible: icon.status !== Image.Ready
                            name: "layout-grid"
                        }
                    }
                    MouseArea {
                        anchors.fill: parent
                        acceptedButtons: Qt.RightButton | Qt.MiddleButton
                        onClicked: mouse => tray.activate(button, mouse.button === Qt.RightButton ? "right" : "middle")
                        onWheel: wheel => {
                            const horizontal = Math.abs(wheel.angleDelta.x) > Math.abs(wheel.angleDelta.y);
                            button.item.scroll(horizontal ? wheel.angleDelta.x : wheel.angleDelta.y, horizontal);
                            wheel.accepted = true;
                        }
                    }
                    Keys.onReturnPressed: click()
                    Keys.onEnterPressed: click()
                    Keys.onPressed: event => {
                        if (event.key === Qt.Key_Menu || (event.key === Qt.Key_F10 && event.modifiers & Qt.ShiftModifier)) {
                            tray.activate(button, "right");
                            event.accepted = true;
                        }
                    }
                }
            }
        }
    }
}
