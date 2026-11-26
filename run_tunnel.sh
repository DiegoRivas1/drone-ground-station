#!/usr/bin/env bash
# Expone la estación a Internet con un túnel de Cloudflare (URL https://....trycloudflare.com).
# Antes: python tools/make_token.py  y arrancar el servidor (run_server.sh). Guía: docs/CLOUDFLARE.md
cd "$(dirname "$0")"

if [ ! -s backend/station_token.txt ] && [ -z "${STATION_TOKEN:-}" ]; then
  echo "NO se abre el túnel: la estación no tiene token y quedaría abierta a todo Internet."
  echo "Crea uno con:  python tools/make_token.py   y reinicia run_server.sh"
  exit 1
fi
command -v cloudflared >/dev/null || { echo "Instala cloudflared: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"; exit 1; }

echo "Cuando aparezca la URL https://....trycloudflare.com, esa es la dirección pública."
exec cloudflared tunnel --url http://localhost:8000
