#!/usr/bin/env bash
# Install or remove the `nexus` command on the PATH, so the CLI runs without
# `uv run`. The install is editable: it follows this checkout, no reinstall
# needed after a code change (only after moving the repo).
#
# Usage: scripts/install_cli.sh install|uninstall
set -euo pipefail

cd "$(dirname "$0")/.."

case "${1:-}" in
    install)
        uv tool install --editable --force .
        echo "Installed: $(command -v nexus || echo 'nexus (add $(uv tool dir --bin) to your PATH)')"
        ;;
    uninstall)
        uv tool uninstall nexus
        ;;
    *)
        echo "Usage: $0 install|uninstall" >&2
        exit 2
        ;;
esac
