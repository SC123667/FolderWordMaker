#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
python -m pip install -r requirements.txt
pyinstaller --noconfirm --windowed --paths src --name "目录汇总Word" run_app.py
