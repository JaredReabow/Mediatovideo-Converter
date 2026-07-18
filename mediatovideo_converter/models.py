"""Shared immutable data models for scanning and conversion."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class GroupingMode(str, Enum):
    """Ways source clips can be combined."""

    DAY = "day"
    CHILD_FOLDER = "child_folder"


class OutputLayout(str, Enum):
    """Ways completed videos can be arranged."""

    MIRROR_DATES = "mirror_dates"
    FLAT = "flat"


class VideoFormat(str, Enum):
    """Supported output containers and encoding policies."""

    MKV_COPY = "mkv_copy"
    MP4_H264 = "mp4_h264"


class NamingMode(str, Enum):
    """Supported output filename styles."""

    MONTH_DAY = "month_day"
    MONTH_DAY_CATEGORY = "month_day_category"


@dataclass(frozen=True)
class MediaGroup:
    """A chronologically ordered set of clips for one output video."""

    day_root: Path
    year: str | None
    month: str | None
    day: str | None
    category: str | None
    files: tuple[Path, ...]


@dataclass(frozen=True)
class ScanResult:
    """Complete result of a source-folder scan."""

    source_root: Path
    groups: tuple[MediaGroup, ...]
    media_file_count: int
    day_count: int
    unrecognised_date_files: int


@dataclass(frozen=True)
class ConversionOptions:
    """User-selected output behavior."""

    output_root: Path
    output_layout: OutputLayout
    video_format: VideoFormat
    naming_mode: NamingMode
    ffmpeg_directory: Path | None = None


@dataclass(frozen=True)
class ConversionSummary:
    """Final counts and paths from a conversion run."""

    completed: tuple[Path, ...]
    failed_groups: tuple[str, ...]
    skipped_files: tuple[Path, ...]
    cancelled: bool


@dataclass(frozen=True)
class MkvConversionResult:
    """Result of converting one existing MKV file to MP4."""

    output: Path | None
    cancelled: bool
