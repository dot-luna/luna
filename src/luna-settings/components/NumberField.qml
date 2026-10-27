import QtQuick
import QtQuick.Controls.Basic
import Luna 1.0 as Luna

// Allow typing numbers as well as adjusting them with Up and Down.
SpinBox {
    id: number

    focusPolicy: Qt.StrongFocus
    editable: true
    contentItem.Accessible.name: Accessible.name

    // Keep the native editable field and keyboard behavior with themed step buttons.
    component StepButton: Rectangle {
        required property string symbol
        required property bool pressed
        required property bool hovered

        implicitWidth: 40
        implicitHeight: 40
        height: number.height
        radius: Math.min(Luna.Theme.barRounding, width / 2, height / 2)
        color: pressed ? Luna.Theme.accent : hovered ? Luna.Theme.selection : Luna.Theme.lighterBackground

        Label {
            anchors.centerIn: parent
            text: parent.symbol
            font: number.font
            color: !parent.enabled ? Luna.Theme.muted
                : parent.pressed ? Luna.Theme.accentForeground
                : parent.hovered ? Luna.Theme.selectionForeground : Luna.Theme.foreground
        }
    }

    up.indicator: StepButton {
        x: number.mirrored ? 0 : number.width - width
        symbol: "+"
        pressed: number.up.pressed
        hovered: number.up.hovered
    }

    down.indicator: StepButton {
        x: number.mirrored ? number.width - width : 0
        symbol: "−"
        pressed: number.down.pressed
        hovered: number.down.hovered
    }

    background: Rectangle {
        implicitWidth: 140
        color: Luna.Theme.background
        radius: Math.min(Luna.Theme.barRounding, width / 2, height / 2)
        border.color: number.visualFocus ? Luna.Theme.accent : Luna.Theme.muted
    }
}
