import QtQuick
import QtQuick.Controls.Basic

// Allow typing numbers as well as adjusting them with Up and Down.
SpinBox {
    focusPolicy: Qt.StrongFocus
    editable: true
    contentItem.Accessible.name: Accessible.name
}
