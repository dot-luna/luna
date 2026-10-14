pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Luna as Luna
import "../components"
import "PairingLogic.js" as Logic

Rectangle {
    id: card

    property var request: null
    property string error: ""
    property int lastRequestId: -1
    signal accepted(string value)
    signal cancelled()

    implicitWidth: 410
    implicitHeight: content.implicitHeight + 40
    width: implicitWidth
    height: implicitHeight
    onRequestChanged: {
        if (request && request.id !== lastRequestId) {
            lastRequestId = request.id;
            input.text = "";
            focusDelay.restart();
        }
    }
    Timer {
        id: focusDelay
        interval: 50
        onTriggered: {
            if (card.request) {
                if (Logic.needsInput(card.request)) input.forceActiveFocus(Qt.TabFocusReason);
                else cancelButton.forceActiveFocus(Qt.TabFocusReason);
            }
        }
    }
    radius: Math.min(14, Luna.Theme.barRounding)
    color: Luna.Theme.background
    border.width: Luna.Theme.borderWidth
    border.color: Luna.Theme.muted

    ColumnLayout {
        id: content
        anchors.fill: parent
        anchors.margins: 20
        spacing: 16

        RowLayout {
            spacing: 10
            Luna.Icon { name: "bluetooth"; ink: Luna.Theme.accent; implicitWidth: 20; implicitHeight: 20 }
            Label {
                Layout.fillWidth: true
                text: card.request && card.request.kind === "service" ? "Bluetooth connection" : "Pair Bluetooth device"
                textFormat: Text.PlainText
                color: Luna.Theme.brightForeground
                font.family: Luna.Theme.uiFont
                font.pixelSize: 16
                font.weight: Font.DemiBold
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 8
            Label {
                Layout.fillWidth: true
                text: card.request ? card.request.name || "Bluetooth device" : ""
                textFormat: Text.PlainText
                wrapMode: Text.WrapAnywhere
                maximumLineCount: 3
                elide: Text.ElideRight
                color: Luna.Theme.brightForeground
                font.family: Luna.Theme.uiFont
                font.pixelSize: 14
                font.weight: Font.Medium
            }
            Label {
                Layout.fillWidth: true
                text: Logic.instructions(card.request)
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                color: Luna.Theme.foreground
                font.family: Luna.Theme.uiFont
                font.pixelSize: 12
            }
            Label {
                Layout.fillWidth: true
                visible: card.request !== null && card.request.kind === "service"
                text: card.request ? Logic.serviceName(card.request.uuid) : ""
                textFormat: Text.PlainText
                wrapMode: Text.WrapAnywhere
                color: Luna.Theme.foreground
                font.family: Luna.Theme.uiFont
                font.pixelSize: 11
            }
        }
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 66
            visible: card.request !== null && !!card.request.code
            radius: Math.min(8, Luna.Theme.barRounding)
            color: Luna.Theme.lighterBackground
            Label {
                anchors.centerIn: parent
                text: card.request && card.request.code ? card.request.code.split("").join(" ") : ""
                textFormat: Text.PlainText
                color: Luna.Theme.accent
                font.family: Luna.Theme.snapshot.fonts.mono
                font.pixelSize: 26
                font.weight: Font.Medium
            }
        }
        Label {
            Layout.fillWidth: true
            visible: card.request !== null && card.request.kind === "display-passkey"
            text: card.request ? (card.request.entered || 0) + " of 6 digits entered" : ""
            color: Luna.Theme.foreground
            font.family: Luna.Theme.uiFont
            font.pixelSize: 11
            horizontalAlignment: Text.AlignHCenter
        }
        TextField {
            id: input
            Layout.fillWidth: true
            visible: Logic.needsInput(card.request)
            implicitHeight: 42
            maximumLength: card.request && card.request.kind === "passkey" ? 6 : 16
            inputMethodHints: card.request && card.request.kind === "passkey" ? Qt.ImhDigitsOnly : Qt.ImhNoPredictiveText
            placeholderText: card.request && card.request.kind === "passkey" ? "Passkey" : "PIN"
            color: Luna.Theme.brightForeground
            placeholderTextColor: Luna.Theme.foreground
            selectionColor: Luna.Theme.selection
            selectedTextColor: Luna.Theme.selectionForeground
            font.family: Luna.Theme.snapshot.fonts.mono
            font.pixelSize: 16
            padding: 10
            Accessible.name: placeholderText
            background: Rectangle {
                radius: Math.min(8, Luna.Theme.barRounding)
                color: Luna.Theme.lighterBackground
                border.color: input.activeFocus ? Luna.Theme.accent : Luna.Theme.muted
                border.width: 1
            }
            Keys.onReturnPressed: if (Logic.validInput(card.request, text)) card.accepted(text)
            Keys.onEnterPressed: if (Logic.validInput(card.request, text)) card.accepted(text)
        }
        Label {
            Layout.fillWidth: true
            visible: card.error !== ""
            text: card.error
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            color: Luna.Theme.colors.error
            font.family: Luna.Theme.uiFont
            font.pixelSize: 12
        }
        RowLayout {
            Layout.fillWidth: true
            Item { Layout.fillWidth: true }
            ActionButton {
                id: cancelButton
                text: "Cancel"
                onClicked: card.cancelled()
            }
            ActionButton {
                text: card.request && card.request.kind === "service" ? "Allow" : "Pair"
                selected: true
                visible: !Logic.isDisplay(card.request)
                enabled: Logic.validInput(card.request, input.text)
                onClicked: card.accepted(input.text)
            }
        }
    }
}
