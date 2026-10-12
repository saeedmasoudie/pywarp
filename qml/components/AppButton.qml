import QtQuick
import QtQuick.Controls
import "../theme"

Button {
    id: root
    hoverEnabled: true
    property bool primary: false
    property bool danger: false
    property bool quiet: false
    property bool pill: false
    readonly property color restingColor: primary
        ? Theme.accent
        : danger
            ? Theme.danger
            : quiet
                ? "transparent"
                : Theme.surfaceRaised
    readonly property color hoverTone: danger
        ? Theme.danger : primary ? Theme.accentHover : Theme.blue
    implicitHeight: 42
    leftPadding: 18
    rightPadding: 18
    font.pixelSize: 13
    font.weight: primary ? Font.DemiBold : Font.Medium
    scale: down ? 0.97 : 1

    Behavior on scale {
        NumberAnimation {
            duration: Theme.animationFast
            easing.type: Easing.OutCubic
        }
    }

    contentItem: Text {
        text: root.text
        font: root.font
        color: root.enabled
            ? (root.primary || root.danger
                ? "white"
                : root.hovered ? Theme.blue : Theme.text)
            : Theme.textMuted
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        id: buttonBackground
        radius: root.pill ? height / 2 : Theme.radiusSmall
        color: {
            if (!root.enabled)
                return Theme.surfaceHover
            if (root.down)
                return root.primary ? Qt.darker(Theme.accent, 1.18)
                    : root.danger ? Qt.darker(Theme.danger, 1.15)
                    : Theme.surfaceHover
            return root.restingColor
        }
        border.width: 1
        border.color: root.hovered && root.enabled
            ? root.hoverTone
            : root.primary || root.danger || root.quiet
                ? "transparent" : Theme.border

        Behavior on color {
            ColorAnimation { duration: Theme.animationFast }
        }
        Behavior on border.color {
            ColorAnimation { duration: Theme.animationFast }
        }

        Rectangle {
            anchors.fill: parent
            anchors.margins: 1
            radius: Math.max(0, parent.radius - 1)
            color: root.hoverTone
            opacity: root.hovered && root.enabled ? 0.14 : 0
            Behavior on opacity {
                NumberAnimation { duration: Theme.animationFast }
            }
        }
    }
}
