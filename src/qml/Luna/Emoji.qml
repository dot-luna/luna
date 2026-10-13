import QtQuick

// Render bundled color artwork without the monochrome tint used by menu icons.
Item {
    id: root
    required property string glyph
    property string artwork: ""

    Image {
        id: image
        anchors.fill: parent
        source: root.artwork ? Qt.resolvedUrl("emoji/" + root.artwork) : ""
        sourceSize: Qt.size(width * Screen.devicePixelRatio, height * Screen.devicePixelRatio)
        fillMode: Image.PreserveAspectFit
        asynchronous: true
    }
    Text {
        anchors.centerIn: parent
        visible: !root.artwork || image.status === Image.Error
        text: root.glyph
        font.family: "Noto Color Emoji"
        font.pixelSize: Math.min(root.width, root.height)
    }
}
