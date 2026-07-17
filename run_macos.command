#!/bin/sh
SCRIPT_DIRECTORY=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export SCRIPT_DIRECTORY
cd "$SCRIPT_DIRECTORY" || exit 1

# Keep the terminal visible so installation progress and errors can be read.
. "$SCRIPT_DIRECTORY/install_macos.sh"
install_macos_and_run
APP_EXIT_CODE=$?

printf '\nPress Return to close this window...'
read answer
exit "$APP_EXIT_CODE"
