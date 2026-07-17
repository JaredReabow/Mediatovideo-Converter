"""Convenient source-checkout launcher for Mediatovideo Converter."""

from __future__ import annotations

import sys


def run_app_main() -> int:
    """Launch the GUI or print a clear dependency error to the terminal."""

    try:
        from mediatovideo_converter.WEB_UI import web_ui_main
    except ModuleNotFoundError as error:
        if error.name not in {"tkinter", "_tkinter"}:
            raise
        print(
            "\nSTARTUP ERROR\n"
            "=============\n"
            "Stage: Loading the graphical interface\n\n"
            "Problem: This Python installation does not include Tkinter.\n\n"
            "What to do: Close this window and start the application with "
            "run_windows.bat or run_macos.command. The launcher will install "
            "a compatible Python and Tkinter automatically.\n\n"
            f"Technical detail: {error}",
            file=sys.stderr,
        )
        return 2

    web_ui_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(run_app_main())
