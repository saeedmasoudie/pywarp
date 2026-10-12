import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"
import "../theme"

Rectangle {
    id: root
    color: Theme.background
    property int step: 0
    readonly property int textAlignment: I18n.rtl
        ? Text.AlignRight : Text.AlignLeft

    Rectangle {
        width: 480
        height: 480
        radius: 240
        x: parent.width - 300
        y: -290
        color: Qt.rgba(
            Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.07
        )
    }
    Rectangle {
        width: 340
        height: 340
        radius: 170
        x: -190
        y: parent.height - 190
        color: Qt.rgba(
            Theme.secondary.r, Theme.secondary.g, Theme.secondary.b, 0.055
        )
    }

    StyledComboBox {
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.margins: 26
        width: 145
        property var values: ["en", "fa", "ru", "zh_CN"]
        model: ["English", "فارسی", "Русский", "简体中文"]
        currentIndex: Math.max(
            0, values.indexOf(AppController.language)
        )
        onActivated: AppController.setLanguage(values[currentIndex])
    }

    ColumnLayout {
        anchors.centerIn: parent
        width: Math.min(parent.width - 90, 720)
        spacing: 18

        Row {
            Layout.alignment: Qt.AlignHCenter
            spacing: 7
            Repeater {
                model: 4
                Rectangle {
                    width: index === root.step ? 30 : 8
                    height: 8
                    radius: 4
                    color: index === root.step
                        ? Theme.accent : Theme.borderBright
                    Behavior on width {
                        NumberAnimation {
                            duration: Theme.animation
                            easing.type: Easing.OutCubic
                        }
                    }
                    Behavior on color {
                        ColorAnimation { duration: Theme.animation }
                    }
                }
            }
        }

        Text {
            Layout.fillWidth: true
            text: root.step === 0
                ? I18n.t("welcome_title", "Welcome to PyWarp")
                : root.step === 1
                    ? I18n.t("warp_check", "Check Cloudflare WARP")
                    : root.step === 2
                        ? I18n.t("setup_title", "Privacy, your way")
                        : I18n.t(
                            "ready_title", "Ready to take control"
                        )
            color: Theme.text
            font.pixelSize: 30
            font.weight: Font.DemiBold
            font.letterSpacing: -0.6
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
        }

        Text {
            Layout.fillWidth: true
            visible: root.step !== 1
            text: root.step === 0
                ? I18n.t(
                    "welcome_body",
                    "Modern Cloudflare WARP control for Linux, without managing the command line by hand."
                )
                : root.step === 2
                    ? I18n.t(
                        "setup_body",
                        "Choose WARP modes, secure DNS, WireGuard or MASQUE, then watch the connection live."
                    )
                    : I18n.t(
                        "ready_body",
                        "PyWarp is ready. You can revisit this guide from Settings at any time."
                    )
            color: Theme.textMuted
            font.pixelSize: 13
            lineHeight: 1.3
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 184
            visible: root.step === 1
            radius: Theme.radiusLarge
            color: Theme.surface
            border.width: 1
            border.color: AppController.warpInstalled
                ? Theme.success : Theme.warning

            RowLayout {
                anchors.fill: parent
                anchors.margins: 20
                spacing: 18

                Rectangle {
                    width: 64
                    height: 64
                    radius: 21
                    color: AppController.warpInstalled
                        ? Theme.successSoft : Theme.dangerSoft
                    LineIcon {
                        anchors.centerIn: parent
                        width: 29
                        height: 29
                        name: AppController.warpInstalled
                            ? "shield" : "advanced"
                        iconColor: AppController.warpInstalled
                            ? Theme.success : Theme.warning
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 5
                    Text {
                        Layout.fillWidth: true
                        text: AppController.warpInstalled
                            ? I18n.t("warp_ready", "WARP is installed and ready")
                            : I18n.t(
                                "warp_missing",
                                "warp-cli was not found on this system"
                            )
                        color: Theme.text
                        font.pixelSize: 16
                        font.weight: Font.DemiBold
                        horizontalAlignment: root.textAlignment
                    }
                    Text {
                        Layout.fillWidth: true
                        text: AppController.warpInstalled
                            ? I18n.t(
                                "warp_ready_hint",
                                "Cloudflare WARP CLI is installed and ready."
                            )
                            : AppController.platformName === "Linux"
                                ? I18n.t(
                                    "linux_install_hint",
                                    "Download the official Cloudflare package for your distribution, install it, then register WARP."
                                )
                                : AppController.platformName === "Darwin"
                                    ? I18n.t(
                                        "mac_install_hint",
                                        "Install the official Cloudflare WARP application, then reopen PyWarp."
                                    )
                                    : I18n.t(
                                        "generic_install_hint",
                                        "Install Cloudflare WARP from the official download page, then reopen PyWarp."
                                    )
                        color: Theme.textMuted
                        font.pixelSize: 11
                        lineHeight: 1.25
                        wrapMode: Text.WordWrap
                        horizontalAlignment: root.textAlignment
                    }
                    Text {
                        Layout.fillWidth: true
                        visible: !AppController.warpInstalled
                            && AppController.platformName === "Linux"
                        text: I18n.t(
                            "install_steps",
                            "Install package  →  warp-cli register  →  reopen PyWarp"
                        )
                        color: Theme.accentHover
                        font.pixelSize: 10
                        font.family: "monospace"
                        horizontalAlignment: root.textAlignment
                    }
                    Flow {
                        Layout.fillWidth: true
                        Layout.preferredHeight: childrenRect.height
                        visible: !AppController.warpInstalled
                        layoutDirection: I18n.rtl
                            ? Qt.RightToLeft : Qt.LeftToRight
                        spacing: 8
                        AppButton {
                            visible: AppController.platformName === "Linux"
                            text: AppController.warpInstalling
                                ? I18n.t(
                                    "installing_warp", "Installing WARP…"
                                )
                                : I18n.t(
                                    "auto_install_warp", "Automatic install"
                                )
                            primary: true
                            enabled: !AppController.warpInstalling
                            onClicked: warpInstallConfirm.open()
                        }
                        AppButton {
                            text: I18n.t(
                                "download_warp", "Official WARP download"
                            )
                            enabled: !AppController.warpInstalling
                            onClicked: AppController.openWarpDownload()
                        }
                        AppButton {
                            text: I18n.t("check_again", "Check again")
                            enabled: !AppController.warpInstalling
                            onClicked: AppController.refreshWarpInstallation()
                        }
                    }
                    Text {
                        Layout.fillWidth: true
                        visible: AppController.warpInstallMessage.length > 0
                            && !AppController.warpInstalled
                        text: AppController.warpInstallMessage
                        color: AppController.warpInstalling
                            ? Theme.warning : Theme.danger
                        font.pixelSize: 9
                        wrapMode: Text.WordWrap
                        horizontalAlignment: root.textAlignment
                    }
                }
            }
        }

        GridLayout {
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: Math.min(parent.width, 610)
            visible: root.step === 2
            columns: 3
            columnSpacing: 10

            Repeater {
                model: [
                    {
                        "title": I18n.t("warp_modes", "7 WARP modes"),
                        "detail": I18n.t(
                            "warp_modes_detail",
                            "VPN, DNS-only, proxy and tunnel controls"
                        ),
                        "color": Theme.accent
                    },
                    {
                        "title": "WireGuard + MASQUE",
                        "detail": I18n.t(
                            "smart_route_detail",
                            "Choose manually, or use Smart route when a manual connection does not work"
                        ),
                        "color": Theme.secondary
                    },
                    {
                        "title": I18n.t(
                            "live_visibility", "Live visibility"
                        ),
                        "detail": I18n.t(
                            "live_visibility_detail",
                            "Quality, traffic, DNS and application logs"
                        ),
                        "color": Theme.blue
                    }
                ]
                Rectangle {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.preferredHeight: 126
                    radius: Theme.radius
                    color: Theme.surface
                    border.color: Theme.border
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 14
                        spacing: 6
                        Rectangle {
                            width: 9
                            height: 9
                            radius: 5
                            color: modelData.color
                        }
                        Text {
                            Layout.fillWidth: true
                            text: modelData.title
                            color: Theme.text
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                            wrapMode: Text.WordWrap
                            horizontalAlignment: root.textAlignment
                        }
                        Text {
                            Layout.fillWidth: true
                            text: modelData.detail
                            color: Theme.textMuted
                            font.pixelSize: 9
                            wrapMode: Text.WordWrap
                            horizontalAlignment: root.textAlignment
                        }
                    }
                }
            }
        }

        RowLayout {
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: 8
            spacing: 10
            AppButton {
                visible: root.step > 0
                text: I18n.t("back", "Back")
                onClicked: root.step--
            }
            AppButton {
                visible: root.step === 3
                text: I18n.t("skip_tour", "Skip tour")
                onClicked: AppController.completeIntro()
            }
            AppButton {
                text: root.step === 3
                    ? I18n.t("start_tour", "Start guided tour")
                    : root.step === 1 && !AppController.warpInstalled
                        ? I18n.t(
                            "continue_anyway", "Continue without WARP"
                        )
                    : I18n.t("continue", "Continue")
                primary: true
                pill: true
                onClicked: {
                    if (root.step < 3)
                        root.step++
                    else
                        AppController.startTour()
                }
            }
        }

        Text {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignHCenter
            visible: root.step === 1 && !AppController.warpInstalled
            text: I18n.t(
                "install_continue",
                "You can continue now and install WARP later from Settings."
            )
            color: Theme.warning
            font.pixelSize: 10
            horizontalAlignment: Text.AlignHCenter
        }
    }

    Popup {
        id: warpInstallConfirm
        anchors.centerIn: Overlay.overlay
        width: Math.min(480, root.width - 40)
        modal: true
        focus: true
        padding: 18
        closePolicy: Popup.CloseOnEscape
        background: Rectangle {
            color: Theme.surface
            radius: Theme.radiusLarge
            border.color: Theme.borderBright
        }
        contentItem: ColumnLayout {
            spacing: 12
            Text {
                Layout.fillWidth: true
                text: I18n.t(
                    "auto_install_title",
                    "Install Cloudflare WARP automatically?"
                )
                color: Theme.text
                font.pixelSize: 16
                font.weight: Font.DemiBold
                wrapMode: Text.WordWrap
                horizontalAlignment: root.textAlignment
            }
            Text {
                Layout.fillWidth: true
                text: I18n.t(
                    "auto_install_body",
                    "PyWarp will add Cloudflare's official package repository, install WARP, and create a personal registration. Administrator approval is requested through PolicyKit."
                )
                color: Theme.textMuted
                font.pixelSize: 10
                lineHeight: 1.25
                wrapMode: Text.WordWrap
                horizontalAlignment: root.textAlignment
            }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                AppButton {
                    text: I18n.t("cancel", "Cancel")
                    onClicked: warpInstallConfirm.close()
                }
                AppButton {
                    text: I18n.t("install", "Install")
                    primary: true
                    onClicked: {
                        warpInstallConfirm.close()
                        AppController.installWarpLinux()
                    }
                }
            }
        }
    }
}
