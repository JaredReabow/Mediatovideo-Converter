# Changelog

All notable changes to Mediatovideo Converter are recorded here.

## [0.2.1] - 2026-07-17

### Changed

- Bounded the GUI worker-message queue and activity log so very large camera
  exports cannot grow interface memory without limit.
- Throttled validation and encoding progress events while retaining final
  progress updates.
- Grouped discovered clips during directory traversal instead of retaining a
  second complete list of every source file.
- Updated application renders to show version 0.2.1.

## [0.2.0] - 2026-07-17

### Added

- Windows prerequisite installer using WinGet and Python's install manager.
- macOS prerequisite installer using an existing compatible Python or Homebrew.
- Automatic checks and post-install verification for Python 3.9+, Tkinter,
  FFmpeg, and FFprobe on every launcher start.
- Visible startup terminal progress, installation stages, and recovery actions.
- Structured Stage, Problem, What to do, and Technical detail error messages.
- Installer and error-message regression tests.

### Changed

- Scan, conversion, output-folder, FFmpeg, and direct-launch failures now explain
  both the likely cause and the next action.
- Updated privacy-safe application renders to show version 0.2.0.

### Documentation

- Added automatic and manual prerequisite installation instructions.
- Added privacy-safe application renders made only with fictional interface
  state for the repository and original Gist.

## [0.1.0] - 2026-07-17

### Added

- Cross-platform Tkinter GUI for Windows and macOS.
- Recursive `.media` scanning with `YYYY/MM/DD` recognition.
- Per-day and per-child-folder grouping.
- Mirrored-date and flat output layouts.
- MKV stream-copy and MP4 H.264/AAC conversion modes.
- Visible scan, validation, current-video, and overall progress.
- Safe cancellation, corrupt-file skipping, collision-free naming, and logs.
- PyInstaller build helper, launchers, documentation, and unit tests.
- Launch-time detection of a Python installation that includes Tkinter.
