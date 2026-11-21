#!/bin/sh
# Starts DiskStrata and opens your browser. Press Ctrl+C to stop it.
# macOS: double-click this file in Finder. Linux: run ./DiskStrata.command
cd "$(dirname "$0")" || exit 1
exec python3 -m diskstrata "$@"
