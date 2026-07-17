"""Consistent, plain-language error messages for user-visible failures."""

from __future__ import annotations

from pathlib import Path


def error_messages_format_operation(stage: str, error: BaseException) -> str:
    """Return a labelled problem, action, and technical detail for an error."""

    technical = str(error).strip() or error.__class__.__name__
    lower_detail = technical.casefold()

    if isinstance(error, PermissionError) or "permission denied" in lower_detail:
        problem = "The application does not have permission to access a required file or folder."
        action = (
            "Choose a folder you can read and write, or update its permissions, "
            "then try again."
        )
    elif isinstance(error, FileNotFoundError):
        problem = "A required file or folder is no longer available."
        action = (
            "Reconnect any removable drive, confirm the selected folders still "
            "exist, then try again."
        )
    elif isinstance(error, OSError) and "no space left" in lower_detail:
        problem = "The destination drive does not have enough free space."
        action = "Free some disk space or choose another output folder, then try again."
    elif stage.casefold().startswith("scan"):
        problem = "The source folder could not be scanned."
        action = (
            "Confirm the drive is connected and readable, then select the source "
            "folder again."
        )
    elif stage.casefold().startswith("convert"):
        problem = "The conversion could not be started or completed."
        action = (
            "Read the technical detail below, confirm FFmpeg is installed, and "
            "check that the output folder is writable."
        )
    else:
        problem = "The requested operation could not be completed."
        action = "Check the details below, correct the problem, then try again."

    return error_messages_format(stage, problem, action, technical)


def error_messages_format(
    stage: str, problem: str, action: str, technical: str | None = None
) -> str:
    """Format a readable error with a stable structure used across the app."""

    lines = [f"Stage: {stage}", "", f"Problem: {problem}", "", f"What to do: {action}"]
    if technical:
        lines.extend(("", f"Technical detail: {technical}"))
    return "\n".join(lines)


def error_messages_path(path: Path) -> str:
    """Return a path in a clearly labelled, user-readable form."""

    return f"Affected path: {path}"
