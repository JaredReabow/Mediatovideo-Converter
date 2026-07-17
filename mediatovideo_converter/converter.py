"""FFmpeg-backed validation, naming, and conversion services."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable, Sequence

from .error_messages import error_messages_format, error_messages_path
from .models import (
    ConversionOptions,
    ConversionSummary,
    MediaGroup,
    NamingMode,
    OutputLayout,
    VideoFormat,
)

ConversionEvent = Callable[[str, dict[str, object]], None]
_INVALID_FILENAME = re.compile(r"[<>:\"/\\|?*\x00-\x1f]")
_VALIDATION_EVENT_INTERVAL_SECONDS = 0.2
_ENCODING_EVENT_INTERVAL_SECONDS = 0.2
_ENCODING_EVENT_MIN_FRACTION_STEP = 0.005


class ConversionCancelled(Exception):
    """Raised internally when conversion cancellation is requested."""


class FFmpegNotFoundError(RuntimeError):
    """Raised when FFmpeg and FFprobe cannot be located."""


class ConversionProcessError(RuntimeError):
    """Raised with a complete user-facing explanation of a group failure."""


def converter_find_tools(ffmpeg_directory: Path | None = None) -> tuple[str, str]:
    """Locate FFmpeg and FFprobe in a selected directory or on ``PATH``."""

    executable_suffix = ".exe" if os.name == "nt" else ""
    if ffmpeg_directory:
        directory = ffmpeg_directory.expanduser().resolve()
        ffmpeg = directory / f"ffmpeg{executable_suffix}"
        ffprobe = directory / f"ffprobe{executable_suffix}"
        if ffmpeg.is_file() and ffprobe.is_file():
            return str(ffmpeg), str(ffprobe)
        raise FFmpegNotFoundError(
            error_messages_format(
                "Checking video tools",
                "FFmpeg and FFprobe were not both found in the selected folder.",
                "Select the folder containing both executables, or restart the app "
                "with run_windows.bat or run_macos.command to install them.",
                error_messages_path(directory),
            )
        )

    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")
    if not ffmpeg_path or not ffprobe_path:
        raise FFmpegNotFoundError(
            error_messages_format(
                "Checking video tools",
                "FFmpeg and FFprobe are required but could not both be found.",
                "Close the app and start it with run_windows.bat or "
                "run_macos.command so the missing tools can be installed. You may "
                "also select an existing FFmpeg bin folder in the app.",
            )
        )
    return ffmpeg_path, ffprobe_path


def converter_plan_targets(
    groups: Sequence[MediaGroup], options: ConversionOptions
) -> tuple[Path, ...]:
    """Create collision-free target paths without modifying the filesystem."""

    reserved: set[Path] = set()
    targets: list[Path] = []
    extension = ".mkv" if options.video_format is VideoFormat.MKV_COPY else ".mp4"
    for group in groups:
        directory = _converter_output_directory(group, options)
        stem = _converter_output_stem(group, options.naming_mode)
        candidate = directory / f"{stem}{extension}"
        suffix_number = 2
        while candidate in reserved or candidate.exists():
            candidate = directory / f"{stem}-{suffix_number}{extension}"
            suffix_number += 1
        reserved.add(candidate)
        targets.append(candidate)
    return tuple(targets)


def converter_convert(
    groups: Sequence[MediaGroup],
    options: ConversionOptions,
    event: ConversionEvent | None = None,
    cancel_event: threading.Event | None = None,
) -> ConversionSummary:
    """Validate and convert all groups, continuing past individual failures."""

    ffmpeg, ffprobe = converter_find_tools(options.ffmpeg_directory)
    targets = converter_plan_targets(groups, options)
    completed: list[Path] = []
    failures: list[str] = []
    skipped: list[Path] = []

    try:
        for index, (group, target) in enumerate(zip(groups, targets), start=1):
            _converter_check_cancel(cancel_event)
            _converter_emit(
                event,
                "group_started",
                index=index,
                total=len(groups),
                target=target,
                file_count=len(group.files),
            )
            valid_files: list[Path] = []
            total_duration = 0.0
            last_validation_event_time = 0.0
            for file_index, media_file in enumerate(group.files, start=1):
                _converter_check_cancel(cancel_event)
                duration = _converter_probe_media(ffprobe, media_file)
                if duration is None:
                    skipped.append(media_file)
                    _converter_emit(event, "file_skipped", path=media_file)
                else:
                    valid_files.append(media_file)
                    total_duration += duration
                now = time.monotonic()
                if (
                    file_index == len(group.files)
                    or now - last_validation_event_time
                    >= _VALIDATION_EVENT_INTERVAL_SECONDS
                ):
                    _converter_emit(
                        event,
                        "validation_progress",
                        current=file_index,
                        total=len(group.files),
                        path=media_file,
                    )
                    last_validation_event_time = now

            if not valid_files:
                label = _converter_group_label(group)
                failures.append(
                    f"{label}\n"
                    + error_messages_format(
                        "Validating source clips",
                        "No readable .media clips remained in this group.",
                        "Check that the camera export is complete and try the original "
                        "files again. The other video groups will continue.",
                    )
                )
                _converter_emit(event, "group_failed", target=target, reason=failures[-1])
                continue

            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                _converter_run_ffmpeg(
                    ffmpeg,
                    valid_files,
                    target,
                    options.video_format,
                    total_duration,
                    event,
                    cancel_event,
                )
            except ConversionCancelled:
                raise
            except ConversionProcessError as error:
                reason = str(error)
                failures.append(f"{_converter_group_label(group)}\n{reason}")
                _converter_emit(event, "group_failed", target=target, reason=reason)
                continue
            except OSError as error:
                reason = _converter_explain_output_error(error, target)
                failures.append(f"{_converter_group_label(group)}\n{reason}")
                _converter_emit(event, "group_failed", target=target, reason=reason)
                continue

            completed.append(target)
            _converter_emit(
                event,
                "group_completed",
                index=index,
                total=len(groups),
                target=target,
            )
    except ConversionCancelled:
        return ConversionSummary(
            completed=tuple(completed),
            failed_groups=tuple(failures),
            skipped_files=tuple(skipped),
            cancelled=True,
        )

    return ConversionSummary(
        completed=tuple(completed),
        failed_groups=tuple(failures),
        skipped_files=tuple(skipped),
        cancelled=False,
    )


def _converter_probe_media(ffprobe: str, media_file: Path) -> float | None:
    """Return duration for a readable clip, using zero when duration is unknown."""

    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(media_file),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
            **_converter_subprocess_window_options(),
        )
    except subprocess.TimeoutExpired:
        return None
    if result.returncode != 0:
        return None
    try:
        return max(0.0, float(result.stdout.strip()))
    except ValueError:
        return 0.0


def _converter_run_ffmpeg(
    ffmpeg: str,
    media_files: Sequence[Path],
    target: Path,
    video_format: VideoFormat,
    total_duration: float,
    event: ConversionEvent | None,
    cancel_event: threading.Event | None,
) -> None:
    """Run one FFmpeg concat job and atomically publish its completed output."""

    partial_target = target.with_name(f".{target.stem}.partial{target.suffix}")
    try:
        with tempfile.TemporaryDirectory(prefix="mediatovideo-") as temporary:
            concat_path = Path(temporary) / "clips.ffconcat"
            concat_path.write_text(
                "ffconcat version 1.0\n"
                + "".join(
                    f"file '{_converter_escape_concat_path(path)}'\n"
                    for path in media_files
                ),
                encoding="utf-8",
            )
            command = [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_path),
            ]
            if video_format is VideoFormat.MKV_COPY:
                command.extend(["-c", "copy"])
            else:
                command.extend(
                    [
                        "-map",
                        "0:v:0?",
                        "-map",
                        "0:a:0?",
                        "-c:v",
                        "libx264",
                        "-preset",
                        "medium",
                        "-crf",
                        "20",
                        "-c:a",
                        "aac",
                        "-b:a",
                        "128k",
                        "-movflags",
                        "+faststart",
                    ]
                )
            command.extend(["-progress", "pipe:1", "-nostats", str(partial_target)])

            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                # Merging stderr prevents a verbose decoder error from filling
                # an unread pipe and deadlocking the progress reader.
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                **_converter_subprocess_window_options(),
            )
            assert process.stdout is not None
            diagnostic_lines: deque[str] = deque(maxlen=12)
            last_encoding_event_time = 0.0
            last_encoding_fraction: float | None = None
            try:
                while True:
                    if cancel_event and cancel_event.is_set():
                        process.terminate()
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                        raise ConversionCancelled()
                    line = process.stdout.readline()
                    if not line and process.poll() is not None:
                        break
                    key, separator, value = line.strip().partition("=")
                    if separator and key in {"out_time_us", "out_time_ms"}:
                        try:
                            elapsed = int(value) / 1_000_000
                        except ValueError:
                            continue
                        fraction = (
                            min(1.0, elapsed / total_duration)
                            if total_duration
                            else None
                        )
                        now = time.monotonic()
                        should_emit = False
                        if fraction is None:
                            should_emit = (
                                now - last_encoding_event_time
                                >= _ENCODING_EVENT_INTERVAL_SECONDS
                            )
                        else:
                            should_emit = (
                                last_encoding_fraction is None
                                or fraction >= 1.0
                                or fraction - last_encoding_fraction
                                >= _ENCODING_EVENT_MIN_FRACTION_STEP
                                or now - last_encoding_event_time
                                >= _ENCODING_EVENT_INTERVAL_SECONDS
                            )
                        if should_emit:
                            _converter_emit(
                                event,
                                "encoding_progress",
                                elapsed=elapsed,
                                duration=total_duration,
                                fraction=fraction,
                            )
                            last_encoding_event_time = now
                            last_encoding_fraction = fraction
                    elif line.strip() and key not in {
                        "bitrate",
                        "drop_frames",
                        "dup_frames",
                        "fps",
                        "frame",
                        "out_time",
                        "progress",
                        "speed",
                        "stream_0_0_q",
                        "total_size",
                    }:
                        diagnostic_lines.append(line.strip())
            finally:
                process.stdout.close()

            if process.returncode != 0:
                final_line = diagnostic_lines[-1] if diagnostic_lines else "FFmpeg failed"
                raise ConversionProcessError(
                    _converter_explain_ffmpeg_error(final_line, target, video_format)
                )
            try:
                os.replace(partial_target, target)
            except OSError as error:
                raise ConversionProcessError(
                    _converter_explain_output_error(error, target)
                ) from error
    finally:
        partial_target.unlink(missing_ok=True)


def _converter_output_directory(
    group: MediaGroup, options: ConversionOptions
) -> Path:
    """Apply the output layout policy owned by this module."""

    if (
        options.output_layout is OutputLayout.MIRROR_DATES
        and group.year
        and group.month
        and group.day
    ):
        return options.output_root / group.year / group.month / group.day
    return options.output_root


def _converter_explain_ffmpeg_error(
    diagnostic: str, target: Path, video_format: VideoFormat
) -> str:
    """Translate common FFmpeg diagnostics into an actionable explanation."""

    lower_diagnostic = diagnostic.casefold()
    if "permission denied" in lower_diagnostic:
        problem = "FFmpeg cannot write to the selected output folder."
        action = "Choose an output folder you can write to, then convert again."
    elif "no space left" in lower_diagnostic:
        problem = "The output drive ran out of free space."
        action = "Free disk space or choose another output drive, then convert again."
    elif "unknown encoder" in lower_diagnostic and "libx264" in lower_diagnostic:
        problem = "This FFmpeg installation does not include the H.264 encoder."
        action = (
            "Restart with the platform launcher to install the supported FFmpeg "
            "package, or choose MKV stream-copy output."
        )
    elif any(
        phrase in lower_diagnostic
        for phrase in (
            "invalid data found",
            "could not find codec parameters",
            "error opening input",
        )
    ):
        problem = "One or more camera clips contain unreadable or unsupported data."
        action = (
            "Check the activity log for skipped clips. Try MP4 output if MKV was "
            "selected, or restore the original camera export and retry."
        )
    elif "non-monoton" in lower_diagnostic or "timestamp" in lower_diagnostic:
        problem = "The source clips contain timestamps that cannot be joined as selected."
        action = "Choose MP4 H.264 output so FFmpeg can rebuild the timestamps."
    elif video_format is VideoFormat.MKV_COPY:
        problem = "FFmpeg could not join these clips without changing their streams."
        action = (
            "Try MP4 H.264 output for this source. It is slower but can repair many "
            "stream-compatibility differences."
        )
    else:
        problem = "FFmpeg could not decode or encode this video group."
        action = (
            "Check the source clips are complete and readable, then review the "
            "technical detail below before retrying."
        )
    return error_messages_format(
        "Creating output video",
        problem,
        action,
        f"Output: {target}\nFFmpeg: {diagnostic}",
    )


def _converter_explain_output_error(error: OSError, target: Path) -> str:
    """Explain filesystem failures encountered while creating an output."""

    detail = str(error).strip() or error.__class__.__name__
    lower_detail = detail.casefold()
    if isinstance(error, PermissionError) or "permission denied" in lower_detail:
        problem = "The selected output folder is not writable."
        action = "Choose a writable output folder, then run the conversion again."
    elif "no space left" in lower_detail:
        problem = "The selected output drive does not have enough free space."
        action = "Free disk space or choose another output folder, then try again."
    else:
        problem = "The completed video could not be written to its destination."
        action = (
            "Confirm the output drive is connected and writable, then choose the "
            "output folder again."
        )
    return error_messages_format(
        "Saving output video",
        problem,
        action,
        f"{error_messages_path(target)}\nSystem: {detail}",
    )


def _converter_output_stem(group: MediaGroup, naming_mode: NamingMode) -> str:
    """Create a portable filename stem from group metadata."""

    if group.month and group.day:
        stem = f"{group.month}-{group.day}"
    else:
        stem = group.day_root.name or "video"
    if naming_mode is NamingMode.MONTH_DAY_CATEGORY and group.category:
        stem = f"{stem}-{group.category}"
    sanitised = _INVALID_FILENAME.sub("-", stem).strip(" .-")
    return sanitised or "video"


def _converter_escape_concat_path(path: Path) -> str:
    """Escape a path for FFmpeg's single-quoted concat-file syntax."""

    return path.resolve().as_posix().replace("'", "'\\''")


def _converter_group_label(group: MediaGroup) -> str:
    """Return a concise human-readable group name for diagnostics."""

    date = "-".join(part for part in (group.year, group.month, group.day) if part)
    label = date or group.day_root.name
    return f"{label} / {group.category}" if group.category else label


def _converter_emit(
    event: ConversionEvent | None, event_name: str, **details: object
) -> None:
    """Safely emit a structured progress event when a listener exists."""

    if event:
        event(event_name, details)


def _converter_check_cancel(cancel_event: threading.Event | None) -> None:
    """Stop quickly before starting the next expensive operation."""

    if cancel_event and cancel_event.is_set():
        raise ConversionCancelled()


def _converter_subprocess_window_options() -> dict[str, object]:
    """Prevent FFmpeg console windows flashing on Windows GUI builds."""

    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}
