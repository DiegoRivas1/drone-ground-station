#!/usr/bin/env sh
# Arranca la estación de tierra (FastAPI) en el puerto 8000, visible en la red local.
set -e
cd "$(dirname "$0")/backend"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
fi
.venv/bin/python -m pip install -q -r requirements.txt
exec .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
