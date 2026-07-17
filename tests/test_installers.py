"""Static contract tests for native prerequisite launchers."""

from __future__ import annotations

import unittest
from pathlib import Path


class InstallerContractTests(unittest.TestCase):
    """Ensure both platforms keep their install and error contracts."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.windows = (cls.root / "install_windows.ps1").read_text(encoding="utf-8")
        cls.macos = (cls.root / "install_macos.sh").read_text(encoding="utf-8")

    def test_windows_installs_and_verifies_all_runtime_components(self) -> None:
        self.assertIn("function Install-WindowsPrerequisites", self.windows)
        self.assertIn("9NQ7512CXL7T", self.windows)
        self.assertIn("Gyan.FFmpeg", self.windows)
        self.assertIn("import sys, tkinter", self.windows)
        self.assertIn("Find-VideoTools", self.windows)
        self.assertIn("Stage:", self.windows)
        self.assertIn("Problem:", self.windows)
        self.assertIn("What to do:", self.windows)

    def test_macos_installs_and_verifies_all_runtime_components(self) -> None:
        self.assertIn("install_macos_prerequisites()", self.macos)
        self.assertIn("brew install python-tk", self.macos)
        self.assertIn("brew install ffmpeg", self.macos)
        self.assertIn("import sys, tkinter", self.macos)
        self.assertIn("installer_find_video_tools", self.macos)
        self.assertIn("Stage:", self.macos)
        self.assertIn("Problem:", self.macos)
        self.assertIn("What to do:", self.macos)

    def test_run_launchers_call_native_installers(self) -> None:
        windows_launcher = (self.root / "run_windows.bat").read_text(encoding="utf-8")
        macos_launcher = (self.root / "run_macos.command").read_text(encoding="utf-8")
        self.assertIn("install_windows.ps1", windows_launcher)
        self.assertIn("install_macos.sh", macos_launcher)
        self.assertIn("Press Return", macos_launcher)
        self.assertIn("pause", windows_launcher.casefold())


if __name__ == "__main__":
    unittest.main()
