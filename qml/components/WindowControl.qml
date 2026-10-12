import QtQuick
import QtQuick.Controls
import "../theme"

Button {
    id: root
    property string symbol: "minimize"
    property bool destructive: false
    readonly property color hoverColor: symbol === "close"
        ? Theme.danger
        : symbol === "maximize" ? Theme.success : Theme.blue

    implicitWidth: 34
    implicitHeight: 28
    hoverEnabled: true
    padding: 0
    ToolTip.visible: hovered
    ToolTip.delay: 500
    ToolTip.text: symbol === "close"
        ? I18n.t("close", "Close")
        : symbol === "maximize"
            ? I18n.t("maximize", "Maximize")
            : symbol === "tiny"
                ? I18n.t("tiny_mode", "Tiny mode")
                : symbol === "expand"
                    ? I18n.t("full_mode", "Full mode")
                    : I18n.t("minimize", "Minimize")

    contentItem: Item {
        Canvas {
            id: iconCanvas
            anchors.centerIn: parent
            width: 14
            height: 14
            onPaint: {
                const ctx = getContext("2d")
                ctx.reset()
                ctx.strokeStyle = root.hovered ? root.hoverColor : Theme.textMuted
                ctx.lineWidth = 1.35
                ctx.lineCap = "round"
                if (root.symbol === "tiny") {
                    ctx.strokeRect(1.8, 3.2, 10.4, 7.6)
                    ctx.beginPath()
                    ctx.moveTo(4.5, 13)
                    ctx.lineTo(9.5, 13)
                    ctx.stroke()
                } else if (root.symbol === "expand") {
                    ctx.strokeRect(1.8, 1.8, 10.4, 10.4)
                    ctx.beginPath()
                    ctx.moveTo(5, 7)
                    ctx.lineTo(9.5, 7)
                    ctx.moveTo(7.25, 4.75)
                    ctx.lineTo(7.25, 9.25)
                    ctx.stroke()
                } else if (root.symbol === "minimize") {
                    ctx.beginPath()
                    ctx.moveTo(2, 10.5)
                    ctx.lineTo(12, 10.5)
                    ctx.stroke()
                } else if (root.symbol === "maximize") {
                    ctx.strokeRect(2.5, 2.5, 9, 9)
                } else {
                    ctx.beginPath()
                    ctx.moveTo(3, 3)
                    ctx.lineTo(11, 11)
                    ctx.moveTo(11, 3)
                    ctx.lineTo(3, 11)
                    ctx.stroke()
                }
            }
        }
        Connections {
            target: root
            function onHoveredChanged() { iconCanvas.requestPaint() }
        }
    }

    background: Rectangle {
        color: root.hovered
            ? Qt.rgba(
                root.hoverColor.r,
                root.hoverColor.g,
                root.hoverColor.b,
                0.13
            )
            : "transparent"
        radius: 9
        scale: root.down ? 0.9 : 1
        Behavior on color {
            ColorAnimation { duration: Theme.animationFast }
        }
        Behavior on scale {
            NumberAnimation { duration: Theme.animationFast }
        }
    }
}
