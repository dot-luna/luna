// Prefer the current playing player, then retain the last choice when playback pauses.
function choose(players, previousName) {
    const available = (players || []).filter(player => !!player);
    const previous = available.find(player => player.dbusName === previousName);
    if (previous && previous.isPlaying) return previous;
    return available.find(player => player.isPlaying) || previous || available[0] || null;
}

function supported(player, action) {
    if (!player || !player.canControl) return false;
    if (action === "play-pause") return !!player.canTogglePlaying;
    if (action === "next") return !!player.canGoNext;
    if (action === "previous") return !!player.canGoPrevious;
    return false;
}

function run(player, action) {
    if (!supported(player, action)) return false;
    if (action === "play-pause") player.togglePlaying();
    else if (action === "next") player.next();
    else if (action === "previous") player.previous();
    return true;
}

// Players may advertise remote cover URLs; displaying controls must not fetch them.
function localArt(value) {
    const source = String(value || "");
    if (/[\u0000\r\n]/.test(source)) return "";
    if (source.startsWith("/") && !source.startsWith("//"))
        return "file://" + source.split("/").map(part => encodeURIComponent(part)).join("/");
    if (/^file:\/\/\/(?!\/)/.test(source)) return source;
    return "";
}
