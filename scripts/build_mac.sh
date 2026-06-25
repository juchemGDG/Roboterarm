#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

if [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
  PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
else
  PYTHON_BIN="python3"
fi

"$PYTHON_BIN" -m pip install -r requirements.txt -r requirements-build.txt
"$PYTHON_BIN" -m PyInstaller --noconfirm --clean roboterarm_gui.spec

APP_PATH="dist/RoboterarmSteuerung.app"
DMG_PATH="dist/RoboterarmSteuerung-macOS.dmg"

if [[ ! -d "$APP_PATH" ]]; then
  echo "App-Bundle nicht gefunden: $APP_PATH"
  exit 1
fi

if [[ -f "$DMG_PATH" ]]; then
  rm -f "$DMG_PATH"
fi

hdiutil create \
  -volname "RoboterarmSteuerung" \
  -srcfolder "$APP_PATH" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

echo "Fertig: $DMG_PATH"
