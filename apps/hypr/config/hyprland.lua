-- Luna's installed Hyprland entry point. Personal settings follow its dofile call.
-- Resolve the physical entry so symlinks and alternate working directories load
-- sibling configuration modules from the same installed application directory.
local source = debug.getinfo(1, "S").source
assert(source:sub(1, 1) == "@", "Load Luna's Hyprland entry from a file")
local quoted = "'" .. source:sub(2):gsub("'", "'\\''") .. "'"
local pipe = assert(io.popen("readlink -f -- " .. quoted, "r"))
local path = pipe:read("*a")
-- Hyprland can reap subprocesses before pclose; trust the resolved output instead.
pipe:close()
local config_dir = assert(path:gsub("\n$", ""):match("^(.*)/[^/]+$"),
    "Cannot locate Luna's installed Hyprland configuration")
local paths = dofile(config_dir .. "/generated/paths.lua")
assert(type(paths) == "table" and type(paths.install_dir) == "string"
    and paths.install_dir:sub(1, 1) == "/", "Regenerate Luna's Hyprland configuration with setup")
local root = paths.install_dir

-- Reload every module and the selected theme snapshot on each configuration load.
dofile(config_dir .. "/monitors.lua")
dofile(config_dir .. "/workspaces.lua")

local resolved = dofile(root .. "/lib/theme/resolved.lua")(root)
local theme = dofile(config_dir .. "/theme.lua")(resolved)
theme.apply()

-- Layer-shell menus need an explicit blur rule; window opacity rules do not apply.
-- Ignore the transparent click-dismiss area outside the menu panel.
hl.layer_rule({ match = { namespace = "^luna-launcher$" }, blur = true, ignore_alpha = 0 })

-- Menu installation logs use a compact dialog instead of joining the tiled layout.
hl.window_rule({
    match = { class = "^luna-install$" },
    float = true,
    center = true,
    size = "760 460",
})

local bind = dofile(config_dir .. "/bindings.lua")
dofile(config_dir .. "/animations.lua")

-- Use the checkout launcher so shell shortcuts also work before bin is on PATH.
local launcher = "'" .. (root .. "/bin/luna"):gsub("'", "'\\''") .. "'"
hl.on("hyprland.start", function()
    -- Finish initializing the daemon unlocked by PAM. Publish the graphical
    -- environment first so D-Bus can display later keyring unlock prompts.
    hl.dispatch(hl.dsp.exec_cmd([[
        if command -v gnome-keyring-daemon >/dev/null 2>&1; then
            if command -v dbus-update-activation-environment >/dev/null 2>&1; then
                dbus-update-activation-environment --systemd DISPLAY WAYLAND_DISPLAY XDG_CURRENT_DESKTOP
            fi
            gnome-keyring-daemon --start --components=secrets,pkcs11
        fi
    ]]))
    hl.dispatch(hl.dsp.exec_cmd(launcher .. " auth start"))
    hl.dispatch(hl.dsp.exec_cmd(launcher .. " screensaver start"))
    hl.dispatch(hl.dsp.exec_cmd(launcher .. " clipboard start"))
    hl.dispatch(hl.dsp.exec_cmd(launcher .. " notifications start"))
end)
bind("SUPER + L", hl.dsp.exec_cmd(launcher .. " lock"), "Lock screen")
bind("SUPER + CTRL + B", hl.dsp.exec_cmd(launcher .. " bar focus"), "Focus Luna bar")
bind("SUPER + CTRL + Space", hl.dsp.exec_cmd(launcher .. " bar controls"), "Open control center")
bind("SUPER + Space", hl.dsp.exec_cmd(launcher .. " launcher toggle"), "Toggle Luna menu")
bind("SUPER + N", hl.dsp.exec_cmd(launcher .. " notifications open"), "Toggle notification history")
bind("SUPER + SHIFT + N", hl.dsp.exec_cmd(launcher .. " notifications dnd"), "Toggle Do Not Disturb")

-- Menu and keyboard captures share the same saving and clipboard behavior.
bind("Print", hl.dsp.exec_cmd(launcher .. " screenshot region"), "Screenshot selected region")
bind("SHIFT + Print", hl.dsp.exec_cmd(launcher .. " screenshot screen"), "Screenshot active screen")
bind("ALT + Print", hl.dsp.exec_cmd(launcher .. " screenshot window"), "Screenshot active window")
bind("CTRL + Print", hl.dsp.exec_cmd(launcher .. " screenshot all"), "Screenshot all screens")
bind("SUPER + Print", hl.dsp.exec_cmd(launcher .. " record toggle"), "Start region recording or stop recording")
bind("SUPER + SHIFT + Print", hl.dsp.exec_cmd(launcher .. " record stop"), "Stop recording")

-- Continuous controls repeat; mute and transport controls act once per keypress.
for _, shortcut in ipairs({
    { "XF86AudioRaiseVolume", "volume-up", "Raise volume", true },
    { "XF86AudioLowerVolume", "volume-down", "Lower volume", true },
    { "XF86AudioMute", "volume-mute", "Toggle sound mute" },
    { "XF86AudioMicMute", "mic-mute", "Toggle microphone mute" },
    { "XF86MonBrightnessUp", "brightness-up", "Raise brightness", true },
    { "XF86MonBrightnessDown", "brightness-down", "Lower brightness", true },
    { "XF86AudioPlay", "play-pause", "Play or pause media" },
    { "XF86AudioNext", "next", "Next track" },
    { "XF86AudioPrev", "previous", "Previous track" },
}) do
    bind(shortcut[1], hl.dsp.exec_cmd(launcher .. " control " .. shortcut[2]), shortcut[3], shortcut[4])
end
