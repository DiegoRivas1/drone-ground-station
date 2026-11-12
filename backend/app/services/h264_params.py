"""SPS/PPS (parámetros) de los videos H.264 del dron.

El Mavic Air casi nunca repite SPS/PPS en su flujo de video. Una grabación que
empieza a mitad del flujo no los tiene y no se puede decodificar
("non-existing PPS 0 referenced"). La app nueva los escribe al empezar a grabar;
para grabaciones antiguas, se toman de otra grabación del mismo dron (los
parámetros no cambian mientras no cambie la resolución del video).
"""
from pathlib import Path

from app.config import RECORRIDOS_DIR, VIDEOS_DIR

# Se buscan en los primeros bytes de cada archivo (la app los pone al principio)
# y, si no, en todo el archivo por bloques.
_CHUNK = 4 * 1024 * 1024
_MAX_PARAM = 512


def _nals(data: bytes):
    """(tipo, nal sin start code) de cada NAL del bloque."""
    i = data.find(b"\x00\x00\x01")
    while i >= 0:
        start = i + 3
        nxt = data.find(b"\x00\x00\x01", start)
        end = len(data) if nxt < 0 else (nxt - 1 if data[nxt - 1] == 0 else nxt)
        if start < len(data):
            yield data[start] & 0x1F, data[start:end]
        i = nxt


def extract(path: Path) -> tuple[bytes | None, bytes | None]:
    """Primer SPS y PPS encontrados en el archivo."""
    sps = pps = None
    try:
        with open(path, "rb") as f:
            prev = b""
            while sps is None or pps is None:
                block = f.read(_CHUNK)
                if not block:
                    break
                data = prev + block
                for t, nal in _nals(data):
                    if t == 7 and sps is None and 1 < len(nal) <= _MAX_PARAM:
                        sps = nal
                    elif t == 8 and pps is None and 0 < len(nal) <= _MAX_PARAM:
                        pps = nal
                prev = data[-_MAX_PARAM:]
    except OSError:
        pass
    return sps, pps


def has_params(path: Path) -> bool:
    sps, pps = extract(path)
    return sps is not None and pps is not None


def find_header(exclude: Path | None = None) -> bytes | None:
    """SPS+PPS de la grabación más reciente que los tenga."""
    candidates = list(VIDEOS_DIR.glob("*.h264")) + list(RECORRIDOS_DIR.rglob("*.h264"))
    candidates = [p for p in candidates if not (exclude and p.resolve() == exclude.resolve())
                  and not p.name.endswith(".fixed.h264")]
    for p in sorted(candidates, key=lambda x: x.stat().st_mtime, reverse=True):
        sps, pps = extract(p)
        if sps and pps:
            return b"\x00\x00\x00\x01" + sps + b"\x00\x00\x00\x01" + pps
    return None


def write_with_header(src: Path, dst: Path, header: bytes) -> None:
    with open(dst, "wb") as out, open(src, "rb") as inp:
        out.write(header)
        while True:
            block = inp.read(_CHUNK)
            if not block:
                break
            out.write(block)
