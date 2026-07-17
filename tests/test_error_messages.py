"""Tests for clear, actionable user-facing failures."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from mediatovideo_converter.converter import converter_convert
from mediatovideo_converter.error_messages import error_messages_format_operation
from mediatovideo_converter.models import (
    ConversionOptions,
    MediaGroup,
    NamingMode,
    OutputLayout,
    VideoFormat,
)


class ErrorMessageTests(unittest.TestCase):
    """Require every important failure to explain the next action."""

    def test_missing_source_error_has_stable_sections(self) -> None:
        message = error_messages_format_operation(
            "Scanning source", FileNotFoundError("camera drive disconnected")
        )

        self.assertIn("Stage: Scanning source", message)
        self.assertIn("Problem:", message)
        self.assertIn("What to do:", message)
        self.assertIn("Technical detail: camera drive disconnected", message)
        self.assertIn("Reconnect", message)

    @unittest.skipIf(os.name == "nt", "POSIX fake executable smoke test")
    def test_ffmpeg_failure_explains_full_output_drive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tools = root / "tools"
            tools.mkdir()
            ffprobe = tools / "ffprobe"
            ffmpeg = tools / "ffmpeg"
            ffprobe.write_text("#!/bin/sh\nprintf '1.0\\n'\n", encoding="utf-8")
            ffmpeg.write_text(
                "#!/bin/sh\nprintf 'No space left on device\\n'\nexit 1\n",
                encoding="utf-8",
            )
            ffprobe.chmod(0o755)
            ffmpeg.chmod(0o755)
            clip = root / "2026" / "01" / "02" / "clip.media"
            clip.parent.mkdir(parents=True)
            clip.write_bytes(b"clip")
            group = MediaGroup(
                day_root=clip.parent,
                year="2026",
                month="01",
                day="02",
                category=None,
                files=(clip,),
            )
            options = ConversionOptions(
                output_root=root / "output",
                output_layout=OutputLayout.FLAT,
                video_format=VideoFormat.MKV_COPY,
                naming_mode=NamingMode.MONTH_DAY,
                ffmpeg_directory=tools,
            )

            summary = converter_convert((group,), options)

            self.assertEqual(len(summary.failed_groups), 1)
            failure = summary.failed_groups[0]
            self.assertIn("Stage: Creating output video", failure)
            self.assertIn("ran out of free space", failure)
            self.assertIn("What to do:", failure)
            self.assertIn("No space left on device", failure)


if __name__ == "__main__":
    unittest.main()
