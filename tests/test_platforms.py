import string
import unittest

from diskstrata.catalog import knowledge
from diskstrata.catalog import linux as cat_linux
from diskstrata.catalog import macos as cat_macos
from diskstrata.catalog import windows as cat_windows
from diskstrata.platforms import linux, macos, windows

MOUNTS = r"""sysfs /sys sysfs rw,nosuid 0 0
/dev/nvme0n1p2 / ext4 rw,relatime 0 0
/dev/nvme0n1p2 /var/lib/docker/vol ext4 rw 0 0
/dev/sdb1 /media/me/My\040Drive vfat rw 0 0
//nas/share /mnt/nas cifs rw 0 0
tmpfs /run tmpfs rw 0 0
"""

MAC_MOUNT = """/dev/disk3s1s1 on / (apfs, sealed, local, read-only, journaled)
/dev/disk3s5 on /System/Volumes/Data (apfs, local, journaled, protect)
/dev/disk4s1 on /Volumes/My Backup (exfat, local, nodev, nosuid, noowners)
//user@nas/share on /Volumes/share (smbfs, nodev, nosuid, mounted by user)
map auto_home on /System/Volumes/Data/home (autofs, automounted, nobrowse)
"""


class ParserTests(unittest.TestCase):
    def test_linux_mounts(self):
        rows = linux.parse_mounts(MOUNTS)
        self.assertIn(("/dev/sdb1", "/media/me/My Drive", "vfat"), rows)   # octal escape decoded
        self.assertEqual(len(rows), 6)

    def test_macos_mount(self):
        rows = macos.parse_mount(MAC_MOUNT)
        self.assertIn(("/dev/disk4s1", "/Volumes/My Backup", "exfat"), rows)
        self.assertIn(("//user@nas/share", "/Volumes/share", "smbfs"), rows)
        self.assertEqual(len(rows), 5)


class CatalogTests(unittest.TestCase):
    """Every path template may only use variables its platform really provides."""

    def test_templates_use_known_variables(self):
        for catalog, adapter in [(cat_windows, windows), (cat_linux, linux), (cat_macos, macos)]:
            known = set(adapter.path_vars())
            templates = ([t for t, _ in catalog.AGENT_BASES] + [h[2] for h in catalog.HOTSPOTS]
                         + [s[1] for s in catalog.SYSTEM_ITEMS])
            for template in templates:
                used = {f for _, f, _, _ in string.Formatter().parse(template) if f}
                self.assertLessEqual(used, known, f"{catalog.__name__}: {template}")

    def test_stale_labels_exist_in_system_items(self):
        for catalog in (cat_windows, cat_linux, cat_macos):
            labels = {s[0] for s in catalog.SYSTEM_ITEMS}
            self.assertLessEqual(catalog.STALE, labels, catalog.__name__)

    def test_rows_are_well_formed(self):
        for catalog in (cat_windows, cat_linux, cat_macos):
            self.assertTrue(all(len(r) == 4 for r in catalog.HOTSPOTS))
            self.assertTrue(all(len(r) == 3 for r in catalog.SYSTEM_ITEMS))


class KnowledgeTests(unittest.TestCase):
    def test_describe_prefers_agent_specific_meaning(self):
        text, hint = knowledge.describe("claude", "projects", False)
        self.assertEqual(hint, "review")
        self.assertIn("transcripts", text)

    def test_describe_falls_back(self):
        self.assertEqual(knowledge.describe(None, "node_modules", False)[1], "safe")
        self.assertEqual(knowledge.describe(None, "whatever.log", True)[1], "safe")
        self.assertEqual(knowledge.describe(None, "mystery", False)[1], "unknown")

    def test_agent_patterns_do_not_shadow_each_other(self):
        def pick(name):
            return next(k for k, _, rx in knowledge.AGENTS if rx.search(name))
        self.assertEqual(pick("saoudrizwan.claude-dev-3.1"), "cline")
        self.assertEqual(pick(".claude"), "claude")
        self.assertEqual(pick("Ollama"), "ollama")


if __name__ == "__main__":
    unittest.main()
