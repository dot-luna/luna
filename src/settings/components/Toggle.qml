import QtQuick
import QtQuick.Controls.Basic

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
        color: toggle.checked ? "#8bb5f5" : "#56565e"
        border.width: toggle.visualFocus ? 2 : 0
        border.color: "#ffffff"

        Rectangle {
            x: toggle.checked ? parent.width - width - 3 : 3
            y: 3
            width: 20
            height: 20
            radius: 10
            color: toggle.checked ? "#172235" : "#eeeeef"
        }

    }

}
