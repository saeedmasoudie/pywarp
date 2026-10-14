import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"
import "../theme"

Item {
    id: root
    property string pendingAccountAction: ""

    function confirmAccountAction(action) {
        pendingAccountAction = action
        accountConfirm.open()
    }

    ScrollView {
        id: settingsScroll
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
            width: settingsScroll.availableWidth
            spacing: 12

            GridLayout {
                Layout.fillWidth: true
                columns: width > 680 ? 2 : 1
                columnSpacing: 12
                rowSpacing: 12

                Panel {
                    Layout.fillWidth: true
                    padding: 16
                    Text {
                        text: I18n.t("appearance", "Appearance")
                        color: Theme.text
                        font.pixelSize: 14
                        font.weight: Font.DemiBold
                    }
                    StyledComboBox {
                        Layout.fillWidth: true
                        property var values: [
                            "system", "dark", "light", "aurora"
                        ]
                        model: [
                            I18n.t("system", "System"),
                            I18n.t("dark", "Dark"),
                            I18n.t("light", "Light"),
                            I18n.t("aurora", "Aurora")
                        ]
                        currentIndex: Math.max(
                            0, values.indexOf(AppController.theme)
                        )
                        onActivated: AppController.setTheme(values[currentIndex])
                    }
                }

                Panel {
                    Layout.fillWidth: true
                    padding: 16
                    Text {
                        text: I18n.t("language", "Language")
                        color: Theme.text
                        font.pixelSize: 14
                        font.weight: Font.DemiBold
                    }
                    StyledComboBox {
                        Layout.fillWidth: true
                        property var values: ["en", "fa", "ru", "zh_CN"]
                        model: ["English", "فارسی", "Русский", "简体中文"]
                        currentIndex: Math.max(
                            0, values.indexOf(AppController.language)
                        )
                        onActivated: AppController.setLanguage(values[currentIndex])
                    }
                }
            }

            Panel {
                Layout.fillWidth: true
                padding: 16
                glowColor: AppController.managedAccount
                    ? Theme.secondary : Theme.accent

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 12

                    Rectangle {
                        Layout.preferredWidth: 42
                        Layout.preferredHeight: 42
                        Layout.alignment: Qt.AlignVCenter
                        radius: 13
                        color: AppController.managedAccount
                            ? Theme.secondarySoft : Theme.accentSoft
                        LineIcon {
                            anchors.centerIn: parent
                            width: 22
                            height: 22
                            name: "shield"
                            iconColor: AppController.managedAccount
                                ? Theme.secondary : Theme.accent
                        }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        Text {
                            text: I18n.t(
                                "warp_account", "WARP account"
                            )
                            color: Theme.text
                            font.pixelSize: 14
                            font.weight: Font.DemiBold
                        }
                        Text {
                            Layout.fillWidth: true
                            text: AppController.managedAccount
                                ? I18n.t(
                                    "team_managed",
                                    "Managed by your Zero Trust organization"
                                )
                                : AppController.registered
                                    ? I18n.t(
                                        "personal_registration",
                                        "Personal WARP registration"
                                    )
                                    : I18n.t(
                                        "no_registration",
                                        "No active registration"
                                    )
                            color: Theme.textMuted
                            font.pixelSize: 10
                            elide: Text.ElideRight
                        }
                    }
                    Rectangle {
                        visible: AppController.managedAccount
                        implicitWidth: teamBadgeRow.implicitWidth + 18
                        implicitHeight: 28
                        radius: 9
                        color: Theme.secondarySoft
                        border.color: Theme.secondary
                        Row {
                            id: teamBadgeRow
                            anchors.centerIn: parent
                            spacing: 6
                            Rectangle {
                                width: 6
                                height: 6
                                radius: 3
                                anchors.verticalCenter: parent.verticalCenter
                                color: Theme.secondary
                                SequentialAnimation on opacity {
                                    running: AppController.managedAccount
                                    loops: Animation.Infinite
                                    NumberAnimation {
                                        to: 0.3
                                        duration: 700
                                    }
                                    NumberAnimation {
                                        to: 1
                                        duration: 700
                                    }
                                }
                            }
                            Text {
                                text: I18n.t(
                                    "zero_trust", "ZERO TRUST"
                                )
                                color: Theme.secondary
                                font.pixelSize: 8
                                font.weight: Font.Bold
                                font.letterSpacing: 0.7
                            }
                        }
                    }
                    AppButton {
                        text: I18n.t("refresh", "Refresh")
                        quiet: true
                        enabled: !AppController.registrationBusy
                        onClicked: AppController.refreshRegistration()
                    }
                }

                GridLayout {
                    visible: AppController.registered
                    Layout.fillWidth: true
                    columns: width > 720 ? 4 : width > 480 ? 2 : 1
                    columnSpacing: 8
                    rowSpacing: 8
                    Repeater {
                        model: [
                            [
                                I18n.t("account_type", "Account type"),
                                AppController.accountType || "—"
                            ],
                            [
                                I18n.t("organization", "Organization"),
                                AppController.organization || "—"
                            ],
                            [
                                I18n.t("device_id", "Device ID"),
                                AppController.deviceId || "—"
                            ],
                            [
                                I18n.t("license", "License"),
                                AppController.licenseKey.length > 0
                                    ? "•••• "
                                        + AppController.licenseKey.slice(-6)
                                    : "—"
                            ]
                        ]
                        Rectangle {
                            required property var modelData
                            Layout.fillWidth: true
                            implicitHeight: 54
                            radius: 10
                            color: Theme.surfaceRaised
                            border.color: Theme.border
                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 10
                                spacing: 2
                                Text {
                                    text: modelData[0]
                                    color: Theme.textFaint
                                    font.pixelSize: 8
                                    font.weight: Font.Bold
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: modelData[1]
                                    color: Theme.text
                                    font.pixelSize: 10
                                    font.family: modelData[0]
                                        === I18n.t("device_id", "Device ID")
                                        ? "monospace"
                                        : Qt.application.font.family
                                    elide: Text.ElideMiddle
                                }
                            }
                        }
                    }
                }

                Text {
                    visible: !AppController.registered
                    Layout.fillWidth: true
                    text: I18n.t(
                        "registration_hint",
                        "Create a personal registration or enroll this device in your organization."
                    )
                    color: Theme.textMuted
                    font.pixelSize: 10
                    wrapMode: Text.WordWrap
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        Text {
                            Layout.fillWidth: true
                            text: I18n.t(
                                "team_enrollment",
                                "Zero Trust organization"
                            )
                            color: Theme.text
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                        }
                        Text {
                            Layout.fillWidth: true
                            text: I18n.t(
                                "organization_name_hint",
                                "Use the short name from your Cloudflare team URL, not a display name."
                            )
                            color: Theme.textFaint
                            font.pixelSize: 9
                            elide: Text.ElideRight
                        }
                    }
                    StyledTextField {
                        id: organizationInput
                        Layout.preferredWidth: 240
                        Layout.maximumWidth: 280
                        maximumLength: 63
                        enabled: AppController.teamEnrollmentSupported
                            && !AppController.registrationBusy
                        placeholderText: I18n.t(
                            "organization_name",
                            "Organization name"
                        )
                    }
                    AppButton {
                        text: AppController.managedAccount
                            ? I18n.t(
                                "change_team", "Change organization"
                            )
                            : I18n.t(
                                "join_team", "Enroll device"
                            )
                        primary: true
                        enabled:
                            organizationInput.text.trim().length > 0
                            && AppController.teamEnrollmentSupported
                            && !AppController.registrationBusy
                        onClicked: root.confirmAccountAction("team")
                    }
                    AppButton {
                        visible: AppController.managedAccount
                            && AppController.supportUrl.length > 0
                        Layout.alignment: Qt.AlignVCenter
                        text: I18n.t(
                            "team_support", "Organization support"
                        )
                        quiet: true
                        onClicked: AppController.openTeamSupport()
                    }
                    Text {
                        visible: AppController.managedAccount
                            && AppController.supportUrl.length === 0
                        Layout.maximumWidth: 150
                        Layout.alignment: Qt.AlignVCenter
                        text: AppController.modeSwitchAllowed
                            ? I18n.t(
                                "mode_change_allowed",
                                "Mode changes allowed"
                            )
                            : I18n.t(
                                "policy_controlled",
                                "Settings controlled by policy"
                            )
                        color: Theme.secondary
                        font.pixelSize: 9
                        font.weight: Font.DemiBold
                        elide: Text.ElideRight
                    }
                }

                RowLayout {
                    visible: AppController.registered
                        && !AppController.managedAccount
                    Layout.fillWidth: true
                    spacing: 8
                    StyledTextField {
                        id: licenseInput
                        Layout.fillWidth: true
                        echoMode: TextInput.Password
                        placeholderText: I18n.t(
                            "license_key", "WARP+ license key"
                        )
                    }
                    AppButton {
                        text: I18n.t("apply_license", "Apply license")
                        enabled: licenseInput.text.length > 0
                            && !AppController.registrationBusy
                        onClicked:
                            AppController.setRegistrationLicense(
                                licenseInput.text
                            )
                    }
                }
                Flow {
                    Layout.fillWidth: true
                    Layout.preferredHeight: childrenRect.height
                    layoutDirection: I18n.rtl
                        ? Qt.RightToLeft : Qt.LeftToRight
                    spacing: 8
                    AppButton {
                        visible: !AppController.managedAccount
                        text: I18n.t(
                            AppController.registered
                                ? "replace_registration"
                                : "new_registration",
                            AppController.registered
                                ? "Replace registration"
                                : "Create personal registration"
                        )
                        enabled: !AppController.registrationBusy
                        onClicked:
                            root.confirmAccountAction("consumer")
                    }
                    AppButton {
                        visible: AppController.registered
                        text: I18n.t(
                            "delete_registration", "Delete registration"
                        )
                        danger: true
                        enabled: !AppController.registrationBusy
                        onClicked:
                            root.confirmAccountAction("delete")
                    }
                }

                ColumnLayout {
                    visible: AppController.registrationDevices.length > 0
                        && !AppController.managedAccount
                    Layout.fillWidth: true
                    spacing: 5
                    LayoutMirroring.enabled: false
                    LayoutMirroring.childrenInherit: true
                    Text {
                        Layout.fillWidth: true
                        text: I18n.t("registered_devices", "Registered devices")
                        color: Theme.textMuted
                        font.pixelSize: 10
                        font.weight: Font.DemiBold
                        horizontalAlignment: I18n.rtl
                            ? Text.AlignRight : Text.AlignLeft
                    }
                    Repeater {
                        model: AppController.registrationDevices.slice(0, 4)
                        Rectangle {
                            required property var modelData
                            Layout.fillWidth: true
                            implicitHeight: 40
                            radius: 8
                            color: Theme.surfaceRaised
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 10
                                anchors.rightMargin: 10
                                spacing: 8
                                layoutDirection: I18n.rtl
                                    ? Qt.RightToLeft : Qt.LeftToRight
                                Text {
                                    Layout.fillWidth: true
                                    text: modelData.model + " · " + modelData.os
                                    color: Theme.text
                                    font.pixelSize: 9
                                    horizontalAlignment: I18n.rtl
                                        ? Text.AlignRight : Text.AlignLeft
                                    elide: Text.ElideRight
                                }
                                Rectangle {
                                    implicitWidth:
                                        deviceStatusText.implicitWidth + 16
                                    implicitHeight: 24
                                    radius: 8
                                    color: modelData.active
                                        ? Theme.successSoft
                                        : Theme.surfaceHover
                                    Text {
                                        id: deviceStatusText
                                        anchors.centerIn: parent
                                        text: modelData.active
                                            ? I18n.t("active", "Active")
                                            : I18n.t("inactive", "Inactive")
                                        color: modelData.active
                                            ? Theme.success : Theme.textFaint
                                        font.pixelSize: 9
                                        font.weight: Font.DemiBold
                                    }
                                }
                            }
                        }
                    }
                    Text {
                        Layout.fillWidth: true
                        visible: AppController.registrationDevices.length > 4
                        text: I18n.t(
                            "more_devices", "+ %1 more"
                        ).replace(
                            "%1",
                            AppController.registrationDevices.length - 4
                        )
                        color: Theme.textFaint
                        font.pixelSize: 9
                        horizontalAlignment: I18n.rtl
                            ? Text.AlignRight : Text.AlignLeft
                    }
                }
            }

            Panel {
                Layout.fillWidth: true
                padding: 0
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    Repeater {
                        model: [
                            [
                                I18n.t("tiny_mode", "Tiny mode"),
                                I18n.t(
                                    "tiny_mode_desc",
                                    "Keep a compact connection controller visible"
                                ),
                                "tiny"
                            ],
                            [
                                I18n.t("dns_activity", "DNS activity"),
                                I18n.t(
                                    "dns_activity_desc",
                                    "Capture DNS requests in Activity"
                                ),
                                "dns"
                            ]
                        ]
                        Item {
                            required property int index
                            required property var modelData
                            Layout.fillWidth: true
                            implicitHeight: 60
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 16
                                anchors.rightMargin: 16
                                spacing: 12
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 2
                                    Text {
                                        Layout.fillWidth: true
                                        text: modelData[0]
                                        color: Theme.text
                                        font.pixelSize: 12
                                        font.weight: Font.DemiBold
                                        horizontalAlignment: I18n.rtl
                                            ? Text.AlignRight
                                            : Text.AlignLeft
                                        elide: Text.ElideRight
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        text: modelData[1]
                                        color: Theme.textMuted
                                        font.pixelSize: 9
                                        horizontalAlignment: I18n.rtl
                                            ? Text.AlignRight
                                            : Text.AlignLeft
                                        elide: Text.ElideRight
                                    }
                                }
                                ModernSwitch {
                                    Layout.alignment: Qt.AlignVCenter
                                    checked: modelData[2] === "tiny"
                                        ? AppController.compactMode
                                        : AppController.dnsLogging
                                    onToggled: function(value) {
                                        if (modelData[2] === "tiny")
                                            AppController.setCompactMode(value)
                                        else
                                            AppController.setDnsLogging(value)
                                    }
                                }
                            }
                            Rectangle {
                                anchors.top: parent.top
                                anchors.bottom: parent.bottom
                                anchors.right: parent.right
                                anchors.topMargin: 12
                                anchors.bottomMargin: 12
                                width: 1
                                visible: index === 0
                                color: Theme.border
                            }
                        }
                    }
                }
            }

            Panel {
                Layout.fillWidth: true
                padding: 16
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 10
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        Rectangle {
                            Layout.preferredWidth: 34
                            Layout.preferredHeight: 34
                            Layout.alignment: Qt.AlignVCenter
                            radius: 10
                            color: Theme.accentSoft
                            LineIcon {
                                anchors.centerIn: parent
                                width: 18
                                height: 18
                                name: "refresh"
                                iconColor: Theme.accent
                            }
                        }
                        Text {
                            Layout.fillWidth: true
                            text: I18n.t("updates", "Updates")
                            color: Theme.text
                            font.pixelSize: 14
                            font.weight: Font.DemiBold
                        }
                        AppButton {
                            implicitHeight: 36
                            leftPadding: 14
                            rightPadding: 14
                            text: AppController.updateChecking
                                ? I18n.t("checking", "Checking…")
                                : I18n.t("check_now", "Check now")
                            enabled: !AppController.updateChecking
                            onClicked: AppController.checkForUpdates()
                        }
                    }
                    GridLayout {
                        Layout.fillWidth: true
                        columns: width > 520 ? 2 : 1
                        columnSpacing: 8
                        rowSpacing: 8
                        Repeater {
                            model: [
                                {
                                    "name": "PyWarp",
                                    "current": AppController.currentVersion,
                                    "latest":
                                        AppController.latestPywarpVersion,
                                    "available":
                                        AppController.pywarpUpdateAvailable
                                },
                                {
                                    "name": "Cloudflare WARP",
                                    "current":
                                        AppController.installedWarpVersion
                                        || "—",
                                    "latest":
                                        AppController.latestWarpVersion,
                                    "available":
                                        AppController.warpUpdateAvailable
                                }
                            ]
                            Rectangle {
                                required property var modelData
                                Layout.fillWidth: true
                                implicitHeight: 50
                                radius: 10
                                color: Theme.surfaceRaised
                                border.color: modelData.available
                                    ? Theme.accent : Theme.border
                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 12
                                    anchors.rightMargin: 12
                                    spacing: 8
                                    Text {
                                        text: modelData.name
                                        color: Theme.text
                                        font.pixelSize: 11
                                        font.weight: Font.DemiBold
                                    }
                                    Item { Layout.fillWidth: true }
                                    ColumnLayout {
                                        spacing: 1
                                        Text {
                                            Layout.alignment: Qt.AlignRight
                                            text: modelData.current
                                            color: Theme.text
                                            font.pixelSize: 12
                                            font.family: "monospace"
                                            font.weight: Font.DemiBold
                                        }
                                        Text {
                                            visible: modelData.latest.length > 0
                                            Layout.alignment: Qt.AlignRight
                                            text: I18n.t(
                                                "latest", "latest"
                                            ) + " " + modelData.latest
                                            color: modelData.available
                                                ? Theme.accent
                                                : Theme.textFaint
                                            font.pixelSize: 9
                                        }
                                    }
                                }
                            }
                        }
                    }
                    Text {
                        Layout.fillWidth: true
                        visible: AppController.updateError.length > 0
                        text: AppController.updateError
                        color: Theme.danger
                        font.pixelSize: 10
                        elide: Text.ElideRight
                    }
                    Flow {
                        visible: AppController.pywarpUpdateAvailable
                            || AppController.warpUpdateAvailable
                        Layout.fillWidth: true
                        Layout.preferredHeight: visible
                            ? childrenRect.height : 0
                        spacing: 8
                        AppButton {
                            visible: AppController.pywarpUpdateAvailable
                            text: I18n.t(
                                "view_release", "View release"
                            )
                            primary: true
                            onClicked: AppController.openPywarpUpdate()
                        }
                        AppButton {
                            visible: AppController.warpUpdateAvailable
                            text: I18n.t("open_warp", "Open WARP")
                            onClicked: AppController.openWarpApplication()
                        }
                    }
                }
            }

            Panel {
                Layout.fillWidth: true
                padding: 16
                RowLayout {
                    Layout.fillWidth: true
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3
                        Text {
                            text: qsTr("Cloudflare WARP")
                            color: Theme.text
                            font.pixelSize: 14
                            font.weight: Font.DemiBold
                        }
                        Text {
                            text: AppController.warpInstalled
                                ? I18n.t(
                                    "warp_ready",
                                    "warp-cli is installed and ready"
                                )
                                : I18n.t(
                                    "warp_missing", "warp-cli was not found"
                                )
                            color: AppController.warpInstalled
                                ? Theme.success : Theme.warning
                            font.pixelSize: 10
                        }
                    }
                    AppButton {
                        visible: !AppController.warpInstalled
                        Layout.minimumWidth: implicitWidth
                        Layout.alignment: I18n.rtl
                            ? Qt.AlignLeft : Qt.AlignRight
                        text: I18n.t("download_warp", "Install help")
                        onClicked: AppController.showIntro()
                    }
                    AppButton {
                        visible: AppController.warpInstalled
                        Layout.minimumWidth: implicitWidth
                        Layout.alignment: I18n.rtl
                            ? Qt.AlignLeft : Qt.AlignRight
                        text: I18n.t("open_warp", "Open WARP")
                        onClicked: AppController.openWarpApplication()
                    }
                }
            }

            Panel {
                Layout.fillWidth: true
                padding: 16
                RowLayout {
                    Layout.fillWidth: true
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        Text {
                            text: "PyWarp"
                            color: Theme.text
                            font.pixelSize: 14
                            font.weight: Font.DemiBold
                        }
                        Text {
                            text: I18n.t(
                                "made_by", "Made by Saeed Masoudi"
                            )
                            color: Theme.textMuted
                            font.pixelSize: 10
                        }
                    }
                    RowLayout {
                        Layout.alignment: (I18n.rtl
                            ? Qt.AlignLeft : Qt.AlignRight) | Qt.AlignVCenter
                        spacing: 8
                        AppButton {
                            Layout.minimumWidth: implicitWidth
                            text: I18n.t("github", "GitHub")
                            onClicked: AppController.openExternalUrl(
                                "https://github.com/saeedmasoudie"
                            )
                        }
                        AppButton {
                            Layout.minimumWidth: implicitWidth
                            text: I18n.t("website", "Website")
                            onClicked: AppController.openExternalUrl(
                                "https://saeedmasoudie.ir/"
                            )
                        }
                        AppButton {
                            Layout.minimumWidth: implicitWidth
                            text: I18n.t("open_guide", "Guide")
                            onClicked: AppController.showIntro()
                        }
                    }
                }
            }
        }
    }

    Popup {
        id: accountConfirm
        anchors.centerIn: Overlay.overlay
        width: Math.min(410, root.width - 40)
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
                text: root.pendingAccountAction === "delete"
                    ? I18n.t(
                        "delete_registration_title",
                        "Delete WARP registration?"
                    )
                    : root.pendingAccountAction === "team"
                        ? I18n.t(
                            "team_enrollment_confirm_title",
                            "Open Cloudflare enrollment?"
                        )
                    : I18n.t(
                        "replace_registration_title",
                        "Replace the current registration?"
                    )
                color: Theme.text
                font.pixelSize: 16
                font.weight: Font.DemiBold
                wrapMode: Text.WordWrap
            }
            Text {
                Layout.fillWidth: true
                text: root.pendingAccountAction === "delete"
                    ? I18n.t(
                        "delete_registration_body",
                        "WARP will stop working until a new registration is created."
                    )
                    : root.pendingAccountAction === "team"
                        ? I18n.t(
                            AppController.registered
                                ? "team_enrollment_replace_body"
                                : "team_enrollment_new_body",
                            AppController.registered
                                ? "Cloudflare sign-in will open in your browser for \"%1\". Your current WARP registration will be deleted before enrollment starts. If the name is wrong or you cancel, you will need to create a personal registration again."
                                : "Cloudflare sign-in will open in your browser for \"%1\". Continue only if this is the organization name provided by your administrator."
                        ).replace("%1", organizationInput.text.trim())
                    : I18n.t(
                        "replace_registration_body",
                        "PyWarp will disconnect and replace the current account on this device."
                    )
                color: Theme.textMuted
                font.pixelSize: 10
                wrapMode: Text.WordWrap
            }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                AppButton {
                    text: I18n.t("cancel", "Cancel")
                    onClicked: accountConfirm.close()
                }
                AppButton {
                    text: root.pendingAccountAction === "team"
                        ? I18n.t(
                            AppController.registered
                                ? "open_browser_replace"
                                : "open_browser",
                            AppController.registered
                                ? "Open browser & replace"
                                : "Open browser"
                        )
                        : I18n.t("continue", "Continue")
                    danger: root.pendingAccountAction === "delete"
                        || (root.pendingAccountAction === "team"
                            && AppController.registered)
                    primary: !danger
                    onClicked: {
                        accountConfirm.close()
                        if (root.pendingAccountAction === "team")
                            AppController.enrollTeam(
                                organizationInput.text
                            )
                        else if (root.pendingAccountAction === "consumer")
                            AppController.createConsumerRegistration()
                        else
                            AppController.deleteRegistration()
                    }
                }
            }
        }
    }
}
