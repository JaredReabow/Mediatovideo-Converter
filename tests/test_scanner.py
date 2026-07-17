"""Tests for date discovery and grouping behavior."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mediatovideo_converter.models import GroupingMode
from mediatovideo_converter.scanner import scanner_scan


class ScannerTests(unittest.TestCase):
    """Exercise the folder structures supported by the GUI."""

    def test_day_grouping_from_dcim_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "DCIM"
            first_day = root / "2026" / "07" / "16"
            second_day = root / "2026" / "07" / "17"
            self._touch_media(first_day / "Camera A" / "002.media")
            self._touch_media(first_day / "Camera A" / "001.MEDIA")
            self._touch_media(second_day / "Camera B" / "001.media")
            (second_day / "ignore.txt").parent.mkdir(parents=True, exist_ok=True)
            (second_day / "ignore.txt").write_text("ignored", encoding="utf-8")

            result = scanner_scan(root, GroupingMode.DAY)

            self.assertEqual(result.media_file_count, 3)
            self.assertEqual(result.day_count, 2)
            self.assertEqual(len(result.groups), 2)
            self.assertEqual(result.groups[0].files[0].name, "001.MEDIA")
            self.assertEqual(result.groups[1].day, "17")

    def test_child_folder_grouping_in_selected_day(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            day = Path(temporary) / "2026" / "7" / "17"
            self._touch_media(day / "Front" / "001.media")
            self._touch_media(day / "Rear" / "001.media")
            self._touch_media(day / "loose.media")

            result = scanner_scan(day, GroupingMode.CHILD_FOLDER)

            self.assertEqual(result.day_count, 1)
            self.assertEqual([group.category for group in result.groups], [
                "Day root",
                "Front",
                "Rear",
            ])
            self.assertTrue(all(group.month == "07" for group in result.groups))

    def test_non_date_layout_falls_back_to_selected_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "Camera export"
            self._touch_media(root / "Event 1" / "clip.media")

            result = scanner_scan(root, GroupingMode.CHILD_FOLDER)

            self.assertEqual(result.unrecognised_date_files, 1)
            self.assertEqual(result.groups[0].category, "Event 1")
            self.assertIsNone(result.groups[0].year)

    @staticmethod
    def _touch_media(path: Path) -> None:
        """Create a tiny placeholder clip at ``path``."""

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"test")


if __name__ == "__main__":
    unittest.main()
