// Shared helpers for the operator and display pages.

const PIN_KEY = "funbooth.pin";

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

export function store(key, value) {
  try {
    if (value === undefined) return localStorage.getItem(key);
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    // Private mode or storage disabled: settings just won't be remembered.
  }
  return null;
}

export const getPin = () => store(PIN_KEY) || "";
export const forgetPin = () => store(PIN_KEY, null);

/** Ask for the booth PIN until the server accepts it. */
export async function ensurePin() {
  const saved = getPin();
  if (saved && (await checkPin(saved))) return saved;

  const dialog = document.createElement("dialog");
  dialog.className = "pin-dialog";
  dialog.innerHTML = `
    <form method="dialog">
      <div class="pin-emoji">🔒</div>
      <h2>Enter booth PIN</h2>
      <input name="pin" type="password" inputmode="numeric" autocomplete="off" required>
      <p class="pin-error" hidden>That PIN didn't work. Try again.</p>
      <button class="btn btn-primary" value="ok">Unlock</button>
    </form>`;
  document.body.append(dialog);
  dialog.addEventListener("cancel", (e) => e.preventDefault());
  dialog.showModal();
  const input = dialog.querySelector("input");
  const error = dialog.querySelector(".pin-error");

  return new Promise((resolve) => {
    dialog.querySelector("form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const pin = input.value.trim();
      if (await checkPin(pin)) {
        store(PIN_KEY, pin);
        dialog.close();
        dialog.remove();
        resolve(pin);
      } else {
        error.hidden = false;
        input.select();
      }
    });
  });
}

async function checkPin(pin) {
  try {
    const res = await fetch("/api/auth", { method: "POST", headers: { "X-Booth-Pin": pin } });
    return res.ok;
  } catch {
    return false;
  }
}

export async function api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: { ...(options.headers || {}), "X-Booth-Pin": getPin() },
  });
  if (res.status === 401) {
    forgetPin();
    location.reload();
  }
  const body = res.headers.get("content-type")?.includes("json") ? await res.json() : null;
  if (!res.ok) throw new Error(body?.detail || `Request failed (${res.status})`);
  return body;
}

/**
 * Live connection to the booth. Reconnects automatically; `handlers[msg.type](msg)` is
 * called for every message and `onStatus(true|false)` when the link goes up or down.
 */
export function connect(role, handlers, onStatus = () => {}) {
  let ws;
  let retry = 0;
  let timer;
  let queue = [];

  const open = () => {
    clearTimeout(timer);
    if (ws && ws.readyState <= WebSocket.OPEN) return;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws?role=${role}&pin=${encodeURIComponent(getPin())}`);
    ws.onopen = () => {
      retry = 0;
      onStatus(true);
      queue.forEach((m) => ws.send(m));
      queue = [];
    };
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      handlers[msg.type]?.(msg);
    };
    ws.onclose = (event) => {
      onStatus(false);
      if (event.code === 4401) {
        forgetPin();
        location.reload();
        return;
      }
      retry = Math.min(retry + 1, 4);
      timer = setTimeout(open, 500 * 2 ** retry);
    };
  };
  open();

  // iPads drop sockets when the screen sleeps; reconnect as soon as we're visible again.
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") open();
  });

  return {
    send(obj) {
      const text = JSON.stringify(obj);
      if (ws.readyState === WebSocket.OPEN) ws.send(text);
      else queue.push(text);
    },
  };
}

export async function loadThemes() {
  const res = await fetch("/api/themes");
  const list = await res.json();
  return Object.fromEntries(list.map((t) => [t.id, t]));
}

export function applyThemeColors(theme, root = document.documentElement) {
  if (!theme) return;
  root.style.setProperty("--theme-frame", theme.frame);
  root.style.setProperty("--theme-accent", theme.accent);
  root.style.setProperty("--theme-ink", theme.ink);
}

/** Camera preview + capture. Crops to the print aspect ratio so what guests see is what prints. */
export class Camera {
  constructor(video) {
    this.video = video;
    this.stream = null;
    this.facing = "user";
    this.error = null;
    this.busy = false;
    this.onended = null;
  }

  get ready() {
    return !!this.stream && this.video.videoWidth > 0;
  }

  /**
   * Start or stop to match `want`; resolves true if anything changed. A failed start is
   * not retried until retry() is called, so the iPad doesn't keep prompting for access.
   */
  async sync(want) {
    if (this.busy || (want && this.error) || want === !!this.stream) return false;
    this.busy = true;
    try {
      if (want) {
        try {
          await this.start();
          this.error = null;
        } catch (err) {
          this.stop();
          this.error = err;
        }
      } else {
        this.stop();
      }
    } finally {
      this.busy = false;
    }
    return true;
  }

  retry() {
    this.error = null;
  }

  async start(facing = this.facing) {
    this.stop();
    this.facing = facing;
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error("this browser can't use the camera here (HTTPS is required)");
    }
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: { facingMode: facing, width: { ideal: 1920 }, height: { ideal: 1080 } },
    });
    const stream = this.stream;
    stream.getVideoTracks()[0]?.addEventListener("ended", () => {
      if (this.stream !== stream) return;
      this.stop();
      this.onended?.();
    });
    this.video.srcObject = this.stream;
    this.video.classList.toggle("mirrored", facing === "user");
    await this.video.play();
    if (!this.video.videoWidth) {
      await new Promise((r) => this.video.addEventListener("loadedmetadata", r, { once: true }));
    }
  }

  stop() {
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    this.video.srcObject = null;
  }

  /** Grab the current frame, centre-cropped to `aspect` (width / height). */
  capture(aspect, maxSide = 2048) {
    const vw = this.video.videoWidth;
    const vh = this.video.videoHeight;
    let sw = vw;
    let sh = vw / aspect;
    if (sh > vh) {
      sh = vh;
      sw = vh * aspect;
    }
    const scale = Math.min(1, maxSide / Math.max(sw, sh));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(sw * scale);
    canvas.height = Math.round(sh * scale);
    canvas.getContext("2d").drawImage(this.video, (vw - sw) / 2, (vh - sh) / 2, sw, sh, 0, 0, canvas.width, canvas.height);
    return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.92));
  }
}

export const aspectFor = (orientation) => (orientation === "portrait" ? 3 / 4 : 16 / 9);

export async function uploadPhoto(blob) {
  const form = new FormData();
  form.append("photo", blob, "capture.jpg");
  return api("/api/capture", { method: "POST", body: form });
}

/**
 * Prepares files for the iPad share sheet (AirDrop, Messages, Save Image, printer apps).
 * Safari only opens the share sheet straight from a tap, so files are fetched ahead of time.
 */
export class Sharer {
  constructor() {
    this.key = null;
    this.files = null;
  }

  get supported() {
    return !!navigator.canShare;
  }

  async prepare(photo, printUrl) {
    const key = photo ? `${photo.id}:${photo.version}:${printUrl}` : null;
    if (key === this.key) return;
    this.key = key;
    this.files = null;
    if (!photo?.result_url || !this.supported) return;
    try {
      const stem = `funbooth-${photo.id.slice(0, 8)}`;
      const [plain, framed] = await Promise.all([fetchFile(photo.result_url, `${stem}.jpg`), fetchFile(printUrl, `${stem}-print.jpg`)]);
      if (this.key === key) this.files = [framed, plain];
    } catch {
      this.files = null;
    }
  }

  get ready() {
    return !!this.files && navigator.canShare({ files: this.files });
  }

  async share(title) {
    if (!this.ready) return false;
    try {
      await navigator.share({ files: this.files, title });
    } catch (err) {
      if (err.name !== "AbortError") throw err;
    }
    return true;
  }
}

async function fetchFile(url, name) {
  const res = await fetch(url);
  if (!res.ok) throw new Error("download failed");
  return new File([await res.blob()], name, { type: "image/jpeg" });
}

let toastTimer;
export function toast(text, level = "info") {
  let el = $("#toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast";
    document.body.append(el);
  }
  el.textContent = text;
  el.dataset.level = level;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), level === "error" ? 6000 : 3000);
}

/** Keep the screen awake (Safari 16.4+). Re-acquired whenever the page becomes visible. */
export function keepAwake() {
  if (!("wakeLock" in navigator)) return;
  const request = () => navigator.wakeLock.request("screen").catch(() => {});
  request();
  document.addEventListener("visibilitychange", () => document.visibilityState === "visible" && request());
}

/** Full-size print URL that changes whenever the printed frame would change. */
export function printUrlFor(photo, prefs) {
  if (!photo?.print_url) return null;
  const key = encodeURIComponent(`${prefs.event_name}|${prefs.print_qr ? 1 : 0}`);
  return `${photo.print_url}&k=${key}`;
}
