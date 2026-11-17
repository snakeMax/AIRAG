#!/usr/bin/env bash
# Run AIRAG from source (macOS/Linux, for development).
set -e
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/python -m pip install -q --disable-pip-version-check -r requirements.txt
exec .venv/bin/python -m airag "$@"
