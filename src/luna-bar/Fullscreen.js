function isActive(monitor) {
    const workspace = monitor && monitor.activeWorkspace;
    // Hyprland's workspace flag also includes maximized windows. Only internal
    // mode 2 covers the screen; client-only fullscreen still fits inside a tile.
    return !!workspace && workspace.hasFullscreen
        && workspace.toplevels.values.some(window => window.lastIpcObject.fullscreen === 2);
}
