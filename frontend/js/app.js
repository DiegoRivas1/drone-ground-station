// Punto de entrada del panel: WebSocket de telemetría, pestañas y listas.
import { api, escapeHtml, fmtBytes, fmtDateTime, fmtTime, setPill, toast } from "./api.js";
import { clearTrack, initMap, setFollow, showHistory, updateDrone } from "./map.js";
import { initRoutes, loadRoutes } from "./routes.js";
import { renderAge, renderTelemetry } from "./telemetry.js";
import { initVideo } from "./video.js";
import { initRecorridos } from "./recorridos.js";

const $ = (id) => document.getElementById(id);
let lastTelemetryMs = null;
let currentFlight = null;
const MAX_EVENTS = 300;

// ---------------- pestañas ----------------
function initTabs() {
  document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t === tab));
    document.querySelectorAll(".tab-panel").forEach((p) =>
      p.classList.toggle("active", p.id === `tab-${tab.dataset.tab}`));
    if (tab.dataset.tab === "flights") loadFlights();
    if (tab.dataset.tab === "videos") loadVideos();
  }));
}

// ---------------- telemetría en vivo ----------------
function onSamples(flightId, samples) {
  if (!samples.length) return;
  if (flightId !== currentFlight) {
    currentFlight = flightId;
    $("flight-id").textContent = flightId;
    clearTrack();
  }
  samples.forEach(updateDrone);
  renderTelemetry(samples[samples.length - 1]);
  lastTelemetryMs = Date.now();
}

function eventClass(type) {
  if (/ERROR|TIMEOUT|ABORT|DISCONNECTED/.test(type)) return "bad";
  if (/STOP|LANDING/.test(type)) return "warn";
  if (/FINISHED|REACHED|STABILIZED|LANDED|CONNECTED|STARTED/.test(type)) return "ok";
  return "";
}

function addEvent(e, prepend = true) {
  const list = $("events-list");
  list.querySelector(".empty")?.remove();
  const li = document.createElement("li");
  li.innerHTML = `
    <div class="row"><span class="type ${eventClass(e.type)}">${escapeHtml(e.type)}</span>
      <span class="muted">${fmtTime(e.ts_ms)}</span></div>
    ${e.details ? `<span>${escapeHtml(e.details)}</span>` : ""}`;
  if (prepend) list.prepend(li); else list.append(li);
  while (list.children.length > MAX_EVENTS) list.lastChild.remove();
}

function connectTelemetry() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/telemetry`);
  ws.onopen = () => setPill("pill-ws", "ok", "Panel: conectado");
  ws.onclose = () => {
    setPill("pill-ws", "bad", "Panel: reconectando");
    setTimeout(connectTelemetry, 2000);
  };
  ws.onerror = () => ws.close();
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.kind === "telemetry") onSamples(msg.data.flight_id, msg.data.samples);
    else if (msg.kind === "event") {
      addEvent(msg.data);
      if (/ERROR|TIMEOUT|ABORT/.test(msg.data.type)) toast(`${msg.data.type}: ${msg.data.details || ""}`);
    } else if (msg.kind === "routes_changed") loadRoutes();
    else if (msg.kind === "video_completed") {
      if ($("tab-videos").classList.contains("active")) loadVideos();
    }
  };
  setInterval(() => { if (ws.readyState === WebSocket.OPEN) ws.send("ping"); }, 15000);
}

function tickStatus() {
  const age = lastTelemetryMs == null ? null : Date.now() - lastTelemetryMs;
  renderAge(age);
  if (age == null) setPill("pill-drone", null, "Dron: sin datos");
  else if (age < 3000) setPill("pill-drone", "ok", "Dron: en línea");
  else if (age < 15000) setPill("pill-drone", "warn", "Dron: retraso");
  else setPill("pill-drone", "bad", "Dron: sin señal");
}

// ---------------- vuelos ----------------
async function loadFlights() {
  const list = $("flights-list");
  let flights = [];
  try { flights = await api("/api/flights"); } catch { list.innerHTML = '<li class="empty">Sin conexión</li>'; return; }
  if (!flights.length) { list.innerHTML = '<li class="empty">Aún no hay vuelos</li>'; return; }
  list.innerHTML = flights.map((f) => `
    <li>
      <div class="row"><span class="title">${escapeHtml(f.id)}</span>
        ${f.id === currentFlight ? '<span class="badge ok">ACTUAL</span>' : ""}</div>
      <span class="muted">${escapeHtml(f.drone_model ?? "")} · ${fmtDateTime(f.started_at_ms)} → ${fmtTime(f.last_seen_ms)}
        · ${f.samples} muestras · ${f.events} eventos${f.ended ? " · aterrizado" : ""}</span>
      <div class="actions">
        <button class="btn btn-ghost btn-sm" data-track="${escapeHtml(f.id)}">Ver traza</button>
        <button class="btn btn-ghost btn-sm" data-events="${escapeHtml(f.id)}">Eventos</button>
        <a class="btn btn-ghost btn-sm" href="/api/flights/${encodeURIComponent(f.id)}/export.csv">CSV</a>
        ${(f.files || []).filter((n) => n.endsWith(".mp4")).map((n) =>
          `<a class="btn btn-ghost btn-sm" href="/api/flights/${encodeURIComponent(f.id)}/files/${encodeURIComponent(n)}">${escapeHtml(n.replace(".mp4", "").toUpperCase())} MP4</a>`).join("")}
        <button class="btn btn-ghost btn-sm" data-archive="${escapeHtml(f.id)}" title="Regenera storage/flights/${escapeHtml(f.id)}/">Guardar carpeta</button>
      </div>
    </li>`).join("");
  list.querySelectorAll("[data-track]").forEach((b) => b.addEventListener("click", async () => {
    const samples = await api(`/api/flights/${encodeURIComponent(b.dataset.track)}/telemetry?limit=50000`);
    const n = showHistory(samples);
    toast(n ? `Traza: ${n} puntos GPS` : "Ese vuelo no tiene posiciones GPS válidas");
  }));
  list.querySelectorAll("[data-archive]").forEach((b) => b.addEventListener("click", async () => {
    b.disabled = true;
    toast("Generando carpeta del vuelo (CSV + MP4)...");
    try {
      const r = await api(`/api/flights/${encodeURIComponent(b.dataset.archive)}/archive`, { method: "POST" });
      toast(r.errors && r.errors.length ? `Guardado con avisos: ${r.errors[0]}` : `Guardado: ${r.files.join(", ")}`);
    } catch (e) { toast(`Error: ${e.message || e}`); }
    loadFlights();
  }));
  list.querySelectorAll("[data-events]").forEach((b) => b.addEventListener("click", async () => {
    const events = await api(`/api/flights/${encodeURIComponent(b.dataset.events)}/events`);
    $("events-list").innerHTML = events.length ? "" : '<li class="empty">Sin eventos</li>';
    events.slice().reverse().forEach((e) => addEvent(e, false));
    document.querySelector('.tab[data-tab="events"]').click();
  }));
}

// ---------------- videos ----------------
async function loadVideos() {
  const list = $("videos-list");
  let videos = [];
  try { videos = await api("/api/videos"); } catch { list.innerHTML = '<li class="empty">Sin conexión</li>'; return; }
  if (!videos.length) { list.innerHTML = '<li class="empty">Aún no hay videos</li>'; return; }
  list.innerHTML = videos.map((v) => {
    const id = encodeURIComponent(v.id);
    const state = !v.completed ? '<span class="badge warn">GRABANDO</span>'
      : v.incomplete ? '<span class="badge warn">INCOMPLETO</span>' : '<span class="badge ok">COMPLETO</span>';
    return `
    <li>
      <div class="row"><span class="title">${escapeHtml(v.id)}</span>${state}</div>
      <span class="muted">${fmtDateTime(v.started_ms)} · ${fmtBytes(v.bytes)} · ${v.chunks} bloques</span>
      <div class="actions">
        <a class="btn btn-ghost btn-sm" href="/api/videos/${id}/file">.h264</a>
        ${v.mp4_available ? `<a class="btn btn-ghost btn-sm" href="/api/videos/${id}/mp4">MP4</a>` : ""}
        <button class="btn btn-danger btn-sm" data-delvideo="${escapeHtml(v.id)}">Eliminar</button>
      </div>
    </li>`;
  }).join("");
  list.querySelectorAll("[data-delvideo]").forEach((b) => b.addEventListener("click", async () => {
    if (!confirm("¿Eliminar este video de la PC?")) return;
    await api(`/api/videos/${encodeURIComponent(b.dataset.delvideo)}`, { method: "DELETE" });
    loadVideos();
  }));
}

// ---------------- arranque ----------------
async function loadInitialState() {
  try {
    const st = await api("/api/status");
    if (st.flight_id && st.sample) {
      currentFlight = st.flight_id;
      $("flight-id").textContent = st.flight_id;
      const recent = await api(`/api/flights/${encodeURIComponent(st.flight_id)}/telemetry?limit=3000`);
      recent.forEach(updateDrone);
      renderTelemetry(st.sample);
      if (st.age_ms != null) lastTelemetryMs = Date.now() - st.age_ms;
      const events = await api(`/api/flights/${encodeURIComponent(st.flight_id)}/events`);
      events.slice(-MAX_EVENTS).forEach((e) => addEvent(e));
    }
  } catch { /* servidor recién iniciado */ }
  if (!$("events-list").children.length) $("events-list").innerHTML = '<li class="empty">Sin eventos todavía</li>';
}

initTabs();
initMap();
initRoutes();
initVideo();
initRecorridos();
$("chk-follow").addEventListener("change", (e) => setFollow(e.target.checked));
$("btn-clear-track").addEventListener("click", clearTrack);
loadInitialState().then(connectTelemetry);
setInterval(tickStatus, 1000);
tickStatus();
