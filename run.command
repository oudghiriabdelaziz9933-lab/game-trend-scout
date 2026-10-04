#!/bin/bash
# One-click launcher for macOS: creates the environment on first run, then starts the app.
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
    echo "First run: creating the Python environment, this takes a minute..."
    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install -r requirements.txt
else
    source .venv/bin/activate
fi
[ -f .env ] || cp .env.example .env
streamlit run app.py
