#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p artifacts
if [[ ! -x .venv/bin/python ]]; then
  "${AUDIENCE_PYTHON:-python3.12}" -m venv .venv
fi
.venv/bin/python -m pip install -c requirements.lock -e '.[dev]'
npm --prefix frontend ci
.venv/bin/python -m audience_simulator.cli bootstrap > artifacts/bootstrap.log
.venv/bin/python -m audience_simulator.cli serve > artifacts/api.log 2>&1 &
api_pid=$!
npm --prefix frontend run dev > artifacts/web.log 2>&1 &
web_pid=$!
trap 'kill "$api_pid" "$web_pid" 2>/dev/null || true' EXIT INT TERM
printf 'Audience Simulator: http://127.0.0.1:3000\nOllama must run locally; use scripts/models.sh in a separate terminal.\n'
wait
