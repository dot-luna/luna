import QtQuick
import QtTest
import "../../src/launcher/FontSelection.js" as Selection

TestCase {
    name: "FontSelection"

    function test_toggle_persists_across_result_objects() {
        const entry = {name: "ttf-outfit", repository: "aur"};
        const selected = Selection.toggle([], entry);
        verify(Selection.contains(selected, {name: "ttf-outfit", repository: "aur"}));
        compare(Selection.toggle(selected, entry).length, 0);
        compare(selected.length, 1);
    }

    function test_installed_and_missing_entries_cannot_be_selected() {
        compare(Selection.toggle([], null).length, 0);
        compare(Selection.toggle([], {name: "ttf-test", repository: "extra", installed: true}).length, 0);
        compare(Selection.toggle([], {name: "Apps"}).length, 0);
    }

    function test_enter_prefers_batch_even_without_visible_results() {
        const entry = {name: "ttf-outfit", repository: "aur"};
        compare(Selection.targets([entry], null)[0], entry);
        compare(Selection.targets([], entry)[0], entry);
        compare(Selection.targets([], null).length, 0);
    }

    function test_mixed_sources_and_exact_local_targets() {
        const packages = [{name: "ttf-one", repository: "extra"}, {name: "ttf-two", repository: "aur"}];
        compare(Selection.argumentsFor(packages, false), ["ttf-one", "extra", "ttf-two", "aur"]);
        const local = {target: "/home/user/fonts/a 'font.ttf"};
        compare(Selection.toggle([], local).length, 1);
        compare(Selection.argumentsFor([local, {target: "ttf-one"}], true), [local.target, "ttf-one"]);
    }
    function test_grouped_local_targets_and_selection_identity() {
        const family = {selectionKey: "local:/fonts/Outfit", target: "/fonts/a.ttf", targets: ["/fonts/a.ttf", "/fonts/b.ttf"]};
        const refreshed = {selectionKey: family.selectionKey, target: "/fonts/b.ttf", targets: family.targets};
        const other = {selectionKey: "local:/copy/Outfit", target: "/copy/a.ttf", targets: ["/copy/a.ttf"]};
        verify(Selection.contains([family], refreshed));
        verify(!Selection.contains([family], other));
        compare(Selection.argumentsFor([family, refreshed, other], true), ["/fonts/a.ttf", "/fonts/b.ttf", "/copy/a.ttf"]);
    }
}
