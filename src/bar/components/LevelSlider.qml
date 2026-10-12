import QtQuick
import QtQuick.Controls.Basic
import Luna as Luna

Slider {
    id: slider

    focusPolicy: Qt.StrongFocus
    implicitHeight: 34
    stepSize: 0.05

    background: Rectangle {
        color: Luna.Theme.muted
        height: 6
        radius: 3
        width: slider.availableWidth
        x: slider.leftPadding
        y: (slider.height - height) / 2

        Rectangle {
            color: Luna.Theme.accent
            height: parent.height
            radius: 3
            width: slider.visualPosition * parent.width
        }
    }
    handle: Rectangle {
        border.color: Luna.Theme.brightForeground
        border.width: slider.visualFocus ? 3 : 0
        color: Luna.Theme.accent
        height: 18
        radius: 9
        width: 18
        x: slider.leftPadding + slider.visualPosition * (slider.availableWidth - width)
        y: (slider.height - height) / 2
    }
}
