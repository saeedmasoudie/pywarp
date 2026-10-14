import QtQuick
import QtQuick.Controls
import "../theme"

ComboBox {
    id: root
    implicitHeight: 40
    leftPadding: I18n.rtl ? 34 : 12
    rightPadding: I18n.rtl ? 12 : 34
    font.pixelSize: 13
    LayoutMirroring.enabled: false
    LayoutMirroring.childrenInherit: true

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
    indicator: Item {
        width: 16
        height: 16
        x: I18n.rtl ? 12 : root.width - width - 12
        anchors.verticalCenter: parent.verticalCenter
        Canvas {
            anchors.fill: parent
            onPaint: {
                const ctx = getContext("2d")
                ctx.reset()
                ctx.strokeStyle = Theme.textMuted
                ctx.lineWidth = 1.6
                ctx.lineCap = "round"
                ctx.lineJoin = "round"
                ctx.beginPath()
                ctx.moveTo(4, 6)
                ctx.lineTo(8, 10)
                ctx.lineTo(12, 6)
                ctx.stroke()
            }
            Connections {
                target: Theme
                function onTextMutedChanged() {
                    parent.requestPaint()
                }
            }
        }
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
        LayoutMirroring.enabled: false
        LayoutMirroring.childrenInherit: true
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
        leftPadding: 10
        rightPadding: 10
        text: root.textRole ? model[root.textRole] : modelData
        highlighted: root.highlightedIndex === index
        contentItem: Text {
            text: parent.text
            color: Theme.text
            font.pixelSize: 13
            elide: Text.ElideRight
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
