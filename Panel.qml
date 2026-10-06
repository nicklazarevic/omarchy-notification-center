import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Palette.js" as Palette

Panel {
  id: root
  moduleName: "laza11.notification-center"
  ipcTarget: moduleName
  manageIpc: false

  readonly property string backend: Quickshell.env("HOME") + "/.config/omarchy/plugins/laza11.notification-center/backend.py"
  property var recentRows: []
  property var savedRows: []
  property var selectedSnapshot: null
  property string selectedKey: ""
  property string tab: "Recent"
  property string message: ""
  property string input: ""
  property var preview: null
  property int overdueCount: 0
  property var dueItems: []
  property string requestedSavedId: ""
  readonly property color ink: bar ? bar.foreground : Color.foreground
  readonly property color muted: Qt.rgba(ink.r, ink.g, ink.b, 0.78)
  readonly property color accent: Color.accent

  function selectedItem() {
    var rows = tab === "Recent" ? recentRows : savedRows
    for (var i = 0; i < rows.length; i++)
      if ((tab === "Recent" ? rows[i].key : rows[i].id) === selectedKey) return rows[i]
    // Preserve a selected Recent row across expiration/reordering.
    if (tab === "Recent" && selectedSnapshot && selectedSnapshot.key === selectedKey)
      return selectedSnapshot
    return null
  }

  function refresh() {
    if (!snapshotProc.running) snapshotProc.running = true
  }

  function invoke(command, argumentsList) {
    if (actionProc.running) return
    actionProc.command = ["python3", backend, command].concat(argumentsList)
    actionProc.running = true
  }

  function onSnapshot(raw) {
    try {
      var response = JSON.parse(raw)
      if (!response.ok) { message = response.error || "Could not read notifications"; return }
      recentRows = response.result.recent || []
      savedRows = response.result.saved || []
      if (requestedSavedId) {
        for (var i = 0; i < savedRows.length; i++) {
          if (savedRows[i].id === requestedSavedId) {
            tab = "Saved"
            selectedKey = requestedSavedId
            selectedSnapshot = null
            open()
            break
          }
        }
        requestedSavedId = ""
      }
    } catch (e) { message = "Could not read notification data" }
  }

  function onAction(raw) {
    try {
      var response = JSON.parse(raw)
      message = response.ok ? "Saved" : (response.error || "Action failed")
      if (response.ok && actionProc.command[2] === "save") {
        tab = "Saved"
        selectedKey = response.result.id
        selectedSnapshot = null
      }
    } catch (e) { message = "Action failed" }
    refresh()
    if (!tickProc.running) tickProc.running = true
  }

  function onPreview(raw) {
    try {
      var response = JSON.parse(raw)
      preview = response.ok ? response.result : null
      message = response.ok ? "Confirm the exact local date and time below" : (response.error || "Invalid time")
    } catch (e) { preview = null; message = "Invalid time" }
  }

  function onTick(raw) {
    try {
      var response = JSON.parse(raw)
      if (!response.ok) return
      overdueCount = response.result.overdue || 0
      dueItems = response.result.due || []
      if (opened) refresh()
    } catch (e) {}
  }

  function openSaved(identifier) {
    if (!/^[0-9a-f]{32}$/.test(identifier)) return
    requestedSavedId = identifier
    refresh()
  }

  onOpenedChanged: if (opened) refresh()
  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  Process {
    id: snapshotProc
    command: ["python3", root.backend, "snapshot"]
    stdout: StdioCollector { waitForEnd: true; onStreamFinished: root.onSnapshot(text) }
  }
  Process {
    id: actionProc
    stdout: StdioCollector { waitForEnd: true; onStreamFinished: root.onAction(text) }
  }
  Process {
    id: previewProc
    stdout: StdioCollector { waitForEnd: true; onStreamFinished: root.onPreview(text) }
  }
  Process {
    id: tickProc
    command: ["python3", root.backend, "tick"]
    stdout: StdioCollector { waitForEnd: true; onStreamFinished: root.onTick(text) }
  }
  Timer {
    interval: 30000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: if (!tickProc.running) tickProc.running = true
  }
  Timer {
    interval: 2000
    running: root.opened
    repeat: true
    onTriggered: root.refresh()
  }

  IpcHandler {
    target: root.moduleName
    function open(): void { root.open() }
    function close(): void { root.close() }
    function toggle(): void { root.toggle() }
    function openSaved(identifier: string): void { root.openSaved(identifier) }
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    iconComponent: Component {
      BellIcon { ink: root.overdueCount > 0 ? Color.urgent : button.foreground }
    }
    opticalSize: Style.space(29) * 0.9
    active: root.overdueCount > 0
    tooltipText: root.overdueCount > 0 ? root.overdueCount + " saved reminder(s) due" : "Notification Center"
    onPressed: {
      if (root.opened) root.close()
      else if (root.dueItems.length > 0) root.openSaved(root.dueItems[0].id)
      else root.open()
    }

    Rectangle {
      visible: root.overdueCount > 0
      width: Style.space(6)
      height: width
      radius: width / 2
      color: Color.urgent
      anchors.right: parent.right
      anchors.top: parent.top
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: fittedContentWidth(Style.space(430))
    contentHeight: fittedContentHeight(content.implicitHeight)

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      blocked: timeField.activeFocus
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }

      Column {
        id: content
        width: parent.width
        spacing: Style.space(10)

        Row {
          width: parent.width
          spacing: Style.space(10)
          Text {
            text: "Notifications"
            color: root.ink
            font.family: root.bar ? root.bar.fontFamily : Style.font.family
            font.pixelSize: Style.font.title
            font.bold: true
          }
          Text {
            text: root.overdueCount > 0 ? root.overdueCount + " due" : ""
            color: Color.urgent
            font.pixelSize: Style.font.body
          }
        }

        Row {
          spacing: Style.space(8)
          Repeater {
            model: ["Recent", "Saved"]
            delegate: Rectangle {
              required property string modelData
              width: label.implicitWidth + Style.space(24)
              height: Style.space(30)
              radius: Style.space(8)
              color: root.tab === modelData ? root.accent : "transparent"
              border.color: root.tab === modelData ? root.accent : root.muted
              Text { id: label; anchors.centerIn: parent; text: modelData; color: root.tab === modelData ? Palette.onAccent(root.accent) : root.ink }
              MouseArea { anchors.fill: parent; onClicked: { root.tab = modelData; root.selectedKey = ""; root.selectedSnapshot = null; root.preview = null } }
            }
          }
        }

        ScrollView {
          id: rowsScroll
          width: parent.width
          height: Math.min(Style.space(276), Math.max(Style.space(42), listColumn.implicitHeight))
          clip: true
          Column {
            id: listColumn
            width: rowsScroll.availableWidth
            spacing: Style.space(8)
            Repeater {
              model: root.tab === "Recent" ? root.recentRows : root.savedRows
              delegate: Rectangle {
                id: rowCard
                required property var modelData
                readonly property string rowKey: root.tab === "Recent" ? modelData.key : modelData.id
                width: listColumn.width
                height: Style.space(64)
                radius: Style.space(9)
                color: root.selectedKey === rowKey
                  ? Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.16)
                  : (rowMouse.containsMouse
                    ? Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.09)
                    : Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.045))
                border.width: root.selectedKey === rowKey ? 2 : 1
                border.color: root.selectedKey === rowKey
                  ? root.accent : Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.24)
                Behavior on color { ColorAnimation { duration: 120 } }
                Column {
                  anchors.fill: parent
                  anchors.margins: Style.space(10)
                  spacing: Style.space(4)
                  Text {
                    text: modelData.summary || "(No title)"
                    color: root.ink
                    font.family: root.bar ? root.bar.fontFamily : Style.font.family
                    font.pixelSize: Style.font.body
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                    width: parent.width
                    textFormat: Text.PlainText
                  }
                  Text {
                    text: (modelData.app || "Notification") + "  ·  " + Qt.formatDateTime(new Date(modelData.timestamp), "MMM d, h:mm AP")
                    color: root.muted
                    font.family: root.bar ? root.bar.fontFamily : Style.font.family
                    font.pixelSize: Style.font.bodySmall
                    elide: Text.ElideRight
                    width: parent.width
                    textFormat: Text.PlainText
                  }
                }
                MouseArea {
                  id: rowMouse
                  anchors.fill: parent
                  hoverEnabled: true
                  onClicked: { root.selectedKey = rowKey; root.selectedSnapshot = modelData; root.preview = null; root.message = "" }
                }
              }
            }
            Text {
              visible: (root.tab === "Recent" ? root.recentRows : root.savedRows).length === 0
              text: root.tab === "Recent" ? "No recent notifications" : "Nothing saved yet"
              color: root.muted
            }
          }
        }

        Rectangle {
          id: detailCard
          width: parent.width
          visible: root.selectedItem() !== null
          height: visible ? detailContent.implicitHeight + Style.space(24) : 0
          radius: Style.space(10)
          color: Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.035)
          border.width: 1
          border.color: Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.2)

          Column {
            id: detailContent
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: Style.space(12)
            spacing: Style.space(9)

            Item {
              width: parent.width
              height: Style.space(20)
              Text {
                text: "DETAILS"
                color: root.muted
                font.family: root.bar ? root.bar.fontFamily : Style.font.family
                font.pixelSize: Style.font.bodySmall
                font.bold: true
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
              }
              Text {
                id: detailClose
                text: "×"
                color: root.muted
                font.pixelSize: Style.font.title
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                MouseArea {
                  anchors.fill: parent
                  anchors.margins: -Style.space(6)
                  onClicked: { root.selectedKey = ""; root.selectedSnapshot = null; root.preview = null }
                }
              }
            }

            ScrollView {
              id: detailScroll
              width: parent.width
              height: Math.min(Style.space(148), Math.max(Style.space(36), detailText.implicitHeight))
              clip: true
              Column {
                id: detailText
                width: detailScroll.availableWidth
                spacing: Style.space(7)
                Text {
                  width: parent.width
                  text: root.selectedItem() ? root.selectedItem().summary || "(No title)" : ""
                  color: root.ink
                  font.family: root.bar ? root.bar.fontFamily : Style.font.family
                  font.pixelSize: Style.font.body
                  font.weight: Font.DemiBold
                  wrapMode: Text.Wrap
                  textFormat: Text.PlainText
                }
                Text {
                  width: parent.width
                  text: root.selectedItem() ? root.selectedItem().body || "No additional message" : ""
                  color: root.ink
                  font.family: root.bar ? root.bar.fontFamily : Style.font.family
                  font.pixelSize: Style.font.body
                  wrapMode: Text.Wrap
                  textFormat: Text.PlainText
                }
                Image {
                  visible: root.tab === "Saved" && root.selectedItem() && root.selectedItem().image !== ""
                  source: visible ? "file://" + root.selectedItem().image : ""
                  fillMode: Image.PreserveAspectFit
                  width: parent.width
                  height: visible ? Style.space(100) : 0
                  asynchronous: true
                }
              }
            }
            Text {
              visible: detailText.implicitHeight > detailScroll.height + 2
              text: "Scroll to read the full message"
              color: root.muted
              font.family: root.bar ? root.bar.fontFamily : Style.font.family
              font.pixelSize: Style.font.bodySmall
            }

            Row {
              spacing: Style.space(8)
              ActionButton {
                visible: root.tab === "Recent"
                text: "Save"
                primary: true
                ink: root.ink
                onClicked: if (root.selectedItem()) root.invoke("save", [JSON.stringify(root.selectedItem())])
              }
              ActionButton {
                visible: root.tab === "Saved"
                text: "Remove"
                ink: root.ink
                onClicked: if (root.selectedItem()) { root.invoke("remove", [root.selectedKey]); root.selectedKey = "" }
              }
              ActionButton {
                visible: root.tab === "Saved" && root.selectedItem() && root.selectedItem().reminder !== null
                text: "Done"
                ink: root.ink
                onClicked: if (root.selectedItem()) root.invoke("done", [root.selectedKey])
              }
            }
            Text {
              visible: root.tab === "Saved" && root.selectedItem() && root.selectedItem().reminder !== null
              width: parent.width
              text: root.selectedItem() && root.selectedItem().reminder ? "Due: " + Qt.formatDateTime(new Date(root.selectedItem().reminder.due * 1000), "dddd, MMMM d, yyyy h:mm AP") : ""
              color: Color.urgent
              wrapMode: Text.Wrap
            }
            Row {
              visible: root.tab === "Saved"
              spacing: Style.space(6)
              TextField {
                id: timeField
                width: Style.space(215)
                placeholderText: "2h30m or 4 PM"
                onTextChanged: root.preview = null
              }
              ActionButton {
                text: "Set reminder"
                ink: root.ink
                onClicked: {
                  if (!root.selectedItem() || previewProc.running) return
                  previewProc.command = ["python3", root.backend, "preview", timeField.text]
                  previewProc.running = true
                }
              }
            }
            Text { visible: !!root.preview; text: root.preview ? root.preview.label : ""; color: root.ink; wrapMode: Text.Wrap; width: parent.width }
            ActionButton {
              visible: !!root.preview && root.tab === "Saved"
              text: "Confirm reminder"
              primary: true
              ink: root.ink
              onClicked: {
                if (root.preview && root.selectedItem()) {
                  root.invoke("schedule", [root.selectedKey, String(root.preview.due)])
                  root.preview = null
                }
              }
            }
          }
        }

        Text { text: root.message; visible: root.message !== ""; color: root.muted; wrapMode: Text.Wrap; width: parent.width }
      }
    }
  }
}
