#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p artifacts/ollama
export OLLAMA_NO_CLOUD=1
export OLLAMA_MODELS="$PWD/artifacts/ollama"
printf 'Start the project Ollama runtime. In another terminal: ollama pull qwen3.5:9b\n'
exec ollama serve
