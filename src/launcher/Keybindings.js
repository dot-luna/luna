// Present the compositor's active bindings without running actions or reading config code.
const modifiers = [
    { mask: 64, name: "Super" },
    { mask: 4, name: "Ctrl" },
    { mask: 1, name: "Shift" },
    { mask: 8, name: "Alt" },
    { mask: 2, name: "CapsLock" },
    { mask: 16, name: "Mod2" },
    { mask: 32, name: "Mod3" },
    { mask: 128, name: "Mod5" }
];

function text(value) {
    return typeof value === "string" || typeof value === "number" ? String(value).trim() : "";
}

function modifierMask(name) {
    const masks = {
        super: 64, meta: 64, win: 64, windows: 64, mod4: 64,
        ctrl: 4, control: 4, shift: 1, alt: 8, mod1: 8,
        caps: 2, capslock: 2, lock: 2, mod2: 16, mod3: 32, mod5: 128
    };
    return masks[name.toLowerCase()] || 0;
}

function keyLabel(key) {
    const labels = {
        return: "Enter", kp_enter: "Numpad Enter", space: "Space", escape: "Esc",
        tab: "Tab", iso_left_tab: "Tab", backspace: "Backspace", delete: "Delete",
        insert: "Insert", home: "Home", end: "End", prior: "Page Up", next: "Page Down",
        page_up: "Page Up", page_down: "Page Down", left: "Left", right: "Right",
        up: "Up", down: "Down", plus: "+", minus: "-", equal: "=",
        comma: ",", period: ".", slash: "/", backslash: "\\", semicolon: ";",
        apostrophe: "'", grave: "`", bracketleft: "[", bracketright: "]",
        mouse_up: "Scroll Up", mouse_down: "Scroll Down",
        mouse_left: "Scroll Left", mouse_right: "Scroll Right",
        xf86audiomute: "Mute", xf86audiomicmute: "Mic Mute",
        xf86audioraisevolume: "Volume Up", xf86audiolowervolume: "Volume Down",
        xf86audioplay: "Play / Pause", xf86audiopause: "Pause", xf86audiostop: "Stop",
        xf86audionext: "Next Track", xf86audioprev: "Previous Track",
        xf86monbrightnessup: "Brightness Up", xf86monbrightnessdown: "Brightness Down"
    };
    const lower = key.toLowerCase();
    const code = /^code:(\d+)$/i.exec(key);
    if (code)
        return "Code " + code[1];

    const mouse = /^mouse:(\d+)$/i.exec(key);
    if (mouse) {
        const buttons = { "272": "Left Mouse", "273": "Right Mouse", "274": "Middle Mouse" };
        return buttons[mouse[1]] || "Mouse " + mouse[1];
    }

    return labels[lower] || (key.length === 1 || /^f\d+$/i.test(key) ? key.toUpperCase() : key);
}

function actionName(binding) {
    const description = text(binding.description);
    if (description)
        return description;

    const dispatcher = text(binding.dispatcher);
    // Lua callback numbers are internal handles, not useful descriptions of an action.
    if (!dispatcher || dispatcher === "__lua")
        return "Custom action";

    const names = {
        exec: "Run", execr: "Run", workspace: "Switch workspace",
        movetoworkspace: "Move to workspace", movetoworkspacesilent: "Move to workspace silently",
        togglefloating: "Toggle floating", fullscreen: "Fullscreen", killactive: "Close window",
        exit: "Exit Hyprland", movewindow: "Move window", resizewindow: "Resize window",
        movefocus: "Focus window", focuswindow: "Focus window", swapwindow: "Swap windows",
        togglespecialworkspace: "Toggle special workspace", submap: "Switch submap",
        moveworkspacetomonitor: "Move workspace to monitor", global: "Global shortcut"
    };
    const readable = dispatcher.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/[_-]+/g, " ");
    const name = names[dispatcher] || readable.charAt(0).toUpperCase() + readable.slice(1);
    const argument = text(binding.arg);
    return name + (argument ? ": " + argument : "");
}

function entries(bindings) {
    if (!Array.isArray(bindings))
        return [];

    const rows = [];
    bindings.forEach(binding => {
        if (!binding || typeof binding !== "object" || Array.isArray(binding))
            return;

        const rawKey = text(binding.key);
        let key = rawKey;
        let mask = Number(binding.modmask) || 0;

        // Some Lua bindings include modifiers in the key string as well as the mask.
        let prefix = /^([a-z0-9_]+)\s*\+\s*/i.exec(key);
        while (prefix && modifierMask(prefix[1])) {
            mask |= modifierMask(prefix[1]);
            key = key.slice(prefix[0].length);
            prefix = /^([a-z0-9_]+)\s*\+\s*/i.exec(key);
        }

        if (!key && Number(binding.keycode) > 0)
            key = "code:" + Number(binding.keycode);
        if (!key && binding.catch_all)
            key = "Any Key";
        if (!key)
            return;

        const keys = modifiers.filter(modifier => mask & modifier.mask).map(modifier => modifier.name);
        keys.push(keyLabel(key));
        const context = [];
        const submap = text(binding.submap);
        if (submap)
            context.push("Submap: " + submap);
        if (binding.mouse)
            context.push("Mouse");
        if (binding.release)
            context.push("On release");
        if (binding.repeat)
            context.push("Repeats");
        if (binding.longPress)
            context.push("Long press");
        if (binding.locked)
            context.push("Works while locked");

        const name = actionName(binding);
        rows.push({
            keybinding: true,
            name: name,
            shortcut: keys.join(" + "),
            keys: keys,
            context: context.join(" · "),
            keywords: [rawKey, key, text(binding.dispatcher),
                binding.dispatcher === "__lua" ? "" : text(binding.arg), submap]
        });
    });
    return rows;
}

// Plain output preserves Lua key expressions that older JSON output can omit.
function parse(output) {
    if (typeof output !== "string")
        throw new Error("Invalid Hyprland keybinding output");
    if (!output.trim())
        return [];

    const bindings = [];
    let binding = null;
    output.split(/\r?\n/).forEach(line => {
        const header = /^bind([a-z]*)\s*$/.exec(line);
        if (header) {
            const flags = header[1];
            binding = {
                locked: flags.includes("l"),
                mouse: flags.includes("m"),
                release: flags.includes("r"),
                repeat: flags.includes("e"),
                longPress: flags.includes("o"),
                non_consuming: flags.includes("n"),
                auto_consuming: flags.includes("a")
            };
            bindings.push(binding);
            return;
        }

        // Split only at the field separator; commands and descriptions can contain colons.
        const field = /^\s+([a-z_]+): ?(.*)$/.exec(line);
        if (!binding || !field)
            return;
        const name = field[1];
        const value = field[2];
        if (["submap", "key", "description", "dispatcher", "arg"].includes(name))
            binding[name] = value;
        else if (name === "modmask" || name === "keycode")
            binding[name] = Number(value);
        else if (name === "catchall")
            binding.catch_all = value === "true";
    });

    const rows = entries(bindings);
    if (!rows.length)
        throw new Error("Could not read Hyprland keybindings");
    return rows;
}

function searchText(value) {
    return value.toLowerCase()
        .replace(/\b(control|ctl)\b/g, "ctrl")
        .replace(/\b(meta|win|windows|mod4)\b/g, "super")
        .replace(/\breturn\b/g, "enter")
        .replace(/\bspacebar\b/g, "space")
        .replace(/\bescape\b/g, "esc")
        .replace(/\bplus\b/g, "+");
}

// Keep compositor order: identical shortcuts may have different submaps or triggers.
function find(rows, query) {
    const normalized = searchText(text(query));
    // A lone plus or a doubled separator searches for the actual '+' key.
    const plusKey = /^\+$/.test(normalized) || /\+\s*\+/.test(normalized);
    const combinations = [];
    const remainder = normalized.replace(/\+\s*\+/g, "+__plus_key__")
        .replace(/[^\s+]+(?:\s*\+\s*(?:code\s+\d+|[^\s+]+))+/g, combination => {
            combinations.push(combination.split(/\s*\+\s*/).map(key =>
                key === "__plus_key__" ? "+" : searchText(keyLabel(key))));
            return " ";
        });
    const words = remainder.replace(/\+/g, " ").split(/\s+/).filter(Boolean);
    return rows.filter(row => {
        if (plusKey && !row.keys.includes("+"))
            return false;
        const keys = row.keys.map(key => searchText(key));
        // Combo searches use actual keys so Super+1 cannot match a workspace 10 description.
        if (!combinations.every(combination => combination.every(key => keys.includes(key))))
            return false;
        const fields = searchText([row.name, row.keys.join(" "), row.context]
            .concat(row.keywords || []).join(" "));
        return words.every(word => fields.includes(word));
    });
}
