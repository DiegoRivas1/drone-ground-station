# drone-ground-station

Estación de tierra para el **DJI Mavic Air**: recibe telemetría, eventos y video desde la app
Android `dron-mavicair-telemetry` por Wi-Fi y los muestra en un panel web.

```
Mavic Air ──radio──► Control remoto ──USB──► Teléfono (app) ──Wi-Fi──► PC (FastAPI)
                                                                        ├── SQLite (vuelos, telemetría, eventos, rutas)
                                                                        ├── storage/videos/*.h264
                                                                        └── Panel web (mapa, telemetría, video en vivo)
```

## Recorridos e informe

**Guía paso a paso para novatos: [GUIA_RECORRIDOS.md](GUIA_RECORRIDOS.md).**

Pestaña **Recorrido** del panel: NUEVO RECORRIDO → NUEVO TRAMO → (● REC / ■ STOP en la app) → … →
FINALIZAR RECORRIDO → GENERAR INFORME. Cada tramo es la pareja (video, telemetría) de una grabación;
el informe se genera con el proyecto `dron_project_reconocimiento/inspeccion-dron`.

## Arrancar

Requisito: Python 3.10 o superior.

- **Windows:** doble clic en `run_server.bat` (la primera vez crea `backend/.venv` e instala dependencias).
- **Linux/Mac:** `./run_server.sh`

Manual:

```
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Al iniciar se imprime la IP de la PC, por ejemplo `http://192.168.1.50:8000`:

1. Abre esa dirección en el navegador → panel.
2. En la app, botón **PC: …** → escribe la misma dirección → Guardar. Arriba a la izquierda debe decir `PC: CONECTADA`.

> **Firewall de Windows:** la primera vez pregunta si permitir Python. Marca **Redes privadas**.
> Si el teléfono no conecta, comprueba que la red Wi-Fi está como *privada* y que el puerto 8000 está permitido.

## Panel web

- **Video en vivo:** al pulsar **● REC** en la app, el video se graba en el teléfono y a la vez se envía aquí.
  Se reproduce en el navegador (H.264 → JMuxer → MediaSource).
- **Telemetría:** batería, altitud, velocidad, rumbo, satélites/GPS, modo de vuelo.
- **Mapa:** posición del dron, traza del vuelo, capas satélite/mapa.
- **Ruta:** marca *Editar ruta*, haz clic en el mapa para poner puntos, **Guardar ruta** y **Activar**.
  En la app: **WP: CARGAR RUTA DEL PANEL** → **SUBIR AL DRON** → **INICIAR MISIÓN**.
- **Vuelos:** historial, traza de cada vuelo, eventos y exportación CSV.
- **Videos:** descarga `.h264` (o MP4 si `ffmpeg` está instalado en la PC).

Los mapas necesitan Internet para descargar las teselas; el resto funciona en red local sin Internet.

## Probar sin el dron

Con el servidor en marcha:

```
python tools/simulate_drone.py                       # telemetría + eventos (vuelo circular)
python tools/simulate_drone.py --video prueba.h264   # además, video en vivo desde un archivo
```

## API (resumen)

Documentación interactiva: `http://<ip>:8000/docs`

| Método | Ruta | Uso |
|---|---|---|
| GET | `/api/health` | Comprobación de conexión (la app la consulta cada 5 s) |
| POST | `/api/telemetry` | Lote de muestras `{flight_id, drone_model, samples[]}` |
| POST | `/api/events` | Evento de vuelo (TAKEOFF_START, MANUAL_STOP, LANDED, …) |
| GET | `/api/status` | Última telemetría recibida |
| GET | `/api/flights` · `/api/flights/{id}/telemetry` · `/events` · `/export.csv` | Historial |
| GET/POST/DELETE | `/api/routes` · `POST /api/routes/{id}/activate` · `GET /api/routes/active` | Rutas |
| POST | `/api/video/{rec}/chunk?flight_id=&seq=` | Bloque H.264 (en orden; duplicados se ignoran) |
| POST | `/api/video/{rec}/complete` | Fin de grabación |
| POST | `/api/video/{rec}/upload` | Archivo completo (si hubo pérdidas por Wi-Fi) |
| GET | `/api/videos` · `/api/videos/{rec}/file` · `/mp4` | Descargas |
| POST | `/api/recorridos` · `/{id}/tramos` · `/{id}/finalizar` · `/{id}/informe` | Botones del panel |
| GET | `/api/recorridos/activo` · `/api/recorridos/diagnostico` | Recorrido abierto · ¿encuentra análisis, ffmpeg, IA? |
| POST | `/api/recorridos/activo/reservar-tramo` | La app pide su número de tramo (al pulsar REC) |
| POST | `/api/recorridos/{id}/tramos/{n}/archivos/{video.h264, telemetria.csv, meta.json}` · `/completar` | La app sube el tramo (al pulsar STOP) |
| GET | `/api/recorridos/{id}/informe/informe_final.html` | Informe |
| WS | `/ws/telemetry` · `/ws/video` | Tiempo real para el panel |

## Estructura

```
backend/
  app/
    main.py              FastAPI, CORS, monta el panel
    config.py            rutas de almacenamiento
    api/                 telemetry · flights · routes · video · ws
    services/            telemetry_service · video_service · ws_hub
                         recorrido_service (tramos) · informe_service (llama a inspeccion-dron)
    models/schemas.py    modelos Pydantic
    database/db.py       SQLite
  storage/               base de datos y videos (se crea sola)
frontend/
  index.html · css/style.css · js/{app,api,map,routes,telemetry,video}.js
  assets/vendor/         Leaflet 1.9.4 y JMuxer 2.1.4 (incluidos, sin CDN)
tools/simulate_drone.py      telemetría/video en vivo simulados
tools/simulate_tramo.py      simula un ● REC / ■ STOP de la app (un tramo)
GUIA_RECORRIDOS.md
```
