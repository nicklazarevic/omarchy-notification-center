import QtQuick

// Drawn in the bar's optical canvas so the bell stays crisp at every scale.
Item {
  id: root
  property color ink: "white"
  onInkChanged: bell.requestPaint()

  Canvas {
    id: bell
    anchors.fill: parent
    antialiasing: true
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onPaint: {
      var ctx = getContext("2d")
      ctx.reset()
      ctx.scale(width / 24, height / 24)
      ctx.strokeStyle = root.ink
      ctx.fillStyle = root.ink
      ctx.lineWidth = 1.55
      ctx.lineCap = "round"
      ctx.lineJoin = "round"

      // Small ring strokes stay inside the icon's optical bounds.
      ctx.beginPath()
      ctx.moveTo(3.45, 7.1)
      ctx.bezierCurveTo(2.3, 8.3, 2.3, 10.2, 3.45, 11.4)
      ctx.moveTo(20.55, 7.1)
      ctx.bezierCurveTo(21.7, 8.3, 21.7, 10.2, 20.55, 11.4)
      ctx.stroke()

      ctx.beginPath()
      ctx.moveTo(5.4, 5.15)
      ctx.bezierCurveTo(3.25, 7.05, 3.25, 11.25, 5.4, 13.15)
      ctx.moveTo(18.6, 5.15)
      ctx.bezierCurveTo(20.75, 7.05, 20.75, 11.25, 18.6, 13.15)
      ctx.stroke()

      // Filled bell, crown, and clapper. The shoulder curves make the shape
      // read as a bell rather than a generic alert triangle at 16–20 px.
      ctx.beginPath()
      ctx.moveTo(12, 3.25)
      ctx.bezierCurveTo(8.7, 3.25, 7.1, 5.75, 7.1, 9.2)
      ctx.lineTo(7.1, 12.25)
      ctx.bezierCurveTo(7.1, 13.4, 6.6, 14.05, 5.75, 14.95)
      ctx.bezierCurveTo(5.35, 15.35, 5.55, 15.95, 6.15, 15.95)
      ctx.lineTo(17.85, 15.95)
      ctx.bezierCurveTo(18.45, 15.95, 18.65, 15.35, 18.25, 14.95)
      ctx.bezierCurveTo(17.4, 14.05, 16.9, 13.4, 16.9, 12.25)
      ctx.lineTo(16.9, 9.2)
      ctx.bezierCurveTo(16.9, 5.75, 15.3, 3.25, 12, 3.25)
      ctx.closePath()
      ctx.fill()
      ctx.beginPath()
      ctx.arc(12, 17.1, 1.5, 0, Math.PI * 2)
      ctx.fill()
    }
  }
}
