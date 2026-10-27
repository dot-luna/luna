.pragma library

// Imported by VideoWallpaper.qml to build mpvpaper options and recognize decoded video.
// This helper does not launch processes; media paths are passed separately as arguments.

/**
 * Translate the wallpaper fit mode into mpv settings and configure silent, looping playback.
 * User mpv configuration and scripts are disabled so they cannot change wallpaper behavior.
 *
 * @param {string} fit Video fit mode; unsupported values use center.
 * @param {string} background Qt's normalized hexadecimal color.
 * @param {boolean} paused Whether playback starts paused.
 * @returns {string} mpvpaper's configuration options, without user-controlled paths.
 */
function options(fit, background, paused) {
    // Crop to fill, preserve the whole frame, stretch, or retain its unscaled dimensions.
    var sizing = {
        fill: "keepaspect=yes panscan=1 video-unscaled=no",
        fit: "keepaspect=yes panscan=0 video-unscaled=no",
        stretch: "keepaspect=no panscan=0 video-unscaled=no",
        center: "keepaspect=yes panscan=0 video-unscaled=yes"
    };

    return [
        // Ignore interactive/player settings that are inappropriate for an unattended background.
        "config=no load-scripts=no input-default-bindings=no input-terminal=no terminal=no",
        "loop-file=inf audio=no sub=no osc=no osd-level=0",

        // Decode automatically and use high-quality scaling when the chosen fit resizes the video.
        "hwdec=auto scale=ewa_lanczossharp cscale=ewa_lanczossharp dscale=mitchell",
        "background=color background-color='" + background + "'",
        "pause=" + (paused ? "yes" : "no"),

        // VideoWallpaper sets the working directory to a private mktemp directory before launch.
        "input-ipc-server=./ipc",

        // Tiling is image-only; it and unknown fit modes use centered video instead.
        Object.prototype.hasOwnProperty.call(sizing, fit) ? sizing[fit] : sizing.center
    ].join(" ");
}

/**
 * Require decoded output dimensions before reporting playback as ready.
 * mpv may expose null video-out-params while it is still opening or decoding the source.
 *
 * @param {?Object} parameters The data returned by mpv's video-out-params property.
 * @returns {boolean} Whether mpv has reported a video output with positive width and height.
 */
function videoReady(parameters) {
    return parameters !== null && typeof parameters === "object"
        && Number(parameters.w) > 0 && Number(parameters.h) > 0;
}
