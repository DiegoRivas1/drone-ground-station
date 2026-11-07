"""Genera el informe de un recorrido usando el proyecto de análisis
(dron_project_reconocimiento/inspeccion-dron).

Pasos:
  1. Por cada tramo recibido: 01_procesar_video.py  → analisis/tramo_NN/resultados_frames.csv
  2. Une todos los resultados (cada fila conserva su tramo_id) → analisis/resultados_frames.csv
  3a. Con clave de Gemini/Groq en inspeccion-dron/.env: 02_generar_reporte.py (redacción con IA)
  3b. Sin clave, o si la IA falla: resumen determinista con src/agregacion.py
  4. Informe final: analisis/reporte.md y analisis/reporte.html (con imágenes de hallazgos)
"""
import csv
import html
import json
import os
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import markdown
from fastapi import HTTPException

from app.config import INSPECCION_DIR, INSPECCION_PYTHON, VIDEO_OFFSET_MS
from app.services import recorrido_service as rs

_trabajos: dict[str, threading.Thread] = {}
_MAX_LOG = 20000

RESUMEN_SNIPPET = (
    "import sys, json, pandas as pd\n"
    "sys.path.insert(0, '.')\n"
    "from src.agregacion import resumir_por_tramo\n"
    "df = pd.read_csv(sys.argv[1])\n"
    "open(sys.argv[2], 'w', encoding='utf-8').write("
    "json.dumps(resumir_por_tramo(df), ensure_ascii=False, indent=2))\n"
)


# ---------------------------------------------------------------------------
# Diagnóstico
# ---------------------------------------------------------------------------

def _leer_env(path: Path) -> dict:
    """Lector mínimo de .env (sólo para saber QUÉ proveedor y SI hay clave; no se registra)."""
    vals = {}
    if not path.exists():
        return vals
    for linea in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, v = linea.split("=", 1)
        v = v.split(" #")[0].split("\t#")[0].strip().strip('"').strip("'")
        vals[k.strip()] = v
    return vals


def estado_llm() -> dict:
    env = {**_leer_env(INSPECCION_DIR / ".env"), **{k: v for k, v in os.environ.items()
                                                       if k in ("LLM_PROVIDER", "GEMINI_API_KEY", "GROQ_API_KEY")}}
    proveedor = (env.get("LLM_PROVIDER") or "gemini").lower()
    clave = env.get("GROQ_API_KEY" if proveedor == "groq" else "GEMINI_API_KEY", "")
    ok = len(clave) > 15 and "pega" not in clave.lower()
    return {"proveedor": proveedor, "clave_configurada": ok}


def diagnostico() -> dict:
    return {
        "inspeccion_dir": str(INSPECCION_DIR),
        "inspeccion_encontrado": (INSPECCION_DIR / "01_procesar_video.py").exists(),
        "python": INSPECCION_PYTHON,
        "ffmpeg": rs.ffmpeg_path() is not None,
        **estado_llm(),
    }


# ---------------------------------------------------------------------------
# Trabajo en segundo plano
# ---------------------------------------------------------------------------

def iniciar(rid: str) -> dict:
    rec = rs.obtener(rid)
    if rid in _trabajos and _trabajos[rid].is_alive():
        raise HTTPException(409, "El informe ya se está generando")
    if not (INSPECCION_DIR / "01_procesar_video.py").exists():
        raise HTTPException(
            500, f"No encuentro el proyecto de análisis en {INSPECCION_DIR}. "
                 "Define INSPECCION_DIR (ver README).")
    pendientes = [t["n"] for t in rec["tramos"] if t["estado"] in ("grabando", "subiendo", "procesando")]
    if pendientes:
        raise HTTPException(409, f"Hay tramos sin terminar de llegar: {pendientes}. Espera o descártalos.")
    validos = [t for t in rec["tramos"] if t["estado"] == "recibido" and t["muestras_gps"] >= 2]
    if not validos:
        raise HTTPException(409, "No hay tramos recibidos con telemetría GPS para analizar.")

    rs.actualizar_informe(rid, estado="generando", inicio_ms=int(time.time() * 1000),
                          fin_ms=None, error=None, log="", con_ia=None)
    th = threading.Thread(target=_generar, args=(rid,), daemon=True)
    _trabajos[rid] = th
    th.start()
    return rs.obtener(rid)["informe"]


class _Log:
    def __init__(self, rid: str):
        self.rid = rid
        self.texto = ""
        self._ultimo = 0.0

    def __call__(self, linea: str) -> None:
        self.texto += linea.rstrip() + "\n"
        if len(self.texto) > _MAX_LOG:
            self.texto = self.texto[-_MAX_LOG:]
        if time.time() - self._ultimo > 1.0:
            self.flush()

    def flush(self) -> None:
        self._ultimo = time.time()
        rs.actualizar_informe(self.rid, log=self.texto)


def _ejecutar(cmd: list[str], log: _Log, timeout: int = 3600, etiqueta: str | None = None) -> int:
    log("$ " + (etiqueta or " ".join(Path(c).name if i == 0 else c for i, c in enumerate(cmd))))
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    p = subprocess.Popen(cmd, cwd=INSPECCION_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding="utf-8", errors="replace", env=env)
    inicio = time.time()
    assert p.stdout is not None
    for linea in p.stdout:
        log("  " + linea.rstrip())
        if time.time() - inicio > timeout:
            p.kill()
            log("  ** tiempo agotado **")
            break
    return p.wait()


def _generar(rid: str) -> None:
    log = _Log(rid)
    con_ia = False
    try:
        rec = rs.obtener(rid)
        base = rs.directorio(rid)
        analisis = base / "analisis"
        analisis.mkdir(exist_ok=True)

        validos = [t for t in rec["tramos"] if t["estado"] == "recibido" and t["muestras_gps"] >= 2]
        omitidos = [t for t in rec["tramos"] if t not in validos and t["estado"] != "descartado"]
        for t in omitidos:
            log(f"Tramo {t['n']} omitido: {t.get('error') or t.get('aviso') or t['estado']}")

        # 1. Analizar cada tramo
        filas_total = []
        campos = None
        for t in validos:
            n = t["n"]
            td = base / f"tramo_{n:02d}"
            salida = analisis / f"tramo_{n:02d}"
            log(f"\n=== Tramo {n}: análisis de video ===")
            cmd = [INSPECCION_PYTHON, "01_procesar_video.py",
                   "--video", str(td / "video.mp4"),
                   "--telemetria", str(td / "telemetria.csv"),
                   "--salida", str(salida),
                   "--offset-ms", str(VIDEO_OFFSET_MS)]
            if (td / "meta.json").exists():
                cmd += ["--meta", str(td / "meta.json")]
            if _ejecutar(cmd, log) != 0:
                raise RuntimeError(f"El análisis del tramo {n} falló (ver log).")

            # 2. Unir resultados; las imágenes quedan relativas a analisis/
            with open(salida / "resultados_frames.csv", newline="", encoding="utf-8") as f:
                lector = csv.DictReader(f)
                campos = campos or lector.fieldnames
                for fila in lector:
                    fila["tramo_id"] = n
                    if fila.get("imagen"):
                        fila["imagen"] = f"tramo_{n:02d}/{fila['imagen']}"
                    filas_total.append(fila)

        unido = analisis / "resultados_frames.csv"
        with open(unido, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=campos)
            w.writeheader()
            w.writerows(filas_total)
        (analisis / "info_corrida.json").write_text(json.dumps(
            {"video": f"{rec['nombre']} ({len(validos)} tramos)"}, ensure_ascii=False), encoding="utf-8")
        log(f"\nResultados unidos: {len(filas_total)} fotogramas de {len(validos)} tramos")

        # 3. Redacción
        cuerpo_ia = None
        if estado_llm()["clave_configurada"]:
            log("\n=== Redacción con IA (02_generar_reporte.py) ===")
            if _ejecutar([INSPECCION_PYTHON, "02_generar_reporte.py", "--resultados", str(unido)], log) == 0 \
                    and (analisis / "reporte.md").exists():
                cuerpo_ia = (analisis / "reporte.md").read_text(encoding="utf-8")
                con_ia = True
            else:
                log("La IA falló: se genera el informe sin redacción automática.")
        else:
            log("\nSin clave de Gemini/Groq en inspeccion-dron/.env: informe sin redacción con IA.")

        resumen_path = analisis / "resumen_tramos.json"
        if not resumen_path.exists():
            if _ejecutar([INSPECCION_PYTHON, "-c", RESUMEN_SNIPPET, str(unido), str(resumen_path)], log,
                         etiqueta="resumen por tramo (src/agregacion.py)") != 0:
                raise RuntimeError("No se pudo calcular el resumen por tramo.")
        resumen = json.loads(resumen_path.read_text(encoding="utf-8"))

        # 4. Informe final
        md = _componer_md(rec, validos, omitidos, resumen, cuerpo_ia)
        (analisis / "informe_final.md").write_text(md, encoding="utf-8")
        (analisis / "informe_final.html").write_text(_a_html(rec["nombre"], md), encoding="utf-8")
        log("\nInforme listo: analisis/informe_final.html")
        log.flush()
        rs.actualizar_informe(rid, estado="listo", fin_ms=int(time.time() * 1000), con_ia=con_ia)
    except Exception as e:  # noqa: BLE001 - se muestra en el panel
        log(f"\nERROR: {e}")
        log.flush()
        rs.actualizar_informe(rid, estado="error", fin_ms=int(time.time() * 1000), error=str(e))


# ---------------------------------------------------------------------------
# Composición del informe
# ---------------------------------------------------------------------------

def _fmt_dur(s):
    if s is None:
        return "--"
    return f"{int(s // 60)} min {int(s % 60)} s" if s >= 60 else f"{s:.0f} s"


def _componer_md(rec, validos, omitidos, resumen, cuerpo_ia) -> str:
    fecha = datetime.fromtimestamp(rec["creado_ms"] / 1000).strftime("%d/%m/%Y %H:%M")
    dist_total = sum(t["distancia_m"] or 0 for t in validos)
    dur_total = sum(t["duracion_s"] or 0 for t in validos)
    riesgo = {r["tramo_id"]: r for r in resumen}

    out = [f"# Informe de inspección: {rec['nombre']}",
           f"- **Fecha del recorrido:** {fecha}",
           f"- **Tramos analizados:** {len(validos)}",
           f"- **Distancia recorrida:** {dist_total:.0f} m · **Tiempo de vuelo grabado:** {_fmt_dur(dur_total)}",
           f"- **Generado:** {datetime.now().strftime('%d/%m/%Y %H:%M')}"
           + ("" if cuerpo_ia else " (sin redacción con IA)"),
           "",
           "## Tramos del recorrido",
           "",
           "| Tramo | Duración | Distancia | Muestras GPS | Fotogramas | Riesgo |",
           "|---|---|---|---|---|---|"]
    for t in validos:
        r = riesgo.get(t["n"], {})
        out.append(f"| {t['n']} | {_fmt_dur(t['duracion_s'])} | {t['distancia_m'] or 0:.0f} m | "
                   f"{t['muestras_gps']} | {r.get('n_fotogramas', '--')} | **{r.get('nivel_riesgo', '--')}** |")
    if omitidos:
        out += ["", "**Tramos no analizados:** " + "; ".join(
            f"tramo {t['n']} ({t.get('error') or t.get('aviso') or t['estado']})" for t in omitidos)]

    if cuerpo_ia:
        # Se omite la cabecera propia de 02_generar_reporte.py (empieza en '## Resumen ejecutivo').
        i = cuerpo_ia.find("## Resumen ejecutivo")
        out += ["", cuerpo_ia[i:] if i >= 0 else cuerpo_ia]
    else:
        out += ["", "## Resultados por tramo"]
        for r in resumen:
            terreno = ", ".join(f"{k} {v}%" for k, v in r.get("pct_terreno", {}).items()) or "sin dato"
            out += ["",
                    f"### Tramo {r['tramo_id']} – Riesgo: {r['nivel_riesgo']}",
                    f"- Inicio: {r['inicio']['lat']:.6f}, {r['inicio']['lon']:.6f} → "
                    f"Fin: {r['fin']['lat']:.6f}, {r['fin']['lon']:.6f}",
                    f"- Altitud: {r['altitud_m']['min']:.1f} – {r['altitud_m']['max']:.1f} m",
                    f"- Fotogramas analizados: {r['n_fotogramas']}",
                    f"- Obstáculos detectados: {r['total_obstaculos']} "
                    f"(máx. {r['max_obstaculos_por_frame']} en un fotograma)",
                    f"- Fotogramas con aglomeración de personas: {r['frames_aglomeracion']}",
                    f"- Terreno ({r.get('metodo_terreno', '')}): {terreno}"]

    hallazgos = [(r["tramo_id"], h) for r in resumen for h in r.get("hallazgos", [])]
    out += ["", "## Anexo: hallazgos con imagen"]
    if not hallazgos:
        out.append("Sin hallazgos (no se detectaron obstáculos ni aglomeraciones).")
    for n, h in hallazgos:
        out.append(f"\n**Tramo {n} · segundo {h['t_video_s']:.0f}** — {h['n_obstaculos']} obstáculo(s), "
                   f"{h['n_personas']} persona(s) · {h['lat']:.6f}, {h['lon']:.6f}")
        if h.get("imagen"):
            out.append(f"\n![Tramo {n} s{h['t_video_s']:.0f}]({h['imagen']})")

    out += ["", "---",
            "*Detecciones automáticas: pueden contener falsos positivos o negativos. "
            "Revise las imágenes antes de tomar decisiones.*"]
    return "\n".join(out)


def _a_html(titulo: str, md: str) -> str:
    cuerpo = markdown.markdown(md, extensions=["tables"])
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(titulo)}</title>
<style>
  body {{ font: 15px/1.55 system-ui, "Segoe UI", Roboto, sans-serif; color: #1b1f24; background: #fff;
         max-width: 900px; margin: 0 auto; padding: 32px 20px; }}
  h1 {{ font-size: 26px; border-bottom: 3px solid #00a3bf; padding-bottom: 8px; }}
  h2 {{ font-size: 20px; margin-top: 32px; border-bottom: 1px solid #ddd; padding-bottom: 4px; }}
  h3 {{ font-size: 16px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 14px; }}
  th, td {{ border: 1px solid #d0d7de; padding: 6px 10px; text-align: left; }}
  th {{ background: #f3f6f8; }}
  img {{ max-width: 100%; border: 1px solid #d0d7de; border-radius: 6px; margin: 6px 0; }}
  .print {{ position: fixed; top: 12px; right: 12px; padding: 6px 12px; cursor: pointer; }}
  @media print {{ .print {{ display: none; }} body {{ padding: 0; }} img {{ page-break-inside: avoid; }} }}
</style></head>
<body>
<button class="print" onclick="window.print()">Imprimir / PDF</button>
{cuerpo}
</body></html>"""
