"""Tkinter graphical interface for Mediatovideo Converter.

The UI talks to scanner and converter modules only through their public APIs.
Worker threads communicate through a queue so Tk is never updated off-thread.
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from . import __version__
from .converter import FFmpegNotFoundError, converter_convert, converter_find_tools
from .error_messages import error_messages_format, error_messages_format_operation
from .models import (
    ConversionOptions,
    ConversionSummary,
    GroupingMode,
    NamingMode,
    OutputLayout,
    ScanResult,
    VideoFormat,
)
from .scanner import ScanCancelled, scanner_scan

_GROUPING_LABELS = {
    "One video per day": GroupingMode.DAY,
    "One video per child folder in each day": GroupingMode.CHILD_FOLDER,
}
_LAYOUT_LABELS = {
    "Replicate YYYY/MM/DD folders": OutputLayout.MIRROR_DATES,
    "Put all videos in one folder": OutputLayout.FLAT,
}
_FORMAT_LABELS = {
    "MKV — fast, lossless stream copy": VideoFormat.MKV_COPY,
    "MP4 — compatible H.264 (slower)": VideoFormat.MP4_H264,
}
_NAMING_LABELS = {
    "Month-Day (07-17)": NamingMode.MONTH_DAY,
    "Month-Day-Category (07-17-Camera1)": NamingMode.MONTH_DAY_CATEGORY,
}
_MAX_UI_MESSAGES = 5000
_MAX_LOG_LINES = 2000


class MediaToVideoApp:
    """Own and coordinate the desktop interface."""

    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._messages: queue.Queue[tuple[Any, ...]] = queue.Queue(
            maxsize=_MAX_UI_MESSAGES
        )
        self._cancel_event = threading.Event()
        self._scan_result: ScanResult | None = None
        self._busy_operation: str | None = None
        self._log_line_count = 0

        self._source = tk.StringVar()
        self._output = tk.StringVar()
        self._ffmpeg_directory = tk.StringVar()
        self._grouping = tk.StringVar(value=next(iter(_GROUPING_LABELS)))
        self._layout = tk.StringVar(value=next(iter(_LAYOUT_LABELS)))
        self._format = tk.StringVar(value=next(iter(_FORMAT_LABELS)))
        self._naming = tk.StringVar(value=next(iter(_NAMING_LABELS)))
        self._status = tk.StringVar(value="Choose a source folder, then scan it.")
        self._scan_detail = tk.StringVar(value="Not scanned")
        self._overall_detail = tk.StringVar(value="No conversion running")
        self._current_detail = tk.StringVar(value="Waiting")

        self._configure_window()
        self._build_interface()
        self._source.trace_add("write", self._source_or_grouping_changed)
        self._grouping.trace_add("write", self._source_or_grouping_changed)
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._root.after(100, self._poll_messages)

    def _configure_window(self) -> None:
        """Set cross-platform window defaults."""

        self._root.title(f"Mediatovideo Converter {__version__}")
        self._root.minsize(760, 720)
        self._root.geometry("900x780")
        try:
            ttk.Style().theme_use("aqua" if sys.platform == "darwin" else "vista")
        except tk.TclError:
            pass

    def _build_interface(self) -> None:
        """Create all controls and visible progress surfaces."""

        outer = ttk.Frame(self._root, padding=16)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(4, weight=1)

        title = ttk.Label(
            outer,
            text="Mediatovideo Converter",
            font=("TkDefaultFont", 18, "bold"),
        )
        title.grid(row=0, column=0, sticky="w")
        ttk.Label(
            outer,
            text="Combine camera .media clips into usable MKV or MP4 videos.",
        ).grid(row=1, column=0, sticky="w", pady=(2, 12))

        paths = ttk.LabelFrame(outer, text="Folders and FFmpeg", padding=10)
        paths.grid(row=2, column=0, sticky="ew")
        paths.columnconfigure(1, weight=1)
        self._add_path_row(paths, 0, "Source", self._source, self._choose_source)
        self._add_path_row(paths, 1, "Output", self._output, self._choose_output)
        self._add_path_row(
            paths,
            2,
            "FFmpeg bin",
            self._ffmpeg_directory,
            self._choose_ffmpeg,
            optional=True,
        )

        options = ttk.LabelFrame(outer, text="Conversion options", padding=10)
        options.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        options.columnconfigure(1, weight=1)
        self._add_combo(options, 0, "Grouping", self._grouping, _GROUPING_LABELS)
        self._add_combo(options, 1, "Output layout", self._layout, _LAYOUT_LABELS)
        self._add_combo(options, 2, "Video format", self._format, _FORMAT_LABELS)
        self._add_combo(options, 3, "File naming", self._naming, _NAMING_LABELS)

        middle = ttk.Panedwindow(outer, orient=tk.VERTICAL)
        middle.grid(row=4, column=0, sticky="nsew", pady=(10, 0))

        preview_frame = ttk.LabelFrame(middle, text="Scan results", padding=8)
        preview_frame.rowconfigure(1, weight=1)
        preview_frame.columnconfigure(0, weight=1)
        scan_status = ttk.Frame(preview_frame)
        scan_status.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        scan_status.columnconfigure(0, weight=1)
        ttk.Label(scan_status, textvariable=self._scan_detail).grid(
            row=0, column=0, sticky="w"
        )
        self._scan_progress = ttk.Progressbar(scan_status, mode="indeterminate")
        self._scan_progress.grid(row=1, column=0, sticky="ew", pady=(4, 0))

        self._groups_table = ttk.Treeview(
            preview_frame,
            columns=("date", "category", "clips"),
            show="headings",
            height=6,
        )
        self._groups_table.heading("date", text="Date / folder")
        self._groups_table.heading("category", text="Category")
        self._groups_table.heading("clips", text="Clips")
        self._groups_table.column("date", width=260)
        self._groups_table.column("category", width=260)
        self._groups_table.column("clips", width=70, anchor=tk.E)
        self._groups_table.grid(row=1, column=0, sticky="nsew")
        preview_scroll = ttk.Scrollbar(
            preview_frame, orient=tk.VERTICAL, command=self._groups_table.yview
        )
        preview_scroll.grid(row=1, column=1, sticky="ns")
        self._groups_table.configure(yscrollcommand=preview_scroll.set)
        middle.add(preview_frame, weight=1)

        progress_frame = ttk.LabelFrame(middle, text="Conversion progress", padding=8)
        progress_frame.columnconfigure(0, weight=1)
        ttk.Label(progress_frame, textvariable=self._overall_detail).grid(
            row=0, column=0, sticky="w"
        )
        self._overall_progress = ttk.Progressbar(
            progress_frame, mode="determinate", maximum=1
        )
        self._overall_progress.grid(row=1, column=0, sticky="ew", pady=(4, 7))
        ttk.Label(progress_frame, textvariable=self._current_detail).grid(
            row=2, column=0, sticky="w"
        )
        self._current_progress = ttk.Progressbar(
            progress_frame, mode="determinate", maximum=100
        )
        self._current_progress.grid(row=3, column=0, sticky="ew", pady=(4, 7))
        self._log = tk.Text(progress_frame, height=7, wrap="word", state=tk.DISABLED)
        self._log.grid(row=4, column=0, sticky="nsew")
        progress_frame.rowconfigure(4, weight=1)
        log_scroll = ttk.Scrollbar(
            progress_frame, orient=tk.VERTICAL, command=self._log.yview
        )
        log_scroll.grid(row=4, column=1, sticky="ns")
        self._log.configure(yscrollcommand=log_scroll.set)
        middle.add(progress_frame, weight=1)

        controls = ttk.Frame(outer)
        controls.grid(row=5, column=0, sticky="ew", pady=(12, 0))
        controls.columnconfigure(3, weight=1)
        self._scan_button = ttk.Button(
            controls, text="1. Scan source", command=self._start_scan
        )
        self._scan_button.grid(row=0, column=0, padx=(0, 8))
        self._convert_button = ttk.Button(
            controls,
            text="2. Convert videos",
            command=self._start_conversion,
            state=tk.DISABLED,
        )
        self._convert_button.grid(row=0, column=1, padx=(0, 8))
        self._cancel_button = ttk.Button(
            controls, text="Cancel", command=self._cancel, state=tk.DISABLED
        )
        self._cancel_button.grid(row=0, column=2)
        ttk.Button(
            controls, text="Open output folder", command=self._open_output
        ).grid(row=0, column=4, padx=(8, 0))

        status = ttk.Label(
            outer,
            textvariable=self._status,
            relief=tk.SUNKEN,
            anchor="w",
            padding=(6, 4),
        )
        status.grid(row=6, column=0, sticky="ew", pady=(10, 0))

    def _add_path_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        command: Any,
        optional: bool = False,
    ) -> None:
        """Add a labelled folder entry and browse button."""

        label_text = f"{label} (optional)" if optional else label
        ttk.Label(parent, text=label_text).grid(
            row=row, column=0, sticky="w", padx=(0, 8), pady=3
        )
        ttk.Entry(parent, textvariable=variable).grid(
            row=row, column=1, sticky="ew", pady=3
        )
        ttk.Button(parent, text="Browse…", command=command).grid(
            row=row, column=2, padx=(8, 0), pady=3
        )

    def _add_combo(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        choices: dict[str, Any],
    ) -> None:
        """Add a read-only option selector."""

        ttk.Label(parent, text=label).grid(
            row=row, column=0, sticky="w", padx=(0, 8), pady=3
        )
        ttk.Combobox(
            parent,
            textvariable=variable,
            values=tuple(choices),
            state="readonly",
        ).grid(row=row, column=1, sticky="ew", pady=3)

    def _choose_source(self) -> None:
        """Choose a source folder and visibly acknowledge the action."""

        folder = filedialog.askdirectory(title="Choose a .media source folder")
        if folder:
            self._source.set(folder)
            self._status.set("Source selected. Click Scan source to inspect it.")
            if not self._output.get().strip():
                self._output.set(str(Path(folder).parent / "Converted Videos"))
        else:
            self._status.set("Source selection cancelled; no folder changed.")

    def _choose_output(self) -> None:
        """Choose an output folder and visibly acknowledge the action."""

        folder = filedialog.askdirectory(title="Choose an output folder")
        if folder:
            self._output.set(folder)
            self._status.set("Output folder selected.")
        else:
            self._status.set("Output selection cancelled; no folder changed.")

    def _choose_ffmpeg(self) -> None:
        """Choose the folder containing FFmpeg and FFprobe."""

        folder = filedialog.askdirectory(title="Choose the FFmpeg bin folder")
        if folder:
            self._ffmpeg_directory.set(folder)
            try:
                converter_find_tools(Path(folder))
            except FFmpegNotFoundError as error:
                self._status.set(str(error))
                messagebox.showwarning("FFmpeg not found", str(error))
            else:
                self._status.set("FFmpeg and FFprobe found in the selected folder.")
        else:
            self._status.set("FFmpeg folder selection cancelled; no folder changed.")

    def _source_or_grouping_changed(self, *_args: object) -> None:
        """Invalidate stale scan data when its inputs change."""

        if self._scan_result is not None and not self._busy_operation:
            self._scan_result = None
            self._convert_button.configure(state=tk.DISABLED)
            self._scan_detail.set("Source or grouping changed — scan again")
            self._clear_group_table()

    def _start_scan(self) -> None:
        """Validate input and launch a responsive source scan."""

        if self._busy_operation:
            self._status.set(f"Already busy with {self._busy_operation}.")
            return
        source = Path(self._source.get().strip()).expanduser()
        if not source.is_dir():
            self._show_input_error(
                "The source folder does not exist or is not currently available.",
                "Reconnect any removable drive, then choose an existing source folder.",
                f"Selected source: {source}",
            )
            return

        grouping = _GROUPING_LABELS[self._grouping.get()]
        self._scan_result = None
        self._clear_group_table()
        self._set_busy("scanning")
        self._scan_detail.set("Scanning folders…")
        self._scan_progress.start(12)
        self._append_log(f"Scanning {source}")

        def worker() -> None:
            try:
                result = scanner_scan(
                    source,
                    grouping,
                    progress=lambda count, path: self._queue_message(
                        ("scan_progress", count, path), lossy=True
                    ),
                    cancel_event=self._cancel_event,
                )
            except ScanCancelled:
                self._queue_message(("scan_cancelled",))
            except Exception as error:  # Surface unexpected filesystem errors.
                self._queue_message(("operation_error", "Scanning source", error))
            else:
                self._queue_message(("scan_done", result))

        threading.Thread(target=worker, name="media-scan", daemon=True).start()

    def _start_conversion(self) -> None:
        """Validate output settings and launch conversion in a worker thread."""

        if self._busy_operation:
            self._status.set(f"Already busy with {self._busy_operation}.")
            return
        if not self._scan_result or not self._scan_result.groups:
            self._show_input_error(
                "There are no scanned .media groups ready to convert.",
                "Choose a source folder and complete Scan source before converting.",
            )
            return
        output_text = self._output.get().strip()
        if not output_text:
            self._show_input_error(
                "No output folder has been selected.",
                "Choose where the completed videos should be saved, then try again.",
            )
            return

        options = ConversionOptions(
            output_root=Path(output_text).expanduser().resolve(),
            output_layout=_LAYOUT_LABELS[self._layout.get()],
            video_format=_FORMAT_LABELS[self._format.get()],
            naming_mode=_NAMING_LABELS[self._naming.get()],
            ffmpeg_directory=(
                Path(self._ffmpeg_directory.get().strip()).expanduser()
                if self._ffmpeg_directory.get().strip()
                else None
            ),
        )
        groups = self._scan_result.groups
        self._set_busy("converting")
        self._overall_progress.configure(maximum=max(1, len(groups)), value=0)
        self._overall_detail.set(f"Preparing 0 of {len(groups)} videos")
        self._current_progress.configure(mode="determinate", maximum=100, value=0)
        self._current_detail.set("Locating FFmpeg…")
        self._append_log(f"Starting conversion of {len(groups)} video group(s).")

        def worker() -> None:
            try:
                summary = converter_convert(
                    groups,
                    options,
                    event=lambda name, details: self._queue_message(
                        ("conversion_event", name, details),
                        lossy=name in {"validation_progress", "encoding_progress"},
                    ),
                    cancel_event=self._cancel_event,
                )
            except Exception as error:  # Includes missing dependencies.
                self._queue_message(("operation_error", "Converting videos", error))
            else:
                self._queue_message(("conversion_done", summary))

        threading.Thread(target=worker, name="media-convert", daemon=True).start()

    def _handle_conversion_event(self, name: str, details: dict[str, object]) -> None:
        """Render one structured converter progress event."""

        if name == "group_started":
            index = int(details["index"])
            total = int(details["total"])
            target = Path(details["target"])
            self._overall_detail.set(f"Video {index} of {total}: {target.name}")
            self._current_detail.set(
                f"Validating 0 of {details['file_count']} clips for {target.name}"
            )
            self._current_progress.stop()
            self._current_progress.configure(mode="determinate", value=0)
            self._append_log(f"Validating clips for {target}")
        elif name == "validation_progress":
            current = int(details["current"])
            total = max(1, int(details["total"]))
            self._current_progress.configure(
                mode="determinate", maximum=total, value=current
            )
            self._current_detail.set(f"Validated {current} of {total} clips")
        elif name == "file_skipped":
            self._append_log(
                "Skipped unreadable clip; conversion will continue with the remaining "
                f"clips: {details['path']}"
            )
        elif name == "encoding_progress":
            fraction = details.get("fraction")
            if fraction is None:
                if str(self._current_progress.cget("mode")) != "indeterminate":
                    self._current_progress.configure(mode="indeterminate")
                    self._current_progress.start(12)
                self._current_detail.set("Encoding video… duration unavailable")
            else:
                self._current_progress.stop()
                self._current_progress.configure(
                    mode="determinate", maximum=100, value=float(fraction) * 100
                )
                self._current_detail.set(f"Encoding video… {float(fraction) * 100:.1f}%")
        elif name == "group_completed":
            index = int(details["index"])
            self._overall_progress.configure(value=index)
            self._current_progress.stop()
            self._current_progress.configure(mode="determinate", maximum=100, value=100)
            self._append_log(f"Completed: {details['target']}")
        elif name == "group_failed":
            self._append_log(f"Failed: {details['reason']}")

    def _finish_scan(self, result: ScanResult) -> None:
        """Display scan counts and group preview."""

        self._scan_progress.stop()
        self._scan_result = result
        self._set_idle()
        self._scan_detail.set(
            f"Found {result.media_file_count} clips across {result.day_count} day(s), "
            f"creating {len(result.groups)} video(s)."
        )
        for group in result.groups:
            date_label = (
                f"{group.year}/{group.month}/{group.day}"
                if group.year
                else str(group.day_root)
            )
            self._groups_table.insert(
                "", tk.END, values=(date_label, group.category or "All clips", len(group.files))
            )
        if result.media_file_count:
            self._convert_button.configure(state=tk.NORMAL)
            self._status.set(
                f"Scan complete: {len(result.groups)} output video(s) ready to convert."
            )
            if result.unrecognised_date_files:
                self._append_log(
                    f"Note: {result.unrecognised_date_files} clip(s) were outside a "
                    "YYYY/MM/DD path and were grouped under the selected source."
                )
        else:
            self._status.set("Scan complete: no .media files were found.")
            messagebox.showwarning(
                "No .media files found",
                error_messages_format(
                    "Scanning source",
                    "No files ending in .media were found below the selected folder.",
                    "Confirm the correct camera folder is selected and that the drive "
                    "is fully connected, then scan again.",
                    f"Scanned folder: {result.source_root}",
                ),
            )

    def _finish_conversion(self, summary: ConversionSummary) -> None:
        """Display a complete, cancelled, or partially failed run summary."""

        self._current_progress.stop()
        self._set_idle()
        if summary.cancelled:
            self._status.set(
                f"Conversion cancelled after {len(summary.completed)} completed video(s)."
            )
            self._current_detail.set("Cancelled")
            self._append_log("Conversion cancelled by user.")
            return

        completed = len(summary.completed)
        failed = len(summary.failed_groups)
        skipped = len(summary.skipped_files)
        self._overall_progress.configure(value=completed + failed)
        self._overall_detail.set(f"Finished: {completed} completed, {failed} failed")
        self._current_detail.set("Conversion run finished")
        self._status.set(
            f"Finished: {completed} video(s) created, {failed} failed, "
            f"{skipped} unreadable clip(s) skipped."
        )
        detail = self._status.get()
        if summary.failed_groups:
            detail += "\n\nFailure details:\n\n" + "\n\n".join(
                summary.failed_groups[:8]
            )
            messagebox.showwarning("Conversion finished with errors", detail)
        else:
            messagebox.showinfo("Conversion finished", detail)

    def _poll_messages(self) -> None:
        """Process worker messages on Tk's main thread."""

        try:
            while True:
                message = self._messages.get_nowait()
                kind = message[0]
                if kind == "scan_progress":
                    self._scan_detail.set(
                        f"Scanning… checked {message[1]} items\n{message[2]}"
                    )
                elif kind == "scan_done":
                    self._finish_scan(message[1])
                elif kind == "scan_cancelled":
                    self._scan_progress.stop()
                    self._scan_detail.set("Scan cancelled")
                    self._status.set("Scan cancelled; no results were changed.")
                    self._set_idle()
                elif kind == "conversion_event":
                    self._handle_conversion_event(message[1], message[2])
                elif kind == "conversion_done":
                    self._finish_conversion(message[1])
                elif kind == "operation_error":
                    self._scan_progress.stop()
                    self._current_progress.stop()
                    self._set_idle()
                    if isinstance(message[2], FFmpegNotFoundError):
                        details = str(message[2])
                    else:
                        details = error_messages_format_operation(message[1], message[2])
                    self._status.set(f"{message[1]} could not complete. See the error dialog.")
                    self._append_log(details)
                    messagebox.showerror(f"{message[1]} error", details)
        except queue.Empty:
            pass
        finally:
            self._root.after(100, self._poll_messages)

    def _set_busy(self, operation: str) -> None:
        """Disable conflicting actions and enable cancellation."""

        self._busy_operation = operation
        self._cancel_event.clear()
        self._scan_button.configure(state=tk.DISABLED)
        self._convert_button.configure(state=tk.DISABLED)
        self._cancel_button.configure(state=tk.NORMAL)
        self._status.set(f"{operation.capitalize()} in progress…")

    def _set_idle(self) -> None:
        """Restore controls after a worker finishes."""

        self._busy_operation = None
        self._scan_button.configure(state=tk.NORMAL)
        self._cancel_button.configure(state=tk.DISABLED)
        if self._scan_result and self._scan_result.groups:
            self._convert_button.configure(state=tk.NORMAL)

    def _cancel(self) -> None:
        """Request cancellation and immediately acknowledge the click."""

        if not self._busy_operation:
            self._status.set("Nothing is currently running to cancel.")
            return
        self._cancel_event.set()
        self._cancel_button.configure(state=tk.DISABLED)
        self._status.set(
            f"Cancellation requested; waiting for {self._busy_operation} to stop safely…"
        )

    def _open_output(self) -> None:
        """Open the output directory using the host operating system."""

        output_text = self._output.get().strip()
        if not output_text:
            self._show_input_error(
                "No output folder has been selected.",
                "Choose an output folder before using Open output folder.",
            )
            return
        output = Path(output_text).expanduser()
        if not output.is_dir():
            self._show_input_error(
                "The output folder does not exist yet.",
                "Run a conversion first or choose an existing output folder.",
                f"Selected output: {output}",
            )
            return
        self._status.set(f"Opening output folder: {output}")
        try:
            if os.name == "nt":
                os.startfile(output)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(output)])
            else:
                subprocess.Popen(["xdg-open", str(output)])
        except OSError as error:
            details = error_messages_format_operation("Opening output folder", error)
            self._status.set("The output folder could not be opened. See the error dialog.")
            self._append_log(details)
            messagebox.showerror("Open output folder error", details)

    def _show_input_error(
        self, problem: str, action: str, technical: str | None = None
    ) -> None:
        """Show validation feedback in both status bar and dialog."""

        details = error_messages_format("Checking settings", problem, action, technical)
        self._status.set(problem)
        self._append_log(details)
        messagebox.showwarning("Action needed", details)

    def _queue_message(self, message: tuple[Any, ...], lossy: bool = False) -> None:
        """Queue worker messages without allowing unbounded memory growth."""

        if lossy:
            try:
                self._messages.put_nowait(message)
            except queue.Full:
                pass
            return
        self._messages.put(message)

    def _append_log(self, text: str) -> None:
        """Append one readable line to the persistent activity log."""

        # Trim oldest lines so long runs do not grow the text buffer forever.
        while self._log_line_count >= _MAX_LOG_LINES:
            self._log.configure(state=tk.NORMAL)
            self._log.delete("1.0", "2.0")
            self._log.configure(state=tk.DISABLED)
            self._log_line_count -= 1

        self._log.configure(state=tk.NORMAL)
        self._log.insert(tk.END, text.rstrip() + "\n")
        self._log.see(tk.END)
        self._log.configure(state=tk.DISABLED)
        self._log_line_count += 1

    def _clear_group_table(self) -> None:
        """Remove all stale rows from the scan preview."""

        for item in self._groups_table.get_children():
            self._groups_table.delete(item)

    def _on_close(self) -> None:
        """Protect an active output from an accidental window close."""

        if self._busy_operation and not messagebox.askyesno(
            "Operation running",
            f"{self._busy_operation.capitalize()} is still running. Cancel and exit?",
        ):
            self._status.set(f"Continuing {self._busy_operation}.")
            return
        if self._busy_operation:
            self._cancel_event.set()
        self._root.destroy()


def web_ui_main() -> None:
    """Launch the Mediatovideo Converter desktop application."""

    root = tk.Tk()
    MediaToVideoApp(root)
    root.mainloop()


if __name__ == "__main__":
    web_ui_main()
