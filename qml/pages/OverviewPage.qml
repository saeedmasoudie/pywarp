import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"
import "../theme"

Item {
    id: root
    readonly property color stateColor: AppController.connected
        ? Theme.success
        : AppController.transitioning ? Theme.warning : Theme.accent

    function latencyColor(value) {
        const latency = parseFloat(value)
        if (isNaN(latency))
            return Theme.textMuted
        return latency <= 80
            ? Theme.success : latency <= 180
                ? Theme.warning : Theme.danger
    }

    function lossColor(value) {
        const loss = parseFloat(value)
        if (isNaN(loss))
            return Theme.textMuted
        return loss <= 1
            ? Theme.success : loss <= 3
                ? Theme.warning : Theme.danger
    }

    ScrollView {
        anchors.fill: parent
        contentWidth: availableWidth
        clip: true
        background: null
        ScrollBar.horizontal: ScrollBar {
            policy: ScrollBar.AlwaysOff
            visible: false
            implicitWidth: 0
            implicitHeight: 0
        }
        ScrollBar.vertical: ScrollBar {
            policy: ScrollBar.AlwaysOff
            visible: false
            implicitWidth: 0
            implicitHeight: 0
        }

        ColumnLayout {
            width: parent.width
            spacing: 10

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 132
                radius: Theme.radiusLarge
                clip: true
                color: Theme.surface
                border.width: 1
                border.color: Qt.rgba(
                    root.stateColor.r,
                    root.stateColor.g,
                    root.stateColor.b,
                    0.35
                )
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop {
                        position: 0
                        color: Qt.rgba(
                            root.stateColor.r,
                            root.stateColor.g,
                            root.stateColor.b,
                            Theme.dark ? 0.12 : 0.07
                        )
                    }
                    GradientStop { position: 1; color: Theme.surface }
                }

                Rectangle {
                    width: 260
                    height: 260
                    radius: 130
                    x: parent.width * 0.42
                    y: -185
                    color: "transparent"
                    border.width: 1
                    border.color: Qt.rgba(
                        root.stateColor.r,
                        root.stateColor.g,
                        root.stateColor.b,
                        0.1
                    )
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 18
                    spacing: 14

                    CountryFlag {
                        width: 64
                        height: 64
                        radius: 19
                        code: AppController.countryCode
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3
                        RowLayout {
                            spacing: 8
                            Text {
                                text: AppController.countryName
                                color: Theme.text
                                font.pixelSize: 22
                                font.weight: Font.DemiBold
                                font.letterSpacing: -0.4
                            }
                            Rectangle {
                                visible: AppController.countryCode.length > 0
                                implicitWidth: countryCode.implicitWidth + 14
                                implicitHeight: 22
                                radius: 7
                                color: Theme.surfaceBright
                                Text {
                                    id: countryCode
                                    anchors.centerIn: parent
                                    text: AppController.countryCode
                                    color: Theme.textMuted
                                    font.pixelSize: 8
                                    font.weight: Font.Bold
                                }
                            }
                        }
                        Text {
                            text: AppController.connected
                                ? I18n.t(
                                    "protected_cloudflare",
                                    "Protected through Cloudflare WARP"
                                )
                                : I18n.reasonTitle(
                                    AppController.reasonCode,
                                    AppController.status,
                                    AppController.reasonTitle
                                )
                            color: Theme.textMuted
                            font.pixelSize: 10
                        }
                        RowLayout {
                            spacing: 7
                            Rectangle {
                                width: 6
                                height: 6
                                radius: 3
                                color: root.stateColor
                            }
                            Text {
                                text: AppController.publicIp
                                color: Theme.textFaint
                                font.pixelSize: 9
                                font.family: "monospace"
                            }
                        }
                    }

                    ColumnLayout {
                        spacing: 6
                        QuickConnectButton {
                            connected: AppController.connected
                            connecting: AppController.connecting
                            disconnecting: AppController.disconnecting
                            enabled: !AppController.disconnecting
                                && (!AppController.busy
                                    || AppController.connecting)
                            onClicked: AppController.toggleConnection()
                        }
                        Text {
                            Layout.alignment: Qt.AlignHCenter
                            text: I18n.reason(
                                AppController.reasonCode,
                                AppController.status,
                                AppController.reason
                            )
                            color: Theme.textFaint
                            font.pixelSize: 8
                            elide: Text.ElideRight
                            Layout.maximumWidth: 190
                        }
                    }
                }
            }

            Panel {
                Layout.fillWidth: true
                Layout.preferredHeight: 210
                padding: 16
                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        Layout.fillWidth: true
                        text: I18n.t(
                            "connection_route", "Connection route"
                        )
                        color: Theme.text
                        font.pixelSize: 14
                        font.weight: Font.DemiBold
                    }
                    Rectangle {
                        implicitWidth: routeState.implicitWidth + 18
                        implicitHeight: 26
                        radius: 13
                        color: AppController.connected
                            ? Theme.successSoft : Theme.surfaceRaised
                        Text {
                            id: routeState
                            anchors.centerIn: parent
                            text: AppController.connected
                                ? I18n.t("route_active", "Route active")
                                : AppController.transitioning
                                    ? I18n.t(
                                        "building_route", "Building route"
                                    )
                                    : I18n.t(
                                        "route_preview", "Route preview"
                                    )
                            color: AppController.connected
                                ? Theme.success : Theme.textMuted
                            font.pixelSize: 8
                            font.weight: Font.DemiBold
                        }
                    }
                }
                RouteRoadmap {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    active: AppController.connected
                    moving: AppController.transitioning
                    onStepClicked: function(kind) {
                        AppController.navigateToSetting(kind)
                    }
                }
            }

            Panel {
                Layout.fillWidth: true
                Layout.preferredHeight: 210
                padding: 16

                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        Layout.fillWidth: true
                        text: I18n.t(
                            "network_telemetry", "Network telemetry"
                        )
                        color: Theme.text
                        font.pixelSize: 14
                        font.weight: Font.DemiBold
                    }
                    Text {
                        text: AppController.connected
                            ? I18n.t("live", "Live")
                            : I18n.t("waiting_for_tunnel", "Waiting for tunnel")
                        color: AppController.connected
                            ? Theme.secondary : Theme.textFaint
                        font.pixelSize: 8
                        font.weight: Font.DemiBold
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: 12

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.horizontalStretchFactor: 45
                        radius: 12
                        color: Theme.surfaceRaised
                        border.color: Theme.border

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 11
                            spacing: 4
                            RowLayout {
                                Layout.fillWidth: true
                                Text {
                                    Layout.fillWidth: true
                                    text: I18n.t(
                                        "ping_history", "Ping history"
                                    )
                                    color: Theme.textMuted
                                    font.pixelSize: 9
                                }
                                LiveValue {
                                    value: AppController.latency
                                    textColor: root.latencyColor(value)
                                    pixelSize: 14
                                }
                            }
                            Sparkline {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                values: AppController.latencyHistory
                                lineColor: root.latencyColor(
                                    AppController.latency
                                )
                            }
                        }
                    }

                    GridLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.horizontalStretchFactor: 55
                        columns: 2
                        columnSpacing: 8
                        rowSpacing: 8

                        Repeater {
                            model: [
                                {
                                    "label": I18n.t(
                                        "global_ip", "GLOBAL IP"
                                    ),
                                    "value": AppController.publicIp,
                                    "detail": AppController.countryCode,
                                    "tone": Theme.accent
                                },
                                {
                                    "label": I18n.t(
                                        "packet_loss", "PACKET LOSS"
                                    ),
                                    "value": AppController.loss,
                                    "detail": AppController.handshake,
                                    "tone": root.lossColor(
                                        AppController.loss
                                    )
                                },
                                {
                                    "label": I18n.t(
                                        "received", "RECEIVED"
                                    ),
                                    "value": AppController.received,
                                    "detail": AppController.downloadRate,
                                    "tone": Theme.secondary
                                },
                                {
                                    "label": I18n.t("sent", "SENT"),
                                    "value": AppController.sent,
                                    "detail": AppController.uploadRate,
                                    "tone": Theme.accent
                                }
                            ]
                            Rectangle {
                                required property var modelData
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                radius: 11
                                color: Theme.surfaceRaised
                                border.color: Theme.border
                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 9
                                    spacing: 3
                                    Text {
                                        text: modelData.label
                                        color: Theme.textFaint
                                        font.pixelSize: 7
                                        font.weight: Font.Bold
                                        font.letterSpacing: 0.7
                                    }
                                    LiveValue {
                                        Layout.fillWidth: true
                                        value: modelData.value
                                        textColor: modelData.tone
                                        pixelSize: 13
                                    }
                                    Text {
                                        text: modelData.detail
                                        color: Theme.textMuted
                                        font.pixelSize: 8
                                        elide: Text.ElideRight
                                        Layout.fillWidth: true
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
