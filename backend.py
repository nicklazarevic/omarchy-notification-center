#!/usr/bin/env python3
"""Private state and read-only Omarchy notification file adapter.

The shell's on-disk notification format is internal. Treat every field as
untrusted, skip malformed entries, and never write to the shell's directories.
"""
import argparse
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile
import uuid
from urllib.parse import unquote, urlparse

PLUGIN = "laza11.notification-center"
STATE = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
ROOT = STATE / PLUGIN
ITEMS = ROOT / "items"
NOTIFICATIONS = STATE / "omarchy/notifications"
IMAGE_ROOT = NOTIFICATIONS / "images"
MAX_JSON = 128 * 1024
MAX_IMAGE = 8 * 1024 * 1024
MAX_TEXT = 32 * 1024
ID = re.compile(r"^[0-9a-f]{32}$")
FILENAME = re.compile(r"^(\d{10,17})-(\d+)\.json$")
RELATIVE = re.compile(r"(?i)^\s*(?:(\d+)h)?\s*(?:(\d+)m)?\s*$")
CLOCK = re.compile(r"(?i)^\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)\s*$")


def plain(value):
    return str(value if isinstance(value, (str, int, float)) else "")[:MAX_TEXT]


def read_json(path):
    try:
        if path.is_symlink() or path.stat().st_size > MAX_JSON:
            return None
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError, UnicodeError):
        return None


def own_due_alert(value):
    if value.get("app") != "Nickomarchy Saved Reminder" or value.get("summary") != "Saved reminder due":
        return False
    try:
        argv = json.loads(value.get("execArgv", ""))
    except (TypeError, ValueError):
        return False
    if not isinstance(argv, list):
        return False
    current = len(argv) == 4 and argv[:3] == ["omarchy-shell", PLUGIN, "openSaved"]
    legacy = len(argv) == 6 and argv[:5] == ["omarchy-shell", "shell", "call", PLUGIN, "openSaved"]
    return (current or legacy) and isinstance(argv[-1], str) and ID.fullmatch(argv[-1]) is not None


def recent():
    rows = {}
    # Same filename can briefly be present on both sides of an archive move.
    for directory in (NOTIFICATIONS / "history", NOTIFICATIONS):
        try:
            paths = list(directory.glob("*.json"))
        except OSError:
            continue
        for path in paths:
            match = FILENAME.fullmatch(path.name)
            if not match:
                continue
            value = read_json(path)
            if not isinstance(value, dict):
                continue
            try:
                timestamp = int(value.get("timestamp"))
                original_id = int(value.get("originalId", value.get("id")))
            except (ValueError, TypeError):
                continue
            if timestamp != int(match.group(1)) or original_id != int(match.group(2)):
                continue
            if timestamp <= 0 or original_id <= 0:
                continue
            # Linked due alerts are ours; they belong in Saved, never Recent.
            if own_due_alert(value):
                continue
            key = path.name[:-5]
            rows[key] = {
                "key": key, "app": plain(value.get("app")),
                "summary": plain(value.get("summary")),
                "body": plain(value.get("body")),
                "timestamp": timestamp,
                "image": plain(value.get("image")),
                "appIcon": plain(value.get("appIcon")),
                # Never expose a sender-supplied execArgv to the panel.
            }
    return sorted(rows.values(), key=lambda row: (-row["timestamp"], row["key"]))[:10]


def ensure_root():
    for path in (ROOT, ITEMS):
        if path.is_symlink():
            raise ValueError("state directory is a symlink")
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(path, 0o700)


def item_path(identifier):
    if not ID.fullmatch(identifier or ""):
        raise ValueError("invalid item ID")
    return ITEMS / (identifier + ".json")


def atomic_json(path, value):
    fd, temp = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def saved():
    result = []
    if not ITEMS.is_dir():
        return result
    for path in ITEMS.glob("*.json"):
        if not ID.fullmatch(path.stem):
            continue
        item = read_json(path)
        if isinstance(item, dict) and item.get("version") == 1 and item.get("id") == path.stem:
            result.append(item)
    return sorted(result, key=lambda item: item.get("savedAt", 0), reverse=True)


def copy_image(value, item_id, role):
    if not isinstance(value, str):
        return ""
    if value.startswith("file://"):
        parsed = urlparse(value)
        if parsed.netloc not in ("", "localhost"):
            return ""
        value = unquote(parsed.path)
    source = Path(value)
    # Only files copied by the Omarchy service into its own image directory.
    if source.parent != IMAGE_ROOT or not source.name or "/" in source.name:
        return ""
    if any(path.is_symlink() for path in (STATE, STATE / "omarchy", NOTIFICATIONS, IMAGE_ROOT)):
        return ""
    target = ITEMS / (item_id + "-" + role)
    try:
        fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            metadata = os.fstat(fd)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_IMAGE:
                return ""
            target = ITEMS / (item_id + "-" + role)
            out = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            try:
                remaining = MAX_IMAGE + 1
                while remaining:
                    block = os.read(fd, min(65536, remaining))
                    if not block:
                        break
                    os.write(out, block)
                    remaining -= len(block)
                if remaining == 0:
                    raise ValueError("image too large")
                os.fsync(out)
            finally:
                os.close(out)
            return str(target)
        finally:
            os.close(fd)
    except (OSError, ValueError):
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        return ""


def save(raw):
    # The panel passes its selected in-memory snapshot. A toast may expire or
    # fall beyond Recent's cap before Save is clicked.
    if len(raw) > MAX_JSON:
        raise ValueError("notification snapshot too large")
    row = json.loads(raw)
    if not isinstance(row, dict) or not re.fullmatch(r"\d{10,17}-\d+", str(row.get("key", ""))):
        raise ValueError("invalid notification snapshot")
    if int(row.get("timestamp", 0)) != int(row["key"].split("-")[0]):
        raise ValueError("notification timestamp mismatch")
    identifier = uuid.uuid4().hex
    record = {
        "version": 1, "id": identifier, "savedAt": int(dt.datetime.now().timestamp() * 1000),
        "sourceKey": row["key"], "app": plain(row.get("app")),
        "summary": plain(row.get("summary")), "body": plain(row.get("body")),
        "timestamp": int(row["timestamp"]), "image": "", "appIcon": "",
        "reminder": None,
        # No arbitrary third-party command is promoted into a durable action.
        "openTarget": None,
    }
    for role in ("image", "appIcon"):
        record[role] = copy_image(row.get(role), identifier, role)
    atomic_json(item_path(identifier), record)
    return record


def parse_due(spec, now=None):
    now = now or dt.datetime.now().astimezone()
    from zoneinfo import ZoneInfo
    try:
        zone = ZoneInfo(os.environ.get("TZ") or Path("/etc/localtime").resolve().relative_to("/usr/share/zoneinfo").as_posix())
    except (ValueError, OSError, KeyError):
        zone = now.tzinfo
    relative = RELATIVE.fullmatch(spec)
    if relative and (relative.group(1) or relative.group(2)):
        minutes = int(relative.group(1) or 0) * 60 + int(relative.group(2) or 0)
        if not 1 <= minutes <= 525600:
            raise ValueError("duration must be between 1 minute and 1 year")
        return (now.astimezone(dt.timezone.utc) + dt.timedelta(minutes=minutes)).astimezone(zone)
    clock = CLOCK.fullmatch(spec)
    if clock:
        hour, minute = int(clock.group(1)), int(clock.group(2) or 0)
        if hour not in range(1, 13) or minute not in range(60):
            raise ValueError("invalid clock time")
        hour = hour % 12 + (12 if clock.group(3).lower() == "pm" else 0)
        # Resolve local wall clock with system timezone, including DST folds.
        day = now.astimezone(zone).date()
        candidates = []
        for offset in range(0, 3):
            date = day + dt.timedelta(days=offset)
            for fold in (0, 1):
                candidate = dt.datetime(date.year, date.month, date.day, hour, minute, tzinfo=zone, fold=fold)
                instant = candidate.astimezone(dt.timezone.utc)
                if instant.astimezone(zone).replace(tzinfo=None) == candidate.replace(tzinfo=None) and instant > now.astimezone(dt.timezone.utc):
                    candidates.append(instant)
            if candidates:
                return min(candidates).astimezone(zone)
        raise ValueError("no valid future occurrence")
    raise ValueError("use a duration like 2h30m or a clock time like 4 PM")


def format_due(due):
    return due.strftime("%A, %B %-d, %Y at %-I:%M %p %Z (UTC%z)")


def mutate(identifier, operation, due=None):
    path = item_path(identifier)
    item = read_json(path)
    if not isinstance(item, dict) or item.get("id") != identifier or item.get("version") != 1:
        raise ValueError("saved item not found")
    if operation == "remove":
        path.unlink()
        for role in ("image", "appIcon"):
            (ITEMS / (identifier + "-" + role)).unlink(missing_ok=True)
        return {"removed": identifier}
    if operation == "done":
        item["reminder"] = None
    elif operation == "schedule":
        if due is None:
            raise ValueError("missing due time")
        item["reminder"] = {"due": due}
    atomic_json(path, item)
    return item


def tick():
    now = int(dt.datetime.now(dt.timezone.utc).timestamp())
    due = []
    for item in saved():
        reminder = item.get("reminder")
        if not isinstance(reminder, dict):
            continue
        if not isinstance(reminder.get("due"), int) or reminder["due"] > now:
            continue
        due.append({"id": item["id"], "due": reminder["due"]})
    due.sort(key=lambda item: (item["due"], item["id"]))
    return {"overdue": len(due), "due": due}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("snapshot", "save", "remove", "preview", "schedule", "done", "tick", "exists"))
    parser.add_argument("args", nargs="*")
    args = parser.parse_args()
    ensure_root()
    with (ROOT / ".lock").open("a+b") as lock:
        os.chmod(ROOT / ".lock", 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.command == "snapshot":
            result = {"recent": recent(), "saved": saved()}
        elif args.command == "tick":
            result = tick()
        elif args.command == "save":
            result = save(args.args[0])
        elif args.command == "preview":
            due = parse_due(args.args[0])
            result = {"due": int(due.timestamp()), "label": format_due(due)}
        elif args.command == "schedule":
            result = mutate(args.args[0], "schedule", int(args.args[1]))
        elif args.command in ("remove", "done"):
            result = mutate(args.args[0], args.command)
        elif args.command == "exists":
            result = {"exists": item_path(args.args[0]).is_file()}
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, IndexError) as error:
        print(json.dumps({"ok": False, "error": str(error)}))
        sys.exit(1)
