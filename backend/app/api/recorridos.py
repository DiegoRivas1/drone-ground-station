"""Recorridos y tramos: botones del panel + subida de archivos desde el teléfono."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.services import informe_service, recorrido_service as rs

router = APIRouter(prefix="/api/recorridos", tags=["recorridos"])


class NuevoRecorrido(BaseModel):
    nombre: str = Field(default="Recorrido", max_length=80)


class Reserva(BaseModel):
    estado: str = "grabando"   # grabando (al pulsar REC) | subiendo (al pulsar STOP)


# ---------------- panel ----------------

@router.get("")
def listar():
    return rs.listar()


@router.get("/diagnostico")
def diagnostico():
    """¿Encuentra el proyecto de análisis, ffmpeg y la clave de IA?"""
    return informe_service.diagnostico()


@router.get("/activo")
def activo():
    return rs.activo()


@router.post("")
def crear(body: NuevoRecorrido):
    return rs.crear(body.nombre)


@router.get("/{rid}")
def obtener(rid: str):
    return rs.obtener(rid)


@router.post("/{rid}/tramos")
def nuevo_tramo(rid: str):
    return rs.nuevo_tramo(rid)


@router.post("/{rid}/finalizar")
def finalizar(rid: str):
    return rs.finalizar(rid)


@router.post("/{rid}/reabrir")
def reabrir(rid: str):
    return rs.reabrir(rid)


@router.post("/{rid}/tramos/{n}/descartar")
def descartar(rid: str, n: int):
    return rs.descartar(rid, n)


@router.get("/{rid}/tramos/{n}/archivos/{nombre}")
def descargar_archivo(rid: str, n: int, nombre: str):
    p = rs.archivo_tramo(rid, n, nombre)
    return FileResponse(p, filename=f"{rid}_tramo{n:02d}_{nombre}")


@router.post("/{rid}/informe")
def generar_informe(rid: str):
    return informe_service.iniciar(rid)


@router.get("/{rid}/informe/{ruta:path}")
def archivo_informe(rid: str, ruta: str):
    """Sirve analisis/<ruta> (informe HTML y sus imágenes)."""
    base = (rs.directorio(rid) / "analisis").resolve()
    p = (base / ruta).resolve()
    if base not in p.parents or not p.is_file():
        raise HTTPException(404, "No encontrado")
    return FileResponse(p)


# ---------------- teléfono ----------------

@router.post("/activo/reservar-tramo")
def reservar_tramo(body: Reserva):
    """REC en el teléfono → qué recorrido/tramo le toca. 409 si no hay recorrido abierto."""
    return rs.reservar_tramo(body.estado)


@router.post("/{rid}/tramos/{n}/archivos/{nombre}")
async def subir_archivo(rid: str, n: int, nombre: str, request: Request):
    size = await rs.guardar_archivo(rid, n, nombre, request)
    return {"archivo": nombre, "bytes": size}


@router.post("/{rid}/tramos/{n}/completar")
def completar(rid: str, n: int):
    return rs.completar(rid, n)
