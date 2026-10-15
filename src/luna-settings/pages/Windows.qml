import "../components"
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ColumnLayout {
    spacing: 12

    SectionTitle {
        text: "Layout"
        Layout.topMargin: 0
    }

    SettingsGroup {
        SettingsRow {
            title: "Window gaps"
            description: "Space between tiled windows, in pixels"

            NumberField {
                from: 0
                to: 40
                value: 5
                Accessible.name: "Window gaps"
            }

        }

        SettingsRow {
            title: "Border width"
            description: "Window border thickness, in pixels"

            NumberField {
                from: 0
                to: 8
                value: 1
                Accessible.name: "Border width"
            }

        }

        SettingsRow {
            title: "Corner radius"
            description: "Window rounding, in pixels"
            divider: false

            NumberField {
                from: 0
                to: 30
                value: 0
                Accessible.name: "Corner radius"
            }

        }

    }

    SectionTitle {
        text: "Effects"
    }

    SettingsGroup {
        SettingsRow {
            title: "Background blur"
            description: "Blur the desktop behind translucent windows"

            Toggle {
                checked: true
                Accessible.name: "Background blur"
            }

        }

        SettingsRow {
            title: "Active window opacity"
            description: "Percentage of window opacity"
            divider: false

            NumberField {
                from: 30
                to: 100
                value: 90
                Accessible.name: "Active window opacity"
            }

        }

    }

}
