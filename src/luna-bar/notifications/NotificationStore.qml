pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Services.Notifications
import "NotificationLogic.js" as Logic

// Session-only history keeps at most 100 snapshots. Popup expiry preserves live actions.
QtObject {
    id: store

    property bool dnd: false
    property bool panelOpen: false
    readonly property var entries: _entries
    readonly property var popupEntries: _popups
    readonly property int unreadCount: entries.filter(entry => entry.unread).length
    signal received()
    signal soundRequested(int urgency)

    property var _entries: []
    property var _popups: []
    property var _records: ({})
    property var _order: []
    property bool _preferencesReady: false

    function rebuild() {
        const history = [];
        const candidates = [];
        for (const id of _order) {
            const record = _records[id];
            if (!record)
                continue;
            if (!record.transient)
                history.push(record.snapshot);
            if (record.popup && record.notification)
                candidates.push(record.snapshot);
        }
        const selected = dnd || panelOpen ? [] : candidates.sort(Logic.popupOrder).slice(0, 3);
        const previous = _popups.map(entry => entry.id);
        const now = Date.now();
        for (const entry of selected) {
            if (!previous.includes(entry.id))
                _records[entry.id].lastTick = now;
        }
        _entries = history.slice(0, 100);
        _popups = selected;
    }

    function receive(notification) {
        notification.tracked = true;
        const restoreCritical = notification.lastGeneration && notification.urgency === 2;
        if (notification.transient && (dnd || panelOpen || (notification.lastGeneration && !restoreCritical))) {
            notification.expire();
            return;
        }
        const now = Date.now();
        const watcher = observers.createObject(store, {notification: notification, notificationId: notification.id});
        _records[notification.id] = {
            notification: notification,
            observer: watcher,
            sourceAppIcon: notification.appIcon,
            snapshot: makeSnapshot(notification, now, !panelOpen && !notification.lastGeneration),
            transient: notification.transient,
            popup: !dnd && !panelOpen && (!notification.lastGeneration || restoreCritical),
            remaining: Logic.timeout(notification),
            lastTick: now,
            hovered: false
        };
        watcher.ready = true;
        _order = [notification.id].concat(_order.filter(id => id !== notification.id));
        trimHistory();
        rebuild();
        if (!notification.lastGeneration)
            received();
        if (Logic.shouldPlaySound(notification, dnd, panelOpen))
            soundRequested(notification.urgency);
    }

    function refresh(notification) {
        const record = notification ? _records[notification.id] : null;
        if (!record || record.notification !== notification)
            return;
        const now = Date.now();
        record.sourceAppIcon = notification.appIcon;
        record.snapshot = makeSnapshot(notification, now, !panelOpen);
        record.transient = notification.transient;
        record.popup = !dnd && !panelOpen;
        record.remaining = Logic.timeout(notification);
        record.lastTick = now;
        _order = [notification.id].concat(_order.filter(id => id !== notification.id));
        if (record.transient && !record.popup) {
            notification.expire();
        } else {
            trimHistory();
            rebuild();
            received();
        }
    }

    function makeSnapshot(notification, timestamp, unread) {
        const desktopId = Logic.desktopId(notification.desktopEntry);
        const application = !notification.appIcon && desktopId ? DesktopEntries.byId(desktopId) : null;
        return Logic.snapshot(notification, timestamp, unread, application ? application.icon : "");
    }

    function updateIcons() {
        let changed = false;
        for (const id of _order) {
            const record = _records[id];
            const desktopId = Logic.desktopId(record.snapshot.desktopEntry);
            if (record.sourceAppIcon || !desktopId)
                continue;
            const application = DesktopEntries.byId(desktopId);
            if (application && application.icon && application.icon !== record.snapshot.appIcon) {
                record.snapshot = Object.assign({}, record.snapshot, {appIcon: application.icon});
                changed = true;
            }
        }
        if (changed)
            rebuild();
    }

    function trimHistory() {
        const archived = _order.filter(id => _records[id] && !_records[id].transient);
        for (const id of archived.slice(100)) {
            // Critical popups remain pending even when they fall outside the bounded history view.
            if (!pendingCritical(id))
                forget(id, true);
        }
        // Transient notifications have no history destination, so bound their pending queue too.
        const transient = _order.filter(id => _records[id] && _records[id].transient);
        for (const id of transient.slice(3)) {
            if (!pendingCritical(id))
                forget(id, true);
        }
    }

    function pendingCritical(id) {
        const record = _records[id];
        return record && record.popup && record.notification && record.snapshot.urgency === 2;
    }

    function closed(id) {
        const record = _records[id];
        if (!record)
            return;
        record.notification = null;
        record.popup = false;
        record.snapshot = Logic.closed(record.snapshot);
        if (record.observer) {
            record.observer.notification = null;
            record.observer.destroy();
            record.observer = null;
        }
        if (record.transient) {
            delete _records[id];
            _order = _order.filter(value => value !== id);
        }
        rebuild();
    }

    function dismiss(id) {
        const record = _records[id];
        if (record && record.notification)
            record.notification.dismiss();
    }

    function forget(id, expired) {
        const record = _records[id];
        if (!record)
            return;
        if (record.notification) {
            if (expired)
                record.notification.expire();
            else
                record.notification.dismiss();
        }
        delete _records[id];
        _order = _order.filter(value => value !== id);
    }

    function remove(id) {
        forget(id, false);
        rebuild();
    }

    function clear() {
        for (const id of _order.slice())
            forget(id, false);
        rebuild();
    }

    function markRead() {
        for (const id of _order) {
            const record = _records[id];
            if (record.snapshot.unread)
                record.snapshot = Object.assign({}, record.snapshot, {unread: false});
        }
        rebuild();
    }

    function invoke(id, actionId) {
        const record = _records[id];
        if (!record)
            return;
        const imageAction = actionId === "luna-open-image" && record.snapshot.appName === "Luna Screenshot";
        const recordingAction = actionId === "luna-open-recording" && record.snapshot.appName === "Luna Recording";
        if (imageAction || recordingAction) {
            const path = recordingAction ? Logic.localRecordingPath(record.snapshot.recordingFile)
                : Logic.localImagePath(record.snapshot.image);
            if (path) {
                record.snapshot = Object.assign({}, record.snapshot, {unread: false});
                record.popup = false;
                Quickshell.execDetached(["xdg-open", path]);
                dismiss(id);
                rebuild();
            }
            return;
        }
        if (!record.notification)
            return;
        const action = record.notification.actions.find(candidate => candidate.identifier === actionId);
        if (action) {
            record.snapshot = Object.assign({}, record.snapshot, {unread: false});
            record.popup = false;
            action.invoke();
            rebuild();
        }
    }

    function open(id) {
        const record = _records[id];
        if (!record)
            return false;
        const changed = record.snapshot.unread || record.popup;
        if (record.snapshot.unread)
            record.snapshot = Object.assign({}, record.snapshot, {unread: false});
        record.popup = false;
        record.hovered = false;
        if (record.snapshot.appName === "Luna Screenshot" && Logic.localImagePath(record.snapshot.image)) {
            invoke(id, "luna-open-image");
            return true;
        }
        if (record.snapshot.appName === "Luna Recording" && Logic.localRecordingPath(record.snapshot.recordingFile)) {
            invoke(id, "luna-open-recording");
            return true;
        }
        // Only the explicit default action means opening; another first action could be destructive.
        if (record.notification && record.notification.actions.some(action => action.identifier === "default")) {
            invoke(id, "default");
            return true;
        }
        const desktopId = Logic.desktopId(record.snapshot.desktopEntry);
        const application = desktopId ? DesktopEntries.byId(desktopId) : null;
        if (application && !application.noDisplay && application.command.length) {
            application.execute();
            dismiss(id);
            rebuild();
            return true;
        }
        if (changed)
            rebuild();
        return false;
    }

    function setHovered(id, hovered) {
        const record = _records[id];
        if (record) {
            record.hovered = hovered;
            record.lastTick = Date.now();
        }
    }

    function tick() {
        const now = Date.now();
        let changed = false;
        for (const entry of _popups.slice()) {
            const record = _records[entry.id];
            if (!record || !record.remaining)
                continue;
            if (!record.hovered)
                record.remaining = Math.max(0, record.remaining - (now - record.lastTick));
            record.lastTick = now;
            if (!record.remaining) {
                record.popup = false;
                changed = true;
                if (record.transient && record.notification)
                    record.notification.expire();
            }
        }
        if (changed)
            rebuild();
    }

    function suppressPopups() {
        for (const id of _order.slice()) {
            const record = _records[id];
            record.popup = false;
            record.hovered = false;
            if (record.transient && record.notification)
                record.notification.expire();
        }
        rebuild();
    }

    onDndChanged: {
        if (dnd)
            suppressPopups();
        if (_preferencesReady)
            preferences.setText(JSON.stringify({dnd: dnd}) + "\n");
    }
    onPanelOpenChanged: {
        if (panelOpen) {
            suppressPopups();
            markRead();
        }
    }

    // Only the quiet-mode preference reaches disk; notification content stays in this process.
    property FileView preferences: FileView {
        path: (Quickshell.env("XDG_CONFIG_HOME") || Quickshell.env("HOME") + "/.config") + "/luna/notifications.json"
        blockLoading: true
        blockWrites: true
        atomicWrites: true
        printErrors: false
    }
    Component.onCompleted: {
        try {
            const saved = preferences.text();
            if (saved)
                dnd = JSON.parse(saved).dnd === true;
        } catch (error) {
            console.warn("Could not read Luna notification preferences:", error);
        }
        _preferencesReady = true;
    }

    property NotificationServer server: NotificationServer {
        keepOnReload: true
        persistenceSupported: true
        actionsSupported: true
        bodySupported: true
        bodyMarkupSupported: false
        bodyHyperlinksSupported: false
        bodyImagesSupported: false
        imageSupported: true
        actionIconsSupported: false
        inlineReplySupported: false
        onNotification: notification => store.receive(notification)
    }

    property Timer expiry: Timer {
        interval: 100
        repeat: true
        running: store.popupEntries.some(entry => store._records[entry.id] && store._records[entry.id].remaining > 0)
        onTriggered: store.tick()
    }

    // Desktop scanning is asynchronous; its icon supersedes a hint fallback, never an explicit sender icon.
    property Connections applicationIcons: Connections {
        target: DesktopEntries
        function onApplicationsChanged() {
            store.updateIcons();
        }
    }

    property Component observers: Component {
        QtObject {
            id: observer
            required property var notification
            required property int notificationId
            property bool ready: false
            // A replacement updates the existing object, including action labels, without a new server signal.
            property string content: notification ? JSON.stringify([
                Logic.snapshot(notification, 0, false), notification.transient, notification.expireTimeout
            ]) : ""
            onContentChanged: {
                if (ready && notification)
                    update.restart();
            }
            property Timer update: Timer {
                id: update
                interval: 0
                onTriggered: store.refresh(observer.notification)
            }
            property Connections lifecycle: Connections {
                target: observer.notification
                function onClosed(reason) {
                    store.closed(observer.notificationId);
                }
            }
        }
    }
}
