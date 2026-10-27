.pragma library

/**
 * Shared helpers imported by shell.qml and WallpaperSurface.qml.
 * Read supported global options with defaults, choose a media renderer, and encode local paths.
 * Unknown options and reserved per-monitor sections are ignored; no files are changed here.
 */

/** @typedef {{source: string, fit: "fill"|"fit"|"stretch"|"center"|"tile", background_color: string}} WallpaperOptions */
/** @typedef {{pause_when_output_inactive: boolean}} PlaybackOptions */
/** @typedef {{type: "none"|"fade", duration_ms: number}} TransitionOptions */
/** @typedef {{wallpaper: WallpaperOptions, playback: PlaybackOptions, transition: TransitionOptions}} WallpaperSettings */

/**
 * Use a recognized value or that option's default, without rejecting the whole document.
 * A null document still means config loading failed and leaves the surface dark.
 * @param {?Object} config Parsed TOML; individual values may be missing or unsupported.
 * @returns {WallpaperSettings|null}
 */
function resolve(config) {
    if (!config) return null;

    const wallpaper = config.wallpaper || {};
    const playback = config.playback || {};
    const transition = config.transition || {};

    return {
        // Empty source means solid color. Keep valid options even if a neighboring value is wrong.
        wallpaper: {
            source: typeof wallpaper.source === "string" && wallpaper.source.startsWith("/")
                && !/[\x00-\x1f]/.test(wallpaper.source) ? wallpaper.source : "",
            fit: ["fill", "fit", "stretch", "center", "tile"].includes(wallpaper.fit) ? wallpaper.fit : "center",
            background_color: typeof wallpaper.background_color === "string"
                && /^#[0-9a-fA-F]{6}$/.test(wallpaper.background_color) ? wallpaper.background_color : "#000000"
        },

        // Accept actual TOML booleans; quoted values such as "false" use the default.
        playback: {
            pause_when_output_inactive: typeof playback.pause_when_output_inactive === "boolean"
                ? playback.pause_when_output_inactive : true
        },

        // QML uses signed integer milliseconds; unsupported durations use the normal 200 ms fade.
        transition: {
            type: ["none", "fade"].includes(transition.type) ? transition.type : "fade",
            duration_ms: Number.isInteger(transition.duration_ms) && transition.duration_ms >= 0
                && transition.duration_ms <= 2147483647 ? transition.duration_ms : 200
        }
    };
}

/**
 * Select a renderer from ffprobe metadata, independent of the filename.
 * Qt handles GIF/WebP animation and still-image formats; mpv handles video and APNG.
 * @param {{format?: {format_name?: string}, streams?: Array<{codec_name?: string}>}} metadata
 * @returns {"image"|"animated"|"video"}
 */
function mediaKind(metadata) {
    const format = metadata.format?.format_name || "";
    const codec = metadata.streams?.[0]?.codec_name || "";
    if (codec === "gif" || codec === "webp") return "animated";
    if (!codec || format === "image2" || format.endsWith("_pipe")) return "image";
    return "video";
}

/**
 * Encode each path segment so spaces, #, and ? remain part of the local filename.
 * @param {string} path
 * @returns {string}
 */
function fileUrl(path) {
    return path ? "file://" + path.split("/").map(encodeURIComponent).join("/") : "";
}
