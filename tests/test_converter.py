"""Tests for output naming and dependency discovery policies."""

from __future__ import annotations

import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

from mediatovideo_converter.converter import (
    FFmpegNotFoundError,
    converter_convert,
    converter_find_tools,
    converter_plan_targets,
)
from mediatovideo_converter.models import (
    ConversionOptions,
    MediaGroup,
    NamingMode,
    OutputLayout,
    VideoFormat,
)


class ConverterPlanningTests(unittest.TestCase):
    """Verify portable, deterministic output paths."""

    def test_mirrored_category_filename(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            group = self._group(root, "Front: Camera")
            options = ConversionOptions(
                output_root=root / "output",
                output_layout=OutputLayout.MIRROR_DATES,
                video_format=VideoFormat.MP4_H264,
                naming_mode=NamingMode.MONTH_DAY_CATEGORY,
            )

            targets = converter_plan_targets((group,), options)

            self.assertEqual(
                targets[0],
                root / "output" / "2026" / "07" / "17" / "07-17-Front- Camera.mp4",
            )

    def test_flat_duplicate_names_receive_numeric_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            groups = (self._group(root, "Front"), self._group(root, "Rear"))
            options = ConversionOptions(
                output_root=root / "output",
                output_layout=OutputLayout.FLAT,
                video_format=VideoFormat.MKV_COPY,
                naming_mode=NamingMode.MONTH_DAY,
            )

            targets = converter_plan_targets(groups, options)

            self.assertEqual(targets[0].name, "07-17.mkv")
            self.assertEqual(targets[1].name, "07-17-2.mkv")

    def test_custom_ffmpeg_folder_requires_both_tools(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            suffix = ".exe" if os.name == "nt" else ""
            (directory / f"ffmpeg{suffix}").touch()

            with self.assertRaises(FFmpegNotFoundError):
                converter_find_tools(directory)

            (directory / f"ffprobe{suffix}").touch()
            ffmpeg, ffprobe = converter_find_tools(directory)
            self.assertTrue(ffmpeg.endswith(f"ffmpeg{suffix}"))
            self.assertTrue(ffprobe.endswith(f"ffprobe{suffix}"))

    @unittest.skipIf(os.name == "nt", "POSIX fake executable smoke test")
    def test_conversion_pipeline_publishes_completed_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tools = root / "tools"
            tools.mkdir()
            self._write_fake_tool(
                tools / "ffprobe",
                "import sys\nprint('1.0')\n",
            )
            self._write_fake_tool(
                tools / "ffmpeg",
                "import pathlib, sys\n"
                "pathlib.Path(sys.argv[-1]).write_bytes(b'converted')\n"
                "print('out_time_us=1000000', flush=True)\n"
                "print('progress=end', flush=True)\n",
            )
            group = self._group(root, "Front")
            group.files[0].parent.mkdir(parents=True)
            group.files[0].write_bytes(b"clip")
            options = ConversionOptions(
                output_root=root / "output",
                output_layout=OutputLayout.FLAT,
                video_format=VideoFormat.MKV_COPY,
                naming_mode=NamingMode.MONTH_DAY_CATEGORY,
                ffmpeg_directory=tools,
            )
            events: list[str] = []

            summary = converter_convert(
                (group,), options, event=lambda name, _details: events.append(name)
            )

            self.assertFalse(summary.cancelled)
            self.assertFalse(summary.failed_groups)
            self.assertEqual(len(summary.completed), 1)
            self.assertEqual(summary.completed[0].read_bytes(), b"converted")
            self.assertIn("encoding_progress", events)
            self.assertIn("group_completed", events)

    @staticmethod
    def _group(root: Path, category: str) -> MediaGroup:
        """Build a representative one-clip group."""

        clip = root / "2026" / "07" / "17" / category / "001.media"
        return MediaGroup(
            day_root=root / "2026" / "07" / "17",
            year="2026",
            month="07",
            day="17",
            category=category,
            files=(clip,),
        )

    @staticmethod
    def _write_fake_tool(path: Path, body: str) -> None:
        """Write an executable Python command used as a deterministic test tool."""

        path.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)


if __name__ == "__main__":
    unittest.main()
