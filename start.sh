#!/usr/bin/env bash
# Audience Simulator: un solo comando per installare, preparare e avviare tutto in locale.
#   ./start.sh                      avvia l'app (la prima volta installa le dipendenze)
#   SKIP_MODEL_DOWNLOAD=1 ./start.sh  non scaricare il modello locale all'avvio
#   AUDIENCE_OLLAMA_MODEL=qwen3.5:9b ./start.sh   usa un altro modello locale
set -euo pipefail
cd "$(dirname "$0")"

MODEL="${AUDIENCE_OLLAMA_MODEL:-qwen3.5:4b}"
export AUDIENCE_OLLAMA_MODEL="$MODEL"
STATE=".venv/.installed"
mkdir -p artifacts

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[33m%s\033[0m\n' "$*" >&2; }
die() { printf '\033[31m%s\033[0m\n' "$*" >&2; exit 1; }
hash_of() { cat "$@" | (shasum -a 256 2>/dev/null || sha256sum) | cut -d' ' -f1; }

# --- 1. Python 3.12+ e Node 20.9+ ------------------------------------------------------------
PYTHON=""
for candidate in "${AUDIENCE_PYTHON:-}" python3.13 python3.12 python3; do
  [[ -n "$candidate" ]] && command -v "$candidate" >/dev/null 2>&1 || continue
  if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)'; then PYTHON="$candidate"; break; fi
done
[[ -n "$PYTHON" ]] || die "Serve Python 3.12 o più recente. macOS: brew install python@3.12 · Linux: apt install python3.12 python3.12-venv"
command -v node >/dev/null 2>&1 || die "Serve Node.js 20.9 o più recente. Scaricalo da https://nodejs.org (oppure: brew install node)"
node -e 'const [a,b]=process.versions.node.split(".").map(Number); process.exit(a>20||(a===20&&b>=9)?0:1)' \
  || die "Node.js troppo vecchio ($(node --version)): serve la 20.9 o più recente."

# --- 2. Dipendenze Python (solo se cambiate) --------------------------------------------------
if [[ ! -x .venv/bin/python ]]; then
  say "Creo l'ambiente Python…"
  "$PYTHON" -m venv .venv
fi
WANT="$(hash_of pyproject.toml requirements.lock)"
if [[ ! -f "$STATE" || "$(cat "$STATE")" != "$WANT" ]]; then
  say "Installo le dipendenze Python (solo la prima volta)…"
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -c requirements.lock -e .
  echo "$WANT" > "$STATE"
fi

# --- 3. Dipendenze e build del frontend (solo se cambiati) ------------------------------------
WEB_STATE="frontend/.next/.built"
WANT_WEB="$(hash_of frontend/package-lock.json frontend/package.json frontend/next.config.ts $(find frontend/app frontend/components frontend/lib -type f | sort))"
if [[ ! -f "$WEB_STATE" || "$(cat "$WEB_STATE")" != "$WANT_WEB" ]]; then
  say "Preparo l'interfaccia (solo la prima volta, circa un minuto)…"
  (cd frontend && npm ci --no-audit --no-fund --loglevel=error && npm run build >"../artifacts/web-build.log" 2>&1) \
    || { tail -20 artifacts/web-build.log >&2; die "Build dell'interfaccia non riuscita: vedi artifacts/web-build.log"; }
  echo "$WANT_WEB" > "$WEB_STATE"
fi

# --- 4. Motore AI locale (Ollama) -------------------------------------------------------------
# Opzionale: senza Ollama l'app parte lo stesso e dà una stima statistica dai dati storici.
OLLAMA_PID=""
if command -v ollama >/dev/null 2>&1; then
  if ! curl -fsS --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    say "Avvio Ollama…"
    OLLAMA_NO_CLOUD=1 ollama serve >artifacts/ollama.log 2>&1 &
    OLLAMA_PID=$!
    for _ in $(seq 1 30); do
      curl -fsS --max-time 1 http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break
      sleep 0.5
    done
  fi
  if curl -fsS --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    if [[ "${SKIP_MODEL_DOWNLOAD:-0}" != "1" ]] && ! ollama list 2>/dev/null | awk 'NR>1 && $1 !~ /embed/ {found=1} END {exit !found}'; then
      say "Scarico il modello $MODEL (circa 3 GB, una volta sola). Puoi anche farlo dopo dall'app."
      ollama pull "$MODEL" || warn "Download non riuscito: potrai riprovare dall'app, in Impostazioni."
    fi
  else
    warn "Ollama è installato ma non risponde: apri l'app Ollama. L'app parte comunque."
  fi
else
  warn "Ollama non trovato. È facoltativo: l'app funziona, ma senza le reazioni dei consumatori simulati."
  warn "Per usarlo: installa https://ollama.com/download e rilancia ./start.sh (oppure scarica il modello dall'app)."
fi

# --- 5. Porte libere --------------------------------------------------------------------------
free_port() {
  "$PYTHON" - "$1" <<'PY'
import socket, sys
port = int(sys.argv[1])
while True:
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", port)); print(port); break
        except OSError:
            port += 1
PY
}
API_PORT="$(free_port "${AUDIENCE_API_PORT:-8000}")"
WEB_PORT="$(free_port "${AUDIENCE_WEB_PORT:-3000}")"

# --- 6. Avvio ---------------------------------------------------------------------------------
stop_all() {
  trap - EXIT INT TERM
  [[ -n "${API_PID:-}" ]] && kill "$API_PID" 2>/dev/null || true
  [[ -n "${WEB_PID:-}" ]] && kill "$WEB_PID" 2>/dev/null || true
  [[ -n "$OLLAMA_PID" ]] && kill "$OLLAMA_PID" 2>/dev/null || true
}
trap stop_all EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

say "Avvio l'app…"
.venv/bin/python -m audience_simulator.cli bootstrap >artifacts/bootstrap.log 2>&1 \
  || { tail -20 artifacts/bootstrap.log >&2; die "Preparazione dei dati non riuscita: vedi artifacts/bootstrap.log"; }
.venv/bin/python -m audience_simulator.cli serve --port "$API_PORT" >artifacts/api.log 2>&1 &
API_PID=$!
(cd frontend && API_BASE_URL="http://127.0.0.1:$API_PORT" exec npx next start --hostname 127.0.0.1 --port "$WEB_PORT") >artifacts/web.log 2>&1 &
WEB_PID=$!

wait_for() {
  for _ in $(seq 1 120); do
    curl -fsS --max-time 2 "$1" >/dev/null 2>&1 && return 0
    kill -0 "$2" 2>/dev/null || return 1
    sleep 0.5
  done
  return 1
}
wait_for "http://127.0.0.1:$API_PORT/api/v1/health" "$API_PID" || { tail -20 artifacts/api.log >&2; die "Il backend non parte: vedi artifacts/api.log"; }
wait_for "http://127.0.0.1:$WEB_PORT" "$WEB_PID" || { tail -20 artifacts/web.log >&2; die "L'interfaccia non parte: vedi artifacts/web.log"; }

URL="http://127.0.0.1:$WEB_PORT"
say "Audience Simulator è pronto: $URL"
echo "Premi Ctrl+C per fermarlo. Log in artifacts/."
if [[ "${AUDIENCE_NO_BROWSER:-0}" != "1" ]]; then
  (open "$URL" 2>/dev/null || xdg-open "$URL" 2>/dev/null || true) &
fi
while kill -0 "$API_PID" 2>/dev/null && kill -0 "$WEB_PID" 2>/dev/null; do sleep 2; done
die "Un servizio si è fermato: controlla artifacts/api.log e artifacts/web.log"
