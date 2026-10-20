#!/bin/bash
# Installs the [dev] extra into .venv for Claude Code cloud sessions, so
# pytest, ruff and mypy are ready when the session starts. Local sessions
# are left alone: contributors manage their own environments.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

if command -v uv >/dev/null 2>&1; then
  [ -x .venv/bin/python ] || uv venv --quiet .venv
  uv pip install --quiet --python .venv/bin/python -e ".[dev]"
else
  [ -x .venv/bin/python ] || python3 -m venv .venv
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -e ".[dev]"
fi
