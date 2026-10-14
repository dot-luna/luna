import QtQuick
import QtTest
import "../../src/luna-bar/MediaLogic.js" as Media

TestCase {
    name: "Media"

    function player(name, playing) {
        return {dbusName: name, isPlaying: playing, canControl: true,
            canTogglePlaying: true, canGoNext: true, canGoPrevious: true};
    }
    function test_playing_player_wins_over_paused_selection() {
        const paused = player("paused", false);
        const playing = player("playing", true);
        compare(Media.choose([paused, playing], "paused"), playing);
    }
    function test_keeps_current_player_when_multiple_are_playing() {
        const first = player("first", true);
        const selected = player("selected", true);
        compare(Media.choose([first, selected], "selected"), selected);
        compare(Media.choose([selected, first], "selected"), selected);
    }
    function test_keeps_last_player_when_everything_is_paused() {
        const first = player("first", false);
        const selected = player("selected", false);
        compare(Media.choose([first, selected], "selected"), selected);
    }
    function test_removed_player_falls_back_and_empty_is_safe() {
        const remaining = player("remaining", false);
        compare(Media.choose([remaining], "removed"), remaining);
        compare(Media.choose([], "removed"), null);
        compare(Media.choose(null, "removed"), null);
    }
    function test_transport_respects_capabilities() {
        const current = player("player", true);
        const calls = [];
        current.togglePlaying = () => calls.push("toggle");
        current.next = () => calls.push("next");
        current.previous = () => calls.push("previous");
        verify(Media.run(current, "play-pause"));
        verify(Media.run(current, "next"));
        verify(Media.run(current, "previous"));
        compare(calls.join(","), "toggle,next,previous");
        current.canGoNext = false;
        current.canGoPrevious = false;
        current.canTogglePlaying = false;
        verify(!Media.run(current, "next"));
        verify(!Media.run(current, "previous"));
        verify(!Media.run(current, "play-pause"));
        compare(calls.length, 3);
    }
    function test_uncontrollable_or_unknown_actions_do_nothing() {
        const current = player("player", true);
        current.canControl = false;
        verify(!Media.run(current, "next"));
        current.canControl = true;
        verify(!Media.run(current, "quit"));
        verify(!Media.run(null, "play-pause"));
    }
    function test_art_only_uses_local_files() {
        compare(Media.localArt("/tmp/cover #1.png"), "file:///tmp/cover%20%231.png");
        compare(Media.localArt("file:///tmp/cover.png"), "file:///tmp/cover.png");
        for (const source of ["https://example.com/cover.png", "http://localhost/cover.png", "file://server/cover.png", "//server/cover.png", "file:////server/cover.png", "data:image/png;base64,AA", "relative.png", "/tmp/cover\n.png"])
            compare(Media.localArt(source), "");
    }
}
