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
    implicitHeight: 32
    padding: 7

    background: Rectangle {
        border.color: Luna.Theme.brightForeground
        border.width: button.visualFocus ? 1 : 0
        color: button.hovered ? Luna.Theme.selection : "transparent"
        opacity: button.enabled ? 1 : 0.5
        radius: Math.min(Luna.Theme.barRounding, width / 2, height / 2)
    }
    contentItem: RowLayout {
        spacing: button.text !== "" ? 8 : 0

        Luna.Icon {
            implicitWidth: button.symbol.startsWith("chevron-") || button.symbol.startsWith("bluetooth") ? 12 : 14
            implicitHeight: implicitWidth
            Layout.maximumWidth: implicitWidth
            Layout.maximumHeight: implicitHeight
            Layout.alignment: Qt.AlignVCenter
            ink: button.selected ? Luna.Theme.accent : button.hovered ? Luna.Theme.selectionForeground : Luna.Theme.foreground
            name: button.symbol || "sliders-horizontal"
            visible: button.symbol !== ""
        }
        Label {
            visible: button.text !== ""
            font.family: Luna.Theme.uiFont
            font.pixelSize: 12
            Layout.fillWidth: true
            color: button.selected ? Luna.Theme.accent : button.hovered ? Luna.Theme.selectionForeground : Luna.Theme.foreground
            elide: Text.ElideRight
            text: button.text
        }
    }

    Keys.onEnterPressed: click()
    Keys.onReturnPressed: click()
}
