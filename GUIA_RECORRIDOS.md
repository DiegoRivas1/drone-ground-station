# Guía: recorridos, tramos e informe

Flujo completo:

```
PC: NUEVO RECORRIDO
 └─ PC: NUEVO TRAMO → Celular: ● REC … ■ STOP → llega (tramo 1: video + telemetría)
 └─ PC: NUEVO TRAMO → Celular: ● REC … ■ STOP → llega (tramo 2: video + telemetría)
 └─ …
PC: FINALIZAR RECORRIDO → GENERAR INFORME → Abrir informe (HTML, imprimible a PDF)
```

Todo es gratis. Lo único que usa Internet es el mapa y, si pones una clave, la redacción con IA (Gemini o Groq).

---

## 1. Qué se conecta con qué

```
Mavic Air ──radio──► Control remoto ──cable USB──► Celular A (app)
                                                        │ Wi-Fi
                                   Celular B (zona Wi-Fi / "compartir datos")
                                                        │ Wi-Fi
                                                       PC
```

- El **dron NO se conecta a ningún Wi-Fi**: habla con su control y el control con el celular A por cable.
- **Celular A y PC se conectan a la misma red** (la zona Wi-Fi del celular B). Así se ven entre sí.
- Lo que va del celular A a la PC **no gasta datos móviles** (no sale a Internet).
- No uses el modo del Mavic Air "Wi-Fi sin control": ocupa el Wi-Fi del celular y no podrá hablar con la PC.
- Si no se ven: algunos celulares aíslan a los clientes de su zona Wi-Fi. Alternativa: que la **PC cree la red**
  (Windows → Configuración → Red e Internet → Zona con cobertura inalámbrica móvil) y el celular A se conecte a ella.

---

## 2. Preparar la PC (una sola vez)

Necesitas **Python 3.10 o superior** (python.org, marca "Add Python to PATH" al instalar).

### 2.1 Carpetas

Pon las dos carpetas una al lado de la otra (o el análisis en `C:\Users\TU_USUARIO\dron_project_reconocimiento`):

```
C:\Users\HP\
├── drone-ground-station\            ← este proyecto (servidor + panel)
└── dron_project_reconocimiento\
    └── inspeccion-dron\             ← tu proyecto de análisis (YOLO + informe)
```

Si están en otro lugar, edita `run_server.bat` y quita el `REM` de la línea `set INSPECCION_DIR=...`.

### 2.2 Proyecto de análisis (tarda unos minutos: descarga PyTorch y YOLO)

```bash
cd C:\Users\HP\dron_project_reconocimiento\inspeccion-dron
```

```bash
python -m venv venv
```

```bash
venv\Scripts\pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu
```

### 2.3 (Opcional) Redacción del informe con IA

```bash
copy .env.example .env
```

Abre `.env` con el Bloc de notas y pega tu clave gratuita:
- Gemini: https://aistudio.google.com → "Get API key" → `GEMINI_API_KEY=...`
- o Groq: https://console.groq.com → `LLM_PROVIDER=groq` y `GROQ_API_KEY=...`

Sin clave el informe se genera igual, con los datos y sin el texto redactado por IA.

### 2.4 Firewall (terminal **como administrador**)

```bash
netsh advfirewall firewall add rule name="Dron 8000" dir=in action=allow protocol=TCP localport=8000
```

---

## 3. Cada día de vuelo

1. Celular A y PC conectados al Wi-Fi del celular B.
2. **Arranca el servidor:** doble clic en `drone-ground-station\run_server.bat`.
   La ventana muestra algo así (déjala abierta):
   ```
   Panel:          http://10.146.205.254:8000
   Análisis (inspeccion-dron): OK
   ffmpeg: OK | IA (gemini): clave OK
   ```
3. **Panel:** abre en el navegador de la PC la dirección que aparece.
4. **App:** botón **PC: …** → escribe esa misma dirección → Guardar. Arriba debe decir `PC: CONECTADA`.
5. En el panel, pestaña **Recorrido**:
   1. Escribe un nombre → **NUEVO RECORRIDO** (ya queda el tramo 1 esperando).
   2. En la app: **● REC** al empezar el tramo, **■ STOP** al terminarlo.
      La app muestra `TRAMO 1 ENVIADO ✓` y el panel `RECIBIDO`.
   3. **NUEVO TRAMO** en el panel → **● REC / ■ STOP** en la app … tantas veces como tramos.
   4. **FINALIZAR RECORRIDO**.
   5. **GENERAR INFORME** → espera (verás el progreso) → **Abrir informe** → botón *Imprimir / PDF*.

Si al pulsar STOP no había Wi-Fi o ningún recorrido abierto, el tramo queda guardado en el celular.
Cuando se arregle, pulsa en la app **REENVIAR TRAMOS PENDIENTES**.

Si un tramo salió mal (o la app se cerró a mitad de un tramo), pulsa **Descartar** en el panel:
no entra en el informe.

---

## 4. Dónde queda cada cosa

**En la PC:**
```
drone-ground-station\backend\storage\recorridos\20261106_131545_Talud_norte\
├── recorrido.json
├── tramo_01\  video.h264  video.mp4  telemetria.csv  meta.json
├── tramo_02\  …
└── analisis\
    ├── tramo_01\  resultados_frames.csv  frames\*.jpg   (salida de 01_procesar_video.py)
    ├── resultados_frames.csv                            (todos los tramos juntos)
    ├── resumen_tramos.json
    ├── informe_final.md
    └── informe_final.html   ← el informe
```

**En el celular** (copia de seguridad, nunca se borra sola):
`Android/data/com.diegorivas.drone/files/tramos/tramo_AAAAMMDD_HHMMSS/`

---

## 5. Probar sin el dron

Con el servidor en marcha y un recorrido abierto en el panel:

```bash
cd C:\Users\HP\drone-ground-station
```

```bash
backend\.venv\Scripts\python tools\simulate_tramo.py --video C:\ruta\a\cualquier_video.mp4
```

Cada ejecución simula un ● REC / ■ STOP de la app (un tramo). Luego FINALIZAR y GENERAR INFORME en el panel.

---

## 6. Problemas frecuentes

| Síntoma | Causa / solución |
|---|---|
| App: `PC sin conexión` | ¿Misma red? ¿IP correcta (`ipconfig`)? ¿Firewall (paso 2.4)? Prueba abrir `http://IP:8000` en el navegador del celular. |
| App: `No hay un recorrido abierto en la PC` | Pulsa NUEVO RECORRIDO en el panel y luego REENVIAR TRAMOS PENDIENTES. |
| Tramo con aviso `sin posición GPS` | Grabado en interior o sin satélites: se recibe pero no se puede analizar. |
| Panel: `no encuentro inspeccion-dron` | Ajusta `INSPECCION_DIR` en `run_server.bat` (paso 2.1). |
| Informe: error en `01_procesar_video.py` | Mira el registro bajo el botón; normalmente falta instalar el paso 2.2. |
| Informe "sin redacción con IA" | No hay clave en `inspeccion-dron\.env` (paso 2.3) o se agotó el plan gratuito. |
| Las detecciones parecen desfasadas | La transmisión llega ~0.2 s tarde: `set VIDEO_OFFSET_MS=200` en `run_server.bat`. |

**Limitación actual del análisis:** sin modelos propios en `inspeccion-dron\modelos\`, se usa YOLO general
(detecta personas y vehículos, **no rocas**) y el terreno se estima por color.
