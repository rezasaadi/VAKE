#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec "${VAKE_PYTHON:-python3}" -m ui.server "$@"
