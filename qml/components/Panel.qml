import QtQuick
import QtQuick.Layouts
import "../theme"

Rectangle {
    id: root
    default property alias content: contentLayout.data
    property int padding: 18
    property bool elevated: false
    property bool interactive: false
    property color glowColor: "transparent"

    function pulseAttention() {
        attentionPulse.restart()
    }

    color: mouseArea.containsMouse && interactive
        ? Theme.surfaceHover : elevated ? Theme.surfaceRaised : Theme.surface
    radius: Theme.radius
    border.color: glowColor.a > 0
        ? Qt.rgba(glowColor.r, glowColor.g, glowColor.b, 0.34)
        : mouseArea.containsMouse && interactive
            ? Theme.borderBright : Theme.border
    border.width: 1
    implicitHeight: contentLayout.implicitHeight + padding * 2
    scale: mouseArea.pressed && interactive ? 0.992 : 1

    Behavior on color {
        ColorAnimation { duration: Theme.animationFast }
    }
    Behavior on border.color {
        ColorAnimation { duration: Theme.animationFast }
    }
    Behavior on scale {
        NumberAnimation {
            duration: Theme.animationFast
            easing.type: Easing.OutCubic
        }
    }

    ColumnLayout {
        id: contentLayout
        anchors.fill: parent
        anchors.margins: root.padding
        spacing: 12
    }

    Rectangle {
        id: attentionBorder
        anchors.fill: parent
        z: 2
        radius: root.radius
        color: "transparent"
        border.width: 2
        border.color: Theme.accent
        opacity: 0

    }

    SequentialAnimation {
        id: attentionPulse
        loops: 3
        NumberAnimation {
            target: attentionBorder
            property: "opacity"
            from: 0
            to: 1
            duration: 220
            easing.type: Easing.OutCubic
        }
        NumberAnimation {
            target: attentionBorder
            property: "opacity"
            from: 1
            to: 0
            duration: 520
            easing.type: Easing.InCubic
        }
    }

    MouseArea {
        id: mouseArea
        anchors.fill: parent
        hoverEnabled: root.interactive
        enabled: root.interactive
        acceptedButtons: Qt.NoButton
    }
}
