import QtQuick
import QtQuick.Controls
import "../theme"

ComboBox {
    id: root
    implicitHeight: 40
    leftPadding: I18n.rtl ? 34 : 12
    rightPadding: I18n.rtl ? 12 : 34
    font.pixelSize: 13

    contentItem: Text {
        leftPadding: 0
        rightPadding: 0
        text: root.displayText
        font: root.font
        color: Theme.text
        horizontalAlignment: I18n.rtl ? Text.AlignRight : Text.AlignLeft
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    indicator: Text {
        x: I18n.rtl ? 12 : root.width - width - 12
        anchors.verticalCenter: parent.verticalCenter
        text: "⌄"
        color: Theme.textMuted
        font.pixelSize: 17
    }
    background: Rectangle {
        color: root.hovered ? Theme.surfaceHover : Theme.surfaceRaised
        radius: Theme.radiusSmall
        border.color: root.activeFocus ? Theme.accent : Theme.border
    }
    popup: Popup {
        y: root.height + 5
        width: root.width
        implicitHeight: Math.min(contentItem.implicitHeight + 8, 300)
        padding: 4
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: root.popup.visible ? root.delegateModel : null
            currentIndex: root.highlightedIndex
            ScrollIndicator.vertical: ScrollIndicator {}
        }
        background: Rectangle {
            color: Theme.surface
            radius: Theme.radiusSmall
            border.color: Theme.border
        }
    }
    delegate: ItemDelegate {
        required property int index
        required property var modelData
        width: root.width - 8
        height: 38
        text: root.textRole ? model[root.textRole] : modelData
        highlighted: root.highlightedIndex === index
        contentItem: Text {
            text: parent.text
            color: Theme.text
            font.pixelSize: 13
            horizontalAlignment: I18n.rtl
                ? Text.AlignRight : Text.AlignLeft
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            radius: 6
            color: parent.highlighted ? Theme.surfaceHover : "transparent"
        }
    }
}
