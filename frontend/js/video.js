// Video en vivo: bloques H.264 crudos por WebSocket → JMuxer → MediaSource → <video>.
//
// Robustez:
//  - Tras crear el reproductor se descartan datos hasta ver un SPS (inicio de GOP),
//    porque JMuxer necesita SPS/PPS para generar el segmento inicial.
//  - Si llegan datos pero el <video> no arranca en unos segundos, se recrea el
//    reproductor (watchdog). También al empezar una grabación nueva tras una pausa.
/* global JMuxer */
import { setPill } from "./api.js";

let ws = null;
let jmuxer = null;
let lastDataMs = 0;
let reconnectTimer = null;
let waitingForSps = true;
let playerCreatedMs = 0;
let fedSinceCreate = false;

function createPlayer() {
  if (jmuxer) { try { jmuxer.destroy(); } catch { /* ignorar */ } }
  jmuxer = new JMuxer({
    node: "live-video",
    mode: "video",
    flushingTime: 0,
    fps: 30,
    debug: false,
    onError: () => { /* datos dañados: se recupera en el próximo keyframe */ },
  });
  waitingForSps = true;
  fedSinceCreate = false;
  playerCreatedMs = Date.now();
}

/** Índice del último SPS (00 00 01 67) del bloque, incluyendo un 00 previo si es start code de 4 bytes. */
function findSps(bytes) {
  for (let i = bytes.length - 4; i >= 0; i--) {
    if (bytes[i] === 0 && bytes[i + 1] === 0 && bytes[i + 2] === 1 && (bytes[i + 3] & 0x1f) === 7) {
      return i > 0 && bytes[i - 1] === 0 ? i - 1 : i;
    }
  }
  return -1;
}

function onChunk(buf) {
  const now = Date.now();
  // Una pausa larga indica una grabación nueva: empezar limpio.
  if (lastDataMs && now - lastDataMs > 5000) createPlayer();
  lastDataMs = now;
  document.getElementById("video-empty").classList.add("hidden");

  let bytes = new Uint8Array(buf);
  if (waitingForSps) {
    const idx = findSps(bytes);
    if (idx < 0) return;           // seguir esperando el inicio de un GOP
    bytes = bytes.subarray(idx);
    waitingForSps = false;
  }
  try {
    jmuxer.feed({ video: bytes });
    fedSinceCreate = true;
  } catch { /* ignorar bloque */ }
}

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/video`);
  ws.binaryType = "arraybuffer";
  ws.onopen = () => createPlayer(); // el servidor envía primero el último GOP
  ws.onmessage = (ev) => { if (ev.data instanceof ArrayBuffer) onChunk(ev.data); };
  ws.onclose = () => {
    clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(connect, 2000);
  };
  ws.onerror = () => ws.close();
}

export function initVideo() {
  if (typeof JMuxer === "undefined") {
    setPill("pill-video", "bad", "Video: falta JMuxer");
    return;
  }
  createPlayer();
  connect();

  document.getElementById("btn-video-reconnect").addEventListener("click", () => {
    if (ws) ws.close(); // al reconectar se recrea el reproductor
  });

  setInterval(() => {
    const live = Date.now() - lastDataMs < 3000;
    setPill("pill-video", live ? "ok" : null, live ? "Video: en vivo" : "Video: inactivo");
    if (!live) document.getElementById("video-empty").classList.remove("hidden");

    const v = document.getElementById("live-video");
    // Watchdog: recibimos y alimentamos datos pero el video no arranca → reiniciar.
    if (live && fedSinceCreate && v.readyState === 0 && Date.now() - playerCreatedMs > 4000) {
      createPlayer();
    }
    // Mantener el video al borde del directo.
    if (live && v.buffered.length) {
      const end = v.buffered.end(v.buffered.length - 1);
      if (end - v.currentTime > 1.5) v.currentTime = end - 0.2;
      if (v.paused) v.play().catch(() => {});
    }
    if (ws && ws.readyState === WebSocket.OPEN) ws.send("ping");
  }, 1000);
}
