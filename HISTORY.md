# Project History

This file is append-only. Add new entries at the end; do not rewrite earlier
project history.

## 2026-07-17 — Version 0.1.0

- Started from JaredReabow's fork of `media-to-mkv-converter.sh`.
- Replaced the interactive workflow with the new Mediatovideo Converter Python
  GUI while retaining the original shell proof of concept for reference.
- Added cross-platform scanning, grouping, FFmpeg conversion, progress,
  cancellation, tests, packaging support, and user documentation.

## 2026-07-17 — Application renders and Gist handoff

- Added two privacy-safe interface renders using only fictional state.
- Prepared the original Gist to describe this graphical implementation and
  direct readers to the complete GitHub repository.

## 2026-07-17 — Version 0.2.0

- Added native Windows and macOS prerequisite installers that run before the
  app, install missing Python, Tkinter, FFmpeg, and FFprobe components, and
  verify them before launch.
- Kept a terminal visible throughout startup so installation progress and
  failures never occur without feedback.
- Standardised installation, scan, conversion, and filesystem errors around a
  clear stage, problem, recovery action, and technical detail.
- Added installer/error regression tests and updated the documentation renders.

## 2026-07-17 — Version 0.2.1

- Published the queued performance work for large exports: bounded UI messages
  and logs, throttled high-frequency progress events, and single-pass scanning.
- Preserved final scan/conversion feedback while reducing avoidable memory and
  interface-update pressure.
