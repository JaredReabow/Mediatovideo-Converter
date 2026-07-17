#!/bin/sh
# Mediatovideo Converter macOS prerequisite installer and launcher.

STEP_NUMBER=0
PYTHON_COMMAND=""

installer_header() {
    clear
    printf '%s\n' '============================================================'
    printf '%s\n' ' Mediatovideo Converter - macOS startup'
    printf '%s\n' '============================================================'
    printf '%s\n' 'This window checks and installs the required components.'
    printf '%s\n\n' 'It remains open so progress and errors are always visible.'
}

installer_step() {
    STEP_NUMBER=$((STEP_NUMBER + 1))
    printf '[%s] %s\n' "$STEP_NUMBER" "$1"
}

installer_success() {
    printf '    OK: %s\n' "$1"
}

installer_error() {
    stage=$1
    problem=$2
    action=$3
    details=${4:-}
    printf '\n%s\n' '============================================================'
    printf '%s\n' ' STARTUP ERROR'
    printf '%s\n' '============================================================'
    printf 'Stage:   %s\n' "$stage"
    printf 'Problem: %s\n' "$problem"
    if [ -n "$details" ]; then
        printf 'Details: %s\n' "$details"
    fi
    printf 'What to do: %s\n\n' "$action"
    return 1
}

installer_load_homebrew() {
    if command -v brew >/dev/null 2>&1; then
        return 0
    fi
    for brew_path in /opt/homebrew/bin/brew /usr/local/bin/brew; do
        if [ -x "$brew_path" ]; then
            eval "$("$brew_path" shellenv)"
            return 0
        fi
    done
    return 1
}

installer_find_python() {
    PYTHON_COMMAND=""
    candidates=""
    if installer_load_homebrew; then
        candidates="$(brew --prefix)/bin/python3"
    fi
    candidates="$candidates /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3"
    for candidate in $candidates; do
        if [ -x "$candidate" ] && "$candidate" -c 'import sys, tkinter; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
            PYTHON_COMMAND=$candidate
            return 0
        fi
    done
    if command -v python3 >/dev/null 2>&1 && python3 -c 'import sys, tkinter; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
        PYTHON_COMMAND=$(command -v python3)
        return 0
    fi
    return 1
}

installer_install_homebrew() {
    installer_step 'Homebrew is required for missing components; installing Homebrew.'
    if ! command -v curl >/dev/null 2>&1; then
        installer_error \
            'Installing Homebrew' \
            'The macOS curl download tool is unavailable.' \
            'Install the macOS Command Line Tools, then run run_macos.command again.'
        return 1
    fi
    if ! /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"; then
        installer_error \
            'Installing Homebrew' \
            'The official Homebrew installer did not complete.' \
            'Check the internet connection and any password prompt above, then run this launcher again.'
        return 1
    fi
    if ! installer_load_homebrew; then
        installer_error \
            'Verifying Homebrew' \
            'Homebrew finished installing but its brew command could not be found.' \
            'Restart the Mac, then run run_macos.command again.'
        return 1
    fi
    installer_success 'Homebrew is installed and available.'
}

installer_require_homebrew() {
    if installer_load_homebrew; then
        installer_success 'Homebrew is available.'
        return 0
    fi
    installer_install_homebrew
}

installer_install_python() {
    installer_step 'Python 3.9+ with Tkinter was not found; installing python-tk.'
    if ! installer_require_homebrew; then
        return 1
    fi
    if ! brew install python-tk; then
        installer_error \
            'Installing Python and Tkinter' \
            'Homebrew could not install the python-tk formula.' \
            'Check the internet connection, available disk space, and Homebrew error above, then retry.'
        return 1
    fi
    if ! installer_find_python; then
        installer_error \
            'Verifying Python and Tkinter' \
            'python-tk installed, but a compatible Python with Tkinter still cannot be loaded.' \
            'Run brew doctor in Terminal, correct its reported problems, then run this launcher again.'
        return 1
    fi
    installer_success 'Python and Tkinter are installed and working.'
}

installer_find_video_tools() {
    command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1
}

installer_install_ffmpeg() {
    installer_step 'FFmpeg or FFprobe was not found; installing FFmpeg.'
    if ! installer_require_homebrew; then
        return 1
    fi
    if ! brew install ffmpeg; then
        installer_error \
            'Installing FFmpeg' \
            'Homebrew could not install FFmpeg.' \
            'Check the internet connection, available disk space, and Homebrew error above, then retry.'
        return 1
    fi
    if ! installer_find_video_tools; then
        installer_error \
            'Verifying FFmpeg' \
            'FFmpeg installed, but both ffmpeg and ffprobe could not be found.' \
            'Run brew doctor in Terminal, correct its reported problems, then run this launcher again.'
        return 1
    fi
    installer_success 'FFmpeg and FFprobe are installed and working.'
}

install_macos_prerequisites() {
    installer_step 'Checking Python 3.9+ and Tkinter.'
    if installer_find_python; then
        installer_success "Compatible Python and Tkinter found at $PYTHON_COMMAND."
    elif ! installer_install_python; then
        return 1
    fi

    installer_step 'Checking FFmpeg and FFprobe.'
    if installer_find_video_tools; then
        installer_success 'FFmpeg and FFprobe found.'
    elif ! installer_install_ffmpeg; then
        return 1
    fi
    installer_success 'No additional Python packages are required.'
}

install_macos_and_run() {
    installer_header
    if ! install_macos_prerequisites; then
        return 1
    fi
    installer_step 'Starting Mediatovideo Converter.'
    "$PYTHON_COMMAND" "$SCRIPT_DIRECTORY/run_app.py"
    exit_code=$?
    if [ "$exit_code" -ne 0 ]; then
        installer_error \
            'Running Mediatovideo Converter' \
            'The application stopped unexpectedly.' \
            'Read the error shown above. Run this launcher again after correcting it.' \
            "Application exit code: $exit_code"
        return 1
    fi
    printf '\n'
    installer_success 'Mediatovideo Converter closed normally.'
}
