import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Luna 1.0 as Luna

// Related controls share one inset desktop preferences surface.
Pane {
    default property alias rows: column.data

    padding: 0
    Layout.fillWidth: true

    background: Rectangle {
        color: Luna.Theme.lighterBackground
        radius: Math.min(Luna.Theme.barRounding, width / 2, height / 2)
        border.color: Luna.Theme.muted
    }

    contentItem: ColumnLayout {
        id: column

        spacing: 0
    }

}
