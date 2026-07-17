@echo off
setlocal
title Mediatovideo Converter startup
cd /d "%~dp0"

echo Opening the Mediatovideo Converter prerequisite checker...
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_windows.ps1"
set "APP_EXIT_CODE=%ERRORLEVEL%"

echo.
if not "%APP_EXIT_CODE%"=="0" (
    echo Mediatovideo Converter could not start. Review the STARTUP ERROR above.
) else (
    echo Mediatovideo Converter finished normally.
)
echo.
pause
exit /b %APP_EXIT_CODE%
