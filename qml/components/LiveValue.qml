import QtQuick
import "../theme"

Item {
    id: root
    property string value: "—"
    property color textColor: Theme.text
    property int pixelSize: 20
    property int weight: Font.DemiBold
    property int alignment: Text.AlignLeft

    implicitWidth: valueText.implicitWidth
    implicitHeight: valueText.implicitHeight

    Text {
        id: valueText
        anchors.fill: parent
        text: root.value
        color: root.textColor
        font.pixelSize: root.pixelSize
        font.weight: root.weight
        horizontalAlignment: root.alignment
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        transformOrigin: Item.Center
    }

    onValueChanged: valuePulse.restart()

    SequentialAnimation {
        id: valuePulse
        NumberAnimation {
            target: valueText
            property: "scale"
            to: 1.07
            duration: 110
            easing.type: Easing.OutCubic
        }
        NumberAnimation {
            target: valueText
            property: "scale"
            to: 1
            duration: 190
            easing.type: Easing.OutBack
        }
    }
}
