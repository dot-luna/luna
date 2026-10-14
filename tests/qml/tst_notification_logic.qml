import QtQuick
import QtTest
import "../../src/luna-bar/notifications/NotificationLogic.js" as Logic

TestCase {
    name: "NotificationLogic"

    function test_timeout_units_defaults_and_persistent_critical() {
        compare(Logic.timeout({urgency: 0, expireTimeout: -1}), 4000);
        compare(Logic.timeout({urgency: 1, expireTimeout: -1}), 7000);
        compare(Logic.timeout({urgency: 1, expireTimeout: 250}), 250);
        compare(Logic.timeout({urgency: 1, expireTimeout: 0}), 0);
        compare(Logic.timeout({urgency: 2, expireTimeout: 20}), 0);
    }

    function test_snapshot_keeps_plain_values_and_untrusted_markup_as_text() {
        const notification = {
            id: 12, appName: "Example", summary: "<b>Title</b>", body: "<img src='https://example.test/image'>",
            urgency: 1, actions: [{identifier: "open", text: "Open"}], image: "", appIcon: "example"
        };
        const entry = Logic.snapshot(notification, 1234, true);
        notification.actions[0].text = "Changed";
        compare(entry.actions[0].text, "Open");
        compare(entry.summary, "<b>Title</b>");
        compare(entry.body, notification.body);
        compare(entry.timestamp, 1234);
        compare(entry.unread, true);
        compare(entry.live, true);
    }

    function test_critical_popups_first_then_newest() {
        const entries = [{id: 1, urgency: 2, timestamp: 1}, {id: 2, urgency: 0, timestamp: 3}, {id: 3, urgency: 1, timestamp: 2}];
        entries.sort(Logic.popupOrder);
        compare(entries.map(entry => entry.id), [1, 2, 3]);
    }

    function test_close_removes_client_actions_and_expired_image_handles() {
        const entry = Logic.closed(Logic.snapshot({id: 1, image: "image://qsimage/20/1", actions: [{identifier: "open", text: "Open"}]}, 1, true));
        compare(entry.live, false);
        compare(entry.actions.length, 0);
        compare(entry.image, "");
        compare(entry.unread, true);
    }

    function test_screenshot_open_survives_close_with_a_safe_local_image() {
        const entry = Logic.snapshot({id: 1, appName: "Luna Screenshot", image: "image://icon//tmp/my image.png", hints: {"image-path": "/tmp/my image.png"}}, 1, true);
        compare(entry.image, "/tmp/my image.png");
        compare(entry.actions[0].identifier, "luna-open-image");
        const archived = Logic.closed(entry);
        compare(archived.actions[0].identifier, "luna-open-image");
        compare(archived.live, false);
        compare(Logic.snapshot({appName: "Other", image: "/tmp/image.png"}, 1, true).actions.length, 0);
    }

    function test_local_images_reject_remote_hosts_urls_and_invalid_encodings() {
        compare(Logic.localImagePath("file:///tmp/a%20b.png"), "/tmp/a b.png");
        compare(Logic.localImagePath("/tmp/picture.JPEG"), "/tmp/picture.JPEG");
        ["https://example.test/a.png", "file://host/tmp/a.png", "//host/a.png", "image://qsimage/1/1", "file:///tmp/%ZZ.png", "/tmp/program.desktop", "/tmp/a.png\n", "relative.png"].forEach(path => compare(Logic.localImagePath(path), ""));
    }

    function test_recording_open_survives_close_only_for_a_valid_luna_recording() {
        const entry = Logic.snapshot({appName: "Luna Recording", hints: {"x-luna-recording": "file:///tmp/my%20recording.mp4"}}, 1, true);
        compare(entry.recordingFile, "/tmp/my recording.mp4");
        compare(entry.actions, [{identifier: "luna-open-recording", text: "Open recording"}]);
        compare(Logic.closed(entry).actions, entry.actions);
        compare(Logic.closed(entry).recordingFile, entry.recordingFile);
        const other = Logic.snapshot({appName: "Other", hints: {"x-luna-recording": "/tmp/recording.mp4"}}, 1, false);
        compare(other.recordingFile, "");
        compare(other.actions.length, 0);
    }

    function test_recording_paths_reject_remote_urls_hosts_and_other_file_types() {
        compare(Logic.localRecordingPath("/tmp/my ' recording.MP4"), "/tmp/my ' recording.MP4");
        compare(Logic.localRecordingPath("file:///tmp/a%20b.mp4"), "/tmp/a b.mp4");
        ["https://example.test/a.mp4", "file://host/tmp/a.mp4", "//host/a.mp4", "relative.mp4", "/tmp/file.desktop",
         "/tmp/file.png", "/tmp/file.mkv", "file:///tmp/%ZZ.mp4", "file:///tmp/%00.mp4", "/tmp/file.mp4\n"].forEach(path => {
            compare(Logic.localRecordingPath(path), "");
            compare(Logic.snapshot({appName: "Luna Recording", hints: {"x-luna-recording": path}}, 1, false).actions.length, 0);
        });
    }

    function test_desktop_lookup_accepts_ids_without_interpreting_paths_or_commands() {
        compare(Logic.desktopId("org.example.App.desktop"), "org.example.App");
        compare(Logic.desktopId("luna-test"), "luna-test");
        ["../app", "/tmp/app.desktop", "app;command", "app arg", ""].forEach(id => compare(Logic.desktopId(id), ""));
        compare(Logic.snapshot({desktopEntry: "org.example.App"}, 1, false).desktopEntry, "org.example.App");
    }

    function test_sender_icon_takes_precedence_over_desktop_entry_fallback() {
        const notification = {appIcon: "sender-icon", hints: {"image-path": "kitty"}};
        compare(Logic.snapshot(notification, 1, false, "desktop-icon").appIcon, "sender-icon");
        notification.appIcon = "";
        compare(Logic.snapshot(notification, 1, false, "desktop-icon").appIcon, "desktop-icon");
        compare(Logic.snapshot(notification, 1, false).appIcon, "kitty");
    }

    function test_named_image_hints_supply_sender_icons_without_promoting_photos() {
        ["kitty", "zen-browser", "org.example.App", "example_icon-symbolic"].forEach(icon => {
            const entry = Logic.snapshot({hints: {"image-path": icon}, image: "image://icon/" + icon}, 1, false);
            compare(entry.appIcon, icon);
            compare(entry.image, "image://icon/" + icon);
        });
        compare(Logic.snapshot({hints: {image_path: "zed"}}, 1, false).appIcon, "zed");
        ["/tmp/photo.png", "file:///tmp/photo.png", "https://example.test/photo.png", "icons/app.png",
         "icon;command", "icon arg", "kitty\n", ".", "", 42].forEach(hint => {
            compare(Logic.snapshot({hints: {"image-path": hint}}, 1, false).appIcon, "");
        });
    }

    function test_sounds_only_for_new_visible_notifications_without_suppression_hint() {
        compare(Logic.shouldPlaySound({}, false, false), true);
        compare(Logic.shouldPlaySound({}, true, false), false);
        compare(Logic.shouldPlaySound({}, false, true), false);
        compare(Logic.shouldPlaySound({lastGeneration: true, urgency: 2}, false, false), false);
        compare(Logic.shouldPlaySound({hints: {"suppress-sound": true}}, false, false), false);
        compare(Logic.shouldPlaySound({hints: {"suppress-sound": 1}}, false, false), false);
        compare(Logic.shouldPlaySound({hints: {"suppress-sound": false}}, false, false), true);
    }
}
