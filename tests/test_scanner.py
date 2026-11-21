import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from diskstrata import scanner
from diskstrata.scanner import ScanCancelled, Stats, scan_volume

MB = 1024 * 1024


def make_tree(root: Path) -> None:
    (root / "a" / "b").mkdir(parents=True)
    (root / "empty").mkdir()
    (root / "a" / "one.bin").write_bytes(b"x" * MB)
    (root / "a" / "b" / "two.bin").write_bytes(b"y" * 2 * MB)
    (root / "a" / "b" / "pyvenv.cfg").write_text("home = x")


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        make_tree(self.root)
        patcher = mock.patch.multiple(scanner, TREE_MIN=MB, DIR_SIZE_MIN=MB)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_sizes_and_counts(self):
        stats = Stats()
        res = scan_volume(str(self.root), stats)
        self.assertEqual(res.files, 3)
        # allocated size may round up to the filesystem block size on Linux/macOS
        self.assertGreaterEqual(res.size, 3 * MB)
        self.assertLess(res.size, 3 * MB + 64 * 1024)
        self.assertEqual(stats.dirs_scanned, 4)
        self.assertEqual(stats.denied, [])

    def test_tree_shape_and_markers(self):
        stats = Stats()
        node = scan_volume(str(self.root), stats).node
        kids = {c["n"]: c for c in node["c"]}
        self.assertEqual(list(kids), ["a"])             # "empty" is under the tree threshold
        self.assertEqual(kids["a"]["c"][0]["n"], "b")
        self.assertEqual(kids["a"]["c"][0]["k"], "venv")  # pyvenv.cfg marks a virtual env

    def test_dir_sizes_use_normalised_keys(self):
        stats = Stats()
        scan_volume(str(self.root), stats)
        self.assertIn(scanner.path_key(str(self.root / "a" / "b")), stats.dir_sizes)

    def test_cancel(self):
        stats = Stats()
        stats.cancel.set()
        with self.assertRaises(ScanCancelled):
            scan_volume(str(self.root), stats)

    def test_symlinked_folder_is_not_followed(self):
        link = self.root / "link"
        try:
            os.symlink(self.root / "a", link, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not permitted")
        res = scan_volume(str(self.root), Stats())
        self.assertEqual(res.files, 4)                  # the link itself counts as one entry
        self.assertLess(res.size, 3 * MB + 128 * 1024)  # its 3 MB target is not counted twice

    @unittest.skipIf(os.name == "nt", "Windows scandir does not report inode numbers")
    def test_hard_links_are_counted_once(self):
        os.link(self.root / "a" / "one.bin", self.root / "a" / "b" / "alias.bin")
        res = scan_volume(str(self.root), Stats())
        self.assertEqual(res.files, 4)
        self.assertLess(res.size, 3 * MB + 64 * 1024)

    @unittest.skipIf(os.name == "nt", "Windows uses reparse points, not a prune list")
    def test_pruned_locations_are_not_entered(self):
        pruned = frozenset({os.path.join(str(self.root), "a")})
        with mock.patch.object(scanner.plat, "prune_paths", return_value=pruned):
            res = scan_volume(str(self.root), Stats())
        self.assertEqual(res.files, 0)

    @unittest.skipUnless(os.name == "nt", "260-character limit is a Windows thing")
    def test_paths_longer_than_260_characters_are_read(self):
        deep = "\\\\?\\" + str(self.root / "long")
        os.mkdir(deep)
        for _ in range(12):                     # makedirs cannot split an extended-length prefix
            deep += "\\" + "n" * 30
            os.mkdir(deep)
        Path(deep, "f.bin").write_bytes(b"1")
        stats = Stats()
        res = scan_volume(str(self.root), stats)
        self.assertEqual(res.files, 4)
        self.assertEqual(stats.denied, [])

    def test_deep_trees_are_scanned_inside_worker_threads(self):
        deep = self.root / "deep"
        deep.mkdir()
        path = deep
        for _ in range(40):
            path = path / "d"
            path.mkdir()
        (path / "leaf.bin").write_bytes(b"1")
        res = scan_volume(str(self.root), Stats())
        self.assertEqual(res.files, 4)

    def test_unreadable_folder_is_reported(self):
        stats = Stats()
        with mock.patch("os.scandir", side_effect=[PermissionError()]):
            scan_volume(str(self.root), stats)
        self.assertEqual(len(stats.denied), 1)


if __name__ == "__main__":
    unittest.main()
