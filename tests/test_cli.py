import tempfile
import unittest
from pathlib import Path

from diskstrata.cli import _read_secret


class SecretHandOffTests(unittest.TestCase):
    def test_secret_is_read_once_and_the_file_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "elevate.secret"
            path.write_text("s3cret\n")
            self.assertEqual(_read_secret(path), "s3cret")
            self.assertFalse(path.exists())

    def test_missing_or_empty_secret_means_start_a_new_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(_read_secret(Path(tmp) / "nope"))
            empty = Path(tmp) / "empty"
            empty.write_text("")
            self.assertIsNone(_read_secret(empty))
        self.assertIsNone(_read_secret(None))


if __name__ == "__main__":
    unittest.main()
