// Video en vivo: la app envía fotogramas JPEG (~8 por segundo) a /api/live/frame
// y el servidor los reenvía por el WebSocket /ws/live. Cada mensaje binario es una
// imagen completa, así que se muestra al instante (sin decodificador H.264 en el
// navegador ni esperar a un keyframe: ya no hay pantalla negra).
//
// El H.264 de las grabaciones se sigue guardando aparte y se convierte a MP4
// (pestañas Vuelos y Videos).
import { setPill } from "./api.js";

let ws = null;
let reconnectTimer = null;
let lastFrameMs = 0;
let currentUrl = null;
let frames = 0;
let fps = 0;

function showFrame(buf) {
  lastFrameMs = Date.now();
  frames++;
  const url = URL.createObjectURL(new Blob([buf], { type: "image/jpeg" }));
  const img = document.getElementById("live-img");
  img.onload = () => { if (currentUrl && currentUrl !== url) URL.revokeObjectURL(currentUrl); currentUrl = url; };
  img.onerror = () => URL.revokeObjectURL(url);
  img.src = url;
  document.getElementById("video-empty").classList.add("hidden");
}

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/live`);
  ws.binaryType = "arraybuffer";
  ws.onmessage = (ev) => { if (ev.data instanceof ArrayBuffer) showFrame(ev.data); };
  ws.onclose = () => {
    clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(connect, 2000);
  };
  ws.onerror = () => ws.close();
}

export function initVideo() {
  connect();

  document.getElementById("btn-video-reconnect").addEventListener("click", () => {
    if (ws) ws.close();
  });

  setInterval(() => {
    fps = frames;
    frames = 0;
    const live = Date.now() - lastFrameMs < 3000;
    setPill("pill-video", live ? "ok" : null, live ? `Video: en vivo (${fps} fps)` : "Video: inactivo");
    if (!live) document.getElementById("video-empty").classList.remove("hidden");
    if (ws && ws.readyState === WebSocket.OPEN) ws.send("ping");
  }, 1000);
}
