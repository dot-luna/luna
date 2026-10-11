import "../components"
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ColumnLayout {
    spacing: 12

    SectionTitle {
        text: "Desktop shortcuts"
        Layout.topMargin: 0
    }

    Label {
        text: "Super is the Windows or Command key on your keyboard."
        color: "#a6a6ad"
        Layout.fillWidth: true
        wrapMode: Text.WordWrap
    }

    SettingsGroup {
        SettingsRow {
            title: "Open terminal"

            Label {
                text: "Super + Return"
                color: "#a6a6ad"
            }

        }

        SettingsRow {
            title: "Open browser"

            Label {
                text: "Super + Shift + Return"
                color: "#a6a6ad"
            }

        }

        SettingsRow {
            title: "Close window"

            Label {
                text: "Super + W"
                color: "#a6a6ad"
            }

        }

        SettingsRow {
            title: "Switch workspace"

            Label {
                text: "Super + 1–9"
                color: "#a6a6ad"
            }

        }

        SettingsRow {
            title: "Workspace 10"
            divider: false

            Label {
                text: "Super + 0"
                color: "#a6a6ad"
            }

        }

    }

    SectionTitle {
        text: "Navigate Luna Settings"
    }

    SettingsGroup {
        SettingsRow {
            title: "Move between controls"

            Label {
                text: "Tab / Shift + Tab"
                color: "#a6a6ad"
            }

        }

        SettingsRow {
            title: "Choose a page"

            Label {
                text: "Alt + 1–5"
                color: "#a6a6ad"
            }

        }

        SettingsRow {
            title: "Previous / next page"
            Label { text: "Ctrl + Shift + Tab / Ctrl + Tab"; color: "#a6a6ad" }
        }

        SettingsRow {
            title: "Focus navigation"

            Label {
                text: "Ctrl + L"
                color: "#a6a6ad"
            }

        }

        SettingsRow {
            title: "Close settings"
            divider: false

            Label {
                text: "Ctrl + Q"
                color: "#a6a6ad"
            }

        }

    }

}
