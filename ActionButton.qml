import QtQuick
import QtQuick.Controls
import qs.Commons
import "Palette.js" as Palette

Button {
  id: root
  property bool primary: false
  property color ink: Color.foreground
  implicitWidth: Math.max(Style.space(72), label.implicitWidth + Style.space(24))
  implicitHeight: Style.space(32)

  background: Rectangle {
    radius: Style.space(8)
    color: root.primary ? Color.accent : (root.down || root.hovered
      ? Style.selectedFillFor(root.ink, Color.accent)
      : Style.hoverFillFor(root.ink, Color.accent))
    border.width: root.primary ? 0 : 1
    border.color: root.ink
    opacity: root.enabled ? 1 : 0.5
  }
  contentItem: Text {
    id: label
    text: root.text
    font.family: Style.font.family
    font.pixelSize: Style.font.body
    font.bold: root.primary
    color: root.primary ? Palette.onAccent(Color.accent) : root.ink
    horizontalAlignment: Text.AlignHCenter
    verticalAlignment: Text.AlignVCenter
  }
}
