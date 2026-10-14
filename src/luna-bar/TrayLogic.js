function action(item, button) {
    if (!item) return "";
    if (button === "right" || (button === "left" && item.onlyMenu))
        return item.hasMenu ? "menu" : "";
    if (button === "middle") return "secondary";
    return button === "left" ? "activate" : "";
}

function run(item, action, window, point) {
    if (!item) return false;
    if (action === "menu" && item.hasMenu) item.display(window, Math.round(point.x), Math.round(point.y));
    else if (action === "activate") item.activate();
    else if (action === "secondary") item.secondaryActivate();
    else return false;
    return true;
}
