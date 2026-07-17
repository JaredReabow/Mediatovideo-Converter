"""Discover and group camera ``.media`` files without FFmpeg."""

from __future__ import annotations

import os
import re
import threading
from collections import defaultdict
from pathlib import Path
from typing import Callable

from .models import GroupingMode, MediaGroup, ScanResult

ScanProgress = Callable[[int, Path], None]
_YEAR_RE = re.compile(r"^\d{4}$")
_MONTH_DAY_RE = re.compile(r"^\d{1,2}$")


class ScanCancelled(Exception):
    """Raised internally when a requested scan cancellation is observed."""


def scanner_scan(
    source_root: Path,
    grouping_mode: GroupingMode,
    progress: ScanProgress | None = None,
    cancel_event: threading.Event | None = None,
) -> ScanResult:
    """Recursively scan ``source_root`` and group clips in stable path order.

    Date folders are recognised anywhere below the selected source using the
    ``YYYY/MM/DD`` pattern. Files outside that pattern are grouped beneath the
    selected folder so the application remains useful for simpler layouts.
    """

    source_root = source_root.expanduser().resolve()
    if not source_root.is_dir():
        raise ValueError(f"Source folder does not exist: {source_root}")

    media_file_count = 0
    visited = 0
    grouped: dict[tuple[Path, str | None], list[Path]] = defaultdict(list)
    date_details: dict[Path, tuple[str, str, str]] = {}
    unrecognised = 0

    for current_root, directory_names, filenames in os.walk(source_root):
        _scanner_check_cancel(cancel_event)
        directory_names.sort(key=str.casefold)
        filenames.sort(key=str.casefold)
        current_path = Path(current_root)
        visited += len(directory_names) + len(filenames)
        if progress:
            progress(visited, current_path)
        for filename in filenames:
            if Path(filename).suffix.casefold() != ".media":
                continue
            _scanner_check_cancel(cancel_event)
            media_file = current_path / filename
            media_file_count += 1
            date_match = _scanner_find_date_root(media_file.parent, source_root)
            if date_match is None:
                day_root = source_root
                category = _scanner_category(media_file, day_root, grouping_mode)
                unrecognised += 1
            else:
                day_root, year, month, day = date_match
                date_details[day_root] = (year, month, day)
                category = _scanner_category(media_file, day_root, grouping_mode)
            grouped[(day_root, category)].append(media_file)

    groups: list[MediaGroup] = []
    for (day_root, category), files in grouped.items():
        details = date_details.get(day_root)
        year, month, day = details if details else (None, None, None)
        groups.append(
            MediaGroup(
                day_root=day_root,
                year=year,
                month=month,
                day=day,
                category=category,
                files=tuple(sorted(files, key=lambda path: path.as_posix().casefold())),
            )
        )

    groups.sort(key=_scanner_group_sort_key)
    recognised_days = {group.day_root for group in groups if group.year is not None}
    fallback_days = 1 if groups and unrecognised else 0
    return ScanResult(
        source_root=source_root,
        groups=tuple(groups),
        media_file_count=media_file_count,
        day_count=len(recognised_days) + fallback_days,
        unrecognised_date_files=unrecognised,
    )


def _scanner_find_date_root(
    start: Path, source_root: Path
) -> tuple[Path, str, str, str] | None:
    """Return the nearest valid ``YYYY/MM/DD`` ancestor within the source."""

    current = start
    while current == source_root or source_root in current.parents:
        if (
            _MONTH_DAY_RE.fullmatch(current.name)
            and _MONTH_DAY_RE.fullmatch(current.parent.name)
            and _YEAR_RE.fullmatch(current.parent.parent.name)
        ):
            month_value = int(current.parent.name)
            day_value = int(current.name)
            if 1 <= month_value <= 12 and 1 <= day_value <= 31:
                return (
                    current,
                    current.parent.parent.name,
                    f"{month_value:02d}",
                    f"{day_value:02d}",
                )
        if current == source_root:
            break
        current = current.parent
    return None


def _scanner_category(
    media_file: Path, day_root: Path, grouping_mode: GroupingMode
) -> str | None:
    """Return the immediate child folder used for category grouping."""

    if grouping_mode is GroupingMode.DAY:
        return None
    relative_parts = media_file.relative_to(day_root).parts
    return relative_parts[0] if len(relative_parts) > 1 else "Day root"


def _scanner_group_sort_key(group: MediaGroup) -> tuple[str, str, str, str]:
    """Build a deterministic key for groups and their output order."""

    return (
        group.year or "",
        group.month or "",
        group.day or "",
        (group.category or "").casefold(),
    )


def _scanner_check_cancel(cancel_event: threading.Event | None) -> None:
    """Stop quickly when the UI asks the scanner to cancel."""

    if cancel_event and cancel_event.is_set():
        raise ScanCancelled()
