import QtQuick
import QtTest
import "../../../src/launcher/EmojiSelection.js" as Selection

TestCase {
    name: "EmojiSelection"

    function test_duplicates_keep_insertion_order() {
        let selected = Selection.add([], "😀");
        selected = Selection.add(selected, "😀");
        selected = Selection.add(selected, "👍🏽");
        compare(Selection.values(selected, null).join(""), "😀😀👍🏽");
        compare(Selection.removeAt(selected, 0).join(""), "😀👍🏽");
        compare(Selection.removeLast(selected, "😀").join(""), "😀👍🏽");
        compare(selected.length, 3);
    }

    function test_search_does_not_change_batch_and_enter_falls_back() {
        compare(Selection.values(["🇳🇵"], {emoji: "😀"}).join(""), "🇳🇵");
        compare(Selection.values([], {emoji: "😀"}).join(""), "😀");
        compare(Selection.values([], null).length, 0);
        compare(Selection.removeLast(["😀"], "missing").length, 1);
        compare(Selection.add([], undefined).length, 0);
    }
}
