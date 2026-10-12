import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Luna as Luna

Button {
    id: button

    property bool selected: false
    property string symbol: ""

    Accessible.name: text
    focusPolicy: Qt.StrongFocus
    implicitHeight: 40
    padding: 10

    background: Rectangle {
        border.color: Luna.Theme.brightForeground
        border.width: button.visualFocus ? 2 : 0
        color: button.selected ? Luna.Theme.accent : button.hovered ? Luna.Theme.selection : Luna.Theme.lighterBackground
        opacity: button.enabled ? 1 : 0.5
        radius: 8
    }
    contentItem: RowLayout {
        spacing: 8

        Luna.Icon {
            ink: button.selected ? Luna.Theme.accentForeground : Luna.Theme.foreground
            name: button.symbol || "sliders-horizontal"
            visible: button.symbol !== ""
        }
        Label {
            Layout.fillWidth: true
            color: button.selected ? Luna.Theme.accentForeground : Luna.Theme.foreground
            elide: Text.ElideRight
            text: button.text
        }
    }

    Keys.onEnterPressed: click()
    Keys.onReturnPressed: click()
}
