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
}
