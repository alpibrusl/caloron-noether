#!/bin/bash
# ==========================================================================
# sandbox-passthrough.sh — No-op fallback when bubblewrap is unavailable
#
# Usage: sandbox-passthrough.sh <worktree-path> <command> [args...]
#
# Runs the command inside the worktree with no isolation. Used on macOS and
# other systems where bwrap is not available. On Linux, sandbox-agent.sh is
# preferred.
# ==========================================================================
set -euo pipefail

WORKTREE="${1:?Usage: sandbox-passthrough.sh <worktree-path> <command> [args...]}"
shift

if [ $# -eq 0 ]; then
    echo "Usage: sandbox-passthrough.sh <worktree-path> <command> [args...]"
    exit 1
fi

cd "$WORKTREE"
export CALORON_SANDBOXED="0"
exec "$@"
