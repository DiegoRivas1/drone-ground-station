"""Crea el token de acceso de la estación (backend/station_token.txt) si no existe.

    python tools/make_token.py          # crea uno nuevo si falta y lo muestra
    python tools/make_token.py --nuevo  # reemplaza el existente (hay que actualizar la app)

El archivo está en .gitignore. Copia el token a la app Android y no lo compartas por chat.
"""
import secrets
import sys
from pathlib import Path

archivo = Path(__file__).resolve().parent.parent / "backend" / "station_token.txt"

if archivo.exists() and "--nuevo" not in sys.argv:
    print(f"Ya existe un token en {archivo}\n(usa --nuevo para reemplazarlo)\n")
    print(archivo.read_text(encoding="utf-8").strip())
else:
    token = secrets.token_urlsafe(32)
    archivo.write_text(token + "\n", encoding="utf-8")
    print(f"Token guardado en {archivo}\n")
    print(token)
print("\nReinicia el servidor para que lo use.")
