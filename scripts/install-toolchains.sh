#!/usr/bin/env bash
set -euo pipefail
command -v rustup >/dev/null || { echo 'Install Rustup first.' >&2; exit 1; }
command -v elan >/dev/null || { echo 'Install Elan first.' >&2; exit 1; }
rustup toolchain install 1.97.1 --profile minimal
elan toolchain install leanprover/lean4:v4.34.1
