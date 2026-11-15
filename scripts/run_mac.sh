#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

# Uso: scripts/run_mac.sh [modello-ollama]   (avvio in sviluppo, senza Docker: API :8000, interfaccia :3000)
MODEL="${1:-${AUDIENCE_OLLAMA_MODEL:-qwen3.5:4b}}"
export AUDIENCE_OLLAMA_MODEL="$MODEL"
mkdir -p artifacts

# Prima esecuzione: ./start.sh crea l'ambiente Python, installa le dipendenze e prepara l'interfaccia.
if [[ ! -x .venv/bin/python ]]; then
  echo "Ambiente Python mancante: lo preparo con ./start.sh (la prima volta ci vuole qualche minuto)."
  exec ./start.sh
fi
# Dipendenze cambiate dopo un aggiornamento del codice (es. cifratura delle chiavi): le allineo.
if ! .venv/bin/python -c "import cryptography" >/dev/null 2>&1; then
  echo "Aggiorno le dipendenze Python…"
  .venv/bin/python -m pip install --quiet -c requirements.lock -e .
fi
if [[ ! -d frontend/node_modules ]]; then
  echo "Installo le dipendenze dell'interfaccia…"
  (cd frontend && npm ci --no-audit --no-fund --loglevel=error)
fi

# Ollama (facoltativo): lo avvio se è installato ma spento, e lo fermo all'uscita solo se l'ho avviato io.
ollama_pid=""
if command -v ollama >/dev/null 2>&1 && ! curl -fsS --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  OLLAMA_NO_CLOUD=1 ollama serve > artifacts/ollama.log 2>&1 &
  ollama_pid=$!
fi

stop_tree() {
  local pid="$1" child
  for child in $(pgrep -P "$pid" || true); do
    stop_tree "$child"
  done
  kill "$pid" 2>/dev/null || true
}

# Check both ports before stopping anything; never stop another project's server.
previous_pids=""
for port in 8000 3000; do
  for pid in $(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null || true); do
    process_dir=$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' || true)
    process_command=$(ps -p "$pid" -o command= || true)
    if [[ "$port" == 8000 && "$process_dir" == "$PWD" && "$process_command" == *"-m audience_simulator.cli serve"* ]]; then
      previous_pids="$previous_pids $pid"
    elif [[ "$port" == 3000 && "$process_dir" == "$PWD/frontend" && "$process_command" == *"next-server"* ]]; then
      parent_pid=$(ps -p "$pid" -o ppid= | tr -d ' ')
      parent_command=$(ps -p "$parent_pid" -o command= || true)
      if [[ "$parent_command" == *"$PWD/frontend/node_modules/"*"next dev"* ]]; then
        previous_pids="$previous_pids $parent_pid"
      else
        previous_pids="$previous_pids $pid"
      fi
    else
      echo "Porta $port occupata da un altro processo (PID $pid): non lo arresto." >&2
      exit 1
    fi
  done
done
for pid in $previous_pids; do
  echo "Arresto la precedente istanza (PID $pid)…"
  stop_tree "$pid"
done
for port in 8000 3000; do
  for attempt in {1..50}; do
    if ! lsof -nP -iTCP:"$port" -sTCP:LISTEN -t >/dev/null 2>&1; then
      break
    fi
    if [[ "$attempt" == 50 ]]; then
      echo "La porta $port non si è liberata; riavvio annullato." >&2
      exit 1
    fi
    sleep 0.2
  done
done

mkdir -p artifacts

.venv/bin/python -m audience_simulator.cli serve > artifacts/api.log 2>&1 &
api_pid=$!

npm --prefix frontend run dev > artifacts/web.log 2>&1 &
web_pid=$!

cleanup() {
  stop_tree "$api_pid"
  stop_tree "$web_pid"
  [[ -z "$ollama_pid" ]] || stop_tree "$ollama_pid"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

for url in http://127.0.0.1:8000/api/v1/health http://127.0.0.1:3000; do
  for attempt in {1..60}; do
    if curl --fail --silent --max-time 2 "$url" >/dev/null; then
      break
    fi
    if ! kill -0 "$api_pid" 2>/dev/null || ! kill -0 "$web_pid" 2>/dev/null || [[ "$attempt" == 60 ]]; then
      echo "Avvio fallito: controlla artifacts/api.log e artifacts/web.log." >&2
      exit 1
    fi
    sleep 0.5
  done
done

echo "Audience Simulator started"
echo "Model: $AUDIENCE_OLLAMA_MODEL"
echo "Frontend: http://127.0.0.1:3000"
echo "Backend:  http://127.0.0.1:8000"
echo "Logs: artifacts/api.log and artifacts/web.log"

wait
