import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"
import "../theme"

Item {
    id: root
    property int section: 0
    property bool showSectionTabs: true
    property string pendingMode: ""
    property string pendingProtocol: ""
    readonly property string selectedMode: pendingMode.length
        ? pendingMode : AppController.mode
    readonly property string selectedProtocol: pendingProtocol.length
        ? pendingProtocol : AppController.protocol
    property var modes: [
        ["warp", "WARP"],
        ["warp+doh", "WARP + DoH"],
        ["warp+dot", "WARP + DoT"],
        ["doh", "DoH only"],
        ["dot", "DoT only"],
        ["proxy", "Proxy"],
        ["tunnel_only", "Tunnel only"]
    ]

    Connections {
        target: AppController

        function onSettingsChanged() {
            if (root.pendingMode === AppController.mode)
                root.pendingMode = ""
            if (root.pendingProtocol === AppController.protocol)
                root.pendingProtocol = ""
        }

        function onAutoSelectionChanged() {
            if (AppController.autoSelecting) {
                root.pendingMode = ""
                root.pendingProtocol = ""
            }
        }
    }

    function highlightSection(kind, shouldPulse) {
        let target = null
        let scroller = null
        let content = null
        if (kind === "mode") {
            target = trafficModePanel
            scroller = connectionScroll
            content = connectionContent
        } else if (kind === "protocol") {
            target = tunnelEnginePanel
            scroller = connectionScroll
            content = connectionContent
        } else if (kind === "transport") {
            target = masqueTransportPanel
            scroller = connectionScroll
            content = connectionContent
        } else if (kind === "endpoint") {
            target = endpointPanel
            scroller = routingScroll
            content = routingContent
        } else if (kind === "compatibility") {
            target = compatibilityPanel
            scroller = routingScroll
            content = routingContent
        } else if (kind === "smart") {
            target = smartRoutePanel
            scroller = smartScroll
            content = smartContent
        }
        if (!target)
            return
        Qt.callLater(function() {
            const position = target.mapToItem(content, 0, 0)
            const flickable = scroller.contentItem
            flickable.contentY = Math.max(
                0,
                Math.min(
                    position.y - 12,
                    flickable.contentHeight - flickable.height
                )
            )
            if (shouldPulse)
                target.pulseAttention()
        })
    }

    function tourTargetRect(kind, destination) {
        let target = null
        if (kind === "mode")
            target = trafficModePanel
        else if (kind === "protocol")
            target = tunnelEnginePanel
        else if (kind === "transport")
            target = masqueTransportPanel
        else if (kind === "endpoint")
            target = endpointPanel
        else if (kind === "compatibility")
            target = compatibilityPanel
        else if (kind === "smart")
            target = smartRoutePanel
        if (!target || !target.visible)
            return Qt.rect(0, 0, 0, 0)
        const position = target.mapToItem(destination, 0, 0)
        return Qt.rect(
            position.x, position.y, target.width, target.height
        )
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 12

        Rectangle {
            visible: root.showSectionTabs
            Layout.alignment: Qt.AlignHCenter
            implicitWidth: sectionTabs.implicitWidth + 8
            Layout.preferredHeight: visible ? 46 : 0
            radius: 14
            color: Theme.surface
            border.color: Theme.border
            RowLayout {
                id: sectionTabs
                anchors.centerIn: parent
                spacing: 2
                NavTab {
                    text: I18n.t("connection", "Connection")
                    active: root.section === 0
                    onClicked: root.section = 0
                }
                NavTab {
                    text: I18n.t("routing", "Routing")
                    active: root.section === 1
                    onClicked: root.section = 1
                }
                NavTab {
                    text: I18n.t("smart_test", "Smart test")
                    active: root.section === 2
                    onClicked: root.section = 2
                }
            }
        }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: root.section

            ScrollView {
                id: connectionScroll
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
                    id: connectionContent
                    width: connectionScroll.availableWidth
                    spacing: 12

                    Panel {
                        id: trafficModePanel
                        Layout.fillWidth: true
                        padding: 16
                        Text {
                            text: I18n.t("traffic_mode", "Traffic mode")
                            color: Theme.text
                            font.pixelSize: 14
                            font.weight: Font.DemiBold
                        }
                        Text {
                            text: I18n.t(
                                "choose_protection",
                                "Choose what Cloudflare WARP should protect."
                            )
                            color: Theme.textMuted
                            font.pixelSize: 10
                        }
                        Flow {
                            Layout.fillWidth: true
                            Layout.preferredHeight: childrenRect.height
                            spacing: 7
                            Repeater {
                                model: root.modes
                                Rectangle {
                                    required property var modelData
                                    width: modeText.implicitWidth + 24
                                    height: 36
                                    radius: 11
                                    color: root.selectedMode === modelData[0]
                                        ? Theme.accentSoft
                                        : modeMouse.containsMouse
                                            ? Theme.surfaceHover
                                            : Theme.surfaceRaised
                                    border.width: 1
                                    border.color: root.selectedMode === modelData[0]
                                        ? Theme.accent : Theme.border
                                    Text {
                                        id: modeText
                                        anchors.centerIn: parent
                                        text: modelData[1]
                                        color: root.selectedMode === modelData[0]
                                            ? Theme.accent : Theme.textMuted
                                        font.pixelSize: 11
                                        font.weight: Font.DemiBold
                                    }
                                    MouseArea {
                                        id: modeMouse
                                        anchors.fill: parent
                                        enabled: !AppController.managedAccount
                                            || AppController.modeSwitchAllowed
                                        hoverEnabled: true
                                        cursorShape: enabled
                                            ? Qt.PointingHandCursor
                                            : Qt.ArrowCursor
                                        onClicked:
                                            root.pendingMode = modelData[0]
                                                === AppController.mode
                                                ? "" : modelData[0]
                                    }
                                }
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8
                            StyledTextField {
                                id: proxyPort
                                visible: root.selectedMode === "proxy"
                                Layout.preferredWidth: 150
                                text: AppController.proxyPort
                                placeholderText: I18n.t(
                                    "proxy_port", "Proxy port"
                                )
                                validator: IntValidator { bottom: 1; top: 65535 }
                            }
                            Item { Layout.fillWidth: true }
                            Rectangle {
                                visible: root.selectedMode === AppController.mode
                                implicitWidth: currentModeText.implicitWidth + 18
                                implicitHeight: 30
                                radius: 9
                                color: Theme.surfaceRaised
                                border.color: Theme.border
                                Text {
                                    id: currentModeText
                                    anchors.centerIn: parent
                                    text: I18n.t(
                                        "current_mode", "Current mode"
                                    )
                                    color: Theme.textFaint
                                    font.pixelSize: 10
                                }
                            }
                            AppButton {
                                Layout.minimumWidth: implicitWidth
                                text: I18n.t("apply_mode", "Apply mode")
                                primary: root.selectedMode !== AppController.mode
                                enabled: root.selectedMode !== AppController.mode
                                    && !AppController.busy
                                    && (!AppController.managedAccount
                                        || AppController.modeSwitchAllowed)
                                onClicked: AppController.setMode(
                                    root.selectedMode, proxyPort.text
                                )
                            }
                        }
                    }

                    GridLayout {
                        Layout.fillWidth: true
                        columns: width > 700 ? 2 : 1
                        columnSpacing: 12
                        rowSpacing: 12

                        Panel {
                            id: tunnelEnginePanel
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            padding: 16
                            Text {
                                text: I18n.t(
                                    "tunnel_engine", "Tunnel engine"
                                )
                                color: Theme.text
                                font.pixelSize: 14
                                font.weight: Font.DemiBold
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                Repeater {
                                    model: [
                                        [
                                            "WireGuard",
                                            I18n.t("fast_udp", "Fast UDP tunnel")
                                        ],
                                        [
                                            "MASQUE",
                                            I18n.t(
                                                "adaptive_http",
                                                "Adaptive HTTP tunnel"
                                            )
                                        ]
                                    ]
                                    Rectangle {
                                        required property var modelData
                                        Layout.fillWidth: true
                                        implicitHeight: 52
                                        opacity: AppController.managedAccount
                                            ? 0.62 : 1
                                        radius: 10
                                        color: root.selectedProtocol === modelData[0]
                                            ? Theme.secondarySoft
                                            : Theme.surfaceRaised
                                        border.color: root.selectedProtocol === modelData[0]
                                            ? Theme.secondary : Theme.border
                                        RowLayout {
                                            anchors.fill: parent
                                            anchors.leftMargin: 16
                                            anchors.rightMargin: 16
                                            spacing: 12
                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                spacing: 1
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
                                                    color: Theme.textFaint
                                                    font.pixelSize: 9
                                                    horizontalAlignment: I18n.rtl
                                                        ? Text.AlignRight
                                                        : Text.AlignLeft
                                                    elide: Text.ElideRight
                                                }
                                            }
                                            Rectangle {
                                                Layout.preferredWidth: 16
                                                Layout.minimumWidth: 16
                                                Layout.maximumWidth: 16
                                                Layout.preferredHeight: 16
                                                Layout.minimumHeight: 16
                                                Layout.maximumHeight: 16
                                                Layout.alignment: Qt.AlignVCenter
                                                radius: 8
                                                color: "transparent"
                                                border.width: 2
                                                border.color: root.selectedProtocol
                                                    === modelData[0]
                                                    ? Theme.secondary
                                                    : Theme.borderBright
                                                Rectangle {
                                                    anchors.centerIn: parent
                                                    width: 8
                                                    height: 8
                                                    radius: 4
                                                    visible: root.selectedProtocol
                                                        === modelData[0]
                                                    color: Theme.secondary
                                                }
                                            }
                                        }
                                        MouseArea {
                                            anchors.fill: parent
                                            enabled: !AppController.managedAccount
                                            cursorShape: enabled
                                                ? Qt.PointingHandCursor
                                                : Qt.ArrowCursor
                                            onClicked:
                                                root.pendingProtocol =
                                                    modelData[0]
                                                    === AppController.protocol
                                                    ? "" : modelData[0]
                                        }
                                    }
                                }
                            }
                            AppButton {
                                Layout.alignment: I18n.rtl
                                    ? Qt.AlignLeft : Qt.AlignRight
                                Layout.minimumWidth: implicitWidth
                                text: I18n.t(
                                    "apply_protocol", "Apply protocol"
                                )
                                enabled: root.selectedProtocol
                                    !== AppController.protocol
                                    && !AppController.managedAccount
                                primary: enabled
                                onClicked: AppController.setProtocol(
                                    root.selectedProtocol
                                )
                            }
                        }

                        Panel {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            padding: 16
                            Text {
                                text: I18n.t("dns", "DNS")
                                color: Theme.text
                                font.pixelSize: 14
                                font.weight: Font.DemiBold
                            }
                            StyledComboBox {
                                id: dnsCombo
                                Layout.fillWidth: true
                                property var values: ["off", "malware", "full"]
                                model: [
                                    I18n.t("no_filtering", "No filtering"),
                                    I18n.t("block_malware", "Block malware"),
                                    I18n.t(
                                        "malware_adult",
                                        "Malware + adult content"
                                    )
                                ]
                                currentIndex: Math.max(
                                    0, values.indexOf(AppController.dnsFamily)
                                )
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 1
                                    Text {
                                        Layout.fillWidth: true
                                        text: I18n.t(
                                            "live_dns", "Live DNS activity"
                                        )
                                        color: Theme.text
                                        font.pixelSize: 11
                                        horizontalAlignment: I18n.rtl
                                            ? Text.AlignRight
                                            : Text.AlignLeft
                                        elide: Text.ElideRight
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        text: I18n.t(
                                            "dns_activity_hint",
                                            "Show queries in Activity"
                                        )
                                        color: Theme.textFaint
                                        font.pixelSize: 9
                                        horizontalAlignment: I18n.rtl
                                            ? Text.AlignRight
                                            : Text.AlignLeft
                                        elide: Text.ElideRight
                                    }
                                }
                                ModernSwitch {
                                    Layout.alignment: Qt.AlignVCenter
                                    checked: AppController.dnsLogging
                                    onToggled: function(value) {
                                        AppController.setDnsLogging(value)
                                    }
                                }
                            }
                            AppButton {
                                Layout.alignment: I18n.rtl
                                    ? Qt.AlignLeft : Qt.AlignRight
                                text: I18n.t("apply", "Apply")
                                onClicked: AppController.setDnsFamily(
                                    dnsCombo.values[dnsCombo.currentIndex]
                                )
                            }
                        }
                    }

                    Panel {
                        id: masqueTransportPanel
                        Layout.fillWidth: true
                        visible: root.selectedProtocol === "MASQUE"
                            || AppController.protocol === "MASQUE"
                        padding: 14
                        RowLayout {
                            Layout.fillWidth: true
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 1
                                Text {
                                    text: I18n.t(
                                        "masque_transport", "MASQUE transport"
                                    )
                                    color: Theme.text
                                    font.pixelSize: 12
                                    font.weight: Font.DemiBold
                                }
                                Text {
                                    text: I18n.t(
                                        "automatic_fallback",
                                        "Automatic fallback is recommended"
                                    )
                                    color: Theme.textFaint
                                    font.pixelSize: 9
                                }
                            }
                            StyledComboBox {
                                id: masqueCombo
                                Layout.preferredWidth: 250
                                enabled: !AppController.managedAccount
                                property var values: [
                                    "auto", "h3-only",
                                    "h3-with-h2-fallback", "h2-only"
                                ]
                                model: [
                                    I18n.t("automatic", "Automatic"),
                                    I18n.t("http3_only", "HTTP/3 only"),
                                    I18n.t(
                                        "http3_http2_fallback",
                                        "HTTP/3 → HTTP/2 fallback"
                                    ),
                                    I18n.t("http2_only", "HTTP/2 only")
                                ]
                                currentIndex: Math.max(
                                    0,
                                    values.indexOf(AppController.masqueOption)
                                )
                            }
                            AppButton {
                                text: I18n.t("apply", "Apply")
                                enabled: !AppController.managedAccount
                                onClicked: AppController.setMasqueOption(
                                    masqueCombo.values[
                                        masqueCombo.currentIndex
                                    ]
                                )
                            }
                        }
                    }
                }
            }

            ScrollView {
                id: routingScroll
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
                    id: routingContent
                    width: routingScroll.availableWidth
                    spacing: 12

                    Panel {
                        id: endpointPanel
                        Layout.fillWidth: true
                        padding: 16
                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                Layout.fillWidth: true
                                text: I18n.t(
                                    "tunnel_endpoint", "Tunnel endpoint"
                                )
                                color: Theme.text
                                font.pixelSize: 14
                                font.weight: Font.DemiBold
                            }
                            Rectangle {
                                implicitWidth: endpointState.implicitWidth + 18
                                implicitHeight: 27
                                radius: 9
                                color: Theme.surfaceRaised
                                border.color: Theme.border
                                Text {
                                    id: endpointState
                                    anchors.centerIn: parent
                                    text: AppController.customEndpoint
                                        || I18n.t(
                                            "cloudflare_automatic",
                                            "Cloudflare automatic"
                                        )
                                    color: AppController.customEndpoint
                                        ? Theme.accentHover : Theme.textMuted
                                    font.pixelSize: 9
                                    font.family: "monospace"
                                }
                            }
                        }
                        Text {
                            Layout.fillWidth: true
                            text: I18n.t(
                                "endpoint_hint",
                                "Set an IP and port, or let Cloudflare select the route."
                            )
                            color: Theme.textMuted
                            font.pixelSize: 10
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 7
                            StyledTextField {
                                id: endpointInput
                                Layout.fillWidth: true
                                text: AppController.customEndpoint
                                placeholderText: "162.159.192.1:2408"
                                onAccepted: AppController.setCustomEndpoint(text)
                            }
                            AppButton {
                                text: I18n.t("save", "Save")
                                primary: true
                                onClicked: AppController.setCustomEndpoint(
                                    endpointInput.text
                                )
                            }
                            AppButton {
                                text: I18n.t("automatic", "Automatic")
                                onClicked: AppController.resetCustomEndpoint()
                            }
                        }
                        Flow {
                            Layout.fillWidth: true
                            Layout.preferredHeight:
                                AppController.endpointHistory.length ? 29 : 0
                            spacing: 6
                            Repeater {
                                model: AppController.endpointHistory
                                Rectangle {
                                    required property string modelData
                                    width: endpointHistoryText.implicitWidth + 18
                                    height: 27
                                    radius: 9
                                    color: Theme.surfaceRaised
                                    border.color: Theme.border
                                    Text {
                                        id: endpointHistoryText
                                        anchors.centerIn: parent
                                        text: modelData
                                        color: Theme.textMuted
                                        font.pixelSize: 9
                                        font.family: "monospace"
                                    }
                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: endpointInput.text = modelData
                                    }
                                }
                            }
                        }
                    }

                    Panel {
                        id: compatibilityPanel
                        visible: AppController.relaxedTimeoutsSupported
                            || AppController.pmtudSupported
                            || AppController.dohMssClampSupported
                        Layout.fillWidth: true
                        padding: 16
                        glowColor: AppController.relaxedTimeoutsEnabled
                            ? Theme.warning : "transparent"

                        Text {
                            text: I18n.t(
                                "compatibility_tools",
                                "Difficult network compatibility"
                            )
                            color: Theme.text
                            font.pixelSize: 14
                            font.weight: Font.DemiBold
                        }
                        Text {
                            Layout.fillWidth: true
                            text: I18n.t(
                                "compatibility_hint",
                                "Targeted fixes for high latency, packet loss, MTU black holes, and fragmented DNS handshakes."
                            )
                            color: Theme.textMuted
                            font.pixelSize: 10
                            wrapMode: Text.WordWrap
                        }

                        Rectangle {
                            visible: AppController.relaxedTimeoutsSupported
                            Layout.fillWidth: true
                            implicitHeight: 66
                            radius: 10
                            color: Theme.surfaceRaised
                            border.color:
                                AppController.relaxedTimeoutsEnabled
                                ? Theme.warning : Theme.border
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 12
                                anchors.rightMargin: 12
                                spacing: 10
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 2
                                    Text {
                                        text: I18n.t(
                                            "relaxed_timeouts",
                                            "Relaxed connection timeouts"
                                        )
                                        color: Theme.text
                                        font.pixelSize: 12
                                        font.weight: Font.DemiBold
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        text: I18n.t(
                                            "relaxed_timeouts_hint",
                                            "Useful on high-latency or high-loss networks where normal handshakes time out."
                                        )
                                        color: Theme.textMuted
                                        font.pixelSize: 9
                                        elide: Text.ElideRight
                                    }
                                }
                                ModernSwitch {
                                    checked:
                                        AppController.relaxedTimeoutsEnabled
                                    onToggled: function(value) {
                                        AppController.setRelaxedTimeouts(value)
                                    }
                                }
                                AppButton {
                                    implicitHeight: 36
                                    leftPadding: 12
                                    rightPadding: 12
                                    text: I18n.t("reset", "Reset")
                                    quiet: true
                                    onClicked:
                                        AppController.resetRelaxedTimeouts()
                                }
                            }
                        }

                        Rectangle {
                            visible: AppController.pmtudSupported
                            Layout.fillWidth: true
                            implicitHeight: 66
                            radius: 10
                            color: Theme.surfaceRaised
                            border.color: AppController.pmtudEnabled
                                ? Theme.secondary : Theme.border
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 12
                                anchors.rightMargin: 12
                                spacing: 10
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 2
                                    Text {
                                        text: I18n.t(
                                            "masque_pmtud",
                                            "MASQUE path MTU discovery"
                                        )
                                        color: Theme.text
                                        font.pixelSize: 12
                                        font.weight: Font.DemiBold
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        text: I18n.t(
                                            "masque_pmtud_hint",
                                            "Helps when large packets stall on restrictive or unusual network paths."
                                        )
                                        color: Theme.textMuted
                                        font.pixelSize: 9
                                        elide: Text.ElideRight
                                    }
                                }
                                ModernSwitch {
                                    checked: AppController.pmtudEnabled
                                    onToggled: function(value) {
                                        AppController.setPmtud(value)
                                    }
                                }
                                AppButton {
                                    implicitHeight: 36
                                    leftPadding: 12
                                    rightPadding: 12
                                    text: I18n.t("reset", "Reset")
                                    quiet: true
                                    onClicked: AppController.resetPmtud()
                                }
                            }
                        }

                        Rectangle {
                            visible: AppController.dohMssClampSupported
                            Layout.fillWidth: true
                            implicitHeight: 66
                            radius: 10
                            color: Theme.surfaceRaised
                            border.color: AppController.dohMssClampEnabled
                                ? Theme.secondary : Theme.border
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 12
                                anchors.rightMargin: 12
                                spacing: 10
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 2
                                    Text {
                                        text: I18n.t(
                                            "doh_mss_clamp",
                                            "DoH handshake MSS clamp"
                                        )
                                        color: Theme.text
                                        font.pixelSize: 12
                                        font.weight: Font.DemiBold
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        text: I18n.t(
                                            "doh_mss_clamp_hint",
                                            "Helps WARP + DoH when TCP handshake packets are fragmented or dropped."
                                        )
                                        color: Theme.textMuted
                                        font.pixelSize: 9
                                        elide: Text.ElideRight
                                    }
                                }
                                ModernSwitch {
                                    checked: AppController.dohMssClampEnabled
                                    onToggled: function(value) {
                                        AppController.setDohMssClamp(value)
                                    }
                                }
                                AppButton {
                                    implicitHeight: 36
                                    leftPadding: 12
                                    rightPadding: 12
                                    text: I18n.t("reset", "Reset")
                                    quiet: true
                                    onClicked:
                                        AppController.resetDohMssClamp()
                                }
                            }
                        }
                    }

                    Panel {
                        visible: AppController.netbtSupported
                        Layout.fillWidth: true
                        padding: 16
                        glowColor: AppController.netbtEnabled
                            ? Theme.warning : "transparent"

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12
                            Rectangle {
                                Layout.preferredWidth: 38
                                Layout.preferredHeight: 38
                                Layout.alignment: Qt.AlignVCenter
                                radius: 12
                                color: AppController.netbtEnabled
                                    ? Theme.dangerSoft
                                    : Theme.surfaceRaised
                                LineIcon {
                                    anchors.centerIn: parent
                                    width: 20
                                    height: 20
                                    name: "network"
                                    iconColor: AppController.netbtEnabled
                                        ? Theme.warning : Theme.textMuted
                                }
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2
                                Text {
                                    text: I18n.t(
                                        "netbt_title",
                                        "NetBIOS over TCP/IP"
                                    )
                                    color: Theme.text
                                    font.pixelSize: 12
                                    font.weight: Font.DemiBold
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: I18n.t(
                                        "netbt_hint",
                                        "Windows only. Enable this legacy protocol only for old file shares, printers, or single-label internal names."
                                    )
                                    color: Theme.textMuted
                                    font.pixelSize: 9
                                    elide: Text.ElideRight
                                }
                            }
                            Rectangle {
                                visible: root.width > 680
                                Layout.preferredWidth:
                                    netbtRecommendation.implicitWidth + 18
                                Layout.preferredHeight: 36
                                Layout.alignment: Qt.AlignVCenter
                                radius: 9
                                color: Theme.successSoft
                                Text {
                                    id: netbtRecommendation
                                    anchors.centerIn: parent
                                    text: I18n.t(
                                        "recommended_off",
                                        "Recommended: off"
                                    )
                                    color: Theme.success
                                    font.pixelSize: 9
                                    font.weight: Font.DemiBold
                                }
                            }
                            ModernSwitch {
                                Layout.alignment: Qt.AlignVCenter
                                checked: AppController.netbtEnabled
                                onToggled: function(value) {
                                    AppController.setNetbt(value)
                                }
                            }
                            AppButton {
                                Layout.alignment: Qt.AlignVCenter
                                text: I18n.t(
                                    "reset_policy", "Policy default"
                                )
                                quiet: true
                                onClicked: AppController.resetNetbt()
                            }
                        }
                    }

                    GridLayout {
                        Layout.fillWidth: true
                        columns: width > 740 ? 3 : 1
                        columnSpacing: 12
                        rowSpacing: 12

                        Panel {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 360
                            Layout.columnSpan: root.width > 740 ? 2 : 1
                            padding: 16
                            RowLayout {
                                Layout.fillWidth: true
                                Text {
                                    Layout.fillWidth: true
                                    text: I18n.t(
                                        "bypass_rules", "Bypass rules"
                                    )
                                    color: Theme.text
                                    font.pixelSize: 14
                                    font.weight: Font.DemiBold
                                }
                                Text {
                                    text: I18n.activeCount(bypassList.count)
                                    color: Theme.accent
                                    font.pixelSize: 10
                                }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                StyledComboBox {
                                    id: bypassType
                                    Layout.preferredWidth: 115
                                    model: [
                                        "IP / CIDR",
                                        I18n.t("domain", "Domain")
                                    ]
                                }
                                StyledTextField {
                                    id: bypassInput
                                    Layout.fillWidth: true
                                    placeholderText: bypassType.currentIndex === 0
                                        ? "192.168.1.0/24" : "example.com"
                                    onAccepted: addRule.clicked()
                                }
                                AppButton {
                                    id: addRule
                                    text: I18n.t("add", "Add")
                                    primary: true
                                    onClicked: {
                                        AppController.addExclusion(
                                            bypassType.currentIndex === 0
                                                ? "ip" : "host",
                                            bypassInput.text
                                        )
                                        bypassInput.clear()
                                    }
                                }
                            }
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                radius: 10
                                color: Theme.surfaceRaised
                                border.color: Theme.border
                                clip: true
                                ListView {
                                    id: bypassList
                                    anchors.fill: parent
                                    anchors.margins: 5
                                    model: AppController.exclusionModel
                                    spacing: 3
                                    clip: true
                                    ScrollBar.vertical: StyledScrollBar {}
                                    delegate: Rectangle {
                                        required property int index
                                        required property string type
                                        required property string value
                                        width: ListView.view.width
                                        height: 42
                                        radius: 8
                                        color: index % 2
                                            ? "transparent"
                                            : Theme.surface
                                        RowLayout {
                                            anchors.fill: parent
                                            anchors.leftMargin: 10
                                            anchors.rightMargin: 10
                                            Text {
                                                Layout.preferredWidth: 36
                                                text: type.toUpperCase()
                                                color: type === "ip"
                                                    ? Theme.secondary
                                                    : Theme.accent
                                                font.pixelSize: 9
                                                font.weight: Font.Bold
                                            }
                                            Text {
                                                Layout.fillWidth: true
                                                text: value
                                                color: Theme.text
                                                font.pixelSize: 11
                                                font.family: "monospace"
                                                elide: Text.ElideMiddle
                                            }
                                            AppButton {
                                                text: I18n.t(
                                                    "remove", "Remove"
                                                )
                                                quiet: true
                                                onClicked:
                                                    AppController.removeExclusion(
                                                        type, value
                                                    )
                                            }
                                        }
                                    }
                                    Text {
                                        anchors.centerIn: parent
                                        visible: bypassList.count === 0
                                        text: I18n.t(
                                            "no_bypass_rules",
                                            "No bypass rules"
                                        )
                                        color: Theme.textFaint
                                        font.pixelSize: 10
                                    }
                                }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                Item { Layout.fillWidth: true }
                                AppButton {
                                    text: I18n.t("reset_all", "Reset all")
                                    danger: true
                                    onClicked: AppController.resetExclusions()
                                }
                            }
                        }

                        Panel {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 360
                            padding: 16
                            Text {
                                text: I18n.t(
                                    "recent_changes", "Recent changes"
                                )
                                color: Theme.text
                                font.pixelSize: 14
                                font.weight: Font.DemiBold
                            }
                            ListView {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                model: AppController.advancedHistoryModel
                                spacing: 4
                                clip: true
                                delegate: Rectangle {
                                    required property string time
                                    required property string action
                                    required property string value
                                    width: ListView.view.width
                                    height: 50
                                    radius: 8
                                    color: Theme.surfaceRaised
                                    ColumnLayout {
                                        anchors.fill: parent
                                        anchors.margins: 8
                                        spacing: 2
                                        RowLayout {
                                            Layout.fillWidth: true
                                            Text {
                                                Layout.fillWidth: true
                                                text: action
                                                color: Theme.text
                                                font.pixelSize: 10
                                                font.weight: Font.DemiBold
                                            }
                                            Text {
                                                text: time
                                                color: Theme.textFaint
                                                font.pixelSize: 8
                                            }
                                        }
                                        Text {
                                            Layout.fillWidth: true
                                            text: value
                                            color: Theme.textMuted
                                            font.pixelSize: 9
                                            font.family: "monospace"
                                            elide: Text.ElideMiddle
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            ScrollView {
                id: smartScroll
                contentWidth: availableWidth
                clip: true
                background: null
                LayoutMirroring.enabled: false
                LayoutMirroring.childrenInherit: true
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
                    id: smartContent
                    width: smartScroll.availableWidth
                    spacing: 12

                    Panel {
                        id: smartRoutePanel
                        Layout.fillWidth: true
                        padding: 22
                        glowColor: AppController.managedAccount
                            ? Theme.secondary : Theme.accent

                        RowLayout {
                            Layout.fillWidth: true
                            layoutDirection: I18n.rtl
                                ? Qt.RightToLeft : Qt.LeftToRight
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 4
                                Text {
                                    Layout.fillWidth: true
                                    text: I18n.t(
                                        "smart_lab",
                                        "Smart connection test"
                                    )
                                    color: Theme.text
                                    font.pixelSize: 18
                                    font.weight: Font.DemiBold
                                    horizontalAlignment: I18n.rtl
                                        ? Text.AlignRight : Text.AlignLeft
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: AppController.managedAccount
                                        ? I18n.t(
                                            "smart_managed_hint",
                                            "Your organization controls tunnel settings. Smart route will not override its policy."
                                        )
                                        : I18n.t(
                                            "smart_desc",
                                            "Tests 8 WARP and WARP + DoH profiles, then keeps the first route with a verified tunnel and internet access."
                                        )
                                    color: Theme.textMuted
                                    font.pixelSize: 11
                                    wrapMode: Text.WordWrap
                                    horizontalAlignment: I18n.rtl
                                        ? Text.AlignRight : Text.AlignLeft
                                }
                            }
                            ColumnLayout {
                                Layout.preferredWidth:
                                    AppController.autoSelecting ? 120 : 310
                                spacing: 6
                                Flow {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight:
                                        childrenRect.height
                                    layoutDirection: I18n.rtl
                                        ? Qt.RightToLeft : Qt.LeftToRight
                                    spacing: 8
                                    AppButton {
                                        visible:
                                            AppController.autoSelecting
                                        text: I18n.t(
                                            "stop_test", "Stop"
                                        )
                                        danger: true
                                        onClicked:
                                            AppController
                                                .cancelAutoSelection()
                                    }
                                    AppButton {
                                        visible:
                                            !AppController.autoSelecting
                                        text: I18n.t(
                                            "quick_test", "Quick test"
                                        )
                                        primary: true
                                        enabled:
                                            !AppController.managedAccount
                                        onClicked:
                                            AppController
                                                .startQuickSelection()
                                    }
                                    AppButton {
                                        visible:
                                            !AppController.autoSelecting
                                        text: I18n.t(
                                            "full_test",
                                            "Full comparison"
                                        )
                                        enabled:
                                            !AppController.managedAccount
                                        onClicked:
                                            AppController
                                                .startFullSelection()
                                    }
                                }
                                Text {
                                    visible:
                                        !AppController.autoSelecting
                                    Layout.fillWidth: true
                                    text: I18n.t(
                                        "smart_modes_hint",
                                        "Quick stops at the first working route. Full measures and saves every route."
                                    )
                                    color: Theme.textFaint
                                    font.pixelSize: 9
                                    wrapMode: Text.WordWrap
                                    horizontalAlignment: I18n.rtl
                                        ? Text.AlignRight : Text.AlignLeft
                                }
                            }
                        }

                        GridLayout {
                            Layout.fillWidth: true
                            columns: 3
                            columnSpacing: 8
                            layoutDirection: I18n.rtl
                                ? Qt.RightToLeft : Qt.LeftToRight
                            Repeater {
                                model: [
                                    [
                                        I18n.t("profiles", "Profiles"),
                                        AppController.autoTestTotal
                                    ],
                                    [
                                        I18n.t("engines", "Engines"),
                                        "MASQUE + WireGuard"
                                    ],
                                    [
                                        I18n.t("validation", "Validation"),
                                        I18n.t(
                                            "handshake_internet",
                                            "Handshake + internet"
                                        )
                                    ]
                                ]
                                Rectangle {
                                    required property var modelData
                                    Layout.fillWidth: true
                                    implicitHeight: 64
                                    radius: 10
                                    color: Theme.surfaceRaised
                                    border.color: Theme.border
                                    Column {
                                        anchors.centerIn: parent
                                        spacing: 3
                                        Text {
                                            anchors.horizontalCenter: parent.horizontalCenter
                                            text: modelData[0]
                                            color: Theme.textFaint
                                            font.pixelSize: 9
                                        }
                                        Text {
                                            anchors.horizontalCenter: parent.horizontalCenter
                                            text: modelData[1]
                                            color: Theme.text
                                            font.pixelSize: 12
                                            font.weight: Font.DemiBold
                                        }
                                    }
                                }
                            }
                        }
                    }

                    Panel {
                        Layout.fillWidth: true
                        padding: 20
                        RowLayout {
                            Layout.fillWidth: true
                            layoutDirection: I18n.rtl
                                ? Qt.RightToLeft : Qt.LeftToRight
                            SmartScan {
                                Layout.preferredWidth: 110
                                Layout.preferredHeight: 110
                                running: AppController.autoSelecting
                                progress: AppController.autoProgress
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 5
                                RowLayout {
                                    Layout.fillWidth: true
                                    layoutDirection: I18n.rtl
                                        ? Qt.RightToLeft : Qt.LeftToRight
                                    Text {
                                        Layout.fillWidth: true
                                        text: AppController.autoSelecting
                                            ? I18n.t("current_probe", "Current profile")
                                                + " "
                                                + AppController.autoTestIndex
                                                + "/"
                                                + AppController.autoTestTotal
                                            : I18n.t(
                                                "ready_to_test",
                                                "Ready to test this network"
                                            )
                                        color: Theme.text
                                        font.pixelSize: 12
                                        font.weight: Font.DemiBold
                                        horizontalAlignment: I18n.rtl
                                            ? Text.AlignRight : Text.AlignLeft
                                    }
                                    Text {
                                        text: AppController.autoProgress + "%"
                                        color: Theme.accent
                                        font.pixelSize: 12
                                    }
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: I18n.directionalText(
                                        I18n.autoProfile(
                                            AppController.autoProfile
                                        )
                                            || I18n.t(
                                                "no_test_running",
                                                "No test running"
                                            )
                                    )
                                    color: Theme.textMuted
                                    font.pixelSize: 11
                                    font.family: "monospace"
                                    horizontalAlignment: I18n.rtl
                                        ? Text.AlignRight : Text.AlignLeft
                                }
                                TechProgress {
                                    Layout.fillWidth: true
                                    value: AppController.autoProgress
                                    running: AppController.autoSelecting
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: I18n.directionalText(
                                        I18n.autoMessage(
                                            AppController.autoMessage
                                        )
                                    )
                                    color: Theme.textFaint
                                    font.pixelSize: 10
                                    horizontalAlignment: I18n.rtl
                                        ? Text.AlignRight : Text.AlignLeft
                                }
                            }
                        }
                    }

                    Panel {
                        visible: AppController.smartResultCount > 0
                        Layout.fillWidth: true
                        padding: 16

                        RowLayout {
                            Layout.fillWidth: true
                            layoutDirection: I18n.rtl
                                ? Qt.RightToLeft : Qt.LeftToRight
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2
                                Text {
                                    Layout.fillWidth: true
                                    text: I18n.t(
                                        "full_results",
                                        "Full comparison results"
                                    )
                                    color: Theme.text
                                    font.pixelSize: 14
                                    font.weight: Font.DemiBold
                                    horizontalAlignment: I18n.rtl
                                        ? Text.AlignRight : Text.AlignLeft
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: I18n.t(
                                        "results_hint",
                                        "Working profiles are sorted by lower packet loss, then lower latency."
                                    )
                                    color: Theme.textMuted
                                    font.pixelSize: 9
                                    horizontalAlignment: I18n.rtl
                                        ? Text.AlignRight : Text.AlignLeft
                                    elide: Text.ElideRight
                                }
                            }
                            Text {
                                text: AppController.smartResultCount
                                color: Theme.accent
                                font.pixelSize: 12
                                font.weight: Font.DemiBold
                            }
                        }

                        Repeater {
                            model: AppController.smartResultModel
                            Rectangle {
                                required property int index
                                required property string profile
                                required property string latency
                                required property string loss
                                required property bool working
                                required property bool recommended

                                Layout.fillWidth: true
                                implicitHeight: 58
                                radius: 10
                                color: Theme.surfaceRaised
                                border.color: recommended
                                    ? Theme.success : Theme.border

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 12
                                    anchors.rightMargin: 12
                                    spacing: 10
                                    layoutDirection: I18n.rtl
                                        ? Qt.RightToLeft : Qt.LeftToRight
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 2
                                        Text {
                                            Layout.fillWidth: true
                                            text: I18n.directionalText(profile)
                                            color: Theme.text
                                            font.pixelSize: 11
                                            font.weight: Font.DemiBold
                                            horizontalAlignment: I18n.rtl
                                                ? Text.AlignRight
                                                : Text.AlignLeft
                                            elide: Text.ElideRight
                                        }
                                        Text {
                                            text: working
                                                ? I18n.t(
                                                    "working", "Working"
                                                )
                                                : I18n.t(
                                                    "failed", "Failed"
                                                )
                                            color: working
                                                ? Theme.success : Theme.danger
                                            font.pixelSize: 9
                                            horizontalAlignment: I18n.rtl
                                                ? Text.AlignRight
                                                : Text.AlignLeft
                                        }
                                    }
                                    Rectangle {
                                        visible: recommended
                                        implicitWidth:
                                            recommendationText.implicitWidth
                                                + 16
                                        implicitHeight: 26
                                        radius: 8
                                        color: Theme.successSoft
                                        Text {
                                            id: recommendationText
                                            anchors.centerIn: parent
                                            text: I18n.t(
                                                "recommended",
                                                "Recommended"
                                            )
                                            color: Theme.success
                                            font.pixelSize: 8
                                            font.weight: Font.Bold
                                        }
                                    }
                                    ColumnLayout {
                                        spacing: 1
                                        Text {
                                            text: I18n.t(
                                                "ping", "Ping"
                                            )
                                            color: Theme.textFaint
                                            font.pixelSize: 8
                                        }
                                        LiveValue {
                                            value: latency
                                            textColor: working
                                                ? Theme.secondary
                                                : Theme.textFaint
                                            pixelSize: 11
                                        }
                                    }
                                    ColumnLayout {
                                        spacing: 1
                                        Text {
                                            text: I18n.t(
                                                "loss", "Loss"
                                            )
                                            color: Theme.textFaint
                                            font.pixelSize: 8
                                        }
                                        LiveValue {
                                            value: loss
                                            textColor: working
                                                ? Theme.warning
                                                : Theme.textFaint
                                            pixelSize: 11
                                        }
                                    }
                                    AppButton {
                                        implicitHeight: 36
                                        text: I18n.t(
                                            "use_profile", "Use"
                                        )
                                        primary: recommended
                                        enabled: working
                                            && !AppController.busy
                                            && !AppController.autoSelecting
                                        onClicked:
                                            AppController.applySmartResult(
                                                index
                                            )
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
