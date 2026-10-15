import QtQuick
import QtQuick.Controls.Basic
import Luna 1.0 as Luna

// Native Space opens choices; arrows, Enter and Escape select or dismiss them.
ComboBox {
    id: choice
    focusPolicy: Qt.StrongFocus
    palette.buttonText: hovered || down ? Luna.Theme.selectionForeground : Luna.Theme.foreground

    // Popups use their own window, so inherited font attributes need explicit bindings.
    popup.font.family: Luna.Theme.uiFont
    popup.font.pixelSize: choice.font.pixelSize

    popup.background: Rectangle {
        color: Luna.Theme.lighterBackground
        radius: Math.min(Luna.Theme.barRounding, width / 2, height / 2)
        border.color: Luna.Theme.muted
    }

    // Basic's list draws a square contour over its background; keep the themed border.
    popup.contentItem: ListView {
        clip: true
        implicitHeight: contentHeight
        model: choice.delegateModel
        currentIndex: choice.highlightedIndex
        highlightMoveDuration: 0

        ScrollIndicator.vertical: ScrollIndicator {}
    }

    background: Rectangle {
        color: choice.hovered || choice.down ? Luna.Theme.selection : Luna.Theme.lighterBackground
        radius: Math.min(Luna.Theme.barRounding, width / 2, height / 2)
        border.width: choice.visualFocus ? 2 : 1
        border.color: choice.visualFocus ? Luna.Theme.accent : Luna.Theme.muted
    }
}
