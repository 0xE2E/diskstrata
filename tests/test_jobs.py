import os
import time
import unittest
from unittest import mock

from diskstrata import volumes
from diskstrata.analysis import apply_deltas
from diskstrata.jobs import home_volume_id
from diskstrata.scanner import path_key


class HomeVolumeTests(unittest.TestCase):
    def test_deepest_volume_that_holds_home_wins(self):
        vols = [{"id": "/", "root": "/"}, {"id": "/home", "root": "/home"},
                {"id": "/mnt/x", "root": "/mnt/x"}]
        self.assertEqual(home_volume_id(vols, "/home/me"), "/home")
        self.assertEqual(home_volume_id(vols, "/root"), "/")

    @unittest.skipUnless(os.name == "nt", "drive-letter paths are only meaningful on Windows")
    def test_windows_style_roots(self):
        vols = [{"id": "C:", "root": "C:\\"}, {"id": "D:", "root": "D:\\"}]
        self.assertEqual(home_volume_id(vols, "C:\\Users\\me"), "C:")
        self.assertIsNone(home_volume_id(vols, "E:\\Users\\me"))


class GrowthTests(unittest.TestCase):
    def test_growth_is_found_even_below_the_tree_threshold_last_time(self):
        tree = {"n": "/r", "s": 300, "c": [{"n": "grew", "s": 120}, {"n": "new", "s": 60}]}
        prev = {path_key("/r"): 250, path_key("/r/grew"): 49}   # was small last time, still known
        apply_deltas(tree, "/r", prev)
        grew, new = tree["c"]
        self.assertEqual((tree["d"], grew["d"], new["d"]), (50, 71, 60))
        self.assertNotIn("nw", grew)
        self.assertEqual(new["nw"], 1)                           # truly absent last time


class VolumeProbeTests(unittest.TestCase):
    def test_a_hung_probe_returns_the_previous_answer(self):
        with mock.patch.object(volumes.plat, "list_volumes", return_value=[{"id": "A"}]):
            self.assertEqual(volumes.list_volumes(timeout=2), [{"id": "A"}])

        def hang():
            time.sleep(1.5)
            return [{"id": "B"}]

        with mock.patch.object(volumes.plat, "list_volumes", side_effect=hang):
            t0 = time.monotonic()
            self.assertEqual(volumes.list_volumes(timeout=0.2), [{"id": "A"}])
            self.assertLess(time.monotonic() - t0, 1.0)


if __name__ == "__main__":
    unittest.main()
