import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Luna 1.0 as Luna

// Checkable buttons make miniature desktop previews keyboard accessible.
Button {
    id: card

    required property string name
    required property color desktopColor
    required property color windowColor
    required property color accentColor

    text: name
    checkable: true
    focusPolicy: Qt.StrongFocus
    Keys.onReturnPressed: click()
    Keys.onEnterPressed: click()
    Layout.fillWidth: true
    implicitHeight: 150
    padding: 12
    Accessible.name: name + " theme"

    background: Rectangle {
        radius: Math.min(Luna.Theme.barRounding, width / 2, height / 2)
        color: card.hovered ? Luna.Theme.selection : Luna.Theme.lighterBackground
        border.width: card.checked || card.visualFocus ? 2 : 1
        border.color: card.visualFocus ? Luna.Theme.brightForeground : card.checked ? Luna.Theme.accent : Luna.Theme.muted
    }

    contentItem: ColumnLayout {
        spacing: 12

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: card.desktopColor
            radius: 5

            Rectangle {
                width: parent.width * 0.64
                height: parent.height * 0.66
                anchors.centerIn: parent
                radius: 4
                color: card.windowColor

                Rectangle {
                    x: 8
                    y: 8
                    width: parent.width * 0.3
                    height: 5
                    radius: 2
                    color: card.accentColor
                }

                Rectangle {
                    x: 8
                    y: 22
                    width: parent.width * 0.72
                    height: 3
                    color: card.accentColor
                    opacity: 0.25
                }

                Rectangle {
                    x: 8
                    y: 31
                    width: parent.width * 0.51
                    height: 3
                    color: card.accentColor
                    opacity: 0.25
                }

            }

        }

        Label {
            text: card.name
            font.bold: card.checked
            Layout.alignment: Qt.AlignHCenter
            color: card.hovered ? Luna.Theme.selectionForeground : Luna.Theme.foreground
        }

    }

}
