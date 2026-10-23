import QtQuick
import QtTest
import "../../../src/launcher/Keybindings.js" as Keybindings

TestCase {
    name: "Keybindings"

    function test_live_description_and_modifier_order() {
        const binding = {modmask: 77, key: "Return", description: "  Open terminal  ", dispatcher: "__lua", arg: "10"};
        const rows = Keybindings.entries([binding]);
        compare(rows.length, 1);
        compare(rows[0].keybinding, true);
        compare(rows[0].name, "Open terminal");
        compare(rows[0].shortcut, "Super + Ctrl + Shift + Alt + Enter");
        compare(rows[0].keys, ["Super", "Ctrl", "Shift", "Alt", "Enter"]);
        compare(rows[0].context, "");
        compare(binding.description, "  Open terminal  ");
    }

    function test_all_modifier_bits() {
        const row = Keybindings.entries([{modmask: 255, key: "x"}])[0];
        compare(row.keys, ["Super", "Ctrl", "Shift", "Alt", "CapsLock", "Mod2", "Mod3", "Mod5", "X"]);
    }

    function test_missing_descriptions_keep_actions_without_callback_ids() {
        const rows = Keybindings.entries([
            {modmask: 64, key: "Return", dispatcher: "exec", arg: "kitty"},
            {modmask: 65, key: "2", description: " ", dispatcher: "movetoworkspace", arg: "2"},
            {modmask: 64, key: "Space", dispatcher: "__lua", arg: "9471"},
            {modmask: 0, key: "x", dispatcher: "custom_action", arg: "test"}
        ]);
        compare(rows.length, 4);
        compare(rows[0].name, "Run: kitty");
        compare(rows[1].name, "Move to workspace: 2");
        compare(rows[2].name, "Custom action");
        compare(rows[3].name, "Custom action: test");
        compare(Keybindings.find(rows, "9471").length, 0);
        compare(Keybindings.find(rows, "exec kitty")[0], rows[0]);
    }

    function test_same_shortcut_preserves_submaps_and_flags() {
        const rows = Keybindings.entries([
            {modmask: 0, key: "r", submap: "resize", description: "Resize", repeat: true},
            {modmask: 0, key: "r", submap: "move", description: "Move", release: true, longPress: true, locked: true},
            {modmask: 0, key: "r", description: "Default"}
        ]);
        compare(rows.length, 3);
        compare(rows[0].context, "Submap: resize · Repeats");
        compare(rows[1].context, "Submap: move · On release · Long press · Works while locked");
        compare(Keybindings.find(rows, "r")[2].name, "Default");
        compare(Keybindings.find(rows, "resize repeat")[0], rows[0]);
        compare(Keybindings.find(rows, "move release long locked")[0], rows[1]);
    }

    function test_mouse_keycodes_and_embedded_modifiers() {
        const rows = Keybindings.entries([
            {modmask: 64, key: "mouse:272", dispatcher: "movewindow", mouse: true},
            {modmask: 64, key: "mouse:273"},
            {modmask: 0, key: "mouse:274"},
            {modmask: 0, key: "mouse:275"},
            {modmask: 0, key: "", keycode: 30},
            {modmask: 64, key: "SUPER + code:20", keycode: 20},
            {modmask: 0, key: "CONTROL + SUPER + Space"},
            {modmask: 0, key: "mouse_down"}
        ]);
        compare(rows[0].shortcut, "Super + Left Mouse");
        compare(rows[0].context, "Mouse");
        compare(rows[1].shortcut, "Super + Right Mouse");
        compare(rows[2].shortcut, "Middle Mouse");
        compare(rows[3].shortcut, "Mouse 275");
        compare(rows[4].shortcut, "Code 30");
        compare(rows[5].shortcut, "Super + Code 20");
        compare(rows[6].shortcut, "Super + Ctrl + Space");
        compare(rows[7].shortcut, "Scroll Down");
        compare(Keybindings.find(rows, "super+code:20")[0], rows[5]);
        compare(Keybindings.find(rows, "mouse:272")[0], rows[0]);
    }

    function test_search_action_shortcut_and_aliases() {
        const rows = Keybindings.entries([
            {modmask: 68, key: "Return", description: "Open terminal", dispatcher: "exec", arg: "kitty"},
            {modmask: 64, key: "Space", description: "Open launcher"},
            {modmask: 0, key: "XF86AudioRaiseVolume", description: "Raise volume"},
            {modmask: 0, key: "Escape", description: "Leave submap"}
        ]);
        const queries = ["terminal", "  CTRL+SUPER+ENTER  ", "Meta Control Return", "Win+Ctrl+Enter", "windows ctl kitty"];
        queries.forEach(query => compare(Keybindings.find(rows, query)[0], rows[0]));
        compare(Keybindings.find(rows, "SUPER+spacebar launcher")[0], rows[1]);
        compare(Keybindings.find(rows, "XF86AudioRaiseVolume")[0], rows[2]);
        compare(Keybindings.find(rows, "escape")[0], rows[3]);
        compare(Keybindings.find(rows, "esc")[0], rows[3]);
        compare(Keybindings.find(rows, "missing").length, 0);
        compare(Keybindings.find(rows, "   ").length, 4);
    }

    function test_plus_is_a_key_as_well_as_a_separator() {
        const rows = Keybindings.entries([
            {modmask: 64, key: "+", description: "Grow window"},
            {modmask: 64, key: "Return", description: "Open terminal"},
            {modmask: 64, key: "SUPER + plus", description: "Another plus"}
        ]);
        compare(rows[0].shortcut, "Super + +");
        compare(rows[2].shortcut, "Super + +");
        ["+", "super++", "Super + +", "Super + plus"].forEach(query => {
            const found = Keybindings.find(rows, query);
            compare(found.length, 2);
            compare(found[0], rows[0]);
            compare(found[1], rows[2]);
        });
        compare(Keybindings.find(rows, "Super+Return")[0], rows[1]);
    }

    function test_combo_search_uses_actual_keys_instead_of_description_digits() {
        const rows = Keybindings.entries([
            {modmask: 65, key: "1", description: "Move window to workspace 1"},
            {modmask: 65, key: "0", description: "Move window to workspace 10"},
            {modmask: 64, key: "code:20", description: "Resize window"}
        ]);
        ["Super+Shift+1", "Win + Shift + 1", "workspace Super+Shift+1"].forEach(query => {
            const found = Keybindings.find(rows, query);
            compare(found.length, 1);
            compare(found[0], rows[0]);
        });
        compare(Keybindings.find(rows, "Super+Shift+0")[0], rows[1]);
        compare(Keybindings.find(rows, "workspace 1").length, 2);
        compare(Keybindings.find(rows, "Super + Code 20")[0], rows[2]);
    }

    function test_invalid_data_and_catch_all() {
        compare(Keybindings.entries(null).length, 0);
        compare(Keybindings.entries({}).length, 0);
        compare(Keybindings.entries("not JSON").length, 0);
        const rows = Keybindings.entries([null, false, "binding", [], {}, {key: ""}, {keycode: 0}, {catch_all: true, dispatcher: "submap", arg: "reset"}]);
        compare(rows.length, 1);
        compare(rows[0].shortcut, "Any Key");
        compare(rows[0].name, "Switch submap: reset");
    }

    function test_plain_output_retains_key_expressions_and_colons() {
        const output = "bindd\n"
            + "\tmodmask: 64\n\tsubmap: \n\tkey: SUPER + code:20\n\tkeycode: 0\n"
            + "\tcatchall: false\n\tdescription: Resize: smaller\n\tdispatcher: __lua\n\targ: 17\n\n"
            + "bind\n\tmodmask: 0\n\tkey: F1\n\tdispatcher: exec\n"
            + "\targ: notify-send 'Notice: Ready' https://example.test:8080\n";
        const rows = Keybindings.parse(output);
        compare(rows.length, 2);
        compare(rows[0].name, "Resize: smaller");
        compare(rows[0].shortcut, "Super + Code 20");
        compare(rows[0].context, "");
        compare(rows[1].name, "Run: notify-send 'Notice: Ready' https://example.test:8080");
        compare(Keybindings.find(rows, "example.test:8080")[0], rows[1]);
    }

    function test_plain_output_flags_keycodes_and_catch_all() {
        const rows = Keybindings.parse("bindlmerod\r\n"
            + "\tmodmask: 64\r\n\tsubmap: resize\r\n\tkey: mouse:273\r\n\tdescription: Resize window\r\n"
            + "\tdispatcher: resizewindow\r\n\targ: \r\n\r\n"
            + "bind\n\tmodmask: 1\n\tkey: \n\tkeycode: 20\n\tdispatcher: __lua\n\targ: 22\n\n"
            + "bind\n\tkey: \n\tkeycode: 0\n\tcatchall: true\n\tdispatcher: submap\n\targ: reset\n");
        compare(rows.length, 3);
        compare(rows[0].shortcut, "Super + Right Mouse");
        compare(rows[0].context, "Submap: resize · Mouse · On release · Repeats · Long press · Works while locked");
        compare(rows[1].shortcut, "Shift + Code 20");
        compare(rows[1].name, "Custom action");
        compare(rows[2].shortcut, "Any Key");
    }

    function test_plain_output_empty_and_malformed() {
        compare(Keybindings.parse("").length, 0);
        compare(Keybindings.parse("  \n\t").length, 0);
        [null, "not Hyprland bindings", "bind\n\tdispatcher: exec\n"].forEach(output => {
            let failed = false;
            try {
                Keybindings.parse(output);
            } catch (error) {
                failed = true;
            }
            verify(failed, "Malformed output should report a loading error");
        });
    }
}
