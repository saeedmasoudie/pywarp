import QtQuick
import QtQuick.Layouts
import "../theme"

Item {
    id: root

    function metricColor(kind, value) {
        const number = parseFloat(value)
        if (isNaN(number))
            return Theme.textMuted
        if (kind === "ping")
            return number <= 80
                ? Theme.success : number <= 180
                    ? Theme.warning : Theme.danger
        if (kind === "loss")
            return number <= 1
                ? Theme.success : number <= 3
                    ? Theme.warning : Theme.danger
        return kind === "received" ? Theme.secondary : Theme.accent
    }

    readonly property color stateColor: AppController.connected
        ? Theme.success
        : AppController.transitioning ? Theme.warning : Theme.textMuted

    Rectangle {
        anchors.fill: parent
        anchors.margins: 8
        radius: Theme.radius
        color: Theme.surface
        border.width: 1
        border.color: Qt.rgba(
            root.stateColor.r,
            root.stateColor.g,
            root.stateColor.b,
            0.5
        )

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 11
            spacing: 7

            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 46
                spacing: 10

                Rectangle {
                    Layout.preferredWidth: 48
                    Layout.preferredHeight: 36
                    radius: 10
                    color: Theme.surfaceRaised
                    border.color: Theme.border
                    CountryFlag {
                        anchors.fill: parent
                        anchors.margins: 2
                        radius: 8
                        code: AppController.countryCode
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6
                        Rectangle {
                            Layout.preferredWidth: 7
                            Layout.preferredHeight: 7
                            radius: 4
                            color: root.stateColor
                        }
                        Text {
                            Layout.fillWidth: true
                            text: AppController.countryName
                            color: Theme.text
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }
                    }
                    Text {
                        Layout.fillWidth: true
                        text: I18n.status(AppController.status)
                            + "  ·  " + AppController.publicIp
                        color: Theme.textMuted
                        font.pixelSize: 9
                        font.family: "monospace"
                        elide: Text.ElideRight
                    }
                }

                QuickConnectButton {
                    compact: true
                    Layout.preferredWidth: implicitWidth
                    Layout.preferredHeight: implicitHeight
                    Layout.alignment: Qt.AlignVCenter
                    connected: AppController.connected
                    connecting: AppController.connecting
                    disconnecting: AppController.disconnecting
                    enabled: !AppController.disconnecting
                        && (!AppController.busy || AppController.connecting)
                    onClicked: AppController.toggleConnection()
                }
            }

            Item { Layout.fillHeight: true }

            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 38
                Layout.alignment: Qt.AlignBottom
                spacing: 6

                Repeater {
                    model: [
                        {
                            "kind": "ping",
                            "label": I18n.t("ping", "PING"),
                            "value": AppController.latency
                        },
                        {
                            "kind": "loss",
                            "label": I18n.t("loss", "LOSS"),
                            "value": AppController.loss
                        },
                        {
                            "kind": "received",
                            "label": I18n.t("received", "RECEIVED"),
                            "value": AppController.received
                        },
                        {
                            "kind": "sent",
                            "label": I18n.t("sent", "SENT"),
                            "value": AppController.sent
                        }
                    ]
                    Rectangle {
                        id: metricCard
                        required property var modelData
                        readonly property color tone: root.metricColor(
                            modelData.kind, modelData.value
                        )
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        radius: 7
                        color: Theme.surfaceRaised
                        border.color: Theme.border
                        Column {
                            anchors.centerIn: parent
                            spacing: 2
                            Text {
                                anchors.horizontalCenter:
                                    parent.horizontalCenter
                                text: modelData.label
                                color: Theme.textFaint
                                font.pixelSize: 7
                                font.weight: Font.Bold
                                font.letterSpacing: 0.6
                            }
                            Text {
                                anchors.horizontalCenter:
                                    parent.horizontalCenter
                                text: modelData.value
                                color: metricCard.tone
                                font.pixelSize: 10
                                font.family: "monospace"
                                font.weight: Font.DemiBold
                            }
                        }
                    }
                }
            }
        }
    }
}
