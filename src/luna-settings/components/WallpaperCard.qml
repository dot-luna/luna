import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Luna 1.0 as Luna

// Local sample landscapes need no downloaded assets or user images.
Button {
    id: card

    required property string name
    required property color sky
    required property color mountain

    text: name
    checkable: true
    focusPolicy: Qt.StrongFocus
    Keys.onReturnPressed: click()
    Keys.onEnterPressed: click()
    Layout.fillWidth: true
    implicitHeight: 155
    padding: 6
    Accessible.name: name + " wallpaper"

    background: Rectangle {
        radius: Math.min(Luna.Theme.barRounding, width / 2, height / 2)
        color: card.hovered ? Luna.Theme.selection : Luna.Theme.lighterBackground
        border.width: card.checked || card.visualFocus ? 2 : 1
        border.color: card.visualFocus ? Luna.Theme.brightForeground : card.checked ? Luna.Theme.accent : Luna.Theme.muted
    }

    contentItem: ColumnLayout {
        spacing: 8

        Canvas {
            Layout.fillWidth: true
            Layout.fillHeight: true
            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()
            onPaint: {
                const ctx = getContext("2d");
                ctx.fillStyle = card.sky;
                ctx.fillRect(0, 0, width, height);
                ctx.fillStyle = "#e8dbc0";
                ctx.beginPath();
                ctx.arc(width * 0.74, height * 0.28, 10, 0, Math.PI * 2);
                ctx.fill();
                ctx.fillStyle = card.mountain;
                ctx.beginPath();
                ctx.moveTo(0, height * 0.85);
                ctx.lineTo(width * 0.34, height * 0.32);
                ctx.lineTo(width * 0.6, height * 0.74);
                ctx.lineTo(width * 0.8, height * 0.48);
                ctx.lineTo(width, height * 0.78);
                ctx.lineTo(width, height);
                ctx.lineTo(0, height);
                ctx.closePath();
                ctx.fill();
            }
        }

        Label {
            text: card.name
            color: card.hovered ? Luna.Theme.selectionForeground : Luna.Theme.foreground
            Layout.alignment: Qt.AlignHCenter
            Layout.bottomMargin: 4
            font.pixelSize: 12
        }

    }

}
