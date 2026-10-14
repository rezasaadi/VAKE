#!/usr/bin/env bash
set -euo pipefail
script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec "${VAKE_PYTHON:-python3}" "$script_dir/reproduce.py" --stage build "$@"
