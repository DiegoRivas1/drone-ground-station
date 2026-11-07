@echo off
REM Arranca la estacion de tierra (FastAPI) en el puerto 8000, visible en la red local.
REM La primera vez crea el entorno virtual; siempre comprueba las dependencias.
cd /d "%~dp0backend"

REM --- Proyecto de analisis (dron_project_reconocimiento\inspeccion-dron) ---
REM Se busca solo junto a esta carpeta o en C:\Users\TU_USUARIO\dron_project_reconocimiento.
REM Si esta en otro lugar, quita el REM de la linea siguiente y pon la ruta:
REM set INSPECCION_DIR=D:\TRABAJOS\dron_project_reconocimiento\inspeccion-dron
REM Correccion de sincronia video/telemetria en milisegundos (opcional):
REM set VIDEO_OFFSET_MS=200

if not exist ".venv\Scripts\python.exe" (
    echo Creando entorno virtual...
    python -m venv .venv || goto :error
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
)
echo Comprobando dependencias...
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt || goto :error

echo.
echo Si Windows pregunta por el Firewall, permite el acceso en redes PRIVADAS
echo (si no, el telefono no podra conectarse).
echo.
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
goto :eof

:error
echo.
echo Error preparando el servidor. Revisa que Python 3.10+ este instalado.
pause
