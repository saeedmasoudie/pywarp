import QtQuick
import "../theme"

Canvas {
    id: root
    property string name: "overview"
    property color iconColor: Theme.textMuted
    property real strokeWidth: 1.8

    implicitWidth: 22
    implicitHeight: 22
    onNameChanged: requestPaint()
    onIconColorChanged: requestPaint()

    function line(ctx, points) {
        ctx.beginPath()
        ctx.moveTo(points[0][0], points[0][1])
        for (let i = 1; i < points.length; ++i)
            ctx.lineTo(points[i][0], points[i][1])
        ctx.stroke()
    }

    onPaint: {
        const ctx = getContext("2d")
        const sx = width / 24
        const sy = height / 24
        ctx.reset()
        ctx.clearRect(0, 0, width, height)
        ctx.scale(sx, sy)
        ctx.strokeStyle = iconColor
        ctx.fillStyle = "transparent"
        ctx.lineWidth = strokeWidth
        ctx.lineCap = "round"
        ctx.lineJoin = "round"

        if (name === "overview") {
            ctx.strokeRect(3.5, 3.5, 7, 7)
            ctx.strokeRect(13.5, 3.5, 7, 4.5)
            ctx.strokeRect(3.5, 13.5, 7, 7)
            ctx.strokeRect(13.5, 10.5, 7, 10)
        } else if (name === "network") {
            ctx.beginPath(); ctx.arc(12, 12, 8.5, 0, Math.PI * 2); ctx.stroke()
            ctx.beginPath(); ctx.arc(12, 12, 3.2, 0, Math.PI * 2); ctx.stroke()
            line(ctx, [[12, 3.5], [12, 8.8]])
            line(ctx, [[12, 15.2], [12, 20.5]])
            line(ctx, [[3.5, 12], [8.8, 12]])
            line(ctx, [[15.2, 12], [20.5, 12]])
        } else if (name === "activity") {
            line(ctx, [[3, 13], [6.5, 13], [9, 7], [13, 18], [16, 10.5], [18, 13], [21, 13]])
        } else if (name === "advanced") {
            line(ctx, [[4, 7], [20, 7]])
            line(ctx, [[4, 17], [20, 17]])
            ctx.beginPath(); ctx.arc(9, 7, 2.2, 0, Math.PI * 2); ctx.stroke()
            ctx.beginPath(); ctx.arc(16, 17, 2.2, 0, Math.PI * 2); ctx.stroke()
        } else if (name === "settings") {
            ctx.beginPath(); ctx.arc(12, 12, 3.2, 0, Math.PI * 2); ctx.stroke()
            ctx.beginPath(); ctx.arc(12, 12, 8.2, 0, Math.PI * 2); ctx.stroke()
            line(ctx, [[12, 1.8], [12, 3.8]])
            line(ctx, [[12, 20.2], [12, 22.2]])
            line(ctx, [[1.8, 12], [3.8, 12]])
            line(ctx, [[20.2, 12], [22.2, 12]])
        } else if (name === "power") {
            ctx.beginPath(); ctx.arc(12, 13, 8, -Math.PI * 0.72, Math.PI * 0.72); ctx.stroke()
            line(ctx, [[12, 2.5], [12, 12]])
        } else if (name === "stop") {
            ctx.strokeRect(6, 6, 12, 12)
        } else if (name === "close") {
            line(ctx, [[6, 6], [18, 18]])
            line(ctx, [[18, 6], [6, 18]])
        } else if (name === "shield") {
            ctx.beginPath()
            ctx.moveTo(12, 2.5); ctx.lineTo(20, 5.7); ctx.lineTo(19, 13.8)
            ctx.quadraticCurveTo(18, 18.5, 12, 21.5)
            ctx.quadraticCurveTo(6, 18.5, 5, 13.8)
            ctx.lineTo(4, 5.7); ctx.closePath(); ctx.stroke()
        } else if (name === "check") {
            line(ctx, [[4.5, 12.5], [9.5, 17.5], [19.5, 6.5]])
        } else if (name === "warning") {
            ctx.beginPath()
            ctx.moveTo(12, 3); ctx.lineTo(21, 20)
            ctx.lineTo(3, 20); ctx.closePath(); ctx.stroke()
            line(ctx, [[12, 8], [12, 14]])
            ctx.beginPath(); ctx.arc(12, 17.2, 0.7, 0, Math.PI * 2)
            ctx.fillStyle = iconColor; ctx.fill()
        } else if (name === "arrow-up") {
            line(ctx, [[12, 19], [12, 5], [6.5, 10.5]])
            line(ctx, [[12, 5], [17.5, 10.5]])
        } else if (name === "arrow-down") {
            line(ctx, [[12, 5], [12, 19], [6.5, 13.5]])
            line(ctx, [[12, 19], [17.5, 13.5]])
        } else if (name === "refresh") {
            ctx.beginPath(); ctx.arc(12, 12, 7.5, -0.4, Math.PI * 1.55); ctx.stroke()
            line(ctx, [[18.8, 4.7], [19.6, 9.1], [15.3, 8.2]])
        }
    }
}
