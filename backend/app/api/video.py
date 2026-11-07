"""Recepción de video H.264 desde la app y descarga desde el panel."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.models.schemas import VideoComplete
from app.services import video_service
from app.services.ws_hub import hub

router = APIRouter(prefix="/api", tags=["video"])

MAX_CHUNK_BYTES = 32 * 1024 * 1024


@router.post("/video/{recording_id}/chunk")
async def post_chunk(recording_id: str, request: Request, seq: int, flight_id: str = ""):
    video_service.check_id(recording_id)
    data = await request.body()
    if len(data) > MAX_CHUNK_BYTES:
        raise HTTPException(413, "Bloque demasiado grande")
    result = video_service.append_chunk(recording_id, flight_id, seq, data)
    if result["status"] == "ok":
        await hub.broadcast_video(recording_id, data)
    return result


@router.post("/video/{recording_id}/complete")
async def post_complete(recording_id: str, info: VideoComplete, flight_id: str = ""):
    row = video_service.complete(recording_id, flight_id, info.chunks, info.incomplete)
    hub.end_live(recording_id)
    await hub.broadcast_json("video_completed", row)
    return row


@router.post("/video/{recording_id}/upload")
async def post_upload(recording_id: str, request: Request, flight_id: str = ""):
    """Archivo completo (se usa cuando hubo pérdidas por Wi-Fi durante la grabación)."""
    result = await video_service.replace_with_upload(recording_id, flight_id, request)
    await hub.broadcast_json("video_completed", {"id": recording_id, **result})
    return result


@router.get("/videos")
def list_videos():
    return video_service.list_videos()


@router.get("/videos/{recording_id}/file")
def download_h264(recording_id: str):
    path = video_service.video_path(recording_id)
    if not path.exists():
        raise HTTPException(404, "Video no encontrado")
    return FileResponse(path, media_type="video/h264", filename=path.name)


@router.get("/videos/{recording_id}/mp4")
def download_mp4(recording_id: str):
    path = video_service.to_mp4(recording_id)
    return FileResponse(path, media_type="video/mp4", filename=path.name)


@router.delete("/videos/{recording_id}")
def delete_video(recording_id: str):
    video_service.delete_video(recording_id)
    return {"deleted": recording_id}
