pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Quickshell
import Luna as Luna

// One shared layout keeps popup and history actions consistent across urgency levels.
Rectangle {
    id: card

    required property var entry
    property bool popup: false
    property bool expanded: false
    readonly property int urgency: Number(entry.urgency)
    readonly property color priorityColor: urgency === 2 ? Luna.Theme.colors.error
        : urgency === 0 ? Luna.Theme.foreground : Luna.Theme.accent
    readonly property string priorityLabel: urgency === 2 ? "Critical" : urgency === 0 ? "Low" : "Normal"
    readonly property string priorityIcon: urgency === 2 ? "triangle-alert" : urgency === 0 ? "info" : "bell"
    readonly property string imageSource: localImage(entry.image)
    readonly property string appIconSource: resolveAppIcon(entry.appIcon)
    readonly property bool hasAppIcon: appImage.status === Image.Ready
    readonly property var actions: (entry.actions || []).filter(action =>
        action.identifier !== "default" && action.identifier !== "luna-open-image"
            && action.identifier !== "luna-open-recording")

    signal opened()
    signal dismissed()
    signal removed()
    signal actionInvoked(string identifier)
    signal hoverStateChanged(bool hovered)

    function toggleExpanded() {
        if (expanded || summaryText.truncated || bodyText.truncated)
            expanded = !expanded;
    }

    function localImage(value) {
        const source = String(value || "");
        // Notification content must never trigger an external network image request.
        if (source.startsWith("/") && !source.startsWith("//"))
            return "file://" + source.split("/").map(part => encodeURIComponent(part)).join("/");
        if (/^file:\/\/\//.test(source))
            return source;
        if (/^image:\/\/qsimage\/\d+\/\d+$/.test(source))
            return source;
        return "";
    }
    function resolveAppIcon(value) {
        const source = String(value || "");
        if (/[\u0000\r\n]/.test(source)) return "";
        if ((source.startsWith("/") && !source.startsWith("//")) || /^file:\/\/\/(?!\/)/.test(source))
            return localImage(source);
        // Theme icon names are plain identifiers, never arbitrary URL providers.
        if (/^[a-zA-Z0-9][a-zA-Z0-9._-]*$/.test(source))
            return Quickshell.iconPath(source, true);
        return "";
    }

    implicitWidth: 364
    implicitHeight: content.implicitHeight + 28
    color: Luna.Theme.lighterBackground
    border.color: activeFocus ? Luna.Theme.brightForeground : urgency === 2 ? priorityColor
        : Qt.alpha(Luna.Theme.muted, urgency === 0 ? 0.4 : 0.85)
    border.width: 1
    radius: Math.max(0, Math.min(12, Luna.Theme.barRounding))
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: priorityLabel + " notification from " + (entry.appName || "Application") + ": " + (entry.summary || "Notification")
    Accessible.onPressAction: opened()
    Keys.onReturnPressed: opened()
    Keys.onEnterPressed: opened()
    Keys.onSpacePressed: opened()
    Keys.onDeletePressed: popup ? dismissed() : removed()

    HoverHandler {
        onHoveredChanged: card.hoverStateChanged(hovered)
    }
    Rectangle {
        anchors.fill: parent
        anchors.margins: 1
        radius: Math.max(0, card.radius - 1)
        color: card.urgency === 2 ? Qt.alpha(card.priorityColor, 0.045) : "transparent"
    }
    // Explicit action buttons sit above this area and keep their own left-click action.
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        onClicked: mouse => {
            if (mouse.button === Qt.RightButton) {
                if (card.popup) card.dismissed();
                else card.removed();
            } else {
                card.opened();
            }
        }
    }

    component CardButton: Button {
        id: button

        property bool emphasized: false
        focusPolicy: Qt.StrongFocus
        implicitHeight: 30
        implicitWidth: Math.min(implicitContentWidth + 20, content.width)
        leftPadding: 10
        rightPadding: 10
        Accessible.name: text
        background: Rectangle {
            color: button.hovered ? Luna.Theme.selection : button.emphasized ? Qt.alpha(card.priorityColor, 0.11) : "transparent"
            border.color: button.visualFocus ? Luna.Theme.brightForeground : Qt.alpha(card.priorityColor, 0.35)
            border.width: button.emphasized || button.visualFocus ? 1 : 0
            radius: Math.min(6, Luna.Theme.barRounding)
        }
        contentItem: Label {
            text: button.text
            textFormat: Text.PlainText
            color: button.hovered ? Luna.Theme.selectionForeground : button.emphasized ? card.priorityColor : Luna.Theme.foreground
            font.family: Luna.Theme.uiFont
            font.pixelSize: 11
            font.weight: Font.Medium
            elide: Text.ElideRight
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
        Keys.onReturnPressed: click()
        Keys.onEnterPressed: click()
    }

    ColumnLayout {
        id: content

        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 14
        spacing: 8

        RowLayout {
            Layout.fillWidth: true
            spacing: 9

            Rectangle {
                Layout.preferredWidth: 30
                Layout.preferredHeight: 30
                radius: Math.min(8, Luna.Theme.barRounding)
                color: Qt.alpha(card.priorityColor, card.urgency === 0 ? 0.06 : 0.12)
                Image {
                    id: appImage
                    anchors.centerIn: parent
                    width: 20
                    height: 20
                    source: card.appIconSource
                    sourceSize: Qt.size(40, 40)
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    visible: card.hasAppIcon
                }
                Luna.Icon {
                    anchors.centerIn: parent
                    implicitWidth: 16
                    implicitHeight: 16
                    name: card.priorityIcon
                    ink: card.priorityColor
                    visible: !card.hasAppIcon
                }
            }
            Label {
                id: summaryText
                Layout.fillWidth: true
                text: card.entry.summary || "Notification"
                textFormat: Text.PlainText
                color: Luna.Theme.brightForeground
                font.family: Luna.Theme.uiFont
                font.pixelSize: 13
                font.weight: Font.DemiBold
                wrapMode: Text.Wrap
                maximumLineCount: card.expanded ? 1000000 : 2
                elide: Text.ElideRight
            }
        }
        Label {
            id: bodyText
            Layout.fillWidth: true
            visible: text.length > 0
            text: card.entry.body || ""
            textFormat: Text.PlainText
            color: Luna.Theme.foreground
            font.family: Luna.Theme.uiFont
            font.pixelSize: 12
            wrapMode: Text.Wrap
            lineHeight: 1.15
            maximumLineCount: card.expanded ? 1000000 : 3
            elide: Text.ElideRight
        }
        CardButton {
            visible: !card.popup && (card.expanded || summaryText.truncated || bodyText.truncated)
            text: card.expanded ? "Show less" : "Show more"
            leftPadding: 0
            rightPadding: 6
            implicitHeight: 24
            onClicked: card.toggleExpanded()
        }
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 116
            visible: preview.status === Image.Ready
            color: Luna.Theme.background
            radius: Math.min(6, Luna.Theme.barRounding)
            clip: true
            Image {
                id: preview
                anchors.fill: parent
                anchors.margins: 1
                source: card.imageSource
                sourceSize.width: 640
                sourceSize.height: 240
                asynchronous: true
                fillMode: Image.PreserveAspectFit
            }
        }
        Flow {
            Layout.fillWidth: true
            visible: card.actions.length > 0
            spacing: 6
            Repeater {
                model: card.actions
                delegate: CardButton {
                    required property var modelData
                    text: modelData.text || "Open"
                    emphasized: true
                    onClicked: card.actionInvoked(String(modelData.identifier))
                }
            }
        }
    }
}
