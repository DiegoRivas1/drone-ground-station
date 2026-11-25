// Selector de tema: asfalto (predeterminado), catastro y táctico. Se recuerda en el navegador.
const THEMES = ["asfalto", "catastro", "tactico"];
const KEY = "estacion-tema";

export function currentTheme() {
  const t = document.documentElement.dataset.theme;
  return THEMES.includes(t) ? t : "asfalto";
}

function apply(theme) {
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem(KEY, theme); } catch { /* sin almacenamiento: no pasa nada */ }
  document.querySelectorAll("[data-theme-btn]").forEach((b) =>
    b.setAttribute("aria-pressed", String(b.dataset.themeBtn === theme)));
  window.dispatchEvent(new CustomEvent("themechange", { detail: theme }));
}

/** Lee un color del tema activo (para el mapa, que dibuja con JS). */
export function themeColor(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim();
}

export function initThemes() {
  document.querySelectorAll("[data-theme-btn]").forEach((b) =>
    b.addEventListener("click", () => apply(b.dataset.themeBtn)));
  apply(currentTheme());
}
