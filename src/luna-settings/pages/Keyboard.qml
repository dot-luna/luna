import "../components"
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Luna 1.0 as Luna

ColumnLayout {
    spacing: 12

    SectionTitle {
        text: "Desktop shortcuts"
        Layout.topMargin: 0
    }

    Label {
        text: "Super is the Windows or Command key on your keyboard."
        color: Luna.Theme.foreground
        Layout.fillWidth: true
        wrapMode: Text.WordWrap
    }

    SettingsGroup {
        SettingsRow {
            title: "Open terminal"

            Label {
                text: "Super + Return"
                color: Luna.Theme.foreground
            }

        }

        SettingsRow {
            title: "Open browser"

            Label {
                text: "Super + Shift + Return"
                color: Luna.Theme.foreground
            }

        }

        SettingsRow {
            title: "Close window"

            Label {
                text: "Super + W"
                color: Luna.Theme.foreground
            }

        }

        SettingsRow {
            title: "Switch workspace"

            Label {
                text: "Super + 1–9"
                color: Luna.Theme.foreground
            }

        }

        SettingsRow {
            title: "Workspace 10"
            divider: false

            Label {
                text: "Super + 0"
                color: Luna.Theme.foreground
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
                color: Luna.Theme.foreground
            }

        }

        SettingsRow {
            title: "Choose a page"

            Label {
                text: "Alt + 1–5"
                color: Luna.Theme.foreground
            }

        }

        SettingsRow {
            title: "Previous / next page"

            Label {
                text: "Ctrl + Shift + Tab / Ctrl + Tab"
                color: Luna.Theme.foreground
            }

        }

        SettingsRow {
            title: "Focus navigation"

            Label {
                text: "Ctrl + L"
                color: Luna.Theme.foreground
            }

        }

        SettingsRow {
            title: "Close settings"
            divider: false

            Label {
                text: "Ctrl + Q"
                color: Luna.Theme.foreground
            }

        }

    }

}
