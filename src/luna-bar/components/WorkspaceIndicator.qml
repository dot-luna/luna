pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Effects
import Luna as Luna

// User preferences choose the shape; theme colors and rounding remain shared.
Item {
    id: indicatorItem

    required property bool active
    required property var indicator
    required property string workspaceLabel
    readonly property color ink: active ? Luna.Theme.accent : Luna.Theme.foreground
    readonly property bool textMode: indicator.type === "number" || indicator.type === "label"

    implicitHeight: indicator.size
    implicitWidth: textMode ? label.implicitWidth : indicator.size
    opacity: active ? 1 : 0.5

    Label {
        id: label

        anchors.centerIn: parent
        color: indicatorItem.ink
        font.bold: indicatorItem.active
        font.family: Luna.Theme.uiFont
        font.pixelSize: indicatorItem.indicator.size
        text: indicatorItem.indicator.type === "label"
            ? indicatorItem.indicator.label.replace(/\{number\}/g, indicatorItem.workspaceLabel)
            : indicatorItem.workspaceLabel
        textFormat: Text.PlainText
        visible: indicatorItem.textMode || (svg.visible && svg.status === Image.Error)
    }
    Rectangle {
        anchors.centerIn: parent
        color: indicatorItem.ink
        height: indicatorItem.indicator.size
        radius: Math.min(Luna.Theme.barRounding, width / 2, height / 2)
        visible: indicatorItem.indicator.type === "dot"
        width: height
    }
    Image {
        id: svg

        anchors.centerIn: parent
        fillMode: Image.PreserveAspectFit
        height: indicatorItem.indicator.size
        layer.enabled: true
        source: indicatorItem.indicator.source || ""
        sourceSize: Qt.size(width, height)
        visible: indicatorItem.indicator.type === "icon"
        width: height

        layer.effect: MultiEffect {
            colorization: 1
            colorizationColor: indicatorItem.ink
        }
    }
}
