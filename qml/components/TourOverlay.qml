import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

Item {
    id: root
    property int step: 0
    property rect targetRect: Qt.rect(0, 0, 0, 0)
    readonly property int textAlignment: I18n.rtl
        ? Text.AlignRight : Text.AlignLeft
    signal finished()

    readonly property var steps: [
        {
            "target": "mode",
            "page": I18n.t("connection", "Connection"),
            "title": I18n.t("traffic_mode", "Traffic mode"),
            "body": I18n.t(
                "choose_protection",
                "Choose what Cloudflare WARP should protect."
            ),
            "icon": "shield"
        },
        {
            "target": "protocol",
            "page": I18n.t("connection", "Connection"),
            "title": I18n.t("tunnel_engine", "Tunnel engine"),
            "body": I18n.t(
                "choose_protocol",
                "Choose WireGuard or MASQUE for the encrypted tunnel."
            ),
            "icon": "network"
        },
        {
            "target": "endpoint",
            "page": I18n.t("advanced", "Advanced"),
            "title": I18n.t("tunnel_endpoint", "Tunnel endpoint"),
            "body": I18n.t(
                "endpoint_hint",
                "Set an IP and port, or let Cloudflare select the route."
            ),
            "icon": "network"
        },
        {
            "target": "smart",
            "page": I18n.t("smart_test", "Smart route"),
            "title": I18n.t("smart_lab", "Smart connection test"),
            "body": I18n.t(
                "smart_desc",
                "Tests WARP profiles and keeps the first route with a verified tunnel and internet access."
            ),
            "icon": "activity"
        },
        {
            "target": "compatibility",
            "page": I18n.t("advanced", "Advanced"),
            "title": I18n.t(
                "compatibility_tools",
                "Difficult network compatibility"
            ),
            "body": I18n.t(
                "compatibility_hint",
                "Targeted fixes for high latency, packet loss, MTU black holes, and fragmented DNS handshakes."
            ),
            "icon": "advanced"
        }
    ]

    function focusCurrent() {
        focusTimer.restart()
    }

    function start() {
        step = 0
        targetRect = Qt.rect(0, 0, 0, 0)
        visible = true
        focusCurrent()
    }

    function pointTo(rect) {
        targetRect = rect
    }

    onStepChanged: focusCurrent()

    Timer {
        id: focusTimer
        interval: 80
        onTriggered: AppController.navigateToSetting(
            root.steps[root.step].target
        )
    }

    Rectangle {
        anchors.fill: parent
        color: Qt.rgba(Theme.background.r, Theme.background.g,
            Theme.background.b, 0.38)
    }

    MouseArea {
        anchors.fill: parent
    }

    Rectangle {
        id: focusRing
        x: root.targetRect.x
        y: root.targetRect.y
        width: root.targetRect.width
        height: root.targetRect.height
        visible: root.targetRect.width > 0
        radius: Theme.radius
        color: "transparent"
        border.width: 2
        border.color: Theme.accent

        SequentialAnimation on opacity {
            running: focusRing.visible && root.visible
            loops: Animation.Infinite
            NumberAnimation {
                from: 0.95
                to: 0.3
                duration: 700
                easing.type: Easing.InOutSine
            }
            NumberAnimation {
                from: 0.3
                to: 0.95
                duration: 700
                easing.type: Easing.InOutSine
            }
        }

    }

    Rectangle {
        id: tourCard
        width: Math.min(560, parent.width - 48)
        implicitHeight: tourContent.implicitHeight + 32
        height: implicitHeight
        x: root.targetRect.width > 0
            ? Math.max(
                24,
                Math.min(
                    root.width - width - 24,
                    root.targetRect.x
                        + root.targetRect.width / 2 - width / 2
                )
            )
            : (root.width - width) / 2
        y: root.targetRect.width <= 0
            ? root.height - height - 26
            : root.targetRect.y < root.height * 0.48
                ? Math.min(
                    root.height - height - 24,
                    root.targetRect.y + root.targetRect.height + 16
                )
                : Math.max(54, root.targetRect.y - height - 16)
        radius: Theme.radiusLarge
        color: Theme.surface
        border.width: 1
        border.color: Theme.accent

        Behavior on x {
            NumberAnimation {
                duration: Theme.animation
                easing.type: Easing.OutCubic
            }
        }
        Behavior on y {
            NumberAnimation {
                duration: Theme.animation
                easing.type: Easing.OutCubic
            }
        }

        ColumnLayout {
            id: tourContent
            anchors.fill: parent
            anchors.margins: 16
            spacing: 12

            RowLayout {
                Layout.fillWidth: true
                spacing: 12
                Rectangle {
                    Layout.preferredWidth: 42
                    Layout.preferredHeight: 42
                    radius: 13
                    color: Theme.accentSoft
                    LineIcon {
                        anchors.centerIn: parent
                        width: 21
                        height: 21
                        name: root.steps[root.step].icon
                        iconColor: Theme.accent
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    Text {
                        Layout.fillWidth: true
                        text: I18n.t("guided_tour", "GUIDED TOUR")
                            + " · " + (root.step + 1)
                            + "/" + root.steps.length
                        color: Theme.accent
                        font.pixelSize: 9
                        font.weight: Font.Bold
                        font.letterSpacing: 0.8
                        horizontalAlignment: root.textAlignment
                    }
                    Text {
                        Layout.fillWidth: true
                        text: I18n.rtl
                            ? root.steps[root.step].title
                                + "  ←  " + root.steps[root.step].page
                            : root.steps[root.step].page
                                + "  →  " + root.steps[root.step].title
                        color: Theme.text
                        font.pixelSize: 16
                        font.weight: Font.DemiBold
                        elide: Text.ElideRight
                        horizontalAlignment: root.textAlignment
                    }
                }
            }

            Text {
                Layout.fillWidth: true
                text: root.steps[root.step].body
                color: Theme.textMuted
                font.pixelSize: 11
                lineHeight: 1.25
                wrapMode: Text.WordWrap
                horizontalAlignment: root.textAlignment
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                AppButton {
                    text: I18n.t("skip_tour", "Exit tour")
                    quiet: true
                    onClicked: {
                        root.visible = false
                        root.finished()
                    }
                }
                Item { Layout.fillWidth: true }
                AppButton {
                    visible: root.step > 0
                    text: I18n.t("back", "Back")
                    onClicked: root.step--
                }
                AppButton {
                    text: root.step === root.steps.length - 1
                        ? I18n.t("finish_tour", "Finish")
                        : I18n.t("next", "Next")
                    primary: true
                    onClicked: {
                        if (root.step < root.steps.length - 1)
                            root.step++
                        else {
                            root.visible = false
                            root.finished()
                        }
                    }
                }
            }
        }
    }
}
