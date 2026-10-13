import QtQuick
import QtTest
import "../../src/launcher/Search.js" as Search

TestCase {
    name: "LauncherSearch"
    property var entries: [
        {id: "zen", name: "Zen Browser", genericName: "Web Browser", comment: "Browse the web", keywords: ["Internet"], command: ["zen-browser"]},
        {id: "kitty", name: "Kitty", genericName: "Terminal", comment: "", keywords: ["Shell"], command: ["kitty"]},
        {id: "editor", name: "Text Editor", genericName: "Editor", comment: "", keywords: [], command: ["editor"]},
        {id: "hidden", name: "Hidden app", noDisplay: true, command: ["hidden"]},
        {id: "empty", name: "Empty entry", command: []}
    ]

    function test_alphabetical_and_hidden() {
        const found = Search.find(entries, "");
        compare(found.length, 3);
        compare(found[0].id, "kitty");
    }

    function test_case_keywords_and_multiple_words() {
        compare(Search.find(entries, "  WEB   ZEN  ")[0].id, "zen");
        compare(Search.find(entries, "shell")[0].id, "kitty");
        compare(Search.find(entries, "missing").length, 0);
    }

    function test_name_rank_and_input_unchanged() {
        const first = entries[0];
        const other = {id: "another", name: "Another app", comment: "editor", command: ["another"]};
        const found = Search.find(entries.concat([other]), "editor");
        compare(found[0].id, "editor");
        compare(entries[0], first);
    }
    function test_root_search_includes_children_only_for_queries() {
        const menu = [{name: "Apps"}, {name: "System"}];
        compare(Search.rootEntries(menu, entries, "").length, 2);
        compare(Search.rootEntries(menu, entries, "   ").length, 2);
        compare(Search.rootEntries(menu, entries, "system")[0].name, "System");
        compare(Search.rootEntries(menu, entries, "web zen")[0].id, "zen");
        compare(Search.rootEntries(menu, entries, "hidden").length, 0);
        compare(Search.rootEntries(menu, entries, "missing").length, 0);
        // Keep the original desktop-entry object so its execute method remains usable.
        compare(Search.rootEntries(menu, entries, "kitty")[0], entries[1]);
    }

    function test_root_search_combines_sections_and_children() {
        const menu = [{name: "Editor"}];
        const found = Search.rootEntries(menu, entries, "editor");
        compare(found.length, 2);
        compare(found[0], menu[0]);
        compare(found[1].id, "editor");
        compare(Search.find(entries, "system").length, 0);
    }
    function test_nested_menu_scope_and_parent_search() {
        const menu = [
            {name: "Install", route: "install"},
            {name: "Style", parent: "install", route: "install.style", parentLabel: "Install"},
            {name: "Font", parent: "install.style", parentLabel: "Install › Style"}
        ];
        compare(Search.rootEntries(menu, entries, "").length, 1);
        compare(Search.rootEntries(menu, entries, "", "install")[0].name, "Style");
        compare(Search.rootEntries(menu, entries, "", "install.style")[0].name, "Font");
        compare(Search.rootEntries(menu, entries, "install font")[0].name, "Font");
        compare(Search.rootEntries(menu, entries, "font", "install")[0].name, "Font");
        compare(Search.rootEntries(menu, entries, "kitty", "install").length, 0);
        compare(Search.rootEntries(menu, entries, "install", "install.style").length, 1);
    }
    function test_installed_font_search_by_family_package_and_source() {
        const fonts = [
            {name: "ttf-outfit", description: "Outfit", repository: "foreign", target: "ttf-outfit"},
            {name: "My Font — Regular", description: "/home/user/fonts/font.ttf", repository: "local", target: "/home/user/fonts/font.ttf"}
        ];
        compare(Search.installedFonts(fonts, "").length, 2);
        compare(Search.installedFonts(fonts, "OUTFIT foreign")[0].target, "ttf-outfit");
        compare(Search.installedFonts(fonts, "my local")[0].target, fonts[1].target);
        compare(Search.installedFonts(fonts, "missing").length, 0);
    }
    function test_emoji_search_names_categories_and_glyphs() {
        const emoji = [
            { name: "thumbs up: medium skin tone", emoji: "👍🏽", keywords: "People & Body hand-fingers-closed" },
            { name: "flag: Nepal", emoji: "🇳🇵", keywords: "Flags country-flag" }
        ];
        compare(Search.insertEntries(emoji, ":thumbs_up:").length, 1);
        compare(Search.insertEntries(emoji, "nepal")[0].emoji, "🇳🇵");
        compare(Search.insertEntries(emoji, "👍🏽").length, 1);
        compare(Search.insertEntries(emoji, "flags").length, 1);
        compare(Search.insertEntries(emoji, "no match").length, 0);
    }
}
