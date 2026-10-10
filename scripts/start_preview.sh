#!/usr/bin/env bash
# One origin serves the built interface and API. No external search is made at startup.
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

if [[ ! -x .venv/bin/uvicorn ]]; then
  printf '%s\n' 'Backend dependencies are missing. Follow README.md to create .venv and install backend/requirements-lock.txt.' >&2
  exit 1
fi
if [[ ! -d frontend/node_modules ]]; then
  printf '%s\n' 'Frontend dependencies are missing. Run npm --prefix frontend ci.' >&2
  exit 1
fi

npm --prefix frontend run build
export PYTHONPATH="$repo_dir/backend${PYTHONPATH:+:$PYTHONPATH}"
printf 'Starting VersionVerdict interface and API on port %s.\n' "${PORT:-3000}"
exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-3000}" --workers 1
