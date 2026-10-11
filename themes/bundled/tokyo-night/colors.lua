-- Shared Tokyo Night colors, loaded as a Lua table by Luna theme consumers.
return {
    mode = "dark",

    -- Filled accents and selections pair with their readable text and icon colors.
    accent = "#7aa2f7",
    accent_foreground = "#1a1b26",
    selection = "#292e42",
    selection_foreground = "#c0caf5",

    -- Subdued surfaces and decoration; use bright_foreground for text on this fill.
    muted = "#414868",

    -- Background and foreground variants for contrasting surfaces and text.
    background = "#1a1b26",
    dark_background = "#13141c",
    darker_background = "#0e0e14",
    lighter_background = "#24283b",

    foreground = "#a9b1d6",

    -- Reserved for disabled or decorative elements, not readable secondary text.
    dark_foreground = "#565f89",

    light_foreground = "#b4bee6",
    bright_foreground = "#c0caf5",

    -- Status colors can be text or icons; use their foregrounds on filled badges.
    error = "#f7768e",
    error_foreground = "#1a1b26",
    warning = "#e0af68",
    warning_foreground = "#1a1b26",
    notice = "#eb927b",
    notice_foreground = "#1a1b26",
    success = "#9ece6a",
    success_foreground = "#1a1b26",
    info = "#449dab",
    info_foreground = "#1a1b26",

    link = "#7aa2f7",
    secondary_accent = "#ad8ee6",
    secondary_accent_foreground = "#1a1b26",

    -- Readable code comments on both background and lighter_background.
    comment = "#bd8b7b",

    -- Emphasis means visual intensity, not necessarily greater brightness.
    -- Filled variants reuse their base role's foreground; links remain text colors.
    error_emphasis = "#ff7a93",
    warning_emphasis = "#ff9e64",
    success_emphasis = "#b9f27c",
    info_emphasis = "#0db9d7",
    link_emphasis = "#7da6ff",
    secondary_accent_emphasis = "#bb9af7",
}
