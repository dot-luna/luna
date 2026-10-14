pragma Singleton
import QtQuick
import Quickshell.Services.Mpris
import "MediaLogic.js" as Logic

QtObject {
    id: media

    readonly property var players: Mpris.players.values
    property string previousName: ""
    readonly property var player: Logic.choose(players, previousName)
    readonly property bool available: player !== null
    readonly property bool isPlaying: !!(player && player.isPlaying)

    // Remember outside the binding evaluation, so selection never loops on itself.
    onPlayerChanged: Qt.callLater(function() {
        if (media.player) media.previousName = media.player.dbusName;
    })

    function run(action) {
        return Logic.run(player, action);
    }
}
