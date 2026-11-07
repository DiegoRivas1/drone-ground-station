// Editor de rutas GPS y lista de rutas guardadas.
import { api, distanceM, escapeHtml, fmtDateTime, toast } from "./api.js";
import { drawEditRoute, setFollow, setMapClickHandler, showSavedRoute } from "./map.js";

// Mismos límites que FlightValidator.kt en la app.
const MIN_SEGMENT_M = 0.6;
const MAX_SEGMENT_M = 100;

let points = [];
let editing = false;

const $ = (id) => document.getElementById(id);

function currentAlt() { return Number($("route-alt").value) || 5; }
function currentSpeed() { return Number($("route-speed").value) || 1; }

function redraw() {
  drawEditRoute(points, (i, lat, lon) => {
    points[i] = { ...points[i], latitude: lat, longitude: lon };
    redraw();
  });

  const list = $("route-points");
  list.innerHTML = points.map((p, i) => `
    <li>${p.latitude.toFixed(6)}, ${p.longitude.toFixed(6)} · ${p.altitude_m} m
      <button class="btn btn-ghost btn-sm" data-del="${i}" title="Quitar">✕</button></li>`).join("");
  list.querySelectorAll("[data-del]").forEach((b) =>
    b.addEventListener("click", () => { points.splice(Number(b.dataset.del), 1); redraw(); }));

  let total = 0;
  const warnings = [];
  for (let i = 1; i < points.length; i++) {
    const d = distanceM(points[i - 1].latitude, points[i - 1].longitude, points[i].latitude, points[i].longitude);
    total += d;
    if (d < MIN_SEGMENT_M) warnings.push(`tramo ${i} muy corto`);
    if (d > MAX_SEGMENT_M) warnings.push(`tramo ${i} > ${MAX_SEGMENT_M} m`);
  }
  $("route-meta").textContent =
    `${points.length} puntos · ${total.toFixed(1)} m` + (warnings.length ? ` · ⚠ ${warnings.join(", ")}` : "");
}

async function saveRoute() {
  if (points.length < 2) { toast("La ruta necesita al menos 2 puntos"); return; }
  const body = {
    name: $("route-name").value.trim() || "Ruta",
    points: points.map((p, i) => ({ ...p, id: `P${i + 1}` })),
  };
  try {
    await api("/api/routes", { method: "POST", body: JSON.stringify(body) });
    toast("Ruta guardada");
    await loadRoutes();
  } catch (e) {
    toast(`Error: ${e.message}`);
  }
}

export async function loadRoutes() {
  const list = $("routes-list");
  let routes = [];
  try { routes = await api("/api/routes"); } catch { list.innerHTML = '<li class="empty">Sin conexión</li>'; return; }
  if (!routes.length) { list.innerHTML = '<li class="empty">No hay rutas guardadas</li>'; return; }

  list.innerHTML = routes.map((r) => `
    <li>
      <div class="row">
        <span class="title">${escapeHtml(r.name)}</span>
        ${r.active ? '<span class="badge ok">ACTIVA</span>' : ""}
      </div>
      <span class="muted">${r.points.length} puntos · ${fmtDateTime(r.created_ms)}</span>
      <div class="actions">
        <button class="btn btn-ghost btn-sm" data-show="${r.id}">Ver</button>
        <button class="btn btn-ghost btn-sm" data-edit="${r.id}">Editar copia</button>
        ${r.active ? "" : `<button class="btn btn-sm" data-activate="${r.id}">Activar</button>`}
        <button class="btn btn-danger btn-sm" data-delete="${r.id}">Eliminar</button>
      </div>
    </li>`).join("");

  const byId = Object.fromEntries(routes.map((r) => [String(r.id), r]));
  list.querySelectorAll("[data-show]").forEach((b) =>
    b.addEventListener("click", () => showSavedRoute(byId[b.dataset.show])));
  list.querySelectorAll("[data-edit]").forEach((b) => b.addEventListener("click", () => {
    const r = byId[b.dataset.edit];
    points = r.points.map((p) => ({ ...p }));
    $("route-name").value = `${r.name} (copia)`;
    redraw();
    showSavedRoute(null);
  }));
  list.querySelectorAll("[data-activate]").forEach((b) => b.addEventListener("click", async () => {
    await api(`/api/routes/${b.dataset.activate}/activate`, { method: "POST" });
    toast("Ruta activa: la app la descarga con WP: CARGAR RUTA DEL PANEL");
    loadRoutes();
  }));
  list.querySelectorAll("[data-delete]").forEach((b) => b.addEventListener("click", async () => {
    if (!confirm("¿Eliminar esta ruta?")) return;
    await api(`/api/routes/${b.dataset.delete}`, { method: "DELETE" });
    showSavedRoute(null);
    loadRoutes();
  }));
}

export function initRoutes() {
  setMapClickHandler((ll) => {
    if (!editing) return;
    points.push({ latitude: ll.lat, longitude: ll.lng, altitude_m: currentAlt(), speed_mps: currentSpeed() });
    redraw();
  });
  $("chk-edit").addEventListener("change", (e) => {
    editing = e.target.checked;
    if (editing) {
      // Al editar, el mapa no debe moverse siguiendo al dron.
      $("chk-follow").checked = false;
      setFollow(false);
    }
    document.getElementById("map").style.cursor = editing ? "crosshair" : "";
  });
  // Cambiar altitud/velocidad aplica a todos los puntos de la ruta en edición.
  $("route-alt").addEventListener("change", () => { points = points.map((p) => ({ ...p, altitude_m: currentAlt() })); redraw(); });
  $("route-speed").addEventListener("change", () => { points = points.map((p) => ({ ...p, speed_mps: currentSpeed() })); redraw(); });
  $("btn-route-save").addEventListener("click", saveRoute);
  $("btn-route-undo").addEventListener("click", () => { points.pop(); redraw(); });
  $("btn-route-clear").addEventListener("click", () => { points = []; redraw(); });
  redraw();
  loadRoutes();
}
