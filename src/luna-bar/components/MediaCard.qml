pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Luna as Luna
import "../MediaLogic.js" as Logic

Rectangle {
    id: card

    required property var media
    readonly property var player: media.player
    readonly property string artwork: Logic.localArt(player ? player.trackArtUrl : "")

    implicitHeight: content.implicitHeight + 24
    color: Luna.Theme.lighterBackground
    radius: Math.min(8, Luna.Theme.barRounding)
    visible: !!player

    ColumnLayout {
        id: content
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.margins: 12
        spacing: 10

        RowLayout {
            Layout.fillWidth: true
            spacing: 12
            Image {
                Layout.preferredWidth: 48
                Layout.preferredHeight: 48
                visible: status === Image.Ready
                source: card.artwork
                sourceSize: Qt.size(96, 96)
                asynchronous: true
                fillMode: Image.PreserveAspectFit
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                Label {
                    Layout.fillWidth: true
                    text: card.player ? card.player.trackTitle || card.player.trackAlbum || card.player.identity || "Media" : ""
                    textFormat: Text.PlainText
                    color: Luna.Theme.brightForeground
                    font.family: Luna.Theme.uiFont
                    font.pixelSize: 13
                    font.weight: Font.Medium
                    wrapMode: Text.Wrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                }
                Label {
                    Layout.fillWidth: true
                    visible: text.length > 0
                    text: card.player ? card.player.trackArtist || "" : ""
                    textFormat: Text.PlainText
                    color: Luna.Theme.foreground
                    font.family: Luna.Theme.uiFont
                    font.pixelSize: 11
                    elide: Text.ElideRight
                }
            }
        }
        RowLayout {
            Layout.alignment: Qt.AlignHCenter
            visible: Logic.supported(card.player, "previous") || Logic.supported(card.player, "play-pause")
                || Logic.supported(card.player, "next")
            spacing: 8
            ActionButton {
                implicitWidth: 34
                visible: Logic.supported(card.player, "previous")
                symbol: "skip-back"
                Accessible.name: "Previous track"
                onClicked: card.media.run("previous")
            }
            ActionButton {
                implicitWidth: 38
                visible: Logic.supported(card.player, "play-pause")
                symbol: card.player && card.player.isPlaying ? "pause" : "play"
                selected: true
                Accessible.name: card.player && card.player.isPlaying ? "Pause" : "Play"
                onClicked: card.media.run("play-pause")
            }
            ActionButton {
                implicitWidth: 34
                visible: Logic.supported(card.player, "next")
                symbol: "skip-forward"
                Accessible.name: "Next track"
                onClicked: card.media.run("next")
            }
        }
    }
}
