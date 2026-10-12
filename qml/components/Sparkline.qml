import QtQuick
import "../theme"

Canvas {
    id: root
    property var values: []
    property color lineColor: Theme.secondary
    property color fillColor: Qt.rgba(
        lineColor.r, lineColor.g, lineColor.b, 0.12
    )

    onValuesChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()

    onPaint: {
        const ctx = getContext("2d")
        ctx.clearRect(0, 0, width, height)
        if (!values || values.length < 2)
            return
        let low = values[0]
        let high = values[0]
        for (let i = 1; i < values.length; ++i) {
            low = Math.min(low, values[i])
            high = Math.max(high, values[i])
        }
        const range = Math.max(high - low, 8)
        const dx = width / Math.max(values.length - 1, 1)
        function yFor(value) {
            return height - 5 - ((value - low) / range) * (height - 10)
        }

        ctx.beginPath()
        ctx.moveTo(0, yFor(values[0]))
        for (let j = 1; j < values.length; ++j)
            ctx.lineTo(j * dx, yFor(values[j]))
        ctx.lineTo(width, height)
        ctx.lineTo(0, height)
        ctx.closePath()
        ctx.fillStyle = fillColor
        ctx.fill()

        ctx.beginPath()
        ctx.moveTo(0, yFor(values[0]))
        for (let k = 1; k < values.length; ++k)
            ctx.lineTo(k * dx, yFor(values[k]))
        ctx.strokeStyle = lineColor
        ctx.lineWidth = 2
        ctx.lineCap = "round"
        ctx.lineJoin = "round"
        ctx.stroke()
    }
}
