#!/usr/bin/env bash
set -euo pipefail
cd /opt/vake

action="${1:-ui}"
if [[ "$#" -gt 0 ]]; then shift; fi
case "$action" in
  ui)

    exec python3 -m ui.server --bind 0.0.0.0 --port "${VAKE_UI_PORT:-8765}" "$@"
    ;;
  build)
    exec bash scripts/build.sh --offline "$@"
    ;;
  test)
    exec bash scripts/test.sh --offline "$@"
    ;;
  demo)
    exec bash scripts/demo.sh "$@"
    ;;
  reproduce)
    exec bash scripts/reproduce.sh --offline "$@"
    ;;
  check|export|verify)
    exec "${VAKE_CLI_BIN:-./target/debug/vake}" "$action" "$@"
    ;;
  shell)
    exec bash "$@"
    ;;
  *)
    echo "Unknown action: $action" >&2
    echo "Expected ui, build, test, demo, reproduce, check, export, verify, or shell" >&2
    exit 64
    ;;
esac
