import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// Related controls share one inset desktop preferences surface.
Pane {
    default property alias rows: column.data

    padding: 0
    Layout.fillWidth: true

    background: Rectangle {
        color: "#303033"
        radius: 10
        border.color: "#404044"
    }

    contentItem: ColumnLayout {
        id: column

        spacing: 0
    }

}
