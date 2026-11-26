@echo off
REM Expone la estacion a Internet con un tunel de Cloudflare (URL https://....trycloudflare.com).
REM Antes: crea el token (python tools\make_token.py) y arranca el servidor (run_server.bat).
REM Guia completa: docs\CLOUDFLARE.md
cd /d "%~dp0"

if not exist "backend\station_token.txt" (
    if "%STATION_TOKEN%"=="" (
        echo.
        echo NO se abre el tunel: la estacion no tiene token y quedaria abierta a todo Internet.
        echo Crea uno con:  python tools\make_token.py   y reinicia run_server.bat
        echo.
        pause
        exit /b 1
    )
)

where cloudflared >nul 2>nul
if errorlevel 1 (
    echo.
    echo No encuentro cloudflared. Instalalo con:
    echo     winget install --id Cloudflare.cloudflared
    echo y abre una terminal nueva.
    echo.
    pause
    exit /b 1
)

echo.
echo Cuando aparezca la URL https://....trycloudflare.com, esa es la direccion publica.
echo Se abre con el panel (te pide el token) y se pone en la app. Cierra esta ventana para cerrar el tunel.
echo.
cloudflared tunnel --url http://localhost:8000
