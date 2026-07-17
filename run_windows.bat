@echo off
py -3 -c "import tkinter" >nul 2>&1
if not errorlevel 1 (
    py -3 run_app.py
    if errorlevel 1 pause
    exit /b
)

python -c "import tkinter" >nul 2>&1
if not errorlevel 1 (
    python run_app.py
    if errorlevel 1 pause
    exit /b
)

echo Mediatovideo Converter needs Python 3.9 or newer with Tkinter.
echo Install Python from https://www.python.org/downloads/ and try again.
pause
