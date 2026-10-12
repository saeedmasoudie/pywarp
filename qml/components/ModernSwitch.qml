import QtQuick
import QtQuick.Layouts
import "../theme"

Item {
    id: root
    property bool checked: false
    property bool enabled: true
    signal toggled(bool checked)

    implicitWidth: 44
    implicitHeight: 24
    Layout.preferredWidth: implicitWidth
    Layout.minimumWidth: implicitWidth
    Layout.maximumWidth: implicitWidth
    Layout.preferredHeight: implicitHeight
    Layout.minimumHeight: implicitHeight
    Layout.maximumHeight: implicitHeight
    opacity: enabled ? 1 : 0.45

    Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: root.checked ? Theme.accent : Theme.surfaceBright
        border.width: 1
        border.color: root.checked ? Theme.accent : Theme.borderBright
        Behavior on color {
            ColorAnimation { duration: Theme.animationFast }
        }

        Rectangle {
            width: 18
            height: 18
            radius: 9
            y: 3
            x: root.checked
                ? (I18n.rtl ? 3 : parent.width - width - 3)
                : (I18n.rtl ? parent.width - width - 3 : 3)
            color: root.checked ? "white" : Theme.textMuted
            Behavior on x {
                NumberAnimation {
                    duration: 190
                    easing.type: Easing.OutBack
                }
            }
        }
    }

    MouseArea {
        anchors.fill: parent
        enabled: root.enabled
        cursorShape: Qt.PointingHandCursor
        onClicked: root.toggled(!root.checked)
    }
}
