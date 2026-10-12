import QtQuick
import QtQuick.Layouts
import "../theme"

Item {
    id: root
    property bool active: false
    property bool moving: false
    signal stepClicked(string kind)
    property var steps: AppController.protocol === "MASQUE"
        ? [
            {
                "kind": "protocol",
                "label": I18n.t("protocol", "Protocol"),
                "value": AppController.protocol,
                "detail": I18n.t("tunnel_engine", "Tunnel engine")
            },
            {
                "kind": "transport",
                "label": I18n.t("transport", "MASQUE option"),
                "value": AppController.masqueOption,
                "detail": I18n.t("http_transport_preference", "HTTP transport preference")
            },
            {
                "kind": "mode",
                "label": I18n.t("traffic_mode", "Traffic mode"),
                "value": AppController.mode.toUpperCase(),
                "detail": I18n.t("routing_policy", "Routing policy")
            },
            {
                "kind": "endpoint",
                "label": I18n.t("endpoint", "Endpoint"),
                "value": AppController.customEndpoint
                    || AppController.endpointV4
                    || I18n.t("automatic", "Automatic"),
                "detail": AppController.customEndpoint
                    ? I18n.t("custom_route", "Custom route")
                    : I18n.t("cloudflare_selected", "Cloudflare selected")
            }
        ]
        : [
            {
                "kind": "protocol",
                "label": I18n.t("protocol", "Protocol"),
                "value": AppController.protocol,
                "detail": I18n.t("wireguard_tunnel", "WireGuard tunnel")
            },
            {
                "kind": "mode",
                "label": I18n.t("traffic_mode", "Traffic mode"),
                "value": AppController.mode.toUpperCase(),
                "detail": I18n.t("routing_policy", "Routing policy")
            },
            {
                "kind": "endpoint",
                "label": I18n.t("endpoint", "Endpoint"),
                "value": AppController.customEndpoint
                    || AppController.endpointV4
                    || I18n.t("automatic", "Automatic"),
                "detail": AppController.customEndpoint
                    ? I18n.t("custom_route", "Custom route")
                    : I18n.t("cloudflare_selected", "Cloudflare selected")
            }
        ]

    implicitHeight: 140

    RowLayout {
        anchors.fill: parent
        spacing: 14

        Repeater {
            model: root.steps
            Item {
                required property int index
                required property var modelData
                Layout.fillWidth: true
                Layout.fillHeight: true

                Rectangle {
                    id: card
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    height: 110
                    radius: 14
                    color: cardMouse.containsMouse
                        ? Theme.surfaceHover : Theme.surfaceRaised
                    border.width: 1
                    border.color: cardMouse.containsMouse
                        ? Theme.accent : root.active
                            ? Qt.rgba(
                                Theme.secondary.r,
                                Theme.secondary.g,
                                Theme.secondary.b,
                                0.42
                            )
                            : Theme.border
                    scale: cardMouse.pressed ? 0.98
                        : cardMouse.containsMouse ? 1.018 : 1

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
                        anchors.fill: parent
                        anchors.margins: 11
                        spacing: 3
                        RowLayout {
                            Layout.fillWidth: true
                            Rectangle {
                                width: 24
                                height: 24
                                radius: 8
                                color: root.active
                                    ? Theme.secondarySoft
                                    : Theme.surfaceBright
                                Text {
                                    anchors.centerIn: parent
                                    text: index + 1
                                    color: root.active
                                        ? Theme.secondary : Theme.textFaint
                                    font.pixelSize: 9
                                    font.weight: Font.Bold
                                }
                            }
                            Item { Layout.fillWidth: true }
                            Text {
                                visible: cardMouse.containsMouse
                                text: I18n.t("change", "CHANGE")
                                color: Theme.accentHover
                                font.pixelSize: 7
                                font.weight: Font.Bold
                                font.letterSpacing: 0.7
                            }
                        }
                        Text {
                            text: modelData.label.toUpperCase()
                            color: Theme.textFaint
                            font.pixelSize: 7
                            font.weight: Font.Bold
                            font.letterSpacing: 0.8
                        }
                        Text {
                            Layout.fillWidth: true
                            text: modelData.value
                            color: Theme.text
                            font.pixelSize: 11
                            font.weight: Font.DemiBold
                            elide: Text.ElideMiddle
                        }
                        Text {
                            Layout.fillWidth: true
                            text: modelData.detail
                            color: Theme.textMuted
                            font.pixelSize: 8
                            elide: Text.ElideRight
                        }
                    }

                    MouseArea {
                        id: cardMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.stepClicked(modelData.kind)
                    }
                }

                Item {
                    z: 4
                    visible: index < root.steps.length - 1
                    width: 22
                    height: 14
                    x: I18n.rtl ? -20 : parent.width - 2
                    anchors.verticalCenter: parent.verticalCenter

                    Rectangle {
                        anchors.verticalCenter: parent.verticalCenter
                        width: parent.width
                        height: 2
                        radius: 1
                        color: root.active ? Theme.secondary : Theme.borderBright
                    }
                    Rectangle {
                        width: 7
                        height: 7
                        radius: 4
                        anchors.verticalCenter: parent.verticalCenter
                        color: root.moving ? Theme.warning : Theme.secondary
                        visible: root.active || root.moving
                        SequentialAnimation on x {
                            running: root.moving
                            loops: Animation.Infinite
                            NumberAnimation {
                                from: I18n.rtl ? 15 : 0
                                to: I18n.rtl ? 0 : 15
                                duration: 620
                                easing.type: Easing.InOutSine
                            }
                            NumberAnimation {
                                from: I18n.rtl ? 0 : 15
                                to: I18n.rtl ? 15 : 0
                                duration: 620
                                easing.type: Easing.InOutSine
                            }
                        }
                    }
                    Text {
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        text: I18n.rtl ? "‹" : "›"
                        color: root.active ? Theme.secondary : Theme.textFaint
                        font.pixelSize: 16
                    }
                }
            }
        }
    }
}
