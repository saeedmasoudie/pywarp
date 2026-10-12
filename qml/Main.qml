import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Layouts
import "components"
import "pages"
import "theme"

ApplicationWindow {
    id: window
    FontLoader {
        id: persianFont
        source: "../assets/Estedad.ttf"
    }

    font.family: I18n.rtl && persianFont.status === FontLoader.Ready
        ? persianFont.name : Qt.application.font.family
    width: 1080
    height: 760
    minimumWidth: AppController.compactMode ? 420 : 820
    minimumHeight: AppController.compactMode ? 190 : 600
    visible: true
    title: "PyWarp"
    color: Theme.background
    flags: Qt.Window | Qt.FramelessWindowHint
    LayoutMirroring.enabled: I18n.rtl
    LayoutMirroring.childrenInherit: true

    property int currentPage: 0
    property bool appliedCompact: false
    property real expandedWidth: 1080
    property real expandedHeight: 760
    property bool updatesDismissed: false
    property bool minimizing: false
    property string tourFocusTarget: ""
    property var pageTitles: [
        I18n.t("overview", "Overview"),
        I18n.t("connection", "Connection"),
        I18n.t("smart_test", "Smart route"),
        I18n.t("advanced", "Advanced"),
        I18n.t("activity", "Activity"),
        I18n.t("settings", "Settings")
    ]

    function syncCompactMode() {
        if (appliedCompact === AppController.compactMode)
            return
        if (AppController.compactMode) {
            expandedWidth = width
            expandedHeight = height
            width = 430
            height = 200
        } else {
            width = Math.max(expandedWidth, 820)
            height = Math.max(expandedHeight, 600)
        }
        appliedCompact = AppController.compactMode
    }

    function minimizeWindow() {
        if (!minimizing)
            minimizeAnimation.restart()
    }

    Component.onCompleted: syncCompactMode()

    onClosing: function(close) {
        if (TrayService.available && !TrayService.forceQuit) {
            close.accepted = false
            TrayService.hideWindow()
        } else if (!TrayService.forceQuit) {
            close.accepted = false
            quitDialog.open()
        }
    }

    Component { id: overviewPage; OverviewPage {} }
    Component {
        id: connectionPage
        ControlCenterPage { section: 0; showSectionTabs: false }
    }
    Component {
        id: smartPage
        ControlCenterPage { section: 2; showSectionTabs: false }
    }
    Component {
        id: advancedPage
        ControlCenterPage { section: 1; showSectionTabs: false }
    }
    Component { id: activityPage; ActivityPage {} }
    Component { id: settingsPage; SettingsPage {} }

    Rectangle {
        anchors.fill: parent
        color: Theme.background
    }

    ColumnLayout {
        id: appShell
        anchors.fill: parent
        spacing: 0

        Rectangle {
            id: titleBar
            Layout.fillWidth: true
            Layout.preferredHeight: 44
            color: Theme.backgroundElevated

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: 1
                color: Theme.border
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 13
                anchors.rightMargin: 7
                spacing: 8

                LogoMark {
                    width: 24
                    height: 24
                }
                Text {
                    text: "PyWarp"
                    color: Theme.text
                    font.pixelSize: 11
                    font.weight: Font.DemiBold
                }
                Rectangle {
                    width: 6
                    height: 6
                    radius: 3
                    color: AppController.connected
                        ? Theme.success
                        : AppController.transitioning
                            ? Theme.warning : Theme.textFaint
                }
                Text {
                    text: I18n.status(AppController.status)
                    color: Theme.textMuted
                    font.pixelSize: 9
                }

                Item { Layout.fillWidth: true }

                Rectangle {
                    implicitWidth: windowControls.implicitWidth + 6
                    implicitHeight: 34
                    radius: 11
                    color: Theme.surfaceRaised
                    border.color: Theme.border
                    RowLayout {
                        id: windowControls
                        anchors.centerIn: parent
                        spacing: 1
                        WindowControl {
                            symbol: AppController.compactMode ? "expand" : "tiny"
                            onClicked: AppController.toggleCompactMode()
                        }
                        WindowControl {
                            symbol: "minimize"
                        onClicked: window.minimizeWindow()
                        }
                        WindowControl {
                            symbol: "maximize"
                            onClicked: window.visibility === Window.Maximized
                                ? window.showNormal() : window.showMaximized()
                        }
                        WindowControl {
                            symbol: "close"
                            destructive: true
                            onClicked: TrayService.available
                                ? TrayService.hideWindow()
                                : window.close()
                        }
                    }
                }
            }

            MouseArea {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.rightMargin: 160
                acceptedButtons: Qt.LeftButton
                onPressed: window.startSystemMove()
                onDoubleClicked: window.visibility === Window.Maximized
                    ? window.showNormal() : window.showMaximized()
            }
        }

        RowLayout {
            visible: !AppController.compactMode
            Layout.fillWidth: true
            Layout.fillHeight: visible
            spacing: 0

            Rectangle {
                Layout.fillHeight: true
                Layout.preferredWidth: 180
                color: Theme.sidebar
                border.color: Theme.border

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 5

                    Text {
                        Layout.leftMargin: 10
                        Layout.topMargin: 9
                        Layout.bottomMargin: 8
                        text: I18n.t("navigation", "NAVIGATION")
                        color: Theme.textFaint
                        font.pixelSize: 7
                        font.weight: Font.Bold
                        font.letterSpacing: 1.2
                    }

                    Repeater {
                        model: window.pageTitles
                        SidebarNavButton {
                            required property int index
                            required property string modelData
                            Layout.fillWidth: true
                            text: modelData
                            active: window.currentPage === index
                            onClicked: window.currentPage = index
                        }
                    }

                    Item { Layout.fillHeight: true }

                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: 74
                        radius: 12
                        color: Theme.surfaceRaised
                        border.color: Theme.border
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 11
                            spacing: 4
                            RowLayout {
                                Layout.fillWidth: true
                                Rectangle {
                                    width: 7
                                    height: 7
                                    radius: 4
                                    color: AppController.connected
                                        ? Theme.success
                                        : AppController.transitioning
                                            ? Theme.warning : Theme.textFaint
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: I18n.status(AppController.status)
                                    color: Theme.text
                                    font.pixelSize: 9
                                    font.weight: Font.DemiBold
                                }
                            }
                            Text {
                                Layout.fillWidth: true
                                text: AppController.mode.toUpperCase()
                                    + " · " + AppController.protocol
                                color: Theme.textMuted
                                font.pixelSize: 8
                                elide: Text.ElideRight
                            }
                            Text {
                                Layout.fillWidth: true
                                text: AppController.publicIp
                                color: Theme.textFaint
                                font.pixelSize: 8
                                font.family: "monospace"
                                elide: Text.ElideRight
                            }
                        }
                    }

                    AppButton {
                        Layout.fillWidth: true
                        text: I18n.t("tiny_mode", "Tiny mode")
                        quiet: true
                        onClicked: AppController.setCompactMode(true)
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 10

                RowLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: Theme.pageMargin
                    Layout.rightMargin: Theme.pageMargin
                    Layout.topMargin: 13
                    Layout.preferredHeight: 34
                    Text {
                        Layout.fillWidth: true
                        text: window.pageTitles[window.currentPage]
                        color: Theme.text
                        font.pixelSize: 18
                        font.weight: Font.DemiBold
                        font.letterSpacing: -0.3
                    }
                }

                UpdateNotice {
                    Layout.fillWidth: true
                    Layout.leftMargin: Theme.pageMargin
                    Layout.rightMargin: Theme.pageMargin
                    visible: !window.updatesDismissed
                        && (AppController.pywarpUpdateAvailable
                            || AppController.warpUpdateAvailable)
                    Layout.preferredHeight: visible ? implicitHeight : 0
                    onDismissed: window.updatesDismissed = true
                }

                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.leftMargin: Theme.pageMargin
                    Layout.rightMargin: Theme.pageMargin
                    Layout.bottomMargin: 16

                    Loader {
                        id: pageLoader
                        anchors.fill: parent
                        sourceComponent: window.currentPage === 0
                            ? overviewPage
                            : window.currentPage === 1
                                ? connectionPage
                                : window.currentPage === 2
                                    ? smartPage
                                    : window.currentPage === 3
                                        ? advancedPage
                                        : window.currentPage === 4
                                            ? activityPage : settingsPage
                        transform: Translate { id: pageOffset; y: 0 }
                        onSourceComponentChanged: pageEnter.restart()
                    }

                    ParallelAnimation {
                        id: pageEnter
                        NumberAnimation {
                            target: pageLoader
                            property: "opacity"
                            from: 0
                            to: 1
                            duration: 240
                            easing.type: Easing.OutCubic
                        }
                        NumberAnimation {
                            target: pageOffset
                            property: "y"
                            from: 9
                            to: 0
                            duration: 300
                            easing.type: Easing.OutCubic
                        }
                    }
                }
            }
        }

        TinyMode {
            visible: AppController.compactMode
            Layout.fillWidth: true
            Layout.fillHeight: visible
        }
    }

    Rectangle {
        id: busyBar
        anchors.top: parent.top
        width: 190
        height: 2
        visible: AppController.busy || AppController.updateDownloading
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: Theme.accent }
            GradientStop { position: 1; color: Theme.secondary }
        }
        SequentialAnimation on x {
            running: busyBar.visible
            loops: Animation.Infinite
            NumberAnimation {
                from: I18n.rtl ? window.width : -busyBar.width
                to: I18n.rtl ? -busyBar.width : window.width
                duration: 1000
                easing.type: Easing.InOutQuad
            }
        }
    }

    Popup {
        id: toast
        property string kind: "success"
        property real remaining: 1
        readonly property color tone: kind === "error"
            ? Theme.danger : kind === "warning"
                ? Theme.warning : Theme.success
        readonly property string titleText: kind === "error"
            ? I18n.t("notice_error", "Action needs attention")
            : kind === "warning"
                ? I18n.t("notice_warning", "Please check this")
                : I18n.t("notice_success", "Change applied")
        x: I18n.rtl ? 20 : window.width - width - 20
        y: 58
        width: Math.min(390, window.width - 40)
        height: toastContent.implicitHeight + 24
        padding: 12
        closePolicy: Popup.NoAutoClose
        enter: Transition {
            ParallelAnimation {
                NumberAnimation {
                    property: "opacity"
                    from: 0
                    to: 1
                    duration: 180
                }
                NumberAnimation {
                    property: "scale"
                    from: 0.92
                    to: 1
                    duration: 260
                    easing.type: Easing.OutBack
                }
            }
        }
        exit: Transition {
            NumberAnimation { property: "opacity"; to: 0; duration: 140 }
        }
        background: Rectangle {
            color: Theme.surfaceBright
            radius: Theme.radius
            border.width: 1
            border.color: toast.tone
            Rectangle {
                x: I18n.rtl
                    ? parent.width - width - 10 : 10
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 5
                width: (parent.width - 20) * toast.remaining
                height: 2
                color: toast.tone
                radius: 1
            }
        }
        contentItem: RowLayout {
            id: toastContent
            spacing: 10
            Rectangle {
                Layout.preferredWidth: 3
                Layout.fillHeight: true
                radius: 2
                color: toast.tone
            }
            Rectangle {
                Layout.preferredWidth: 36
                Layout.preferredHeight: 36
                Layout.alignment: Qt.AlignVCenter
                radius: 11
                color: Qt.rgba(
                    toast.tone.r,
                    toast.tone.g,
                    toast.tone.b,
                    0.14
                )
                LineIcon {
                    anchors.centerIn: parent
                    width: 18
                    height: 18
                    strokeWidth: 2
                    name: toast.kind === "error" ? "close"
                        : toast.kind === "warning" ? "warning" : "check"
                    iconColor: toast.tone
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
                spacing: 3
                Text {
                    Layout.fillWidth: true
                    text: toast.titleText
                    color: Theme.text
                    font.pixelSize: 12
                    font.weight: Font.DemiBold
                }
                Text {
                    id: toastText
                    Layout.fillWidth: true
                    color: Theme.textMuted
                    font.pixelSize: 10
                    lineHeight: 1.2
                    wrapMode: Text.WordWrap
                }
            }
            WindowControl {
                Layout.alignment: Qt.AlignTop
                symbol: "close"
                onClicked: toast.close()
            }
        }
        NumberAnimation {
            id: toastProgress
            target: toast
            property: "remaining"
            from: 1
            to: 0
            duration: 6200
        }
        Timer {
            id: toastTimer
            interval: 6200
            onTriggered: toast.close()
        }
    }

    Popup {
        id: quitDialog
        property bool quitting: false
        anchors.centerIn: Overlay.overlay
        width: Math.min(390, window.width - 40)
        padding: 0
        modal: true
        focus: true
        closePolicy: quitting ? Popup.NoAutoClose : Popup.CloseOnEscape

        Overlay.modal: Rectangle {
            color: Qt.rgba(0.02, 0.03, 0.08, 0.64)
        }

        background: Rectangle {
            color: Theme.surface
            radius: Theme.radiusLarge
            border.width: 1
            border.color: Theme.borderBright
        }

        contentItem: ColumnLayout {
            spacing: 0

            ColumnLayout {
                Layout.fillWidth: true
                Layout.margins: 22
                spacing: 9

                Rectangle {
                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredWidth: 44
                    Layout.preferredHeight: 44
                    radius: 14
                    color: Theme.dangerSoft

                    LineIcon {
                        anchors.centerIn: parent
                        width: 22
                        height: 22
                        name: "close"
                        iconColor: Theme.danger
                    }
                }

                Text {
                    Layout.fillWidth: true
                    text: I18n.t("quit_title", "Quit PyWarp?")
                    color: Theme.text
                    font.pixelSize: 17
                    font.weight: Font.DemiBold
                    horizontalAlignment: Text.AlignHCenter
                }

                Text {
                    Layout.fillWidth: true
                    text: I18n.t(
                        quitDialog.quitting
                            ? "quit_progress" : "quit_body",
                        quitDialog.quitting
                            ? "Disconnecting the secure tunnel…"
                            : "PyWarp will disconnect the secure tunnel before quitting."
                    )
                    color: Theme.textMuted
                    font.pixelSize: 10
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                color: Theme.border
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.margins: 14
                spacing: 8

                AppButton {
                    Layout.fillWidth: true
                    text: I18n.t("cancel", "Cancel")
                    enabled: !quitDialog.quitting
                    onClicked: quitDialog.close()
                }
                AppButton {
                    Layout.fillWidth: true
                    text: quitDialog.quitting
                        ? I18n.t("disconnecting", "Disconnecting…")
                        : I18n.t("quit", "Quit")
                    danger: true
                    enabled: !quitDialog.quitting
                    onClicked: {
                        quitDialog.quitting = true
                        TrayService.confirmQuit()
                    }
                }
            }
        }
    }

    Connections {
        target: AppController
        function onSettingsChanged() {
            window.syncCompactMode()
        }
        function onUpdateStateChanged() {
            if (!AppController.updateChecking
                    && (AppController.pywarpUpdateAvailable
                        || AppController.warpUpdateAvailable))
                window.updatesDismissed = false
        }
        function onToastRequested(kind, message) {
            toast.kind = kind
            toastText.text = message
            toast.open()
            toastProgress.restart()
            toastTimer.restart()
        }
        function onNavigationRequested(page) {
            window.currentPage = Math.max(
                0, Math.min(window.pageTitles.length - 1, page)
            )
        }
        function onFocusRequested(kind) {
            if (pageLoader.item && pageLoader.item.highlightSection) {
                pageLoader.item.highlightSection(
                    kind, !guidedTour.visible
                )
                if (guidedTour.visible) {
                    window.tourFocusTarget = kind
                    guidedTour.pointTo(Qt.rect(0, 0, 0, 0))
                    Qt.callLater(tourTargetTracker.updateTarget)
                }
            }
        }
        function onTourRequested() {
            guidedTour.start()
        }
    }

    TourOverlay {
        id: guidedTour
        anchors.fill: parent
        z: 150
        visible: false
    }

    Timer {
        id: tourTargetTracker
        interval: 16
        repeat: true
        running: guidedTour.visible
            && window.tourFocusTarget.length > 0

        function updateTarget() {
            if (!guidedTour.visible
                    || !pageLoader.item
                    || !pageLoader.item.tourTargetRect)
                return
            guidedTour.pointTo(
                pageLoader.item.tourTargetRect(
                    window.tourFocusTarget, guidedTour
                )
            )
        }

        onTriggered: updateTarget()
    }

    SequentialAnimation {
        id: minimizeAnimation
        ScriptAction {
            script: window.minimizing = true
        }
        ParallelAnimation {
            NumberAnimation {
                target: appShell
                property: "opacity"
                from: 1
                to: 0
                duration: 130
                easing.type: Easing.InCubic
            }
            NumberAnimation {
                target: appShell
                property: "scale"
                from: 1
                to: 0.985
                duration: 130
                easing.type: Easing.InCubic
            }
        }
        ScriptAction {
            script: {
                window.showMinimized()
                appShell.opacity = 1
                appShell.scale = 1
                window.minimizing = false
            }
        }
    }

    Connections {
        target: TrayService
        function onQuitConfirmationRequested() {
            quitDialog.quitting = false
            quitDialog.open()
        }
    }

    Loader {
        anchors.fill: parent
        z: 100
        active: !AppController.introComplete
        sourceComponent: IntroPage {}
    }

    Rectangle {
        z: 190
        anchors.fill: parent
        color: "transparent"
        border.width: 1
        border.color: Theme.border
    }

    MouseArea {
        z: 200
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: 5
        cursorShape: Qt.SizeHorCursor
        enabled: window.visibility !== Window.Maximized
        onPressed: window.startSystemResize(Qt.LeftEdge)
    }
    MouseArea {
        z: 200
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: 5
        cursorShape: Qt.SizeHorCursor
        enabled: window.visibility !== Window.Maximized
        onPressed: window.startSystemResize(Qt.RightEdge)
    }
    MouseArea {
        z: 200
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 5
        cursorShape: Qt.SizeVerCursor
        enabled: window.visibility !== Window.Maximized
        onPressed: window.startSystemResize(Qt.BottomEdge)
    }
}
