import QtQuick
import QtQuick.Controls
import "../theme"

TextField {
    id: root
    implicitHeight: 40
    leftPadding: 12
    rightPadding: 12
    color: Theme.text
    placeholderTextColor: Theme.textMuted
    selectionColor: Theme.accent
    selectedTextColor: "white"
    font.pixelSize: 13
    verticalAlignment: TextInput.AlignVCenter

    background: Rectangle {
        color: Theme.surfaceRaised
        radius: Theme.radiusSmall
        border.color: root.activeFocus ? Theme.accent : Theme.border
        border.width: 1
    }
}
