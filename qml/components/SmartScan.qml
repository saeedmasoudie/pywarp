import QtQuick
import "../theme"

Item {
    id: root
    property bool running: false
    property real progress: 0

    implicitWidth: 110
    implicitHeight: 110

    Canvas {
        anchors.fill: parent
        onPaint: {
            const ctx = getContext("2d")
            ctx.reset()
            const c = width / 2
            ctx.strokeStyle = Theme.borderBright
            ctx.lineWidth = 1
            for (let r of [18, 34, 50]) {
                ctx.beginPath()
                ctx.arc(c, c, r, 0, Math.PI * 2)
                ctx.stroke()
            }
            ctx.beginPath()
            ctx.moveTo(c, 5)
            ctx.lineTo(c, height - 5)
            ctx.moveTo(5, c)
            ctx.lineTo(width - 5, c)
            ctx.stroke()
        }
    }

    Rectangle {
        anchors.centerIn: parent
        width: 8
        height: 8
        radius: 4
        color: root.running ? Theme.warning : Theme.accent
    }

    Item {
        anchors.fill: parent
        rotation: root.running ? 360 : root.progress * 3.6
        NumberAnimation on rotation {
            running: root.running
            from: 0
            to: 360
            duration: 1700
            loops: Animation.Infinite
        }
        Rectangle {
            x: parent.width / 2 - 1
            y: 6
            width: 2
            height: parent.height / 2 - 8
            radius: 1
            gradient: Gradient {
                GradientStop { position: 0; color: Theme.secondary }
                GradientStop {
                    position: 1
                    color: Qt.rgba(
                        Theme.secondary.r,
                        Theme.secondary.g,
                        Theme.secondary.b,
                        0
                    )
                }
            }
        }
    }

    Repeater {
        model: [
            [22, 25], [82, 34], [30, 78], [76, 83]
        ]
        Rectangle {
            required property var modelData
            x: modelData[0]
            y: modelData[1]
            width: 5
            height: 5
            radius: 3
            color: Theme.secondary
            SequentialAnimation on opacity {
                running: root.running
                loops: Animation.Infinite
                NumberAnimation { to: 0.15; duration: 500 }
                NumberAnimation { to: 1; duration: 500 }
            }
        }
    }
}
