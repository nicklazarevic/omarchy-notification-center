"""Focused storage, adapter, and local-time checks with synthetic records."""
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
from zoneinfo import ZoneInfo

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
spec = importlib.util.spec_from_file_location("notification_backend", Path(__file__).with_name("backend.py"))
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        backend.ROOT = Path(self.tmp.name) / "saved"
        backend.ITEMS = backend.ROOT / "items"
        backend.NOTIFICATIONS = Path(self.tmp.name) / "omarchy/notifications"
        backend.IMAGE_ROOT = backend.NOTIFICATIONS / "images"
        backend.ensure_root()
        (backend.NOTIFICATIONS / "history").mkdir(parents=True)
        backend.IMAGE_ROOT.mkdir()

    def make_row(self, timestamp, identifier=1, directory=None, image=""):
        row = {"timestamp": timestamp, "originalId": identifier, "app": "Test",
               "summary": f"message {timestamp}", "body": "full body", "image": image}
        name = f"{timestamp}-{identifier}.json"
        path = (directory or backend.NOTIFICATIONS / "history") / name
        path.write_text(json.dumps(row))
        return row

    def test_recent_dedupe_cap_and_corrupt(self):
        for i in range(12):
            self.make_row(1700000000000 + i)
        self.make_row(1700000000011, directory=backend.NOTIFICATIONS)
        (backend.NOTIFICATIONS / "history" / "bad.json").write_text("{")
        rows = backend.recent()
        self.assertEqual(len(rows), 10)
        self.assertEqual(rows[0]["key"], "1700000000011-1")
        self.assertEqual(len(set(row["key"] for row in rows)), 10)

    def test_stock_omarchy_serialization(self):
        source = Path("/usr/share/omarchy/shell/plugins/notifications/NotificationLogic.js")
        if not source.exists() or not shutil.which("node"):
            self.skipTest("stock Omarchy source or Node unavailable")
        script = ("const n=require(process.argv[1]); console.log(n.serializePopup("
                  "{id:7,originalId:7,timestamp:1700000000000,app:'Stock test',summary:'hello'},1))")
        raw = subprocess.check_output(["node", "-e", script, str(source)], text=True)
        (backend.NOTIFICATIONS / "history" / "1700000000000-7.json").write_text(raw)
        self.assertEqual(backend.recent()[0]["summary"], "hello")

    def test_only_owned_due_alert_is_filtered(self):
        other = self.make_row(1700000000000)
        other.update(app="Nickomarchy Saved Reminder", summary="Different alert")
        (backend.NOTIFICATIONS / "history" / "1700000000000-1.json").write_text(json.dumps(other))
        owned = self.make_row(1700000000001)
        owned.update(app="Nickomarchy Saved Reminder", summary="Saved reminder due",
                     execArgv=json.dumps(["omarchy-shell", backend.PLUGIN, "openSaved", "a" * 32]))
        (backend.NOTIFICATIONS / "history" / "1700000000001-1.json").write_text(json.dumps(owned))
        legacy = self.make_row(1700000000002)
        legacy.update(app="Nickomarchy Saved Reminder", summary="Saved reminder due",
                      execArgv=json.dumps(["omarchy-shell", "shell", "call", backend.PLUGIN, "openSaved", "b" * 32]))
        (backend.NOTIFICATIONS / "history" / "1700000000002-1.json").write_text(json.dumps(legacy))
        self.assertEqual([row["key"] for row in backend.recent()], ["1700000000000-1"])

    def test_save_survives_recent_expiry_and_image_cleanup(self):
        image = backend.IMAGE_ROOT / "1700000000000-1-image"
        image.write_bytes(b"image")
        row = self.make_row(1700000000000, image=str(image))
        snapshot = backend.recent()[0]
        (backend.NOTIFICATIONS / "history" / "1700000000000-1.json").unlink()
        saved = backend.save(json.dumps(snapshot))
        image.unlink()
        self.assertEqual(Path(saved["image"]).read_bytes(), b"image")
        self.assertEqual(saved["body"], "full body")
        self.assertEqual(len(backend.saved()), 1)
        self.assertEqual(backend.ITEMS.stat().st_mode & 0o777, 0o700)
        self.assertEqual(backend.item_path(saved["id"]).stat().st_mode & 0o777, 0o600)

    def test_reject_symlink_and_fifo_image(self):
        outside = Path(self.tmp.name) / "outside"
        outside.write_bytes(b"secret")
        symlink = backend.IMAGE_ROOT / "linked"
        symlink.symlink_to(outside)
        self.assertEqual(backend.copy_image(str(symlink), "a" * 32, "image"), "")
        fifo = backend.IMAGE_ROOT / "pipe"
        os.mkfifo(fifo)
        self.assertEqual(backend.copy_image(str(fifo), "b" * 32, "image"), "")
        self.assertEqual(backend.copy_image(str(outside), "c" * 32, "image"), "")

    def test_reminder_reschedule_done_and_remove(self):
        self.make_row(1700000000000)
        item = backend.save(json.dumps(backend.recent()[0]))
        identifier = item["id"]
        backend.mutate(identifier, "schedule", 1)
        path = backend.item_path(identifier)
        original = path.read_bytes()
        self.assertEqual(backend.tick()["overdue"], 1)
        self.assertEqual(backend.tick()["due"][0]["id"], identifier)
        self.assertEqual(path.read_bytes(), original)  # polling cannot consume history or mutate reminder
        prior = backend.saved()[0]
        prior["reminder"]["lastAlert"] = 9999999999  # v0.1.0 record still stays due
        backend.atomic_json(path, prior)
        self.assertEqual(backend.tick()["overdue"], 1)
        backend.mutate(identifier, "schedule", 4102444800)
        self.assertEqual(backend.tick()["overdue"], 0)
        backend.mutate(identifier, "done")
        self.assertIsNone(backend.saved()[0]["reminder"])
        backend.mutate(identifier, "remove")
        self.assertEqual(backend.saved(), [])

    def test_dst_gap_fold_and_past_clock(self):
        eastern = ZoneInfo("America/New_York")
        spring = dt.datetime(2026, 3, 8, 1, 55, tzinfo=eastern)
        with mock.patch.dict(os.environ, {"TZ": "America/New_York"}):
            gap = backend.parse_due("2:30 AM", spring)
            self.assertEqual(gap.date(), dt.date(2026, 3, 9))
            fold = backend.parse_due("1:30 AM", dt.datetime(2026, 11, 1, 1, 45, tzinfo=eastern, fold=0))
            self.assertEqual(fold.fold, 1)
            past = backend.parse_due("4 PM", dt.datetime(2026, 10, 6, 17, 0, tzinfo=eastern))
            self.assertEqual(past.date(), dt.date(2026, 10, 7))
            self.assertEqual(int(backend.parse_due("2h30m", spring).timestamp() - spring.timestamp()), 9000)
            self.assertEqual(backend.parse_due("2h30m", spring).strftime("%H:%M %Z"), "05:25 EDT")


if __name__ == "__main__":
    unittest.main()
