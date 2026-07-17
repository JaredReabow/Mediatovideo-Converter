#!/bin/sh
cd "$(dirname "$0")"

# Prefer a normal desktop Python over tool-specific environments (for example,
# PlatformIO's Python), which often omit the Tkinter GUI module.
for python_candidate in \
    /opt/homebrew/bin/python3 \
    /usr/local/bin/python3 \
    /usr/bin/python3 \
    python3
do
    if command -v "$python_candidate" >/dev/null 2>&1 && \
        "$python_candidate" -c "import tkinter" >/dev/null 2>&1
    then
        exec "$python_candidate" run_app.py
    fi
done

echo "Mediatovideo Converter needs Python 3.9 or newer with Tkinter."
echo "Install Python from https://www.python.org/downloads/ and try again."
printf "Press Return to close..."
read answer
