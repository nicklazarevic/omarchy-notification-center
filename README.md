# Notification Center for Omarchy

A bell for Recent notifications, private Saved copies, and reminders attached to a saved item. The bell is a separate bar widget. It does not replace Omarchy's notification service or the existing quick reminder control.

## Install

Requires Omarchy Quattro with the notification persistence format used by the stock `omarchy.notifications` service and Python 3. The widget reads the stock service's files under `~/.local/state/omarchy/notifications/`; this is an internal format, so compatibility must be checked after Omarchy upgrades. No network access is used by the plugin.

After reviewing the code, install the repository with `omarchy plugin add https://github.com/nicklazarevic/omarchy-notification-center.git --enable`. Place `laza11.notification-center` at the end of `bar.layout.right` in `~/.config/omarchy/shell.json` to put it after Power. The plugin ID is permanent; renaming it would create a separate state owner.

## Use

- Click the bell to open the panel. Click a Recent card to read its full message in a bounded, scrollable details area, then **Save** to keep a private copy.
- In Saved, enter `2h30m` or a local clock time such as `4 PM`. Read the full local date, time, zone and UTC offset shown by **Set reminder**, then click **Confirm reminder**. A new time replaces the item's pending reminder.
- **Done** clears the pending reminder. **Remove** deletes the saved record and its copied image.
- Overdue items keep an urgent bell and badge until marked Done or removed. Click the due bell to open the exact saved item. The plugin does not send a notification popup, so it does not consume Omarchy's ten history slots. Do Not Disturb does not hide the badge. If the shell was off or asleep, the next active check catches up.

Recent shows at most ten rows, including a visible popup. It does not extend Omarchy's history retention. Saved is independent of that cap. Sender supplied commands are never kept or executed by Saved, so an **Open** control is shown only if a future version establishes a safe durable target. The row click itself only expands text.

## Private data and removal

To remove the widget, run `omarchy plugin remove laza11.notification-center`. If its ID remains in `bar.layout.right` in `~/.config/omarchy/shell.json`, remove that layout entry too. Saved records and image copies live under `~/.local/state/laza11.notification-center/items/`, with directory mode `0700` and file mode `0600`. No notification text or images belong in this public repository. Disabling, removing, or reinstalling the plugin leaves Saved data in place. To delete it permanently, remove that state directory separately after making any desired backup.

The plugin runs `backend.py` as a short lived Python process to read Recent and manage its own state. It filters older due alerts emitted by version 0.1.0 out of Recent. It does not impersonate Omarchy's privileged `omarchy-action` notification identity.

## Development

Run `omarchy plugin validate .` and `PYTHONDONTWRITEBYTECODE=1 python3 test_backend.py`. `preview.png` is a synthetic illustration and contains no real notifications; its source is `assets/preview.svg`.

License: MIT. See `LICENSE`.
