"""WebSockets para el panel web: telemetría/eventos (JSON) y video en vivo (binario)."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.ws_hub import hub

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/telemetry")
async def ws_telemetry(ws: WebSocket):
    await hub.add_telemetry(ws)
    try:
        while True:
            await ws.receive_text()  # mantener viva la conexión (ping del panel)
    except WebSocketDisconnect:
        pass
    finally:
        hub.remove_telemetry(ws)


@router.websocket("/ws/video")
async def ws_video(ws: WebSocket):
    await hub.add_video(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        hub.remove_video(ws)
