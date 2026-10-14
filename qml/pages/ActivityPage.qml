import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"
import "../theme"

Item {
    id: root
    property int section: 0

    ColumnLayout {
        anchors.fill: parent
        spacing: 12

        RowLayout {
            Layout.fillWidth: true
            Rectangle {
                implicitWidth: activityTabs.implicitWidth + 8
                implicitHeight: 46
                radius: 14
                color: Theme.surface
                border.color: Theme.border
                RowLayout {
                    id: activityTabs
                    anchors.centerIn: parent
                    spacing: 2
                    NavTab {
                        text: I18n.t(
                            "connection_events", "Connection events"
                        )
                        active: root.section === 0
                        onClicked: root.section = 0
                    }
                    NavTab {
                        text: I18n.t("dns_requests", "DNS requests")
                        active: root.section === 1
                        onClicked: root.section = 1
                    }
                }
            }
            Item { Layout.fillWidth: true }
            StyledTextField {
                id: filter
                Layout.preferredWidth: 240
                placeholderText: I18n.t(
                    "filter_activity", "Filter activity"
                )
            }
            AppButton {
                text: I18n.t("clear", "Clear")
                quiet: true
                onClicked: root.section === 0
                    ? AppController.clearAppLogs()
                    : AppController.clearDnsLogs()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: Theme.radius
            color: Theme.surface
            border.color: Theme.border
            clip: true

            ListView {
                id: eventList
                anchors.fill: parent
                anchors.margins: 7
                visible: root.section === 0
                model: AppController.appLogModel
                spacing: 4
                clip: true
                ScrollBar.vertical: StyledScrollBar {}
                delegate: Rectangle {
                    required property int index
                    required property string time
                    required property string date
                    required property string level
                    required property string category
                    required property string message
                    required property string detail
                    property bool matches: !filter.text
                        || message.toLowerCase().includes(filter.text.toLowerCase())
                        || detail.toLowerCase().includes(filter.text.toLowerCase())
                        || category.toLowerCase().includes(filter.text.toLowerCase())
                    width: ListView.view.width
                    height: matches ? 67 : 0
                    visible: height > 0
                    radius: 9
                    color: eventMouse.containsMouse
                        ? Theme.surfaceHover
                        : index % 2 ? "transparent" : Theme.surfaceRaised

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 12
                        anchors.rightMargin: 12
                        spacing: 11

                        Rectangle {
                            width: 3
                            height: 34
                            radius: 2
                            color: level === "ERROR" || level === "CRITICAL"
                                ? Theme.danger
                                : level === "WARNING"
                                    ? Theme.warning
                                    : level === "SUCCESS"
                                        ? Theme.success : Theme.secondary
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 3
                            RowLayout {
                                Layout.fillWidth: true
                                Text {
                                    Layout.fillWidth: true
                                    text: I18n.directionalText(
                                        I18n.activityText(message)
                                    )
                                    color: Theme.text
                                    font.pixelSize: 11
                                    font.weight: Font.DemiBold
                                    horizontalAlignment: I18n.rtl
                                        ? Text.AlignRight : Text.AlignLeft
                                    elide: Text.ElideRight
                                }
                                Text {
                                    text: I18n.directionalText(
                                        I18n.activityCategory(category)
                                    )
                                    color: Theme.textFaint
                                    font.pixelSize: 7
                                    font.weight: Font.Bold
                                    font.letterSpacing: 0.7
                                }
                            }
                            Text {
                                Layout.fillWidth: true
                                text: I18n.directionalText(
                                    I18n.activityText(detail)
                                )
                                color: Theme.textMuted
                                font.pixelSize: 9
                                horizontalAlignment: I18n.rtl
                                    ? Text.AlignRight : Text.AlignLeft
                                elide: Text.ElideRight
                            }
                        }
                        ColumnLayout {
                            Layout.preferredWidth: 70
                            spacing: 2
                            Text {
                                Layout.alignment: Qt.AlignRight
                                text: time
                                color: Theme.textMuted
                                font.pixelSize: 9
                                font.family: "monospace"
                            }
                            Text {
                                Layout.alignment: Qt.AlignRight
                                text: date
                                color: Theme.textFaint
                                font.pixelSize: 7
                            }
                        }
                    }
                    MouseArea {
                        id: eventMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        acceptedButtons: Qt.NoButton
                    }
                }
                Text {
                    anchors.centerIn: parent
                    visible: eventList.count === 0
                    text: I18n.t(
                        "no_events",
                        "Connection events will appear here"
                    )
                    color: Theme.textFaint
                    font.pixelSize: 10
                }
            }

            ListView {
                id: dnsList
                anchors.fill: parent
                anchors.margins: 7
                visible: root.section === 1
                model: AppController.dnsLogModel
                spacing: 3
                clip: true
                ScrollBar.vertical: StyledScrollBar {}
                delegate: Rectangle {
                    required property int index
                    required property string time
                    required property string recordType
                    required property string domain
                    required property string status
                    required property string duration
                    required property string answers
                    property bool matches: !filter.text
                        || domain.toLowerCase().includes(filter.text.toLowerCase())
                        || status.toLowerCase().includes(filter.text.toLowerCase())
                    width: ListView.view.width
                    height: matches ? 50 : 0
                    visible: height > 0
                    radius: 8
                    color: index % 2 ? "transparent" : Theme.surfaceRaised

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 12
                        anchors.rightMargin: 12
                        spacing: 10
                        Text {
                            Layout.preferredWidth: 58
                            text: time
                            color: Theme.textFaint
                            font.pixelSize: 8
                            font.family: "monospace"
                        }
                        Text {
                            Layout.preferredWidth: 38
                            text: recordType
                            color: Theme.secondary
                            font.pixelSize: 9
                            font.weight: Font.Bold
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 1
                            Text {
                                Layout.fillWidth: true
                                text: domain
                                color: Theme.text
                                font.pixelSize: 10
                                elide: Text.ElideMiddle
                            }
                            Text {
                                Layout.fillWidth: true
                                text: answers
                                color: Theme.textFaint
                                font.pixelSize: 8
                                elide: Text.ElideMiddle
                            }
                        }
                        Text {
                            text: status
                            color: status === "NoError"
                                ? Theme.success : Theme.warning
                            font.pixelSize: 9
                        }
                        Text {
                            Layout.preferredWidth: 58
                            text: duration
                            color: Theme.textMuted
                            font.pixelSize: 9
                            horizontalAlignment: Text.AlignRight
                        }
                    }
                }
                Text {
                    anchors.centerIn: parent
                    visible: dnsList.count === 0
                    text: AppController.dnsLogging
                        ? I18n.t(
                            "waiting_dns_requests",
                            "Waiting for DNS requests"
                        )
                        : I18n.t(
                            "enable_dns_activity",
                            "Enable DNS activity in Control center"
                        )
                    color: Theme.textFaint
                    font.pixelSize: 10
                }
            }
        }
    }
}
