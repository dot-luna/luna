pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Quickshell.Io
import Luna as Luna

RowLayout {
    id: worldClock

    required property var city
    required property date instant
    required property bool use24Hour
    required property bool updating
    property string displayTime: "—"
    property string displayDate: ""
    spacing: 16

    // Coreutils uses the system timezone database, including DST and fractional offsets.
    function refresh() {
        if (!updating || !city || !query || query.running)
            return;
        query.command = ["env", "TZ=" + city.timezone, "date", "--date=@" + Math.floor(instant.getTime() / 1000),
            use24Hour ? "+%H:%M%n%a, %d %b" : "+%I:%M %p%n%a, %d %b"];
        query.running = true;
    }

    onInstantChanged: refresh()
    onUpdatingChanged: refresh()
    Component.onCompleted: refresh()

    Process {
        id: query
        stdout: StdioCollector {
            onStreamFinished: {
                const parts = text.trim().split("\n");
                worldClock.displayTime = parts[0] || "—";
                worldClock.displayDate = parts[1] || "";
            }
        }
    }
    ColumnLayout {
        Layout.fillWidth: true
        spacing: 2
        Label {
            Layout.fillWidth: true
            text: worldClock.city.label
            textFormat: Text.PlainText
            elide: Text.ElideRight
            color: Luna.Theme.brightForeground
            font.family: Luna.Theme.uiFont
            font.pixelSize: 13
        }
        Label {
            Layout.fillWidth: true
            text: worldClock.displayDate
            elide: Text.ElideRight
            color: Luna.Theme.foreground
            font.family: Luna.Theme.uiFont
            font.pixelSize: 10
        }
    }
    Label {
        Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
        text: worldClock.displayTime
        color: Luna.Theme.brightForeground
        font.family: Luna.Theme.uiFont
        font.pixelSize: 17
        font.weight: Font.Medium
    }
}
