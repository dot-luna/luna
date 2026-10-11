import QtQuick
import QtQuick.Controls.Basic

// Native Space opens choices; arrows, Enter and Escape select or dismiss them.
ComboBox {
    id: choice
    focusPolicy: Qt.StrongFocus

    background: Rectangle {
        color: "#404044"
        radius: 6
        border.width: choice.visualFocus ? 2 : 1
        border.color: choice.visualFocus ? "#8bb5f5" : "#54545c"
    }
}
