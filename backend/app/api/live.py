"""Video en vivo como fotogramas JPEG.

La app envía ~8 imágenes por segundo de lo que muestra su pantalla (siempre que el
dron esté conectado, sin necesidad de pulsar REC). El panel las recibe por /ws/live.
Es independiente del H.264 de las grabaciones, que se guarda aparte y se convierte a MP4.
"""
import time

from fastapi import APIRouter, HTTPException, Request, Response, WebSocket, WebSocketDisconnect

from app.services.ws_hub import hub

router = APIRouter(tags=["video en vivo"])

MAX_FRAME_BYTES = 2 * 1024 * 1024


@router.post("/api/live/frame")
async def post_frame(request: Request):
    data = await request.body()
    if not data:
        raise HTTPException(400, "Fotograma vacío")
    if len(data) > MAX_FRAME_BYTES:
        raise HTTPException(413, "Fotograma demasiado grande")
    if not data.startswith(b"\xff\xd8"):
        raise HTTPException(415, "Se esperaba una imagen JPEG")
    hub.publish_frame(data, int(time.time() * 1000))
    return {"ok": True, "viewers": len(hub.live_clients)}


@router.get("/api/live/latest.jpg")
def latest_frame():
    if not hub.last_frame:
        raise HTTPException(404, "Aún no ha llegado ningún fotograma")
    return Response(hub.last_frame, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/api/live/status")
def live_status():
    age = int(time.time() * 1000) - hub.last_frame_ms if hub.last_frame_ms else None
    return {"age_ms": age, "viewers": len(hub.live_clients)}


@router.websocket("/ws/live")
async def ws_live(ws: WebSocket):
    await hub.add_live(ws)
    try:
        while True:
            await ws.receive_text()  # ping del panel
    except WebSocketDisconnect:
        pass
    finally:
        hub.remove_live(ws)
