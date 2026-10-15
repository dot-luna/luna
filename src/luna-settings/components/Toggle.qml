import QtQuick
import QtQuick.Controls.Basic
import Luna 1.0 as Luna

// Preserve native switch keyboard behavior while making its state and focus clear.
Switch {
    id: toggle

    padding: 4
    focusPolicy: Qt.StrongFocus
    Keys.onReturnPressed: click()
    Keys.onEnterPressed: click()

    indicator: Rectangle {
        implicitWidth: 44
        implicitHeight: 26
        x: toggle.leftPadding
        y: (toggle.height - height) / 2
        radius: 13
        color: toggle.checked ? Luna.Theme.accent : Luna.Theme.muted
        border.width: toggle.visualFocus ? 2 : 0
        border.color: Luna.Theme.brightForeground

        Rectangle {
            x: toggle.checked ? parent.width - width - 3 : 3
            y: 3
            width: 20
            height: 20
            radius: 10
            color: toggle.checked ? Luna.Theme.accentForeground : Luna.Theme.brightForeground
        }

    }

}
