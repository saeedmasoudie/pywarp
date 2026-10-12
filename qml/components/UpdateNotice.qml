import QtQuick
import QtQuick.Layouts
import "../theme"

Rectangle {
    id: root
    signal dismissed()

    implicitHeight: 64
    radius: 12
    color: Theme.surfaceRaised
    border.width: 1
    border.color: Theme.accent

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 15
        anchors.rightMargin: 15
        spacing: 14

        Rectangle {
            width: 8
            height: 8
            radius: 4
            color: Theme.accent
            SequentialAnimation on opacity {
                running: true
                loops: Animation.Infinite
                NumberAnimation { to: 0.35; duration: 700 }
                NumberAnimation { to: 1; duration: 700 }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Text {
                text: AppController.pywarpUpdateAvailable
                    && AppController.warpUpdateAvailable
                    ? I18n.t("two_updates", "Two updates are available")
                    : AppController.pywarpUpdateAvailable
                        ? I18n.t("pywarp_update", "PyWarp update available")
                        : I18n.t(
                            "warp_update",
                            "Cloudflare WARP update available"
                        )
                color: Theme.text
                font.pixelSize: 11
                font.weight: Font.DemiBold
            }
            Text {
                text: AppController.pywarpUpdateAvailable
                    ? "PyWarp " + AppController.currentVersion
                        + " → " + AppController.latestPywarpVersion
                    : "WARP " + AppController.installedWarpVersion
                        + " → " + AppController.latestWarpVersion
                color: Theme.textMuted
                font.pixelSize: 8
            }
        }

        RowLayout {
            Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
            spacing: 8
            AppButton {
                visible: AppController.pywarpUpdateAvailable
                Layout.minimumWidth: implicitWidth
                text: I18n.t("view_release", "View release")
                primary: true
                onClicked: AppController.openPywarpUpdate()
            }
            AppButton {
                visible: AppController.warpUpdateAvailable
                Layout.minimumWidth: implicitWidth
                text: I18n.t("open_warp", "Open WARP")
                onClicked: AppController.openWarpApplication()
            }
            AppButton {
                Layout.minimumWidth: implicitWidth
                text: I18n.t("later", "Later")
                quiet: true
                onClicked: root.dismissed()
            }
        }
    }
}
