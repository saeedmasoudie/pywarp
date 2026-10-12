import QtQuick
import "../theme"

Item {
    id: root
    property bool connected: false
    property bool connecting: false
    property bool disconnecting: false
    property bool enabled: true
    signal clicked()

    implicitWidth: 224
    implicitHeight: 224
    readonly property color stateColor: connected
        ? Theme.success
        : connecting || disconnecting ? Theme.warning : Theme.accent
    onStateColorChanged: orbit.requestPaint()

    Rectangle {
        anchors.centerIn: parent
        width: 220
        height: 220
        radius: 110
        color: Qt.rgba(
            root.stateColor.r,
            root.stateColor.g,
            root.stateColor.b,
            0.025
        )
        border.width: 1
        border.color: Qt.rgba(
            root.stateColor.r,
            root.stateColor.g,
            root.stateColor.b,
            0.15
        )
        SequentialAnimation on scale {
            running: root.connected || root.connecting || root.disconnecting
            loops: Animation.Infinite
            NumberAnimation { to: 1.04; duration: 1400; easing.type: Easing.InOutSine }
            NumberAnimation { to: 1; duration: 1400; easing.type: Easing.InOutSine }
        }
    }

    Canvas {
        id: orbit
        anchors.centerIn: parent
        width: 194
        height: 194
        onPaint: {
            const ctx = getContext("2d")
            ctx.reset()
            ctx.strokeStyle = root.stateColor
            ctx.lineWidth = root.connecting || root.disconnecting ? 3 : 1.5
            ctx.lineCap = "round"
            const c = width / 2
            const r = width / 2 - 4
            for (let i = 0; i < 6; ++i) {
                const start = i * Math.PI / 3
                ctx.beginPath()
                ctx.arc(c, c, r, start, start + 0.46)
                ctx.stroke()
            }
        }
        onVisibleChanged: requestPaint()
        NumberAnimation on rotation {
            running: root.connecting || root.disconnecting
            from: 0
            to: 360
            duration: 1350
            loops: Animation.Infinite
        }
        Behavior on opacity {
            NumberAnimation { duration: Theme.animation }
        }
    }

    Rectangle {
        id: core
        anchors.centerIn: parent
        width: 154
        height: 154
        radius: 77
        color: Theme.surface
        border.width: 1
        border.color: root.stateColor
        scale: pointer.pressed ? 0.95 : pointer.containsMouse ? 1.025 : 1
        gradient: Gradient {
            orientation: Gradient.Vertical
            GradientStop {
                position: 0
                color: Qt.rgba(
                    root.stateColor.r,
                    root.stateColor.g,
                    root.stateColor.b,
                    Theme.dark ? 0.17 : 0.1
                )
            }
            GradientStop { position: 1; color: Theme.surface }
        }
        Behavior on scale {
            NumberAnimation {
                duration: Theme.animationFast
                easing.type: Easing.OutCubic
            }
        }
        Behavior on border.color {
            ColorAnimation { duration: Theme.animation }
        }

        Column {
            anchors.centerIn: parent
            spacing: 7
            LineIcon {
                anchors.horizontalCenter: parent.horizontalCenter
                width: 30
                height: 30
                name: root.connecting ? "stop" : "shield"
                iconColor: root.stateColor
                strokeWidth: 2
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: root.connecting
                    ? I18n.t("cancel_connection", "CANCEL")
                    : root.disconnecting
                        ? I18n.t("disconnecting", "CLOSING")
                        : root.connected
                            ? I18n.t("disconnect", "DISCONNECT")
                            : I18n.t("connect", "CONNECT")
                color: Theme.text
                font.pixelSize: 10
                font.weight: Font.Bold
                font.letterSpacing: 1.1
            }
        }

        MouseArea {
            id: pointer
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            enabled: root.enabled
            onClicked: root.clicked()
        }
    }
}
