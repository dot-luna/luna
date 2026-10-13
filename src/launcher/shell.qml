pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Hyprland
import Luna as Luna
import "Search.js" as Search
import "FontSelection.js" as FontSelection
import "System.js" as System

ShellRoot {
    id: shell

    property string menuScreenName: ""
    property string systemMessage: ""
    property bool hibernateAvailable: false
    property string currentMenu: ""
    readonly property bool appsView: currentMenu === "apps"
    readonly property bool fontsView: currentMenu === "install.style.font"
    readonly property bool removeFontsView: currentMenu === "remove.style.font"
    readonly property string fontRole: currentMenu === "style.font.ui" ? "ui" : currentMenu === "style.font.mono" ? "mono" : ""
    property var fontFamilies: []
    property string fontPreferenceMessage: ""
    property var installedFonts: []
    property string removalMessage: ""
    // Executables need filesystem paths; QML URL resolution can return a resource URL.
    readonly property string lunaCli: Quickshell.shellDir + "/../../bin/luna"
    property var fontResults: []
    property var fontSelection: []
    property string fontMessage: ""
    property string fontQuery: ""
    property bool fontPending: false

    // Keep missing theme fonts from falling back to a platform serif default.
    readonly property string uiFont: Qt.fontFamilies().some(family => family.toLowerCase() === Luna.Theme.uiFont.toLowerCase()) ? Luna.Theme.uiFont : "sans-serif"
    // Follow the platform text size while retaining the menu’s visual hierarchy.
    readonly property real textSize: Qt.application.font.pointSize > 0 ? Qt.application.font.pointSize : 10
    readonly property real textScale: textSize / 10
    // Routes define navigation; entries without a route remain placeholders.
    readonly property var menuEntries: [
        { name: "Apps", icon: "layout-grid", route: "apps" },
        { name: "Learn", icon: "book-open" },
        { name: "Trigger", icon: "zap" },
        { name: "Style", icon: "palette", route: "style" },
        { name: "Setup", icon: "sliders-horizontal", route: "setup" },
        { name: "Idle", icon: "moon", parent: "setup", parentLabel: "Setup", route: "setup.idle" },
        { name: "Auto Screensaver", icon: "monitor", parent: "setup.idle", parentLabel: "Setup › Idle", route: "setup.idle.screensaver" },
        { name: "Auto Lock", icon: "lock", parent: "setup.idle", parentLabel: "Setup › Idle", route: "setup.idle.lock" },
        { name: "Install", icon: "download", route: "install" },
        { name: "Remove", icon: "trash", route: "remove" },
        { name: "About", icon: "info" },
        { name: "System", icon: "power", route: "system" },
        { name: "Screensaver", action: "screensaver", icon: "monitor", parent: "system", parentLabel: "System" },
        { name: "Lock", action: "lock", icon: "lock", parent: "system", parentLabel: "System" },
        { name: "Suspend", action: "suspend", icon: "moon", parent: "system", parentLabel: "System" },
        { name: "Hibernate", action: "hibernate", icon: "snowflake", parent: "system", parentLabel: "System" },
        { name: "Logout", action: "logout", icon: "log-out", parent: "system", parentLabel: "System" },
        { name: "Reboot", action: "reboot", icon: "refresh-cw", parent: "system", parentLabel: "System" },
        { name: "Shutdown", action: "shutdown", icon: "power", parent: "system", parentLabel: "System" },
        { name: "Set Font", icon: "type", parent: "style", parentLabel: "Style", route: "style.font" },
        { name: "UI", icon: "type", parent: "style.font", parentLabel: "Style › Set Font", route: "style.font.ui" },
        { name: "Mono", icon: "type", parent: "style.font", parentLabel: "Style › Set Font", route: "style.font.mono" },
        { name: "Style", icon: "palette", parent: "install", parentLabel: "Install", route: "install.style" },
        { name: "Install Font", icon: "type", parent: "install.style", parentLabel: "Install › Style", route: "install.style.font" },
        { name: "Style", icon: "palette", parent: "remove", parentLabel: "Remove", route: "remove.style" },
        { name: "Remove Font", icon: "type", parent: "remove.style", parentLabel: "Remove › Style", route: "remove.style.font" }
    ]
    property var idleSettings: ({})
    readonly property var idleEntries: ["screensaver", "lock"].reduce((entries, setting) => entries.concat(
        [0, 60, 300, 600, 900, 1800, 3600].map(seconds => ({
            name: seconds === 0 ? "Disabled" : (seconds / 60) + " minutes",
            icon: setting === "lock" ? "lock" : "monitor",
            parent: "setup.idle." + setting,
            parentLabel: "Setup › Idle › " + (setting === "lock" ? "Auto Lock" : "Auto Screensaver"),
            idleSetting: setting, seconds: seconds
        }))), [])
    readonly property var availableMenuEntries: menuEntries.concat(idleEntries).filter(entry =>
        entry.action !== "hibernate" || hibernateAvailable)
    readonly property var matches: fontRole ? Search.installedFonts(fontFamilies, search.text) : removeFontsView ? Search.installedFonts(installedFonts, search.text) : fontsView ? fontResults : appsView
        ? Search.find(DesktopEntries.applications.values, search.text)
        : Search.rootEntries(availableMenuEntries, DesktopEntries.applications.values, search.text, currentMenu)

    function moveSelection(direction) {
        if (!matches.length)
            return;
        results.currentIndex = (results.currentIndex + direction + matches.length) % matches.length;
        results.positionViewAtIndex(results.currentIndex, ListView.Contain);
    }
    function jumpSelection(index) {
        if (!matches.length)
            return;
        results.currentIndex = Math.max(0, Math.min(matches.length - 1, index));
        results.positionViewAtIndex(results.currentIndex, ListView.Contain);
    }

    function pageSelection(direction) {
        const pageSize = Math.max(1, Math.floor(results.height / (48 * textScale + results.spacing)));
        jumpSelection(results.currentIndex + direction * pageSize);
    }

    function showMenu(route) {
        currentMenu = route;
        search.clear();
        results.currentIndex = matches.length ? 0 : -1;
        results.positionViewAtBeginning();
        search.forceActiveFocus();
    }

    function goBack() {
        showMenu(currentMenu.split(".").slice(0, -1).join("."));
    }

    function toggleFont(entry) {
        fontSelection = FontSelection.toggle(fontSelection, entry);
    }

    function tabSelection(direction) {
        if (fontsView || removeFontsView)
            toggleFont(matches[results.currentIndex]);
        moveSelection(direction);
    }

    function activate(entry) {
        if (fontRole) {
            if (!entry || fontPreferenceSet.running)
                return;
            fontPreferenceMessage = "";
            fontPreferenceSet.command = [lunaCli, "font", "set", fontRole, entry.family];
            fontPreferenceSet.running = true;
            return;
        }
        if (fontsView || removeFontsView) {
            const entries = FontSelection.targets(fontSelection, entry);
            if (!entries.length)
                return;
            const command = ["kitty", "--class", "luna-install", "--start-as", "normal",
                "-o", "remember_window_size=no", "--title", removeFontsView ? "Remove Fonts" : "Install Fonts",
                "--", "lua", "-E", Quickshell.shellDir + (removeFontsView ? "/remove-font.lua" : "/install-font.lua")];
            Quickshell.execDetached(command.concat(FontSelection.argumentsFor(entries, removeFontsView)));
            fontSelection = [];
            panel.visible = false;
            return;
        }
        if (!entry)
            return;
        if (entry.idleSetting) {
            if (!idleUpdate.running) {
                systemMessage = "";
                idleUpdate.command = [lunaCli, "idle", "set", entry.idleSetting, String(entry.seconds)];
                idleUpdate.running = true;
            }
            return;
        }
        if (entry.action) {
            if (systemAction.running)
                return;
            const command = System.command(entry.action, lunaCli);
            if (!command.length)
                return;
            systemMessage = "";
            systemAction.command = command;
            if (["lock", "suspend", "hibernate", "screensaver"].includes(entry.action))
                panel.visible = false;
            systemAction.running = true;
            return;
        }
        if (typeof entry.execute !== "function") {
            if (entry.route)
                showMenu(entry.route);
            return;
        }
        if (!entry.command || !entry.command.length)
            return;

        // Quickshell's desktop-entry execution does not wrap Terminal=true entries.
        if (entry.runInTerminal) {
            Quickshell.execDetached({
                command: ["kitty", "--"].concat(entry.command),
                workingDirectory: entry.workingDirectory
            });
        } else {
            entry.execute();
        }
        panel.visible = false;
    }

    function open() {
        if (!hibernateCheck.running)
            hibernateCheck.running = true;
        if (!idleRead.running)
            idleRead.running = true;
        const monitor = Hyprland.focusedMonitor;
        panel.screen = Quickshell.screens.find(screen => monitor && screen.name === monitor.name) || Quickshell.screens[0];
        menuScreenName = panel.screen.name;
        systemMessage = "";
        fontSelection = [];
        currentMenu = "";
        search.text = "";
        results.currentIndex = matches.length ? 0 : -1;
        panel.visible = true;
        focusDelay.restart();
    }

    // Serialize remote lookups and discard stale responses as the query or route changes.
    function queueFontSearch() {
        fontResults = [];
        fontMessage = "";
        fontPending = fontsView && search.text.trim().length >= 2;
        fontDelay.restart();
    }

    function searchFonts() {
        if (!fontsView || !panel.visible || search.text.trim().length < 2 || fontSearch.running)
            return;
        fontQuery = search.text.trim();
        fontSearch.command = ["timeout", "30s", lunaCli, "font", "search", fontQuery, "--aur", "--json"];
        fontSearch.running = true;
    }

    onCurrentMenuChanged: {
        systemMessage = "";
        fontSelection = [];
        queueFontSearch();
    }

    onRemoveFontsViewChanged: {
        if (removeFontsView) {
            installedFonts = [];
            removalMessage = "";
            fontListing.running = true;
        }
    }

    Process {
        id: fontListing
        command: ["timeout", "30s", shell.lunaCli, "font", "list", "--json"]
        stdout: StdioCollector {}
        stderr: StdioCollector {}
        onExited: (code, status) => {
            if (!shell.removeFontsView)
                return;
            if (code !== 0) {
                console.warn("Font listing failed:", code, stderr.text.trim());
                shell.removalMessage = "Could not load installed fonts.";
                return;
            }
            try {
                shell.installedFonts = JSON.parse(stdout.text).results.map(entry =>
                    Object.assign({}, entry, {icon: "type"}));
            } catch (error) {
                shell.removalMessage = "Could not read installed fonts.";
            }
        }
    }

    Timer {
        id: fontDelay
        interval: 300
        onTriggered: shell.searchFonts()
    }
    Process {
        id: fontSearch
        stdout: StdioCollector {}
        stderr: StdioCollector {}
        onExited: (code, status) => {
            if (!shell.fontsView || !panel.visible)
                return;
            if (shell.fontQuery !== search.text.trim()) {
                fontDelay.restart();
                return;
            }
            shell.fontPending = false;
            if (code !== 0) {
                console.warn("Font search failed:", code, stderr.text.trim());
                shell.fontMessage = code === 124 ? "Search timed out. Try again." : "Font search failed. Try again.";
                return;
            }
            try {
                const response = JSON.parse(stdout.text);
                shell.fontResults = response.results.map(entry => Object.assign({}, entry, {icon: "type"}));
                shell.fontMessage = response.warning || "";
            } catch (error) {
                shell.fontMessage = "Could not read font results.";
            }
        }
    }

    onFontRoleChanged: {
        fontFamilies = [];
        fontPreferenceMessage = "";
        if (fontRole && !fontFamilyList.running) {
            fontFamilyList.requestedRole = fontRole;
            fontFamilyList.command = [lunaCli, "font", "families", fontRole];
            fontFamilyList.running = true;
        }
    }

    Process {
        id: fontFamilyList
        property string requestedRole: ""
        stdout: StdioCollector {}
        stderr: StdioCollector {}
        onExited: (code, status) => {
            if (!shell.fontRole)
                return;
            if (requestedRole !== shell.fontRole) {
                requestedRole = shell.fontRole;
                command = [shell.lunaCli, "font", "families", requestedRole];
                running = true;
                return;
            }
            try {
                if (code !== 0)
                    throw new Error(stderr.text);
                shell.fontFamilies = JSON.parse(stdout.text).results.map(entry =>
                    Object.assign({}, entry, {icon: "type"}));
            } catch (error) {
                shell.fontPreferenceMessage = "Could not load installed font families.";
            }
        }
    }
    Process {
        id: fontPreferenceSet
        stdout: StdioCollector {}
        stderr: StdioCollector {}
        onExited: (code, status) => {
            if (code !== 0) {
                shell.fontPreferenceMessage = "Could not set font.";
                console.warn(stderr.text.trim());
                return;
            }
            Luna.Theme.applyFonts(JSON.parse(stdout.text));
            if (shell.fontRole) {
                const family = Luna.Theme.snapshot.fonts[shell.fontRole];
                shell.fontFamilies = shell.fontFamilies.map(entry =>
                    Object.assign({}, entry, {current: entry.family === family}));
            }
        }
    }

    Process {
        id: systemAction
        stdout: StdioCollector {}
        stderr: StdioCollector {}
        onExited: (code, status) => {
            if (code === 0) {
                panel.visible = false;
            } else {
                if (!panel.visible)
                    shell.open();
                shell.systemMessage = stderr.text.trim() || stdout.text.trim() || "System action failed.";
                console.warn(shell.systemMessage);
            }
        }
    }

    Process {
        id: hibernateCheck
        command: ["busctl", "--timeout=5", "call", "org.freedesktop.login1",
            "/org/freedesktop/login1", "org.freedesktop.login1.Manager", "CanHibernate"]
        running: true
        stdout: StdioCollector {}
        stderr: StdioCollector {}
        onExited: (code, status) => {
            const result = stdout.text.trim();
            shell.hibernateAvailable = code === 0 && (result === 's "yes"' || result === 's "challenge"');
        }
    }

    Process {
        id: idleRead
        command: [shell.lunaCli, "idle", "status"]
        stdout: StdioCollector {}
        stderr: StdioCollector {}
        onExited: (code, status) => {
            if (code === 0) shell.idleSettings = JSON.parse(stdout.text);
        }
    }
    Process {
        id: idleUpdate
        stdout: StdioCollector {}
        stderr: StdioCollector {}
        onExited: (code, status) => {
            if (code === 0) {
                // Lifecycle messages can precede the final JSON line.
                shell.idleSettings = JSON.parse(stdout.text.trim().split("\n").pop());
            } else {
                shell.systemMessage = stderr.text.trim() || "Could not update idle settings.";
            }
        }
    }

    onMatchesChanged: {
        results.currentIndex = matches.length ? 0 : -1;
        results.positionViewAtBeginning();
    }

    IpcHandler {
        function open(): void {
            shell.open();
        }
        function applyFonts(value: string): void {
            Luna.Theme.applyFonts(JSON.parse(value));
        }
        function ping(): string {
            return "ready";
        }
        function stop(): void {
            Qt.quit();
        }
        function toggle(): void {
            if (panel.visible)
                panel.visible = false;
            else
                shell.open();
        }

        target: "launcher"
    }
    // Cover every other output while open, including empty desktop areas where a
    // focus grab may not receive a new focused surface. The first click only dismisses.
    Variants {
        model: Quickshell.screens

        delegate: PanelWindow {
            required property var modelData
            screen: modelData
            visible: panel.visible && modelData.name !== shell.menuScreenName
            color: "transparent"
            exclusionMode: ExclusionMode.Ignore
            WlrLayershell.layer: WlrLayer.Overlay
            WlrLayershell.namespace: "luna-menu-dismiss"
            WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
            anchors { top: true; bottom: true; left: true; right: true }

            MouseArea {
                anchors.fill: parent
                acceptedButtons: Qt.AllButtons
                onPressed: panel.visible = false
            }
        }
    }
    PanelWindow {
        id: panel

        WlrLayershell.keyboardFocus: visible ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.namespace: "luna-launcher"
        color: "transparent"
        exclusionMode: ExclusionMode.Ignore
        visible: false
        onVisibleChanged: {
            if (!visible) {
                focusDelay.stop();
            }
        }

        anchors {
            bottom: true
            left: true
            right: true
            top: true
        }
        Timer {
            id: focusDelay

            interval: 50

            onTriggered: {
                if (panel.visible) {
                    search.forceActiveFocus(Qt.TabFocusReason);
                }
            }
        }
        Shortcut {
            enabled: panel.visible
            sequence: "Escape"

            onActivated: shell.currentMenu ? shell.goBack() : panel.visible = false
        }
        Shortcut {
            enabled: panel.visible && shell.currentMenu !== ""
            sequence: "Alt+Left"
            onActivated: shell.goBack()
        }
        MouseArea {
            anchors.fill: parent

            acceptedButtons: Qt.AllButtons
            onPressed: panel.visible = false
        }
        Rectangle {
            id: card

            readonly property real cornerRadius: Math.min(Luna.Theme.barRounding, width / 2, height / 2)
            readonly property var selectedEntry: shell.matches[results.currentIndex] || null

            anchors.centerIn: parent
            width: Math.min(640 * shell.textScale, panel.width - 2 * Math.max(16, Luna.Theme.outerGap))
            height: Math.min(476 * shell.textScale, panel.height - 2 * Math.max(16, Luna.Theme.outerGap))
            // Supply theme alpha only; Hyprland renders blur behind this surface.
            color: Qt.rgba(Luna.Theme.background.r, Luna.Theme.background.g,
                Luna.Theme.background.b, Luna.Theme.decoration.active_opacity)
            radius: cornerRadius
            border.color: Luna.Theme.muted
            border.width: Luna.Theme.borderWidth

            // The overlay catches outside clicks; keep clicks within the panel local.
            MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons }

            ListPointer {
                anchors.fill: parent
                view: results
                onHoveredIndex: index => results.currentIndex = index
            }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Luna.Theme.borderWidth
                spacing: 0

                // Header: one continuous search surface, without a nested input box.
                Item {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 72 * shell.textScale

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 22
                        anchors.rightMargin: 18
                        spacing: 14

                        Luna.Icon {
                            name: "search"
                            ink: search.text.length ? Luna.Theme.accent : Luna.Theme.foreground
                            Layout.preferredWidth: 20
                            Layout.preferredHeight: 20
                        }
                        TextField {
                            id: search

                            Accessible.description: card.selectedEntry ? card.selectedEntry.name : "No matching entries"
                            Accessible.name: (shell.fontsView || shell.removeFontsView || shell.fontRole) ? "Search fonts" : shell.appsView ? "Search applications" : "Search menu"
                            Layout.fillWidth: true
                            implicitHeight: 48 * shell.textScale
                            padding: 0
                            color: Luna.Theme.brightForeground
                            font.family: shell.uiFont
                            font.pointSize: shell.textSize + 3
                            placeholderText: "Search…"
                            placeholderTextColor: Luna.Theme.foreground
                            selectByMouse: true
                            selectedTextColor: Luna.Theme.accentForeground
                            selectionColor: Luna.Theme.accent
                            background: Item {}

                            onAccepted: shell.activate(card.selectedEntry)
                            onTextChanged: shell.queueFontSearch()

                            Keys.onPressed: event => {
                                if (event.key === Qt.Key_PageUp)
                                    shell.pageSelection(-1);
                                else if (event.key === Qt.Key_PageDown)
                                    shell.pageSelection(1);
                                else if (event.key === Qt.Key_Home)
                                    shell.jumpSelection(0);
                                else if (event.key === Qt.Key_End)
                                    shell.jumpSelection(shell.matches.length - 1);
                                else {
                                    event.accepted = false;
                                    return;
                                }
                                event.accepted = true;
                            }
                            Keys.onBacktabPressed: shell.tabSelection(-1)
                            Keys.onDownPressed: shell.moveSelection(1)
                            Keys.onTabPressed: shell.tabSelection(1)
                            Keys.onUpPressed: shell.moveSelection(-1)
                        }
                        Label {
                            visible: shell.fontSelection.length > 0
                            text: shell.fontSelection.length + " selected"
                            color: Luna.Theme.accent
                            font.family: shell.uiFont
                            font.pointSize: shell.textSize
                        }
                        Button {
                            id: clearSearch

                            visible: search.text.length > 0
                            Accessible.name: "Clear search"
                            focusPolicy: Qt.NoFocus
                            implicitWidth: 28
                            implicitHeight: 28
                            padding: 7
                            background: Rectangle {
                                color: clearSearch.hovered ? Luna.Theme.selection : "transparent"
                                radius: Math.min(Luna.Theme.barRounding, height / 2)
                            }
                            contentItem: Luna.Icon { name: "x"; ink: Luna.Theme.foreground }
                            onClicked: { search.clear(); search.forceActiveFocus(); }
                        }
                    }
                }
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 1
                    color: Luna.Theme.muted
                }

                // Body stays the same height for short searches and empty results.
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.margins: 12
                    spacing: 8

                    Label {
                        Layout.fillWidth: true
                        visible: shell.systemMessage.length > 0
                        text: shell.systemMessage
                        wrapMode: Text.Wrap
                        color: Luna.Theme.foreground
                        font.family: shell.uiFont
                        font.pointSize: shell.textSize
                    }
                    Label {
                        Layout.fillWidth: true
                        visible: (shell.fontsView || shell.removeFontsView || shell.fontRole) && text.length > 0
                        text: shell.fontRole ? shell.fontPreferenceMessage : shell.removeFontsView ? shell.removalMessage : shell.fontMessage
                        wrapMode: Text.Wrap
                        color: Luna.Theme.foreground
                        font.family: shell.uiFont
                        font.pointSize: shell.textSize
                    }
                    ListView {
                        id: results

                        Accessible.name: shell.appsView ? "Applications" : "Menu entries"
                        Accessible.role: Accessible.List
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        boundsBehavior: Flickable.StopAtBounds
                        clip: true
                        currentIndex: -1
                        model: shell.matches
                        spacing: 4

                        ScrollBar.vertical: ScrollBar {
                            id: scrollbar
                            policy: ScrollBar.AsNeeded
                            implicitWidth: 3
                            contentItem: Rectangle {
                                implicitWidth: 3
                                color: scrollbar.pressed ? Luna.Theme.accent : Luna.Theme.muted
                                radius: Math.min(Luna.Theme.barRounding, width / 2)
                                visible: scrollbar.size < 1
                            }
                            background: Item {}
                        }
                        delegate: Button {
                            id: result

                            required property int index
                            required property var modelData
                            readonly property bool selected: results.currentIndex === index
                            readonly property bool marked: (shell.fontsView || shell.removeFontsView) && FontSelection.contains(shell.fontSelection, modelData)
                            readonly property bool applicationEntry: typeof modelData.execute === "function"

                            Accessible.name: modelData.name
                            ToolTip.visible: hovered && !!modelData.targets
                            ToolTip.text: modelData.description || ""
                            Accessible.role: Accessible.ListItem
                            focusPolicy: Qt.NoFocus
                            height: 48 * shell.textScale
                            // Overlay the slim scrollbar instead of reserving a right-only gutter.
                            width: results.width
                            leftPadding: 12
                            rightPadding: 12
                            topPadding: 8
                            bottomPadding: 8
                            hoverEnabled: true

                            background: Rectangle {
                                color: result.selected || result.marked ? Luna.Theme.selection : "transparent"
                                border.width: result.marked ? 1 : 0
                                border.color: Luna.Theme.accent
                                radius: Math.min(Luna.Theme.barRounding, width / 2, height / 2)
                            }
                            contentItem: RowLayout {
                                spacing: 14

                                Item {
                                    Layout.preferredWidth: 20
                                    Layout.preferredHeight: 20

                                    Image {
                                        id: appIcon
                                        anchors.fill: parent
                                        visible: result.applicationEntry
                                        source: !result.applicationEntry || !result.modelData.icon ? ""
                                            : result.modelData.icon.startsWith("/")
                                                ? "file://" + result.modelData.icon.split("/").map(encodeURIComponent).join("/")
                                                : Quickshell.iconPath(result.modelData.icon, true)
                                        sourceSize: Qt.size(32, 32)
                                        fillMode: Image.PreserveAspectFit
                                    }
                                    Luna.Icon {
                                        anchors.fill: parent
                                        visible: !result.applicationEntry || appIcon.status !== Image.Ready
                                        name: result.applicationEntry ? "layout-grid" : result.modelData.icon
                                        ink: result.selected ? Luna.Theme.selectionForeground : Luna.Theme.foreground
                                    }
                                }
                                Label {
                                    Layout.fillWidth: true
                                    color: result.selected ? Luna.Theme.selectionForeground : Luna.Theme.brightForeground
                                    font.family: shell.uiFont
                                    font.pointSize: shell.textSize + 1
                                    font.weight: result.selected ? Font.Medium : Font.Normal
                                    elide: Text.ElideRight
                                    text: result.modelData.name
                                    textFormat: Text.PlainText
                                }
                                Label {
                                    visible: text.length > 0
                                    text: result.modelData.idleSetting
                                        ? (shell.idleSettings[result.modelData.idleSetting + "_seconds"] === result.modelData.seconds ? "Current" : "")
                                        : result.modelData.family ? (result.modelData.current ? "Current" : "") : result.modelData.repository
                                        ? (result.modelData.repository === "aur" ? "AUR" : result.modelData.repository)
                                            + (result.modelData.fileCount > 1 ? " · " + result.modelData.fileCount + " files" : "")
                                            + (result.modelData.installed ? " · Installed" : "")
                                        : result.applicationEntry
                                        ? (shell.appsView ? "" : "Apps")
                                        : ((result.modelData.parent || "") !== shell.currentMenu ? result.modelData.parentLabel || "" : "")
                                    color: result.selected ? Luna.Theme.selectionForeground : Luna.Theme.foreground
                                    opacity: 0.65
                                    font.family: shell.uiFont
                                    font.pointSize: Math.max(1, shell.textSize - 1)
                                    textFormat: Text.PlainText
                                }
                                Luna.Icon {
                                    Layout.preferredWidth: 14
                                    Layout.preferredHeight: 14
                                    name: "chevron-right"
                                    ink: Luna.Theme.selectionForeground
                                    visible: result.selected && !result.applicationEntry && !result.modelData.repository && !result.modelData.family && !result.modelData.action && !result.modelData.idleSetting
                                }
                            }
                            onClicked: {
                                results.currentIndex = index;
                                if (shell.fontsView || shell.removeFontsView)
                                    shell.toggleFont(modelData);
                                else
                                    shell.activate(modelData);
                            }

                        }
                        ColumnLayout {
                            anchors.centerIn: parent
                            spacing: 12
                            visible: results.count === 0

                            Luna.Icon {
                                Layout.alignment: Qt.AlignHCenter
                                Layout.preferredWidth: 28
                                Layout.preferredHeight: 28
                                name: "search"
                                ink: Luna.Theme.foreground
                            }
                            Label {
                                Layout.alignment: Qt.AlignHCenter
                                text: shell.fontRole
                                    ? (fontFamilyList.running ? "Loading…" : shell.fontPreferenceMessage ? "" : "No matching fonts")
                                    : shell.removeFontsView
                                    ? (fontListing.running ? "Loading…" : shell.removalMessage ? "" : "No matching installed fonts")
                                    : shell.fontsView
                                    ? (search.text.trim().length < 2 ? "Type a font name" : shell.fontPending ? "Searching…" : shell.fontMessage ? "" : "No matching fonts")
                                    : search.text.trim() ? "No matching entries" : shell.appsView ? "No applications found" : "No menu entries"
                                color: Luna.Theme.foreground
                                font.family: shell.uiFont
                                font.pointSize: shell.textSize
                            }
                        }
                    }
                }

            }
        }
    }
}
