#!/bin/bash
# Double-click (macOS) or run from a terminal to open the Agent Lab in a browser.
# Everything stays on this machine: the server binds loopback only.
cd "$(dirname "$0")/standalone" || exit 1

PY=${PYTHON:-python3}
command -v "$PY" >/dev/null 2>&1 || PY=python
command -v "$PY" >/dev/null 2>&1 || {
  echo "No Python found. Install Python 3, then try again."; read -r; exit 1; }

if ! "$PY" -c "import requests, pptx, openpyxl" >/dev/null 2>&1; then
  echo "Installing the agent's Python packages (one time)..."
  "$PY" -m pip install --quiet requests python-pptx openpyxl || {
    echo; echo "Install failed. Run:  $PY -m pip install requests python-pptx openpyxl"
    read -r; exit 1; }
fi

# The lab talks to a local Ollama by default. For the llama.cpp path instead,
# see standalone/llamacpp/README.md — start llama-server + ollama_shim.py and
# leave Ollama stopped.
if ! curl -s -m 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "Starting Ollama..."
  (ollama serve >/dev/null 2>&1 &) 2>/dev/null
  sleep 2
fi

exec "$PY" -m webui.server
