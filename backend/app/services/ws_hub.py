"""Difusión en tiempo real al panel web por WebSocket.

- Canal de telemetría/eventos: mensajes JSON.
- Canal de video: bloques H.264 binarios tal cual llegan del teléfono.
  Se guarda el último GOP (desde el último SPS) para que un visor que se
  conecta a mitad de la grabación pueda empezar a decodificar enseguida.
"""
import asyncio
import json
from typing import Any

from fastapi import WebSocket

from app.config import LIVE_GOP_MAX_BYTES

SPS_4 = b"\x00\x00\x00\x01\x67"
SPS_3 = b"\x00\x00\x01\x67"


class Hub:
    def __init__(self) -> None:
        self.telemetry_clients: set[WebSocket] = set()
        self.video_clients: set[WebSocket] = set()
        self.last_gop = bytearray()
        self.live_recording_id: str | None = None
        self._lock = asyncio.Lock()
        # Video en vivo como imágenes JPEG (siempre activo, no depende de REC).
        self.live_clients: set[WebSocket] = set()
        self._live_busy: set[WebSocket] = set()
        self.last_frame: bytes | None = None
        self.last_frame_ms: int = 0

    # ---------- conexión ----------
    async def add_telemetry(self, ws: WebSocket) -> None:
        await ws.accept()
        self.telemetry_clients.add(ws)

    def remove_telemetry(self, ws: WebSocket) -> None:
        self.telemetry_clients.discard(ws)

    async def add_video(self, ws: WebSocket) -> None:
        await ws.accept()
        self.video_clients.add(ws)
        if self.last_gop:
            try:
                await ws.send_bytes(bytes(self.last_gop))
            except Exception:
                self.video_clients.discard(ws)

    def remove_video(self, ws: WebSocket) -> None:
        self.video_clients.discard(ws)

    async def add_live(self, ws: WebSocket) -> None:
        await ws.accept()
        self.live_clients.add(ws)
        if self.last_frame:
            try:
                await ws.send_bytes(self.last_frame)
            except Exception:
                self.live_clients.discard(ws)

    def remove_live(self, ws: WebSocket) -> None:
        self.live_clients.discard(ws)
        self._live_busy.discard(ws)

    def publish_frame(self, frame: bytes, now_ms: int) -> None:
        """Guarda el último fotograma y lo envía a los visores sin bloquear al teléfono.

        Si un visor todavía está recibiendo el fotograma anterior (red lenta), se le
        salta éste: así nunca se acumula retraso en el directo.
        """
        self.last_frame = frame
        self.last_frame_ms = now_ms
        for ws in list(self.live_clients):
            if ws in self._live_busy:
                continue
            self._live_busy.add(ws)
            asyncio.create_task(self._send_frame(ws, frame))

    async def _send_frame(self, ws: WebSocket, frame: bytes) -> None:
        try:
            await asyncio.wait_for(ws.send_bytes(frame), timeout=5)
        except Exception:
            self.live_clients.discard(ws)
        finally:
            self._live_busy.discard(ws)

    # ---------- difusión ----------
    async def broadcast_json(self, kind: str, data: Any) -> None:
        if not self.telemetry_clients:
            return
        msg = json.dumps({"kind": kind, "data": data})
        dead = []
        for ws in list(self.telemetry_clients):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.telemetry_clients.discard(ws)

    async def broadcast_video(self, recording_id: str, chunk: bytes) -> None:
        async with self._lock:
            if recording_id != self.live_recording_id:
                self.live_recording_id = recording_id
                self.last_gop = bytearray()
            idx = _find_sps(chunk)
            if idx >= 0:
                self.last_gop = bytearray(chunk[idx:])
            elif self.last_gop:
                self.last_gop += chunk
            if len(self.last_gop) > LIVE_GOP_MAX_BYTES:
                self.last_gop = bytearray()

        dead = []
        for ws in list(self.video_clients):
            try:
                await ws.send_bytes(chunk)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.video_clients.discard(ws)

    def end_live(self, recording_id: str) -> None:
        if recording_id == self.live_recording_id:
            self.live_recording_id = None
            self.last_gop = bytearray()


def _find_sps(chunk: bytes) -> int:
    """Posición del ÚLTIMO SPS (NAL tipo 7) del bloque, incluido su start code; -1 si no hay."""
    i3 = chunk.rfind(SPS_3)
    if i3 < 0:
        return -1
    # Si ese start code de 3 bytes forma parte de uno de 4 (00 00 00 01), incluir el 00 previo.
    if i3 > 0 and chunk[i3 - 1] == 0:
        return i3 - 1
    return i3


hub = Hub()
