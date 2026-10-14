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
import "Keybindings.js" as Keybindings
import "FontSelection.js" as FontSelection
import "EmojiSelection.js" as EmojiSelection
import "System.js" as System

ShellRoot {
    id: shell

    readonly property bool clipboardView: currentMenu === "insert.clipboard"
    readonly property bool emojiView: currentMenu === "insert.emoji"
    readonly property string gifSource: currentMenu === "insert.gifs" ? "giphy" : ""
    readonly property bool insertView: clipboardView || emojiView || gifSource !== ""
    readonly property bool gridView: emojiView || gifSource !== ""
    readonly property var selectionView: gridView ? insertGrid : results
    property var emojiSelection: []
    property var emojiEntries: []
    readonly property var emojiArtwork: emojiEntries.reduce((map, entry) => {
        map[entry.emoji] = entry.artwork || "";
        return map;
    }, ({}))
    property var gifEntries: []
    property string gifQuery: ""
    property string requestedGifSource: ""
    property int gifOffset: 0
    property bool gifAppending: false
    property bool gifHasMore: false
    property bool gifNeedsKey: false
    readonly property bool giphySetupView: !!gifSource && gifNeedsKey
    onGiphySetupViewChanged: if (giphySetupView && panel.visible) giphySetupButton.forceActiveFocus()

    function setupGiphy() {
        Quickshell.execDetached(["kitty", "--class", "luna-install", "--start-as", "normal", "-o", "remember_window_size=no",
            "--title", "GIPHY Setup", "--", lunaCli, "insert", "configure"]);
        panel.visible = false;
    }
    readonly property var insertEntry: insertView ? (matches[shell.selectionView.currentIndex] || ({})) : ({})

    onEmojiViewChanged: if (emojiView && !emojiEntries.length && !emojiListing.running) emojiListing.running = true
    onGifSourceChanged: queueGifs()

    function queueGifs() {
        gifEntries = [];
        gifHasMore = false;
        gifNeedsKey = false;
        if (gifSource) gifDelay.restart();
    }
    function fetchGifs(offset) {
        if (!gifSource || gifSearch.running) return;
        gifQuery = search.text;
        requestedGifSource = gifSource;
        gifOffset = offset;
        systemMessage = "";
        gifSearch.command = [lunaCli, "insert", "gifs", gifQuery, String(offset)];
        gifSearch.running = true;
    }
    function loadMoreGifs() {
        if (panel.visible && gifSource && gifHasMore && !gifAppending && !gifSearch.running
                && gifQuery === search.text && gifEntries.length > 0)
            fetchGifs(gifEntries.length);
    }
    Timer {
        id: gifDelay
        interval: 400
        onTriggered: shell.fetchGifs(0)
    }
    Process {
        id: emojiListing
        command: [shell.lunaCli, "insert", "emoji"]
        stdout: StdioCollector {}
        stderr: StdioCollector {}
        onExited: (code, status) => {
            if (code === 0) shell.emojiEntries = JSON.parse(stdout.text).results;
            else shell.systemMessage = "Could not load emoji data.";
        }
    }
    Process {
        id: gifSearch
        stdout: StdioCollector {}
        stderr: StdioCollector {}
        onExited: (code, status) => {
            if (!shell.gifSource) return;
            if (shell.requestedGifSource !== shell.gifSource || shell.gifQuery !== search.text) {
                gifDelay.restart();
                return;
            }
            if (code !== 0) {
                shell.systemMessage = "Could not load GIFs. Check your connection or GIPHY key.";
                return;
            }
            try {
                const response = JSON.parse(stdout.text);
                const previousIndex = shell.selectionView.currentIndex;
                const previousScroll = insertGrid.contentY;
                shell.gifAppending = shell.gifOffset > 0;
                shell.gifEntries = shell.gifAppending ? shell.gifEntries.concat(response.results) : response.results;
                if (shell.gifAppending) {
                    insertGrid.currentIndex = previousIndex;
                    insertGrid.contentY = previousScroll;
                }
                shell.gifHasMore = response.hasMore && response.results.length > 0;
                shell.gifAppending = false;
                shell.gifNeedsKey = response.needsKey || false;
                shell.systemMessage = response.message || "";
            } catch (error) {
                shell.systemMessage = "Could not read GIF results.";
            }
        }
    }

    property var clipboardEntries: []
    property var clipboardPreview: ({})
    property string clipboardTarget: ""
    property string previewRequested: ""
    readonly property string previewId: clipboardView && matches[shell.selectionView.currentIndex] ? matches[shell.selectionView.currentIndex].id : ""
    onPreviewIdChanged: loadClipboardPreview()

    function loadClipboardPreview() {
        clipboardPreview = ({});
        if (!previewId || clipboardPreviewProcess.running)
            return;
        previewRequested = previewId;
        clipboardPreviewProcess.command = [lunaCli, "clipboard", "preview", previewId];
        clipboardPreviewProcess.running = true;
    }
    onClipboardViewChanged: if (clipboardView && !clipboardListing.running) clipboardListing.running = true

    Process {
        id: clipboardListing
        command: [shell.lunaCli, "clipboard", "list"]
        stdout: StdioCollector {}
        stderr: StdioCollector {}
        onExited: (code, status) => {
            if (code === 0) shell.clipboardEntries = JSON.parse(stdout.text);
            else shell.systemMessage = "Could not load clipboard history. Check that cliphist is installed.";
        }
    }
    Process {
        id: clipboardPreviewProcess
        stdout: StdioCollector {}
        stderr: StdioCollector {}
        onExited: (code, status) => {
            if (shell.previewRequested !== shell.previewId) {
                shell.loadClipboardPreview();
                return;
            }
            if (code === 0) shell.clipboardPreview = JSON.parse(stdout.text);
        }
    }
    Process {
        id: clipboardTargetProcess
        command: [shell.lunaCli, "clipboard", "target"]
        stdout: StdioCollector {}
        onExited: (code, status) => {
            if (!shell.awaitingOpen)
                return;
            shell.awaitingOpen = false;
            if (code === 0) shell.clipboardTarget = JSON.parse(stdout.text);
            panel.visible = true;
            focusDelay.restart();
        }
    }
    Process {
        id: clipboardPaste
        stderr: StdioCollector {}
        onExited: (code, status) => {
            if (code !== 0) {
                Quickshell.execDetached(["env", "-u", "LD_LIBRARY_PATH", "-u", "LD_PRELOAD", "notify-send", "--app-name=Luna", "--urgency=normal", "Could not paste", stderr.text.trim() || "Could not paste clipboard entry."]);
            }
        }
    }

    property string menuScreenName: ""
    property string systemMessage: ""
    property bool awaitingOpen: false
    property bool hibernateAvailable: false
    property bool recordingActive: false
    property string currentMenu: ""
    readonly property bool appsView: currentMenu === "apps"
    readonly property bool keybindingsView: currentMenu === "learn.keybindings"
    property var keybindingEntries: []
    property string keybindingMessage: ""
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
        { name: "Insert", icon: "smile", route: "insert" },
        { name: "Clipboard", icon: "clipboard", route: "insert.clipboard", parent: "insert", parentLabel: "Insert" },
        { name: "Emoji", icon: "smile", route: "insert.emoji", parent: "insert", parentLabel: "Insert" },
        { name: "GIFs", icon: "film", route: "insert.gifs", parent: "insert", parentLabel: "Insert" },
        { name: "Learn", icon: "book-open", route: "learn" },
        { name: "Hyprland Keybindings", icon: "type", route: "learn.keybindings", parent: "learn", parentLabel: "Learn", keywords: ["keyboard", "shortcuts"] },
        { name: "Trigger", icon: "zap", route: "trigger" },
        { name: "Screenshot", icon: "monitor", route: "trigger.screenshot", parent: "trigger", parentLabel: "Trigger", keywords: ["capture", "print screen"] },
        { name: "Select Region", icon: "monitor", capture: "region", parent: "trigger.screenshot", parentLabel: "Trigger › Screenshot", keywords: ["capture", "area", "selection"] },
        { name: "Active Screen", icon: "monitor", capture: "screen", parent: "trigger.screenshot", parentLabel: "Trigger › Screenshot", keywords: ["capture", "monitor", "display"] },
        { name: "Active Window", icon: "monitor", capture: "window", parent: "trigger.screenshot", parentLabel: "Trigger › Screenshot", keywords: ["capture", "application"] },
        { name: "All Screens", icon: "monitor", capture: "all", parent: "trigger.screenshot", parentLabel: "Trigger › Screenshot", keywords: ["capture", "monitors", "displays", "desktop"] },
        { name: "Screen Recording", icon: "film", route: "trigger.record", parent: "trigger", parentLabel: "Trigger", keywords: ["video", "record", "capture"] },
        { name: "Record Region", icon: "film", record: "region", parent: "trigger.record", parentLabel: "Trigger › Screen Recording", keywords: ["video", "area", "selection"] },
        { name: "Record Screen", icon: "monitor", record: "screen", parent: "trigger.record", parentLabel: "Trigger › Screen Recording", keywords: ["video", "monitor", "display"] },
        { name: "Stop Recording", icon: "square", record: "stop", parent: "trigger.record", parentLabel: "Trigger › Screen Recording", keywords: ["video", "finish", "save"] },
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
        (entry.action !== "hibernate" || hibernateAvailable)
        && (!entry.record || (entry.record === "stop") === recordingActive))
    readonly property var matches: keybindingsView ? Keybindings.find(keybindingEntries, search.text) : emojiView ? Search.insertEntries(emojiEntries, search.text) : gifSource ? gifEntries : clipboardView ? clipboardEntries.filter(entry => entry.name.toLowerCase().includes(search.text.toLowerCase())) : fontRole ? Search.installedFonts(fontFamilies, search.text) : removeFontsView ? Search.installedFonts(installedFonts, search.text) : fontsView ? fontResults : appsView
        ? Search.find(DesktopEntries.applications.values, search.text)
        : Search.rootEntries(availableMenuEntries, DesktopEntries.applications.values, search.text, currentMenu)

    function moveSelection(direction) {
        if (!matches.length)
            return;
        shell.selectionView.currentIndex = (shell.selectionView.currentIndex + direction + matches.length) % matches.length;
        shell.selectionView.positionViewAtIndex(shell.selectionView.currentIndex, ListView.Contain);
    }
    function jumpSelection(index) {
        if (!matches.length)
            return;
        shell.selectionView.currentIndex = Math.max(0, Math.min(matches.length - 1, index));
        shell.selectionView.positionViewAtIndex(shell.selectionView.currentIndex, ListView.Contain);
    }

    function pageSelection(direction) {
        const pageSize = gridView ? Math.max(1, Math.floor(insertGrid.height / insertGrid.cellHeight)) * insertGrid.columns : Math.max(1, Math.floor(results.height / (48 * textScale + results.spacing)));
        jumpSelection(shell.selectionView.currentIndex + direction * pageSize);
    }

    function showMenu(route) {
        currentMenu = route;
        search.clear();
        shell.selectionView.currentIndex = matches.length ? 0 : -1;
        shell.selectionView.positionViewAtBeginning();
        search.forceActiveFocus();
    }

    function goBack() {
        showMenu(currentMenu.split(".").slice(0, -1).join("."));
    }

    function toggleFont(entry) {
        fontSelection = FontSelection.toggle(fontSelection, entry);
    }

    function tabSelection(direction) {
        if (emojiView) {
            const glyph = (matches[shell.selectionView.currentIndex] || {}).emoji;
            emojiSelection = direction > 0 ? EmojiSelection.add(emojiSelection, glyph) : EmojiSelection.removeLast(emojiSelection, glyph);
            return;
        } else if (fontsView || removeFontsView)
            toggleFont(matches[shell.selectionView.currentIndex]);
        moveSelection(direction);
    }

    function activate(entry) {
        // This is a shortcut reference; selecting a row never dispatches its action.
        if (entry && entry.keybinding)
            return;
        if (emojiView || gifSource) {
            const selected = EmojiSelection.values(emojiSelection, entry);
            if (clipboardPaste.running || (emojiView ? !selected.length : !entry)) return;
            const action = emojiView ? "paste-emoji" : "paste-giphy";
            const value = emojiView ? JSON.stringify(selected) : entry.download;
            clipboardPaste.command = [lunaCli, "insert", action, value, clipboardTarget];
            panel.visible = false;
            clipboardPaste.running = true;
            return;
        }
        if (clipboardView) {
            if (!entry || clipboardPaste.running)
                return;
            clipboardPaste.command = [lunaCli, "clipboard", "paste", entry.id, clipboardTarget];
            panel.visible = false;
            clipboardPaste.running = true;
            return;
        }
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
        if (entry.record) {
            if (recordingAction.running)
                return;
            panel.visible = false;
            systemMessage = "";
            recordingAction.command = [lunaCli, "record", entry.record];
            recordingAction.running = true;
            return;
        }
        if (entry.capture) {
            if (screenshotAction.running)
                return;
            systemMessage = "";
            screenshotAction.command = [lunaCli, "screenshot", entry.capture];
            panel.visible = false;
            screenshotAction.running = true;
            return;
        }
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
        awaitingOpen = true;
        if (!recordingStatus.running)
            recordingStatus.running = true;
        if (!hibernateCheck.running)
            hibernateCheck.running = true;
        if (!idleRead.running)
            idleRead.running = true;
        const monitor = Hyprland.focusedMonitor;
        panel.screen = Quickshell.screens.find(screen => monitor && screen.name === monitor.name) || Quickshell.screens[0];
        menuScreenName = panel.screen.name;
        systemMessage = "";
        fontSelection = [];
        emojiSelection = [];
        currentMenu = "";
        search.text = "";
        shell.selectionView.currentIndex = matches.length ? 0 : -1;
        clipboardTarget = "";
        if (!clipboardTargetProcess.running)
            clipboardTargetProcess.running = true;
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
        emojiSelection = [];
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

    // Refresh from the compositor on entry so custom and reloaded bindings appear.
    onKeybindingsViewChanged: {
        if (keybindingsView && !keybindingListing.running) {
            keybindingEntries = [];
            keybindingMessage = "";
            keybindingListing.running = true;
        }
    }

    Process {
        id: keybindingListing
        command: ["timeout", "5s", "hyprctl", "binds"]
        stdout: StdioCollector {}
        stderr: StdioCollector {}
        onExited: (code, status) => {
            if (code !== 0) {
                shell.keybindingMessage = "Could not load Hyprland keybindings.";
                return;
            }
            try {
                shell.keybindingEntries = Keybindings.parse(stdout.text);
            } catch (error) {
                shell.keybindingMessage = "Could not read Hyprland keybindings.";
            }
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
        id: screenshotAction
        stdout: StdioCollector {}
        stderr: StdioCollector {}
        onExited: (code, status) => {
            // Successful captures and cancelled selections keep the menu dismissed.
            if (code !== 0) {
                shell.open();
                shell.systemMessage = stderr.text.trim() || "Screenshot failed.";
                console.warn(shell.systemMessage);
            }
        }
    }
    Process {
        id: recordingAction
        stdout: StdioCollector {}
        stderr: StdioCollector {}
        onExited: (code, status) => {
            if (!recordingStatus.running)
                recordingStatus.running = true;
            if (code !== 0) {
                shell.open();
                shell.systemMessage = stderr.text.trim() || "Recording failed.";
            }
        }
    }
    Process {
        id: recordingStatus
        command: [shell.lunaCli, "record", "status"]
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    shell.recordingActive = JSON.parse(text).running === true;
                } catch (error) {
                    shell.recordingActive = false;
                }
            }
        }
        stderr: StdioCollector {}
    }
    Timer {
        interval: 1000
        running: panel.visible && shell.currentMenu === "trigger.record"
        repeat: true
        onTriggered: if (!recordingStatus.running) recordingStatus.running = true
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
        if (gifAppending) return;
        shell.selectionView.currentIndex = matches.length ? 0 : -1;
        shell.selectionView.positionViewAtBeginning();
    }

    IpcHandler {
        function open(): void {
            shell.open();
        }
        function close(): void {
            // A capture can dismiss the menu while its initial focus lookup is pending.
            shell.awaitingOpen = false;
            panel.visible = false;
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
                    if (shell.giphySetupView) giphySetupButton.forceActiveFocus();
                    else search.forceActiveFocus(Qt.TabFocusReason);
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
            readonly property var selectedEntry: shell.matches[shell.selectionView.currentIndex] || null

            anchors.centerIn: parent
            width: Math.min((shell.clipboardView ? 960 : 640) * shell.textScale, panel.width - 2 * Math.max(16, Luna.Theme.outerGap))
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
                view: shell.selectionView
                onHoveredIndex: index => shell.selectionView.currentIndex = index
            }

            Button {
                id: giphySetupButton
                anchors.centerIn: parent
                visible: shell.giphySetupView
                text: "Set GIPHY API key"
                padding: 14
                contentItem: Label {
                    text: giphySetupButton.text
                    color: Luna.Theme.accent
                    font.family: shell.uiFont
                    font.pointSize: shell.textSize + 1
                }
                background: Rectangle {
                    color: giphySetupButton.hovered ? Luna.Theme.selection : Luna.Theme.lighterBackground
                    radius: Math.min(Luna.Theme.barRounding, height / 2)
                }
                onClicked: shell.setupGiphy()
                Keys.onReturnPressed: shell.setupGiphy()
                Keys.onEnterPressed: shell.setupGiphy()
            }
            ColumnLayout {
                visible: !shell.giphySetupView
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
                            Accessible.name: shell.keybindingsView ? "Search Hyprland keybindings" : shell.insertView ? "Search " + (shell.emojiView ? "emoji" : shell.gifSource ? "GIFs" : "clipboard") : (shell.fontsView || shell.removeFontsView || shell.fontRole) ? "Search fonts" : shell.appsView ? "Search applications" : "Search menu"
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
                            onTextChanged: { shell.queueFontSearch(); shell.queueGifs(); }

                            Keys.onPressed: event => {
                                if (shell.emojiView && event.key === Qt.Key_Backspace && search.text.length === 0 && shell.emojiSelection.length)
                                    shell.emojiSelection = EmojiSelection.removeAt(shell.emojiSelection, shell.emojiSelection.length - 1);
                                else if (shell.gridView && event.key === Qt.Key_Left)
                                    shell.moveSelection(-1);
                                else if (shell.gridView && event.key === Qt.Key_Right)
                                    shell.moveSelection(1);
                                else if (event.key === Qt.Key_PageUp)
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
                            Keys.onDownPressed: shell.moveSelection(shell.gridView ? insertGrid.columns : 1)
                            Keys.onTabPressed: shell.tabSelection(1)
                            Keys.onUpPressed: shell.moveSelection(shell.gridView ? -insertGrid.columns : -1)
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
                        visible: shell.keybindingsView && shell.keybindingMessage.length > 0
                        text: shell.keybindingMessage
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
                    Flickable {
                        id: selectedEmojiPreview
                        visible: shell.emojiView && shell.emojiSelection.length > 0
                        Layout.fillWidth: true
                        Layout.preferredHeight: visible ? 48 * shell.textScale : 0
                        contentWidth: selectedEmojiRow.width
                        contentHeight: height
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        onContentWidthChanged: contentX = Math.max(0, contentWidth - width)
                        Row {
                            id: selectedEmojiRow
                            spacing: 4
                            Repeater {
                                model: shell.emojiSelection
                                delegate: Button {
                                    id: selectedEmoji
                                    required property string modelData
                                    required property int index
                                    width: 44 * shell.textScale
                                    height: 44 * shell.textScale
                                    focusPolicy: Qt.NoFocus
                                    Accessible.name: "Remove " + modelData
                                    padding: 8 * shell.textScale
                                    contentItem: Luna.Emoji {
                                        glyph: selectedEmoji.modelData
                                        artwork: shell.emojiArtwork[glyph] || ""
                                    }
                                    background: Rectangle {
                                        color: Luna.Theme.selection
                                        radius: Math.min(Luna.Theme.barRounding, width / 2, height / 2)
                                    }
                                    onClicked: {
                                        shell.emojiSelection = EmojiSelection.removeAt(shell.emojiSelection, index);
                                        search.forceActiveFocus();
                                    }
                                }
                            }
                        }
                    }
                    RowLayout {
                        visible: shell.gifSource === "giphy"
                        Layout.fillWidth: true
                        Label {
                            Layout.fillWidth: true
                            text: "Powered by GIPHY" + (shell.insertEntry.creator ? " · @" + shell.insertEntry.creator : "")
                            color: Luna.Theme.foreground
                            font.family: shell.uiFont
                            font.pointSize: shell.textSize - 1
                            elide: Text.ElideRight
                        }

                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        spacing: 16
                    GridView {
                        id: insertGrid
                        onContentYChanged: {
                            if (atYEnd) shell.loadMoreGifs();
                        }
                        onCurrentIndexChanged: {
                            if (currentIndex >= count - columns) shell.loadMoreGifs();
                        }
                        visible: shell.gridView
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        readonly property int columns: Math.max(1, Math.floor(width / ((shell.emojiView ? 64 : 180) * shell.textScale)))
                        cellWidth: width / columns
                        cellHeight: (shell.emojiView ? 64 : 128) * shell.textScale
                        model: shell.gridView ? shell.matches : []
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        currentIndex: -1
                        ScrollBar.vertical: ScrollBar {
                            id: gridScrollbar
                            implicitWidth: 3
                            contentItem: Rectangle {
                                color: gridScrollbar.pressed ? Luna.Theme.accent : Luna.Theme.muted
                                radius: Math.min(Luna.Theme.barRounding, width / 2)
                                visible: gridScrollbar.size < 1
                            }
                            background: Item {}
                        }
                        delegate: Button {
                            id: tile
                            required property var modelData
                            required property int index
                            readonly property bool selected: insertGrid.currentIndex === index
                            readonly property bool marked: shell.emojiSelection.includes(modelData.emoji)
                            width: insertGrid.cellWidth - 6
                            height: insertGrid.cellHeight - 6
                            padding: shell.emojiView ? 8 : 4
                            focusPolicy: Qt.NoFocus
                            Accessible.name: modelData.name
                            background: Rectangle {
                                color: tile.selected || tile.marked ? Luna.Theme.selection : "transparent"
                                border.color: Luna.Theme.accent
                                border.width: tile.marked ? 2 : tile.selected ? 1 : 0
                                radius: Math.min(Luna.Theme.barRounding, width / 2, height / 2)
                            }
                            contentItem: Item {
                                Luna.Emoji {
                                    anchors.centerIn: parent
                                    visible: shell.emojiView
                                    width: 36 * shell.textScale
                                    height: width
                                    glyph: tile.modelData.emoji || ""
                                    artwork: tile.modelData.artwork || ""
                                }
                                Image {
                                    anchors.fill: parent
                                    visible: !shell.emojiView && (!tile.selected || gifAnimation.status !== Image.Ready)
                                    source: shell.gifSource ? tile.modelData.image || "" : ""
                                    fillMode: Image.PreserveAspectFit
                                    asynchronous: true
                                    cache: false
                                }
                                AnimatedImage {
                                    id: gifAnimation
                                    anchors.fill: parent
                                    visible: !!shell.gifSource && tile.selected
                                    source: visible ? tile.modelData.animation || "" : ""
                                    playing: visible && panel.visible
                                    fillMode: Image.PreserveAspectFit
                                    cache: false
                                }
                            }
                            MouseArea {
                                anchors.fill: parent
                                enabled: shell.emojiView
                                onClicked: mouse => {
                                    insertGrid.currentIndex = tile.index;
                                    shell.emojiSelection = (mouse.modifiers & Qt.ShiftModifier)
                                        ? EmojiSelection.removeLast(shell.emojiSelection, tile.modelData.emoji)
                                        : EmojiSelection.add(shell.emojiSelection, tile.modelData.emoji);
                                    search.forceActiveFocus();
                                }
                            }
                            onClicked: {
                                insertGrid.currentIndex = index;
                                if (shell.emojiView) {
                                    shell.emojiSelection = EmojiSelection.add(shell.emojiSelection, modelData.emoji);
                                    search.forceActiveFocus();
                                } else shell.activate(modelData);
                            }
                        }
                        Label {
                            anchors.centerIn: parent
                            visible: insertGrid.count === 0
                            text: shell.emojiView ? (emojiListing.running ? "Loading…" : "No matching emoji") : gifSearch.running ? "Loading…" : shell.systemMessage ? "" : "No GIFs found"
                            color: Luna.Theme.foreground
                            font.family: shell.uiFont
                            font.pointSize: shell.textSize
                        }
                    }
                    ListView {
                        id: results
                        visible: !shell.gridView

                        Accessible.name: shell.keybindingsView ? "Hyprland keybindings" : shell.clipboardView ? "Clipboard history" : shell.appsView ? "Applications" : "Menu entries"
                        Layout.preferredWidth: shell.insertView ? 320 * shell.textScale : -1
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
                            readonly property bool selected: shell.selectionView.currentIndex === index
                            readonly property bool marked: (shell.fontsView || shell.removeFontsView) && FontSelection.contains(shell.fontSelection, modelData)
                            readonly property bool applicationEntry: typeof modelData.execute === "function"

                            Accessible.name: modelData.keybinding ? [modelData.name, modelData.shortcut, modelData.context].filter(Boolean).join(", ") : modelData.name
                            ToolTip.visible: hovered && (!!modelData.targets || !!modelData.keybinding)
                            ToolTip.text: modelData.keybinding ? [modelData.name, modelData.shortcut, modelData.context].filter(Boolean).join("\n") : modelData.description || ""
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
                                    visible: !shell.keybindingsView && (!shell.clipboardView || !!result.modelData.image)
                                    Layout.preferredWidth: result.modelData.image ? 48 : 20
                                    Layout.preferredHeight: result.modelData.image ? 32 : 20

                                    Image {
                                        anchors.fill: parent
                                        visible: !!result.modelData.image
                                        source: result.modelData.image || ""
                                        sourceSize: Qt.size(96, 64)
                                        fillMode: Image.PreserveAspectFit
                                        asynchronous: true
                                    }
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
                                        visible: !result.modelData.emoji && !result.modelData.image && (!result.applicationEntry || appIcon.status !== Image.Ready)
                                        name: result.applicationEntry ? "layout-grid" : result.modelData.icon || "type"
                                        ink: result.selected ? Luna.Theme.selectionForeground : Luna.Theme.foreground
                                    }
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 1

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
                                        visible: shell.keybindingsView && !!result.modelData.context
                                        Layout.fillWidth: true
                                        color: result.selected ? Luna.Theme.selectionForeground : Luna.Theme.foreground
                                        opacity: 0.65
                                        font.family: shell.uiFont
                                        font.pointSize: Math.max(1, shell.textSize - 2)
                                        elide: Text.ElideRight
                                        text: result.modelData.context || ""
                                        textFormat: Text.PlainText
                                    }
                                }
                                Label {
                                    visible: !!result.modelData.keybinding
                                    Layout.maximumWidth: results.width * 0.48
                                    text: result.modelData.shortcut || ""
                                    textFormat: Text.PlainText
                                    elide: Text.ElideRight
                                    color: result.selected ? Luna.Theme.selectionForeground : Luna.Theme.accent
                                    font.family: shell.uiFont
                                    font.pointSize: shell.textSize
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
                                    visible: !shell.insertView && !result.modelData.keybinding && result.selected && !result.applicationEntry && !result.modelData.repository && !result.modelData.family && !result.modelData.action && !result.modelData.capture && !result.modelData.idleSetting
                                }
                            }
                            onClicked: {
                                shell.selectionView.currentIndex = index;
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
                                text: shell.keybindingsView ? (keybindingListing.running ? "Loading…" : shell.keybindingMessage ? "" : search.text.trim() ? "No matching keybindings" : "No keybindings found") : shell.emojiView ? (emojiListing.running ? "Loading…" : "No matching emoji") : shell.gifSource ? (gifSearch.running ? "Loading…" : shell.systemMessage ? "" : "No GIFs found") : shell.clipboardView ? (clipboardListing.running ? "Loading…" : "No clipboard entries") : shell.fontRole
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
                    Rectangle {
                        visible: shell.clipboardView
                        Layout.fillHeight: true
                        implicitWidth: 1
                        color: Luna.Theme.muted
                    }
                    Rectangle {
                        visible: shell.clipboardView
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.preferredWidth: 540 * shell.textScale
                        color: Luna.Theme.lighterBackground
                        radius: Math.min(Luna.Theme.barRounding, width / 2, height / 2)
                        clip: true
                        Image {
                            anchors.fill: parent
                            anchors.margins: 14
                            source: shell.clipboardView ? shell.clipboardPreview.image || "" : ""
                            visible: source.toString().length > 0
                            fillMode: Image.PreserveAspectFit
                            cache: false
                            asynchronous: true
                        }
                        ScrollView {
                            anchors.fill: parent
                            anchors.margins: 14
                            visible: shell.clipboardView && !shell.clipboardPreview.image
                            contentWidth: availableWidth
                            // Basic controls otherwise inherit the desktop palette, not Luna's theme.
                            palette.text: Luna.Theme.foreground
                            palette.base: Luna.Theme.lighterBackground
                            palette.highlight: Luna.Theme.selection
                            palette.highlightedText: Luna.Theme.selectionForeground
                            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                            ScrollBar.vertical: ScrollBar {
                                id: previewScrollbar
                                policy: ScrollBar.AsNeeded
                                implicitWidth: 3
                                contentItem: Rectangle {
                                    implicitWidth: 3
                                    color: previewScrollbar.pressed ? Luna.Theme.accent : Luna.Theme.muted
                                    radius: Math.min(Luna.Theme.barRounding, width / 2)
                                    visible: previewScrollbar.size < 1
                                }
                                background: Item {}
                            }
                            TextArea {
                                padding: 0
                                text: shell.clipboardPreview.text || ""
                                readOnly: true
                                selectByMouse: true
                                textFormat: TextEdit.PlainText
                                wrapMode: TextEdit.Wrap
                                font.family: shell.uiFont
                                font.pointSize: shell.textSize
                                color: Luna.Theme.foreground
                                selectedTextColor: Luna.Theme.selectionForeground
                                selectionColor: Luna.Theme.selection
                                background: Item {}
                            }
                        }
                    }
                    }
                }

            }
        }
    }
}
