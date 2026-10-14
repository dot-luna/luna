// Copy application content into plain values; UI code renders these strings as plain text.
function snapshot(notification, timestamp, unread, fallbackIcon) {
    const hints = notification.hints || {};
    const imageHint = hints["image-path"] || hints["image_path"];
    const image = localImagePath(imageHint) || String(notification.image || "");
    const recordingFile = notification.appName === "Luna Recording" ? localRecordingPath(hints["x-luna-recording"]) : "";
    // Libnotify also sends themed sender icons through image-path; photos remain content only.
    const hintIcon = typeof imageHint === "string" && /^[a-z0-9]/i.test(imageHint)
        && !/[^a-z0-9._-]/i.test(imageHint) ? imageHint : "";
    const actions = [];
    for (const action of notification.actions || [])
        actions.push({identifier: String(action.identifier), text: String(action.text)});
    if (notification.appName === "Luna Screenshot" && localImagePath(image))
        actions.push({identifier: "luna-open-image", text: "Open image"});
    if (recordingFile)
        actions.push({identifier: "luna-open-recording", text: "Open recording"});
    const urgency = Number(notification.urgency);
    return {
        id: notification.id,
        appName: String(notification.appName || "Application"),
        summary: String(notification.summary || ""),
        body: String(notification.body || ""),
        image: image,
        recordingFile: recordingFile,
        appIcon: String(notification.appIcon || fallbackIcon || hintIcon || ""),
        desktopEntry: String(notification.desktopEntry || ""),
        urgency: urgency >= 0 && urgency <= 2 ? urgency : 1,
        timestamp: timestamp,
        unread: unread,
        live: true,
        actions: actions
    };
}

function timeout(notification) {
    // Quickshell 0.3.2 forwards the DBus timeout in milliseconds despite older docs saying seconds.
    const requested = Number(notification.expireTimeout);
    if (notification.urgency === 2 || requested === 0)
        return 0;
    return requested > 0 ? requested : notification.urgency === 0 ? 4000 : 7000;
}

function popupOrder(left, right) {
    return Number(right.urgency === 2) - Number(left.urgency === 2)
        || right.timestamp - left.timestamp || right.id - left.id;
}

function closed(snapshot) {
    // The notification owns its in-memory image handle and action objects.
    return Object.assign({}, snapshot, {
        live: false,
        actions: snapshot.actions.filter(action => (action.identifier === "luna-open-image"
            && snapshot.appName === "Luna Screenshot" && localImagePath(snapshot.image))
            || (action.identifier === "luna-open-recording" && snapshot.appName === "Luna Recording"
                && localRecordingPath(snapshot.recordingFile))),
        image: snapshot.image.startsWith("image://qsimage/") ? "" : snapshot.image
    });
}

function localImagePath(image) {
    let path = String(image || "");
    if (path.startsWith("file:///")) {
        try {
            path = decodeURIComponent(path.slice(7));
        } catch (error) {
            return "";
        }
    }
    return /^\/(?!\/)[^\u0000\r\n]*\.(png|jpe?g|webp)$/i.test(path) ? path : "";
}

function localRecordingPath(value) {
    let path = String(value || "");
    if (path.startsWith("file:///")) {
        try {
            path = decodeURIComponent(path.slice(7));
        } catch (error) {
            return "";
        }
    }
    return /^\/(?!\/)/.test(path) && /\.mp4$/i.test(path) && !/[\u0000\r\n]/.test(path) ? path : "";
}

function desktopId(value) {
    const id = String(value || "").replace(/\.desktop$/, "");
    return /^[a-z0-9][a-z0-9._-]*$/i.test(id) ? id : "";
}

function shouldPlaySound(notification, dnd, panelOpen) {
    const suppressed = (notification.hints || {})["suppress-sound"];
    return !dnd && !panelOpen && !notification.lastGeneration && suppressed !== true && suppressed !== 1;
}
