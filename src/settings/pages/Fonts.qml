import "../components"
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ColumnLayout {
    spacing: 12

    SectionTitle {
        text: "Desktop fonts"
        Layout.topMargin: 0
    }

    SettingsGroup {
        SettingsRow {
            title: "Interface"

            Choice {
                model: ["Noto Sans", "Inter", "Cantarell"]
                implicitWidth: 180
                Accessible.name: "Interface font"
            }

        }

        SettingsRow {
            title: "Monospace"

            Choice {
                model: ["JetBrains Mono", "Noto Sans Mono", "Iosevka"]
                implicitWidth: 180
                Accessible.name: "Monospace font"
            }

        }

        SettingsRow {
            title: "Font size"
            description: "Size in points"
            divider: false

            NumberField {
                from: 8
                to: 24
                value: 11
                Accessible.name: "Font size"
            }

        }

    }

    SectionTitle {
        text: "Preview"
    }

    SettingsGroup {
        SettingsRow {
            title: "The quick brown fox jumps over the lazy dog."
            description: "ABCDEFGHIJKLMNOPQRSTUVWXYZ\nabcdefghijklmnopqrstuvwxyz · 0123456789"
            divider: false
        }

    }

    Label {
        text: "Sample font names · this preview does not install or change fonts."
        color: "#a6a6ad"
        font.pixelSize: 12
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }

}
