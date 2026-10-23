import QtQuick
import QtQuick.Controls.Basic
import QtTest
import "../../../src/launcher" as Launcher

Item {
    width: 300
    height: 200

    ListView {
        id: list
        anchors.fill: parent
        model: 40
        delegate: Button { required property int index; width: 300; height: 30; hoverEnabled: true }
    }
    Launcher.ListPointer {
        anchors.fill: parent
        view: list
        onHoveredIndex: index => list.currentIndex = index
    }
    TestCase {
        name: "ListPointer"
        when: windowShown

        function test_scroll_does_not_override_keyboard_selection() {
            mouseMove(list, 20, 45);
            mouseMove(list, 25, 45);
            tryCompare(list, "currentIndex", 1);
            list.currentIndex = 25;
            list.positionViewAtIndex(25, ListView.Contain);
            wait(100);
            compare(list.currentIndex, 25);
            mouseMove(list, 30, 45);
            tryCompare(list, "currentIndex", list.indexAt(30, 45 + list.contentY));
        }
    }
}
