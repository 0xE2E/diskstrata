import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from diskstrata import storage
from diskstrata.storage import Store, embed_json, slug


def sample(volume="C:"):
    return {"meta": {"generated": "2026-01-02 03:04"},
            "volumes": [{"id": volume, "name": "Disk", "root": volume + "\\"}]}


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name))

    def test_slug(self):
        self.assertEqual(slug("C:"), "C")
        self.assertEqual(slug("/"), "root")
        self.assertEqual(slug("/Volumes/My Backup"), "Volumes_My_Backup")

    def test_embed_json_cannot_close_the_script_tag(self):
        html = embed_json("<script>__DS_DATA__</script>", {"p": "</script><!-- <script>"})
        self.assertEqual(html.count("<"), 2)            # only the template's own tags
        payload = re.search(r"<script>(.*)</script>", html).group(1)
        self.assertEqual(json.loads(payload)["p"], "</script><!-- <script>")

    def test_report_history_roundtrip(self):
        self.store.save_report("20260102_030405", sample())
        self.store.save_report("20260102_030406", sample("D:"))
        history = self.store.history()
        self.assertEqual([h["id"] for h in history], ["20260102_030406", "20260102_030405"])
        self.assertGreater(history[0]["size"], 0)
        self.assertEqual(history[0]["volumes"][0]["id"], "D:")
        self.assertTrue(self.store.read_report("20260102_030405"))

    def test_report_ids_are_validated(self):
        self.assertIsNone(self.store.read_report("../../etc/passwd"))
        self.assertIsNone(self.store.read_report("20260102_030405"))   # does not exist

    def test_half_written_scans_are_not_listed(self):
        (self.store.root / "scan_20260102_030405.html").write_text("x")   # no history entry yet
        (self.store.root / "scan_20260102_030406.json").write_text("{bad json")
        self.assertEqual(self.store.history(), [])

    def test_latest_snapshot_picks_newest_for_the_same_volume_only(self):
        self.store.save_snapshot("C:", "20260101_000000", {"C:\\": 1})
        self.store.save_snapshot("C:", "20260102_000000", {"C:\\": 2})
        self.store.save_snapshot("/home", "20260103_000000", {"/home": 9})
        self.assertEqual(self.store.latest_snapshot("C:"), ("20260102_000000", {"C:\\": 2}))
        self.assertEqual(self.store.latest_snapshot("/home")[1], {"/home": 9})
        self.assertEqual(self.store.latest_snapshot("E:"), (None, {}))

    def test_scan_ids_are_utc_and_never_reused(self):
        first = self.store.new_scan_id()
        self.assertRegex(first, r"^\d{8}_\d{6}$")
        self.store.save_report(first, sample())
        self.assertGreater(self.store.new_scan_id(), first)     # same second: moves on

    def test_report_id_must_match_exactly(self):
        self.store.save_report("20260102_030405", sample())
        self.assertIsNone(self.store.read_report("20260102_030405\n"))

    @unittest.skipIf(os.name == "nt", "POSIX permissions")
    def test_files_are_private_to_the_user(self):
        data = Path(self.tmp.name) / "fresh" / "data"
        Store(data).save_report("20260102_030405", sample())
        self.assertEqual(data.stat().st_mode & 0o077, 0)
        self.assertEqual((data / "scan_20260102_030405.html").stat().st_mode & 0o077, 0)

    def test_atomic_write_leaves_no_temp_file(self):
        target = self.store.root / "x.json"
        storage.atomic_write(target, "1")
        storage.atomic_write(target, "2")
        self.assertEqual(target.read_text(), "2")
        self.assertEqual([p.name for p in self.store.root.iterdir()], ["x.json"])


if __name__ == "__main__":
    unittest.main()
