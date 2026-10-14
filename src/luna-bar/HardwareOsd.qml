pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import Luna as Luna

PanelWindow {
    id: osd

    required property string icon
    required property real level
    required property bool muted
    required property string error

    anchors.bottom: true
    margins.bottom: screen ? Math.max(40, Math.round(screen.height * 0.14)) : 80
    implicitWidth: 230
    implicitHeight: error ? 82 : 60
    color: "transparent"
    exclusionMode: ExclusionMode.Ignore
    mask: Region {}
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "luna-hardware-osd"
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

    Rectangle {
        anchors.fill: parent
        color: Luna.Theme.background
        radius: Math.min(14, Luna.Theme.barRounding)
        border.width: Math.max(1, Luna.Theme.borderWidth)
        border.color: osd.error ? Luna.Theme.colors.error : Luna.Theme.muted

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 18
            spacing: 8
            RowLayout {
                Layout.fillWidth: true
                spacing: 14
                Luna.Icon {
                    name: osd.error ? "triangle-alert" : osd.icon
                    ink: osd.error ? Luna.Theme.colors.error : osd.muted ? Luna.Theme.muted : Luna.Theme.accent
                    implicitWidth: 22
                    implicitHeight: 22
                }
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 5
                    color: Luna.Theme.muted
                    radius: Math.min(3, Luna.Theme.barRounding)
                    Rectangle {
                        width: osd.muted ? 0 : parent.width * osd.level
                        height: parent.height
                        radius: parent.radius
                        color: Luna.Theme.accent
                    }
                }
            }
            Label {
                visible: osd.error !== ""
                Layout.fillWidth: true
                text: osd.error
                textFormat: Text.PlainText
                color: Luna.Theme.foreground
                font.family: Luna.Theme.uiFont
                font.pixelSize: 11
                horizontalAlignment: Text.AlignHCenter
                elide: Text.ElideRight
            }
        }
    }
}
