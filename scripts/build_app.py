"""Build a native-looking one-file executable with PyInstaller."""

from __future__ import annotations

import subprocess
import sys


def build_app_main() -> int:
    """Invoke PyInstaller through the active Python environment."""

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        "Mediatovideo Converter",
        "run_app.py",
    ]
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(build_app_main())
