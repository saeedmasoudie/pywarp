import QtQuick
import "../theme"

Item {
    id: root
    property real value: 0
    property bool running: false

    implicitHeight: 10

    Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: Theme.surfaceBright
        border.color: Theme.border
        clip: true

        Rectangle {
            id: fill
            width: Math.max(
                root.value > 0 ? parent.height : 0,
                parent.width * Math.max(0, Math.min(100, root.value)) / 100
            )
            height: parent.height
            radius: height / 2
            clip: true
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: Theme.accent }
                GradientStop { position: 1; color: Theme.secondary }
            }
            Behavior on width {
                NumberAnimation {
                    duration: 360
                    easing.type: Easing.OutCubic
                }
            }

            Rectangle {
                width: 36
                height: parent.height
                radius: parent.radius
                color: Qt.rgba(1, 1, 1, 0.22)
                visible: root.running
                SequentialAnimation on x {
                    running: root.running
                    loops: Animation.Infinite
                    NumberAnimation {
                        from: I18n.rtl ? Math.max(0, fill.width) : -36
                        to: I18n.rtl ? -36 : Math.max(0, fill.width)
                        duration: 900
                        easing.type: Easing.InOutSine
                    }
                }
            }
        }
    }
}
