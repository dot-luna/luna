import "../components"
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ColumnLayout {
    spacing: 12

    SectionTitle {
        text: "Wallpaper"
        Layout.topMargin: 0
    }

    Label {
        text: "Choose a background for your desktop."
        color: "#a6a6ad"
        Layout.fillWidth: true
        wrapMode: Text.WordWrap
    }

    ButtonGroup {
        id: wallpapers
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 10

        WallpaperCard {
            name: "Dusk"
            sky: "#484e6d"
            mountain: "#24283b"
            checked: true
            ButtonGroup.group: wallpapers
        }

        WallpaperCard {
            name: "Clay"
            sky: "#b18c73"
            mountain: "#65554e"
            ButtonGroup.group: wallpapers
        }

        WallpaperCard {
            name: "Pine"
            sky: "#80918b"
            mountain: "#394f49"
            ButtonGroup.group: wallpapers
        }

    }

    SectionTitle {
        text: "Source"
    }

    SettingsGroup {
        SettingsRow {
            title: "Follow theme wallpaper"
            description: "Use a wallpaper included with the selected theme"

            Toggle {
                checked: true
                Accessible.name: "Follow theme wallpaper"
            }

        }

        SettingsRow {
            title: "Image fit"
            divider: false

            Choice {
                model: ["Fill", "Fit", "Center"]
                implicitWidth: 120
                Accessible.name: "Image fit"
            }

        }

    }

    Label {
        text: "Sample wallpapers · file and URL import will be added later."
        color: "#a6a6ad"
        font.pixelSize: 12
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }

}
