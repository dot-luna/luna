import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Item {
    id: row

    property string title
    property string description
    property bool divider: true
    default property alias controls: trailing.data

    Layout.fillWidth: true
    implicitHeight: Math.max(70, labels.implicitHeight + 28)

    RowLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 24

        ColumnLayout {
            id: labels

            Layout.fillWidth: true
            spacing: 4

            Label {
                text: row.title
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
            }

            Label {
                visible: row.description !== ""
                text: row.description
                color: "#a6a6ad"
                font.pixelSize: 12
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
            }

        }

        RowLayout {
            id: trailing

            spacing: 8
        }

    }

    Rectangle {
        visible: row.divider
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.leftMargin: 16
        anchors.rightMargin: 16
        height: 1
        color: "#404044"
    }

}
