// Selector de diseño: catastro (Stitch A) y vialidad (Stitch B). Se recuerda en el navegador.
const THEMES = ["catastro", "vialidad"];
const NAMES = { catastro: "Catastro", vialidad: "Vialidad" };
const KEY = "estacion-tema";

export function currentTheme() {
  const t = document.documentElement.dataset.theme;
  return THEMES.includes(t) ? t : "catastro";
}

/** Lee un color del tema activo (para el mapa, que dibuja con JS). */
export function themeColor(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim();
}

function paintPalette() {
  const el = document.getElementById("ft-palette");
  if (!el) return;
  el.innerHTML = "PALETA:" + ["accent", "info", "extra"].map((n) =>
    `<b style="color:${themeColor(n)}">${themeColor(n).toUpperCase()}</b>`).join(" / ");
}

function apply(theme) {
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem(KEY, theme); } catch { /* sin almacenamiento: no pasa nada */ }
  document.querySelectorAll("[data-theme-btn]").forEach((b) =>
    b.setAttribute("aria-pressed", String(b.dataset.themeBtn === theme)));
  const tag = document.getElementById("theme-tag");
  if (tag) tag.textContent = NAMES[theme];
  paintPalette();
  window.dispatchEvent(new CustomEvent("themechange", { detail: theme }));
}

export function initThemes() {
  document.querySelectorAll("[data-theme-btn]").forEach((b) =>
    b.addEventListener("click", () => apply(b.dataset.themeBtn)));
  apply(currentTheme());
}
