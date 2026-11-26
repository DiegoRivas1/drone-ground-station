// Mapa Leaflet: posición del dron, traza del vuelo, ruta en edición y rutas guardadas.
/* global L */
import { themeColor } from "./themes.js";

// Centro inicial (Arequipa); se recentra al llegar la primera posición del dron.
const DEFAULT_CENTER = [-16.409, -71.5375];

let map;
let droneMarker = null;
let trackLine;
let historyLine;
let editLine;
let editMarkers = [];
let savedRouteLayer;
let segLabels;
let follow = true;
let centeredOnce = false;
let onMapClick = null;

export function initMap() {
  map = L.map("map", { zoomControl: true }).setView(DEFAULT_CENTER, 17);

  const osm = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 20, maxNativeZoom: 19, attribution: "&copy; OpenStreetMap",
  });
  const sat = L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    { maxZoom: 20, maxNativeZoom: 19, attribution: "Imagery &copy; Esri" },
  );
  sat.addTo(map);
  // Las capas se cambian con los botones "Capas" de la tarjeta del mapa.
  document.querySelectorAll("[data-layer]").forEach((b) => b.addEventListener("click", () => {
    const next = b.dataset.layer === "osm" ? osm : sat;
    const prev = next === osm ? sat : osm;
    if (map.hasLayer(prev)) map.removeLayer(prev);
    next.addTo(map);
    document.querySelectorAll("[data-layer]").forEach((x) => x.classList.toggle("active", x === b));
  }));
  L.control.scale({ imperial: false }).addTo(map);

  // Como en Stitch: traza recorrida en azul cielo (info), ruta planificada en lima (accent).
  trackLine = L.polyline([], { color: themeColor("info"), weight: 3, dashArray: "6 4", className: "trace trace-done" }).addTo(map);
  historyLine = L.polyline([], { color: themeColor("extra"), weight: 3, dashArray: "4 6" }).addTo(map);
  editLine = L.polyline([], { color: themeColor("accent"), weight: 3, dashArray: "8 6", className: "trace trace-plan" }).addTo(map);
  segLabels = L.layerGroup().addTo(map);
  savedRouteLayer = L.layerGroup().addTo(map);

  // Leaflet necesita recalcular su tamaño cuando cambia el diseño de la página.
  new ResizeObserver(() => map.invalidateSize()).observe(document.getElementById("map"));

  map.on("click", (e) => { if (onMapClick) onMapClick(e.latlng); });
  map.on("dragstart", () => {
    // Si el usuario arrastra el mapa, deja de seguir al dron.
    const chk = document.getElementById("chk-follow");
    if (chk.checked) { chk.checked = false; follow = false; }
  });
  // Al cambiar de tema, recolorea las trazas ya dibujadas.
  window.addEventListener("themechange", () => {
    trackLine.setStyle({ color: themeColor("info") });
    historyLine.setStyle({ color: themeColor("extra") });
    editLine.setStyle({ color: themeColor("accent") });
  });
  return map;
}

export function setFollow(v) { follow = v; }
export function setMapClickHandler(fn) { onMapClick = fn; }

// Marcador del dron (Stitch): anillo con pulso, cuerpo con flecha de rumbo y etiqueta con la altitud.
// Se crea una sola vez y luego solo se actualizan rumbo y etiqueta, para no reiniciar la animación.
const droneIcon = L.divIcon({
  className: "",
  html: `<div class="drone-mk"><span class="drone-ring"></span><span class="drone-halo"></span>
    <div class="drone-body"><i class="drone-nose"></i></div>
    <div class="drone-label">MAVIC AIR · -- m</div></div>`,
  iconSize: [32, 32],
  iconAnchor: [16, 16],
});

function paintDrone(s) {
  const el = droneMarker.getElement();
  if (!el) return;
  el.querySelector(".drone-body").style.transform = `rotate(${s.heading_deg ?? 0}deg)`;
  const alt = Number.isFinite(s.altitude_m) ? `${s.altitude_m.toFixed(1)} m` : "-- m";
  el.querySelector(".drone-label").textContent = `MAVIC AIR · ${alt}`;
}

function validPos(s) {
  return s && s.latitude != null && s.longitude != null &&
    Number.isFinite(s.latitude) && Number.isFinite(s.longitude) &&
    !(s.latitude === 0 && s.longitude === 0);
}

/** Actualiza el dron en el mapa (la flecha apunta al Norte con rumbo 0°). */
export function updateDrone(s) {
  if (!validPos(s)) return;
  const ll = [s.latitude, s.longitude];
  if (!droneMarker) {
    droneMarker = L.marker(ll, { icon: droneIcon, zIndexOffset: 1000, interactive: false }).addTo(map);
  } else {
    droneMarker.setLatLng(ll);
  }
  paintDrone(s);
  const pts = trackLine.getLatLngs();
  const last = pts[pts.length - 1];
  if (!last || last.distanceTo(ll) > 0.3) trackLine.addLatLng(ll);
  if (pts.length > 20000) trackLine.setLatLngs(pts.slice(-10000));

  if (!centeredOnce) { map.setView(ll, 19); centeredOnce = true; }
  else if (follow) map.panTo(ll, { animate: true, duration: 0.3 });
}

export function clearTrack() { trackLine.setLatLngs([]); }

/** Traza de un vuelo pasado (desde la pestaña Vuelos). */
export function showHistory(samples) {
  const pts = samples.filter(validPos).map((s) => [s.latitude, s.longitude]);
  historyLine.setLatLngs(pts);
  if (pts.length) map.fitBounds(historyLine.getBounds(), { padding: [30, 30], maxZoom: 20 });
  return pts.length;
}

export const wpName = (i) => `WP-${String(i + 1).padStart(2, "0")}`;

const wpIcon = (i) => L.divIcon({
  className: "wp-icon",
  html: `<span>${i + 1}</span><b class="wp-label">${wpName(i)}</b>`,
  iconSize: [22, 22],
  iconAnchor: [11, 11],
});

/** Etiquetas de distancia en el centro de cada tramo de la ruta (como en Stitch). */
function drawSegmentLabels(lls) {
  segLabels.clearLayers();
  for (let i = 1; i < lls.length; i++) {
    const a = L.latLng(lls[i - 1]);
    const b = L.latLng(lls[i]);
    const mid = L.latLng((a.lat + b.lat) / 2, (a.lng + b.lng) / 2);
    L.marker(mid, {
      interactive: false,
      icon: L.divIcon({ className: "seg-label", html: `<span>${a.distanceTo(b).toFixed(1)} m</span>`, iconSize: null }),
    }).addTo(segLabels);
  }
}

/** Dibuja la ruta en edición. points = [{latitude, longitude, ...}] */
export function drawEditRoute(points, onDragEnd) {
  editMarkers.forEach((m) => m.remove());
  editMarkers = points.map((p, i) => {
    const m = L.marker([p.latitude, p.longitude], { icon: wpIcon(i), draggable: true }).addTo(map);
    m.on("dragend", () => {
      const ll = m.getLatLng();
      onDragEnd(i, ll.lat, ll.lng);
    });
    return m;
  });
  const lls = points.map((p) => [p.latitude, p.longitude]);
  editLine.setLatLngs(lls);
  drawSegmentLabels(lls);
}

/** Muestra una ruta guardada (sólo lectura). */
export function showSavedRoute(route) {
  savedRouteLayer.clearLayers();
  if (!route) return;
  const lls = route.points.map((p) => [p.latitude, p.longitude]);
  L.polyline(lls, { color: route.active ? themeColor("ok") : themeColor("muted"), weight: 3 }).addTo(savedRouteLayer);
  route.points.forEach((p, i) => {
    L.circleMarker([p.latitude, p.longitude], { radius: 6, color: "#fff", weight: 2, fillColor: themeColor("ok"), fillOpacity: 1 })
      .bindTooltip(`${p.id} · ${p.altitude_m} m · ${p.speed_mps} m/s`)
      .addTo(savedRouteLayer);
    if (i === 0) map.fitBounds(L.latLngBounds(lls), { padding: [40, 40], maxZoom: 20 });
  });
}

export function dronePosition() {
  return droneMarker ? droneMarker.getLatLng() : null;
}
