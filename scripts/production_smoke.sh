#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "${PYTHON_BIN:-python3}" "$SCRIPT_DIR/production_smoke.py" "$@"
