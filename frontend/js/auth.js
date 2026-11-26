// Acceso con token: si la estación está protegida (para exponerla con Cloudflare), pide el token una vez.
// El servidor responde con una cookie HttpOnly y, desde ahí, fetch, WebSocket y descargas funcionan solos.
// Si la estación no usa token (red local), este módulo no hace nada.

let overlay = null;

function css() {
  const st = document.createElement("style");
  st.textContent = `
    .auth-back { position: fixed; inset: 0; z-index: 5000; display: grid; place-items: center; padding: 16px;
      background: rgba(5, 8, 14, .92); font-family: var(--sans, system-ui, sans-serif); color: var(--text, #f1f5f9); }
    .auth-box { width: min(380px, 100%); padding: 22px; border-radius: 8px; background: var(--c-card, #1e293b);
      border: 1px solid var(--c-border, #334155); border-top: 3px solid var(--accent, #84cc16); box-shadow: 0 20px 50px rgba(0,0,0,.6); }
    .auth-box h2 { margin: 0 0 6px; font-size: 20px; text-transform: uppercase; letter-spacing: .05em; }
    .auth-box p { margin: 0 0 14px; font-size: 14px; color: var(--muted, #94a3b8); }
    .auth-box input { width: 100%; padding: 9px 10px; border-radius: 4px; font: 14px var(--mono, monospace);
      background: var(--c-inset, #0b1120); color: var(--text, #f1f5f9); border: 1px solid var(--c-border, #334155); }
    .auth-box input:focus { outline: none; border-color: var(--accent, #84cc16); }
    .auth-box button { width: 100%; margin-top: 12px; padding: 9px; border: 0; border-radius: 4px; cursor: pointer;
      background: var(--accent, #84cc16); color: var(--accent-ink, #070c18); font: 800 13px var(--sans, sans-serif);
      letter-spacing: .06em; text-transform: uppercase; }
    .auth-box button:disabled { opacity: .6; cursor: default; }
    .auth-err { min-height: 18px; margin-top: 8px; font-size: 13px; color: var(--bad, #f43f5e); }`;
  document.head.appendChild(st);
}

export function showLogin(message = "") {
  if (overlay) return;   // ya está visible: no pisar el mensaje del último intento
  css();
  overlay = document.createElement("div");
  overlay.className = "auth-back";
  overlay.innerHTML = `
    <form class="auth-box" autocomplete="off">
      <h2>Estación de tierra</h2>
      <p>Esta estación está protegida. Escribe el token de acceso para entrar.</p>
      <input type="password" name="token" placeholder="Token de la estación" autocomplete="current-password" required>
      <div class="auth-err" role="alert"></div>
      <button type="submit">Entrar</button>
    </form>`;
  document.body.appendChild(overlay);
  const form = overlay.querySelector("form");
  const err = overlay.querySelector(".auth-err");
  const btn = overlay.querySelector("button");
  err.textContent = message;
  overlay.querySelector("input").focus();
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    btn.disabled = true;
    err.textContent = "";
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: form.token.value }),
      });
      if (res.ok) { location.reload(); return; }
      const body = await res.json().catch(() => ({}));
      err.textContent = body.detail || `Error ${res.status}`;
    } catch {
      err.textContent = "No se pudo conectar con la estación.";
    }
    btn.disabled = false;
  });
}

// Al cargar: ¿la estación pide token y todavía no lo tengo?
fetch("/api/auth/me").then((r) => (r.ok ? r.json() : null)).then((me) => {
  if (me && me.required && !me.authorized) showLogin();
}).catch(() => { /* sin servidor: el panel ya muestra "sin conexión" */ });
