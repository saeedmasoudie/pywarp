import QtQuick
import QtQuick.Controls
import "../theme"

Button {
    id: root
    property bool active: false

    implicitWidth: Math.max(104, label.implicitWidth + 32)
    implicitHeight: 38
    hoverEnabled: true
    padding: 0

    contentItem: Text {
        id: label
        text: root.text
        color: root.active
            ? Theme.accent : root.hovered ? Theme.blue : Theme.textMuted
        font.pixelSize: 11
        font.weight: root.active ? Font.DemiBold : Font.Medium
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }
    background: Rectangle {
        radius: 11
        color: root.active
            ? Theme.accentFaint : "transparent"
        border.width: root.active ? 1 : 0
        border.color: Theme.borderBright
        Behavior on color {
            ColorAnimation { duration: Theme.animationFast }
        }
        Rectangle {
            anchors.fill: parent
            radius: parent.radius
            color: Theme.blue
            opacity: root.hovered && !root.active ? 0.10 : 0
            Behavior on opacity {
                NumberAnimation { duration: Theme.animationFast }
            }
        }
        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 3
            width: root.active ? 26 : root.hovered ? 14 : 0
            height: 2
            radius: 1
            color: root.active ? Theme.accent : Theme.blue
            Behavior on width {
                NumberAnimation {
                    duration: Theme.animation
                    easing.type: Easing.OutCubic
                }
            }
        }
    }
}
