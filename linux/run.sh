#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$ROOT/linux${PYTHONPATH:+:$PYTHONPATH}"
export CODENOTCH_DEMO="${CODENOTCH_DEMO:-0}"

# The host selects XWayland for GNOME before importing GTK, including when
# the desktop session exports GDK_BACKEND=wayland.
export WEBKIT_DISABLE_COMPOSITING_MODE="${WEBKIT_DISABLE_COMPOSITING_MODE:-1}"

exec python3 -m codenotch "$@"
