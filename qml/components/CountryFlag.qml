import QtQuick
import "../theme"

Rectangle {
    id: root
    property string code: ""

    implicitWidth: 68
    implicitHeight: 48
    radius: 12
    color: Theme.surfaceRaised
    border.color: Theme.borderBright
    clip: true

    Image {
        id: flagImage
        anchors.fill: parent
        source: root.code.length === 2
            ? "https://flagcdn.com/w80/" + root.code.toLowerCase() + ".png"
            : ""
        fillMode: Image.PreserveAspectCrop
        smooth: true
        asynchronous: true
        cache: true
    }

    Text {
        anchors.centerIn: parent
        visible: flagImage.status !== Image.Ready
        text: root.code || "—"
        color: Theme.textMuted
        font.pixelSize: 12
        font.weight: Font.Bold
        font.letterSpacing: 1
    }
}
