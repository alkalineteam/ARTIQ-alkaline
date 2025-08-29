#!/usr/bin/env bash
set -euo pipefail

# Enable repository local git hooks located in .githooks/
# Safe to re-run (idempotent).

HOOKS_DIR=".githooks"

if [ ! -d "$HOOKS_DIR" ]; then
  echo "Directory $HOOKS_DIR not found (are you in the repo root?)" >&2
  exit 1
fi

git config core.hooksPath "$HOOKS_DIR"
chmod +x "$HOOKS_DIR"/* || true
echo "Git hooks enabled (core.hooksPath=$HOOKS_DIR)"
echo "Pre-commit hash enforcement active."
