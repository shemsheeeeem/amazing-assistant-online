#!/bin/bash
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is not installed. Get it from https://www.python.org/downloads/ and run this again."
  read -r -p "Press Enter to close."
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "First run: setting up. This takes about a minute..."
  python3 -m venv .venv || { read -r -p "Could not create the Python environment. Press Enter to close."; exit 1; }
fi

.venv/bin/python -m pip install --quiet --disable-pip-version-check -r requirements.txt || {
  read -r -p "Could not install Flask. Check your internet connection. Press Enter to close."
  exit 1
}

HANAP_OPEN_BROWSER=1 .venv/bin/python app.py
