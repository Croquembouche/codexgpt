import tempfile
import time
import unittest
from pathlib import Path

from codexgpt_bridge.downloads import collect_new_downloads, snapshot_downloads
from codexgpt_bridge.safari import build_click_downloads_javascript


class DownloadCaptureTests(unittest.TestCase):
    def test_collect_new_downloads_copies_only_files_missing_from_snapshot(self):
        with tempfile.TemporaryDirectory() as src_tmp, tempfile.TemporaryDirectory() as dst_tmp:
            source = Path(src_tmp)
            destination = Path(dst_tmp)
            existing = source / "old.pdf"
            existing.write_text("old", encoding="utf-8")
            before = snapshot_downloads(source)
            time.sleep(0.01)
            created = source / "new.pdf"
            created.write_text("new", encoding="utf-8")

            copied = collect_new_downloads(before, destination, downloads_dir=source, wait_sec=0)

            self.assertEqual(len(copied), 1)
            self.assertEqual(Path(copied[0]).name, "new.pdf")
            self.assertEqual((destination / "new.pdf").read_text(encoding="utf-8"), "new")
            self.assertFalse((destination / "old.pdf").exists())

    def test_click_downloads_javascript_includes_links_and_buttons(self):
        script = build_click_downloads_javascript()

        self.assertIn("a[download]", script)
        self.assertIn('aria-label*="Download"', script)
        self.assertIn("backend-api/estuary", script)
        self.assertIn("document.createElement('a')", script)
        self.assertIn("clicked", script)


if __name__ == "__main__":
    unittest.main()
