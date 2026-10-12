import QtQuick
import "../theme"

Item {
    id: root
    property bool connected: false
    property bool connecting: false
    property bool disconnecting: false
    property bool enabled: true
    property bool compact: false
    signal clicked()

    implicitWidth: compact ? 142 : 190
    implicitHeight: compact ? 42 : 54
    readonly property color stateColor: connected
        ? Theme.success
        : connecting || disconnecting ? Theme.warning : Theme.accent
    opacity: enabled ? 1 : 0.5
    scale: pointer.pressed ? 0.97 : pointer.containsMouse ? 1.015 : 1

    Behavior on scale {
        NumberAnimation {
            duration: Theme.animationFast
            easing.type: Easing.OutCubic
        }
    }

    Rectangle {
        id: shell
        anchors.fill: parent
        radius: root.compact ? 13 : 16
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: root.stateColor }
            GradientStop {
                position: 1
                color: Qt.lighter(root.stateColor, 1.16)
            }
        }
        border.width: 1
        border.color: Qt.rgba(1, 1, 1, 0.24)

        Rectangle {
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            anchors.leftMargin: root.compact ? 6 : 8
            width: root.compact ? 30 : 38
            height: root.compact ? 30 : 38
            radius: root.compact ? 9 : 12
            color: Qt.rgba(0, 0, 0, 0.15)

            LineIcon {
                anchors.centerIn: parent
                width: root.compact ? 17 : 20
                height: root.compact ? 17 : 20
                name: root.connecting ? "stop" : "shield"
                iconColor: root.connected ? "#07140F" : "white"
                strokeWidth: 2
            }

            Rectangle {
                anchors.fill: parent
                radius: parent.radius
                color: "transparent"
                border.width: 2
                border.color: Qt.rgba(1, 1, 1, 0.25)
                visible: root.connecting || root.disconnecting
                SequentialAnimation on opacity {
                    running: visible
                    loops: Animation.Infinite
                    NumberAnimation { to: 0.15; duration: 500 }
                    NumberAnimation { to: 1; duration: 500 }
                }
            }
        }

        Column {
            anchors.left: parent.left
            anchors.leftMargin: root.compact ? 44 : 58
            anchors.verticalCenter: parent.verticalCenter
            spacing: root.compact ? 0 : 1
            Text {
                text: root.connecting
                    ? I18n.t("cancel_connection", "Cancel connection")
                    : root.disconnecting
                        ? I18n.t("disconnecting", "Disconnecting")
                        : root.connected
                            ? I18n.t("disconnect", "Disconnect")
                            : I18n.t("connect", "Quick connect")
                color: root.connected ? "#07140F" : "white"
                font.pixelSize: root.compact ? 9 : 10
                font.weight: Font.Bold
            }
            Text {
                visible: !root.compact
                text: root.connected
                    ? I18n.t("tunnel_active", "Tunnel active")
                    : root.connecting
                        ? I18n.t("tap_to_cancel", "Tap to cancel")
                        : I18n.t("use_current_route", "Use current route")
                color: root.connected
                    ? Qt.rgba(0.03, 0.08, 0.06, 0.7)
                    : Qt.rgba(1, 1, 1, 0.72)
                font.pixelSize: 7
            }
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
