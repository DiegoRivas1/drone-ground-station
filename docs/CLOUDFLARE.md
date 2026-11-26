# Estación de tierra en Internet con Cloudflare Tunnel

Sirve para que el teléfono (con datos móviles, fuera de tu Wi-Fi) y cualquier navegador lleguen a la
estación que corre **en tu PC**. No se sube nada a Cloudflare: el túnel solo reenvía el tráfico a
`localhost:8000`. La PC tiene que estar encendida, con el servidor y el túnel abiertos.

> Cloudflare Workers/Pages **no** sirven para esto: el backend usa SQLite, ffmpeg y archivos locales.

## Seguridad: por qué hay token

Con el túnel abierto, **cualquiera que conozca la URL** llega a tu servidor. Por eso el backend exige un
token (`backend/app/security.py`):

| Quién | Cómo se identifica |
|---|---|
| App Android | cabecera `X-Station-Token: <token>` en cada petición |
| Panel web | pantalla de acceso una vez → cookie `HttpOnly` (`Secure` y `SameSite=Strict` bajo https) |
| Scripts de prueba | `--token` o variable `STATION_TOKEN` |

- Protegidos: `/api/*`, `/ws/*`, `/docs`, `/redoc`, `/openapi.json`.
- Públicos: el panel estático (HTML/JS/CSS, sin datos), `/api/health` (solo `{"status":"ok"}`) y `/api/auth/*`.
- 10 intentos con token incorrecto en 60 s bloquean ese origen durante un minuto (429), incluso con el token bueno.
- Sin token configurado el servidor funciona como antes (solo red local) y **`run_tunnel` se niega a abrir el túnel**.
- El token **no va a git** (`backend/station_token.txt` está en `.gitignore`). No lo pegues en chats ni capturas.
  Si se filtra: `python tools/make_token.py --nuevo`, reinicia el servidor y actualiza la app.

## Paso a paso (Windows)

1. Instala el cliente del túnel (una vez): `winget install --id Cloudflare.cloudflared` y abre una terminal nueva.
2. Crea el token (una vez): `python tools\make_token.py` → muestra el token y lo guarda en `backend\station_token.txt`.
3. Arranca el servidor: `run_server.bat`. Debe decir `Acceso: con token`.
4. En otra ventana: `run_tunnel.bat`. Aparece una URL `https://algo-aleatorio.trycloudflare.com`.
5. Abre esa URL en un navegador: te pide el token y entra al panel.
6. En la app, esa URL será la dirección del servidor (cuando la rama de la app con soporte de HTTPS y token esté lista).

Prueba rápida sin la app, con el simulador:

```
python tools\simulate_drone.py --url https://algo-aleatorio.trycloudflare.com --token <token> --seconds 30
```

## Límites que conviene conocer

- **La URL cambia cada vez** que abres el túnel rápido, y no tiene garantía de disponibilidad. Para una URL fija
  hace falta un *túnel con nombre* y un dominio tuyo en Cloudflare (se puede sumar Cloudflare Access encima).
- **Tamaño de subida:** Cloudflare limita el cuerpo de cada petición (alrededor de 100 MB en el plan gratuito).
  Los bloques de video en vivo (~0,5 s) son muy pequeños, pero el respaldo que sube el archivo **completo** cuando
  hubo pérdidas puede superarlo en tramos largos. En ese caso la copia íntegra queda en el teléfono.
- **Latencia:** el video y la telemetría pasan por Cloudflare y por datos móviles: espera más retraso que en Wi-Fi local.
- **Mientras vuelas**, no dependas de esto para controlar el dron: el control sigue siendo el mando; la estación solo recibe datos.
- Cierra el túnel (`Ctrl+C` / cierra la ventana) cuando no lo uses.

## Variables opcionales

| Variable | Para qué |
|---|---|
| `STATION_TOKEN` | token por variable de entorno (tiene prioridad sobre el archivo) |
| `STATION_CORS_ORIGINS` | orígenes permitidos por CORS, separados por comas. Por defecto ninguno: el panel va por el mismo origen |

## Pruebas

```
cd backend
pip install pytest httpx
python -m pytest tests -q
```
