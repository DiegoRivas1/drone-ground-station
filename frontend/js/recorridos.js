// Pestaña Recorrido: NUEVO RECORRIDO → NUEVO TRAMO (x N) → FINALIZAR → GENERAR INFORME.
import { api, escapeHtml, fmtBytes, fmtDateTime, toast } from "./api.js";

const $ = (id) => document.getElementById(id);
let seleccionado = null;   // id del recorrido mostrado
let ultimoJson = "";

const ESTADOS = {
  esperando: ["info", "ESPERANDO REC"],
  grabando: ["warn", "GRABANDO"],
  subiendo: ["warn", "SUBIENDO"],
  procesando: ["warn", "PROCESANDO"],
  recibido: ["ok", "RECIBIDO"],
  error: ["bad", "ERROR"],
  descartado: ["", "DESCARTADO"],
};

function badge(estado) {
  const [cls, txt] = ESTADOS[estado] ?? ["", estado.toUpperCase()];
  const anim = ["grabando", "subiendo", "procesando"].includes(estado) ? " pulse" : "";
  return `<span class="badge ${cls}${anim}">${txt}</span>`;
}

function dur(s) {
  if (s == null) return "--";
  return s >= 60 ? `${Math.floor(s / 60)} min ${Math.round(s % 60)} s` : `${Math.round(s)} s`;
}

function renderTramos(rec) {
  const ul = $("rec-tramos");
  if (!rec.tramos.length) {
    ul.innerHTML = '<li class="empty">Aún no hay tramos.</li>';
    return;
  }
  ul.innerHTML = rec.tramos.map((t) => {
    const base = `/api/recorridos/${encodeURIComponent(rec.id)}/tramos/${t.n}/archivos`;
    const listo = t.estado === "recibido" || t.estado === "error";
    return `
      <li>
        <div class="row"><span class="title">Tramo ${t.n}</span>${badge(t.estado)}</div>
        ${listo || t.estado === "descartado" ? `<span class="muted">${dur(t.duracion_s)} · ${t.distancia_m ?? 0} m ·
          ${t.muestras_gps} puntos GPS · video ${fmtBytes(t.video_bytes)}</span>` : ""}
        ${t.aviso ? `<span class="tramo-aviso">⚠ ${escapeHtml(t.aviso)}</span>` : ""}
        ${t.error ? `<span class="tramo-error">✕ ${escapeHtml(t.error)}</span>` : ""}
        ${listo ? `<div class="actions">
            <a class="btn btn-ghost btn-sm" href="${base}/video.mp4">Video MP4</a>
            <a class="btn btn-ghost btn-sm" href="${base}/telemetria.csv">Telemetría</a>
            ${t.estado !== "descartado" ? `<button class="btn btn-danger btn-sm" data-descartar="${t.n}">Descartar</button>` : ""}
          </div>` : ""}
        ${["esperando", "grabando", "subiendo"].includes(t.estado) ? `<div class="actions">
            <button class="btn btn-danger btn-sm" data-descartar="${t.n}"
              title="Si la app se cerró o el tramo no va a llegar">Descartar</button></div>` : ""}
      </li>`;
  }).join("");
  ul.querySelectorAll("[data-descartar]").forEach((b) => b.addEventListener("click", async () => {
    if (!confirm(`¿Excluir el tramo ${b.dataset.descartar} del informe?`)) return;
    await api(`/api/recorridos/${encodeURIComponent(rec.id)}/tramos/${b.dataset.descartar}/descartar`, { method: "POST" });
    refrescar(true);
  }));
}

function instruccion(rec) {
  if (rec.estado !== "abierto") return "Recorrido finalizado. Ya puedes generar el informe.";
  const t = rec.tramos.find((x) => ["esperando", "grabando", "subiendo", "procesando"].includes(x.estado));
  if (!t) return "Pulsa NUEVO TRAMO (o directamente ● REC en la app: se crea un tramo nuevo solo).";
  return {
    esperando: `Tramo ${t.n} listo: en la app pulsa ● REC para empezar a grabarlo.`,
    grabando: `Grabando tramo ${t.n}… En la app pulsa ■ STOP al terminar el tramo.`,
    subiendo: `Recibiendo los archivos del tramo ${t.n}…`,
    procesando: `Convirtiendo el video del tramo ${t.n}…`,
  }[t.estado];
}

function renderInforme(rec) {
  const inf = rec.informe ?? { estado: "no_generado" };
  const btn = $("btn-informe");
  const lnk = $("lnk-informe");
  const log = $("informe-log");
  const generando = inf.estado === "generando";
  btn.disabled = generando;
  btn.textContent = generando ? "GENERANDO…" : inf.estado === "listo" ? "REGENERAR INFORME" : "GENERAR INFORME";

  lnk.hidden = inf.estado !== "listo";
  lnk.href = `/api/recorridos/${encodeURIComponent(rec.id)}/informe/informe_final.html`;

  const txt = {
    no_generado: "Aún no se ha generado.",
    generando: "Analizando tramos (puede tardar varios minutos)…",
    listo: `Listo ${fmtDateTime(inf.fin_ms)}${inf.con_ia ? " · redactado con IA" : " · sin redacción con IA"}.`,
    error: `Error: ${inf.error ?? ""}`,
  }[inf.estado] ?? inf.estado;
  $("informe-estado").textContent = txt;
  $("informe-estado").classList.toggle("pulse", generando);

  log.hidden = !inf.log;
  if (inf.log && log.textContent !== inf.log) {
    log.textContent = inf.log;
    log.scrollTop = log.scrollHeight;
  }
}

function renderDetalle(rec) {
  $("rec-detalle").hidden = false;
  $("rec-titulo").textContent = rec.nombre;
  $("rec-sub").textContent = `${fmtDateTime(rec.creado_ms)} · ${rec.id}`;
  const est = $("rec-estado");
  est.textContent = rec.estado === "abierto" ? "ABIERTO" : "FINALIZADO";
  est.className = `badge ${rec.estado === "abierto" ? "ok" : ""}`;
  $("rec-acciones-abierto").hidden = rec.estado !== "abierto";
  $("btn-rec-reabrir").hidden = rec.estado === "abierto";
  $("rec-instruccion").textContent = instruccion(rec);
  renderTramos(rec);
  renderInforme(rec);
}

async function renderLista(activoId) {
  let lista = [];
  try { lista = await api("/api/recorridos"); } catch { return; }
  const ul = $("rec-lista");
  if (!lista.length) { ul.innerHTML = '<li class="empty">Todavía no hay recorridos.</li>'; return; }
  ul.innerHTML = lista.map((r) => `
    <li class="clickable ${r.id === seleccionado ? "selected" : ""}" data-id="${escapeHtml(r.id)}">
      <div class="row"><span class="title">${escapeHtml(r.nombre)}</span>
        ${r.id === activoId ? '<span class="badge ok">ABIERTO</span>' : ""}
        ${r.informe === "listo" ? '<span class="badge info">INFORME</span>' : ""}</div>
      <span class="muted">${fmtDateTime(r.creado_ms)} · ${r.tramos} tramo(s)</span>
    </li>`).join("");
  ul.querySelectorAll("[data-id]").forEach((li) => li.addEventListener("click", () => {
    seleccionado = li.dataset.id;
    refrescar(true);
  }));
}

export async function refrescar(forzar = false) {
  let activo = null;
  try { activo = await api("/api/recorridos/activo"); } catch { return; }
  $("rec-nuevo").hidden = !!activo;
  if (!seleccionado && activo) seleccionado = activo.id;

  let rec = null;
  if (seleccionado) {
    try { rec = activo?.id === seleccionado ? activo : await api(`/api/recorridos/${encodeURIComponent(seleccionado)}`); }
    catch { seleccionado = null; }
  }
  const json = JSON.stringify([rec, activo?.id]);
  if (!forzar && json === ultimoJson) return;
  ultimoJson = json;

  if (rec) renderDetalle(rec); else $("rec-detalle").hidden = true;
  renderLista(activo?.id);
}

async function accion(fn, okMsg) {
  try {
    await fn();
    if (okMsg) toast(okMsg);
  } catch (e) {
    toast(`Error: ${e.message}`);
  }
  refrescar(true);
}

export function initRecorridos() {
  $("btn-rec-nuevo").addEventListener("click", () => accion(async () => {
    const rec = await api("/api/recorridos", {
      method: "POST", body: JSON.stringify({ nombre: $("rec-nombre").value || "Recorrido" }),
    });
    seleccionado = rec.id;
    await api(`/api/recorridos/${encodeURIComponent(rec.id)}/tramos`, { method: "POST" });
  }, "Recorrido creado: tramo 1 esperando REC en la app"));

  $("btn-tramo-nuevo").addEventListener("click", () => accion(async () => {
    const t = await api(`/api/recorridos/${encodeURIComponent(seleccionado)}/tramos`, { method: "POST" });
    toast(`Tramo ${t.n} listo: pulsa ● REC en la app`);
  }));

  $("btn-rec-finalizar").addEventListener("click", () => {
    if (!confirm("¿Finalizar el recorrido? Ya no se aceptarán más tramos.")) return;
    accion(() => api(`/api/recorridos/${encodeURIComponent(seleccionado)}/finalizar`, { method: "POST" }),
      "Recorrido finalizado");
  });

  $("btn-rec-reabrir").addEventListener("click", () =>
    accion(() => api(`/api/recorridos/${encodeURIComponent(seleccionado)}/reabrir`, { method: "POST" }),
      "Recorrido reabierto"));

  $("btn-informe").addEventListener("click", () =>
    accion(() => api(`/api/recorridos/${encodeURIComponent(seleccionado)}/informe`, { method: "POST" }),
      "Generando informe…"));

  api("/api/recorridos/diagnostico").then((d) => {
    const partes = [
      d.inspeccion_encontrado ? "análisis ✓" : `⚠ no encuentro inspeccion-dron (${d.inspeccion_dir})`,
      d.ffmpeg ? "ffmpeg ✓" : "⚠ falta ffmpeg",
      d.clave_configurada ? `IA ${d.proveedor} ✓` : "IA sin clave (informe sin redacción)",
    ];
    $("rec-diag").textContent = partes.join(" · ");
  }).catch(() => {});

  refrescar(true);
  setInterval(() => refrescar(false), 2000);
}
