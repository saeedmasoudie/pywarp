import QtQuick
import QtQuick.Controls
import "../theme"

ScrollBar {
    id: root

    policy: ScrollBar.AsNeeded
    interactive: true
    implicitWidth: 8
    implicitHeight: 8
    padding: 2

    contentItem: Rectangle {
        implicitWidth: 4
        implicitHeight: 40
        radius: 2
        color: root.pressed || root.hovered
            ? Theme.textMuted : Theme.borderBright
        opacity: root.size < 1 && root.active ? 0.9 : 0

        Behavior on color {
            ColorAnimation { duration: Theme.animationFast }
        }
        Behavior on opacity {
            NumberAnimation { duration: Theme.animationFast }
        }
    }

    background: Item {}
}
