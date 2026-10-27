import "../components"
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Luna 1.0 as Luna

ColumnLayout {
    spacing: 12

    SectionTitle {
        text: "Theme"
        Layout.topMargin: 0
    }

    Label {
        text: "Colors for your desktop and applications."
        color: Luna.Theme.foreground
        Layout.fillWidth: true
        wrapMode: Text.WordWrap
    }

    ButtonGroup {
        id: themes
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 12

        ThemeCard {
            name: "Tokyo Night"
            desktopColor: "#13141c"
            windowColor: "#24283b"
            accentColor: "#7aa2f7"
            checked: true
            ButtonGroup.group: themes
        }

        ThemeCard {
            name: "Luna Light"
            desktopColor: "#d8d6d0"
            windowColor: "#faf9f6"
            accentColor: "#416a91"
            ButtonGroup.group: themes
        }

    }

    SectionTitle {
        text: "Style"
    }

    SettingsGroup {
        SettingsRow {
            title: "Color mode"
            description: "Preferred appearance for supported applications"

            Choice {
                model: ["Dark", "Light"]
                implicitWidth: 120
                Accessible.name: "Color mode"
            }

        }

        SettingsRow {
            title: "Follow theme mode"
            description: "Use the color mode provided by your theme"
            divider: false

            Toggle {
                checked: true
                Accessible.name: "Follow theme mode"
            }

        }

    }

    SectionTitle {
        text: "Accent color"
    }

    SettingsGroup {
        SettingsRow {
            title: "Theme accent"
            description: Luna.Theme.snapshot.name + " · " + Luna.Theme.accent
            divider: false

            Rectangle {
                width: 24
                height: 24
                radius: 12
                color: Luna.Theme.accent
            }

        }

    }

}
