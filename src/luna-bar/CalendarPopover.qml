pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import Luna as Luna
import "components"
import "Calendar.js" as Calendar

PanelWindow {
    id: panel

    required property var config
    required property date currentDate
    property int topOffset: 32
    property int displayedYear: currentDate.getFullYear()
    property int displayedMonth: currentDate.getMonth()
    property date selectedDate: currentDate
    readonly property var cells: Calendar.monthDays(displayedYear, displayedMonth, config.week_start)

    function today() {
        displayedYear = currentDate.getFullYear();
        displayedMonth = currentDate.getMonth();
        selectedDate = currentDate;
    }
    function open() {
        today();
        visible = true;
        focusDelay.restart();
    }
    function dismiss() {
        focusDelay.stop();
        visible = false;
    }
    function changeMonth(amount) {
        const date = new Date(displayedYear, displayedMonth + amount, 1, 12);
        displayedYear = date.getFullYear();
        displayedMonth = date.getMonth();
    }

    WlrLayershell.keyboardFocus: visible ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "luna-calendar"
    color: "transparent"
    exclusionMode: ExclusionMode.Ignore
    visible: false
    onVisibleChanged: if (!visible && focusDelay) focusDelay.stop()
    anchors { top: true; bottom: true; left: true; right: true }

    Timer {
        id: focusDelay
        interval: 50
        onTriggered: if (panel.visible) monthTitle.forceActiveFocus(Qt.OtherFocusReason)
    }
    Shortcut {
        enabled: panel.visible
        context: Qt.ApplicationShortcut
        sequence: "Escape"
        onActivated: panel.dismiss()
        onActivatedAmbiguously: panel.dismiss()
    }
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.AllButtons
        onPressed: panel.dismiss()
    }

    component NavigationButton: Button {
        id: navigation
        focusPolicy: Qt.StrongFocus
        implicitHeight: 30
        implicitWidth: Math.max(30, contentItem.implicitWidth + 12)
        background: Rectangle {
            color: navigation.hovered ? Luna.Theme.selection : "transparent"
            border.width: navigation.visualFocus ? 1 : 0
            border.color: Luna.Theme.accent
            radius: Luna.Theme.barRounding
        }
        contentItem: Label {
            text: navigation.text
            color: Luna.Theme.brightForeground
            font.family: Luna.Theme.uiFont
            font.pixelSize: 14
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
    }

    Rectangle {
        id: card
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        anchors.topMargin: panel.topOffset + Luna.Theme.outerGap
        width: Math.min(360, panel.width - 2 * Luna.Theme.outerGap)
        height: Math.min(body.implicitHeight + 40, Math.max(0, panel.height - y - Luna.Theme.outerGap))
        color: Luna.Theme.background
        border.color: Luna.Theme.muted
        border.width: Luna.Theme.borderWidth
        radius: Math.min(Luna.Theme.barRounding, width / 2, height / 2)
        clip: true

        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.AllButtons
        }
        ScrollView {
            id: scroll
            anchors.fill: parent
            anchors.margins: 20
            contentWidth: availableWidth
            contentHeight: body.implicitHeight
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            ColumnLayout {
                id: body
                width: scroll.availableWidth
                spacing: 18
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 5
                    Label {
                        text: Qt.formatDateTime(panel.currentDate, panel.config.use_24_hour ? "HH:mm" : "h:mm AP")
                        color: Luna.Theme.brightForeground
                        font.family: Luna.Theme.uiFont
                        font.pixelSize: 34
                    }
                    Label {
                        Layout.fillWidth: true
                        text: Qt.formatDateTime(panel.currentDate, "dddd, MMMM d, yyyy")
                        elide: Text.ElideRight
                        color: Luna.Theme.foreground
                        font.family: Luna.Theme.uiFont
                        font.pixelSize: 12
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    NavigationButton {
                        id: monthTitle
                        Layout.fillWidth: true
                        text: Qt.formatDateTime(new Date(panel.displayedYear, panel.displayedMonth, 1, 12), "MMMM yyyy")
                        Accessible.name: text + ", go to current month"
                        onClicked: panel.today()
                    }
                    NavigationButton {
                        text: "‹"
                        Accessible.name: "Previous month"
                        onClicked: panel.changeMonth(-1)
                    }
                    NavigationButton {
                        text: "›"
                        Accessible.name: "Next month"
                        onClicked: panel.changeMonth(1)
                    }
                }
                GridLayout {
                    Layout.fillWidth: true
                    columns: 7
                    columnSpacing: 3
                    rowSpacing: 4
                    Repeater {
                        model: 7
                        delegate: Label {
                            required property int index
                            Layout.fillWidth: true
                            Layout.preferredWidth: 1
                            text: Qt.formatDateTime(new Date(2023, 0, 1 + (index + panel.config.week_start) % 7, 12), "ddd")
                            color: Luna.Theme.foreground
                            font.family: Luna.Theme.uiFont
                            font.pixelSize: 10
                            horizontalAlignment: Text.AlignHCenter
                        }
                    }
                    Repeater {
                        model: panel.cells
                        delegate: Button {
                            id: day
                            required property var modelData
                            readonly property bool isToday: Calendar.sameDay(modelData, panel.currentDate)
                            readonly property bool selected: Calendar.sameDay(modelData, panel.selectedDate)
                            Layout.fillWidth: true
                            Layout.preferredWidth: 1
                            implicitHeight: 32
                            focusPolicy: Qt.StrongFocus
                            Accessible.name: Qt.formatDateTime(modelData, "dddd, MMMM d, yyyy")
                            background: Rectangle {
                                color: day.isToday ? Luna.Theme.accent : day.hovered ? Luna.Theme.selection : "transparent"
                                border.color: Luna.Theme.accent
                                border.width: (day.selected && !day.isToday) || day.visualFocus ? 1 : 0
                                radius: Math.min(Luna.Theme.barRounding, width / 2, height / 2)
                            }
                            contentItem: Label {
                                text: day.modelData.getDate()
                                color: day.isToday ? Luna.Theme.accentForeground : day.hovered ? Luna.Theme.selectionForeground : Luna.Theme.foreground
                                opacity: day.modelData.getMonth() === panel.displayedMonth ? 1 : 0.4
                                font.family: Luna.Theme.uiFont
                                font.pixelSize: 12
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                            }
                            onClicked: panel.selectedDate = modelData
                        }
                    }
                }
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 1
                    color: Luna.Theme.muted
                    visible: panel.config.world_clocks.length > 0
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 10
                    visible: panel.config.world_clocks.length > 0
                    Repeater {
                        model: panel.config.world_clocks
                        delegate: WorldClock {
                            required property var modelData
                            Layout.fillWidth: true
                            city: modelData
                            instant: panel.currentDate
                            use24Hour: panel.config.use_24_hour
                            updating: panel.visible
                        }
                    }
                }
            }
        }
    }
}
