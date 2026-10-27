.pragma library

/**
 * Media helpers for the renderer: choose a backend and encode local paths.
 * Lua supplies resolved, validated settings; these helpers never read or validate config.
 */

/** @typedef {{source: string, fit: "fill"|"fit"|"stretch"|"center"|"tile", background_color: string}} WallpaperOptions */
/** @typedef {{pause_when_output_inactive: boolean}} PlaybackOptions */
/** @typedef {{type: "none"|"fade", duration_ms: number}} TransitionOptions */
/** @typedef {{wallpaper: WallpaperOptions, playback: PlaybackOptions, transition: TransitionOptions}} WallpaperSettings */

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
