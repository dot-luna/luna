import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Luna as Luna

// Compact split tile: the main action and detail arrow remain separate controls.
Rectangle {
    id: tile
    property string title: ""
    property string description: ""
    property string symbol: ""
    property bool selected: false
    property bool actionEnabled: true
    signal activated()
    signal detailsRequested()
    implicitHeight: 44
    implicitWidth: 140
    color: "transparent"
    radius: Luna.Theme.barRounding

    RowLayout {
        anchors.fill: parent
        spacing: 2
        Button {
            id: primary
            Layout.fillWidth: true
            Layout.fillHeight: true
            enabled: tile.actionEnabled
            focusPolicy: Qt.StrongFocus
            Accessible.name: tile.title + (tile.description ? ", " + tile.description : "")
            padding: 10
            background: Rectangle {
                color: tile.selected ? Luna.Theme.accent : primary.hovered ? Luna.Theme.selection : Luna.Theme.lighterBackground
                radius: Luna.Theme.barRounding
                border.width: primary.visualFocus ? 1 : 0
                border.color: Luna.Theme.brightForeground
                opacity: primary.enabled ? 1 : 0.5
            }
            contentItem: RowLayout {
                spacing: 9
                Luna.Icon {
                    implicitWidth: tile.symbol.startsWith("bluetooth") ? 12 : 14
                    implicitHeight: implicitWidth
                    Layout.maximumWidth: implicitWidth
                    Layout.maximumHeight: implicitHeight
                    Layout.alignment: Qt.AlignVCenter
                    name: tile.symbol
                    ink: tile.selected ? Luna.Theme.accentForeground : Luna.Theme.foreground
                    opacity: primary.enabled ? 1 : 0.45
                }
                Label {
                    Layout.fillWidth: true
                    text: tile.title
                    font.family: Luna.Theme.uiFont
                    font.pixelSize: 12
                    font.weight: Font.Medium
                    color: tile.selected ? Luna.Theme.accentForeground : Luna.Theme.foreground
                    elide: Text.ElideRight
                }
            }
            onClicked: tile.activated()
            Keys.onReturnPressed: click()
            Keys.onEnterPressed: click()
            Keys.onRightPressed: detail.forceActiveFocus(Qt.TabFocusReason)
            ToolTip.visible: hovered && tile.description !== ""
            ToolTip.text: tile.description
        }
        Button {
            id: detail
            objectName: tile.objectName + "Details"
            Layout.preferredWidth: 28
            Layout.fillHeight: true
            focusPolicy: Qt.StrongFocus
            Accessible.name: tile.title + " details"
            background: Rectangle {
                color: detail.hovered ? Luna.Theme.selection : Luna.Theme.lighterBackground
                border.width: detail.visualFocus ? 1 : 0
                border.color: Luna.Theme.brightForeground
                radius: Luna.Theme.barRounding
            }
            contentItem: Item {
                Luna.Icon {
                    anchors.centerIn: parent
                    implicitWidth: 12
                    implicitHeight: 12
                    name: "chevron-right"
                    ink: Luna.Theme.foreground
                }
            }
            onClicked: tile.detailsRequested()
            Keys.onReturnPressed: click()
            Keys.onEnterPressed: click()
            Keys.onLeftPressed: primary.forceActiveFocus(Qt.TabFocusReason)
        }
    }
}
