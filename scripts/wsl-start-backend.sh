#!/usr/bin/env bash
# FastAPI for local Vite: dev proxy in vite.config.ts points to localhost:7860 in THIS machine.
# If Vite runs in WSL, the API must also run in WSL (not only on Windows).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
exec ../.venv/bin/uvicorn main:app --host 0.0.0.0 --port 7860
