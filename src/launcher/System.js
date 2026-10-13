// Normal session/power requests retain systemd's inhibitor and authorization checks.
function command(action, lunaCli) {
    if (["lock", "suspend", "hibernate", "screensaver"].includes(action) && lunaCli)
        return [lunaCli, action];
    if (action === "logout")
        return ["hyprctl", "eval", "hl.dispatch(hl.dsp.exit())"];
    if (action === "reboot")
        return ["systemctl", "reboot"];
    if (action === "shutdown")
        return ["systemctl", "poweroff"];
    return [];
}
