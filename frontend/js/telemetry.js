// Muestra la telemetría del dron en las tarjetas.

const $ = (id) => document.getElementById(id);

function num(v, digits, unit = "") {
  return v == null || Number.isNaN(v) ? "--" : `${Number(v).toFixed(digits)}${unit}`;
}

export function renderTelemetry(s) {
  if (!s) return;
  const bat = s.battery_pct;
  $("tl-battery").textContent = bat == null ? "--" : `${bat}%`;
  const bar = $("tl-battery-bar");
  bar.style.width = `${bat ?? 0}%`;
  const batColor = bat == null ? "var(--c-border)" : bat < 20 ? "var(--bad)" : bat < 40 ? "var(--warn)" : "var(--ok)";
  bar.style.background = batColor;
  // misma batería en la cabecera
  $("hdr-bat").textContent = bat == null ? "Batería: --" : `Batería: ${bat}%`;
  const hb = $("hdr-bat-bar");
  hb.style.width = `${bat ?? 0}%`;
  hb.style.background = batColor;

  $("tl-alt").textContent = num(s.altitude_m, 1, " m");
  $("tl-speed").textContent = num(s.speed_mps, 1, " m/s");
  $("tl-heading").textContent = num(s.heading_deg, 0, "°");
  $("tl-compass").style.setProperty("--deg", `${Number.isFinite(s.heading_deg) ? s.heading_deg : 0}deg`);
  $("hud-alt").textContent = `ALT ${num(s.altitude_m, 1, " m")}`;
  $("hud-spd").textContent = num(s.speed_mps, 1, " m/s");
  $("tl-gps").textContent = s.satellites == null && s.gps_level == null
    ? "--" : `${s.satellites ?? "-"} sat · ${s.gps_level ?? "-"}/5`;
  $("tl-state").textContent = s.is_flying ? "Volando" : s.motors_on ? "Motores ON" : "En tierra";
  $("tl-lat").textContent = num(s.latitude, 7);
  $("tl-lon").textContent = num(s.longitude, 7);
  $("tl-mode").textContent = s.flight_mode ?? "--";
  $("tl-vz").textContent = s.velocity_z == null ? "--" : `${(-s.velocity_z).toFixed(1)} m/s`;
}

export function renderAge(ageMs) {
  const el = $("tl-age");
  if (ageMs == null) { el.textContent = "sin datos"; return; }
  el.textContent = ageMs < 1500 ? "en vivo" : `hace ${(ageMs / 1000).toFixed(0)} s`;
}
