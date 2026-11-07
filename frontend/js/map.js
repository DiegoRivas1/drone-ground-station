// Mapa Leaflet: posición del dron, traza del vuelo, ruta en edición y rutas guardadas.
/* global L */

// Centro inicial (Arequipa); se recentra al llegar la primera posición del dron.
const DEFAULT_CENTER = [-16.409, -71.5375];

let map;
let droneMarker = null;
let trackLine;
let historyLine;
let editLine;
let editMarkers = [];
let savedRouteLayer;
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
  L.control.layers({ "Satélite": sat, "Mapa": osm }).addTo(map);
  L.control.scale({ imperial: false }).addTo(map);

  trackLine = L.polyline([], { color: "#00c2e0", weight: 3 }).addTo(map);
  historyLine = L.polyline([], { color: "#b388ff", weight: 3, dashArray: "4 6" }).addTo(map);
  editLine = L.polyline([], { color: "#f0a020", weight: 3, dashArray: "6 6" }).addTo(map);
  savedRouteLayer = L.layerGroup().addTo(map);

  // Leaflet necesita recalcular su tamaño cuando cambia el diseño de la página.
  new ResizeObserver(() => map.invalidateSize()).observe(document.getElementById("map"));

  map.on("click", (e) => { if (onMapClick) onMapClick(e.latlng); });
  map.on("dragstart", () => {
    // Si el usuario arrastra el mapa, deja de seguir al dron.
    const chk = document.getElementById("chk-follow");
    if (chk.checked) { chk.checked = false; follow = false; }
  });
  return map;
}

export function setFollow(v) { follow = v; }
export function setMapClickHandler(fn) { onMapClick = fn; }

const droneIcon = (heading) => L.divIcon({
  className: "",
  html: `<div class="drone-icon" style="transform: rotate(${heading ?? 0}deg)">➤</div>`,
  iconSize: [26, 26],
  iconAnchor: [13, 13],
});

function validPos(s) {
  return s && s.latitude != null && s.longitude != null &&
    Number.isFinite(s.latitude) && Number.isFinite(s.longitude) &&
    !(s.latitude === 0 && s.longitude === 0);
}

/** Actualiza el dron en el mapa. El icono ➤ apunta al Este, por eso se resta 90°. */
export function updateDrone(s) {
  if (!validPos(s)) return;
  const ll = [s.latitude, s.longitude];
  const icon = droneIcon((s.heading_deg ?? 0) - 90);
  if (!droneMarker) {
    droneMarker = L.marker(ll, { icon, zIndexOffset: 1000 }).addTo(map).bindTooltip("Mavic Air");
  } else {
    droneMarker.setLatLng(ll);
    droneMarker.setIcon(icon);
  }
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

const wpIcon = (label) => L.divIcon({ className: "wp-icon", html: label, iconSize: [22, 22], iconAnchor: [11, 11] });

/** Dibuja la ruta en edición. points = [{latitude, longitude, ...}] */
export function drawEditRoute(points, onDragEnd) {
  editMarkers.forEach((m) => m.remove());
  editMarkers = points.map((p, i) => {
    const m = L.marker([p.latitude, p.longitude], { icon: wpIcon(i + 1), draggable: true }).addTo(map);
    m.on("dragend", () => {
      const ll = m.getLatLng();
      onDragEnd(i, ll.lat, ll.lng);
    });
    return m;
  });
  editLine.setLatLngs(points.map((p) => [p.latitude, p.longitude]));
}

/** Muestra una ruta guardada (sólo lectura). */
export function showSavedRoute(route) {
  savedRouteLayer.clearLayers();
  if (!route) return;
  const lls = route.points.map((p) => [p.latitude, p.longitude]);
  L.polyline(lls, { color: route.active ? "#2fbf71" : "#8b98a8", weight: 3 }).addTo(savedRouteLayer);
  route.points.forEach((p, i) => {
    L.circleMarker([p.latitude, p.longitude], { radius: 6, color: "#fff", weight: 2, fillColor: "#2fbf71", fillOpacity: 1 })
      .bindTooltip(`${p.id} · ${p.altitude_m} m · ${p.speed_mps} m/s`)
      .addTo(savedRouteLayer);
    if (i === 0) map.fitBounds(L.latLngBounds(lls), { padding: [40, 40], maxZoom: 20 });
  });
}

export function dronePosition() {
  return droneMarker ? droneMarker.getLatLng() : null;
}
