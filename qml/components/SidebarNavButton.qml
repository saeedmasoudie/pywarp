import QtQuick
import QtQuick.Controls
import "../theme"

Button {
    id: root
    property bool active: false

    implicitWidth: 150
    implicitHeight: 42
    hoverEnabled: true
    leftPadding: 18
    rightPadding: 12

    contentItem: Text {
        text: root.text
        color: root.active
            ? Theme.accent : root.hovered ? Theme.blue : Theme.textMuted
        font.pixelSize: 10
        font.weight: root.active ? Font.DemiBold : Font.Medium
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    background: Rectangle {
        radius: 10
        color: root.active
            ? Theme.accentFaint : "transparent"
        border.width: root.active ? 1 : 0
        border.color: Qt.rgba(
            Theme.accent.r,
            Theme.accent.g,
            Theme.accent.b,
            0.35
        )
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
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            width: 3
            height: root.active ? 20 : root.hovered ? 12 : 0
            radius: 2
            color: root.active ? Theme.accent : Theme.blue
            Behavior on height {
                NumberAnimation {
                    duration: Theme.animation
                    easing.type: Easing.OutCubic
                }
            }
        }
    }
}
