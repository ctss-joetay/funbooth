import {
  $, $$, Camera, Sharer, applyThemeColors, aspectFor, connect, ensurePin, forgetPin,
  keepAwake, loadThemes, printUrlFor, store, toast, uploadPhoto,
} from "/static/common.js";

const FACING_KEY = "funbooth.display.facing";

const els = {
  body: document.body,
  frame: $("#frame"),
  video: $("#video"),
  still: $("#still"),
  count: $("#count"),
  flash: $("#flash"),
  procText: $("#proc-text"),
  side: $("#side"),
  qr: $("#qr"),
  qrHint: $("#qr-hint"),
  airdrop: $("#airdrop"),
  conn: $("#conn"),
  settings: $("#settings"),
};

const camera = new Camera(els.video);
camera.facing = store(FACING_KEY) || "user";
const sharer = new Sharer();

let themes = {};
let state = null;
let myId = null;
let started = false;
let localCapture = null; // blob URL of the frame this iPad just shot
let countdownTimer = null;
let procTimer = null;

await ensurePin();
themes = await loadThemes();

const link = connect(
  "display",
  {
    welcome(msg) {
      myId = msg.client_id;
      link.send({ type: "camera", ready: camera.ready });
    },
    state(msg) {
      const previousPhase = state?.phase;
      state = msg;
      if (state.phase !== "countdown") stopCountdown();
      if (state.phase !== "processing" && previousPhase === "processing") clearLocalCapture();
      render();
    },
    countdown: runCountdown,
    photo() {},
    toast(msg) { toast(msg.text, msg.level); },
  },
  (online) => els.conn.classList.toggle("on", online),
);

// -- start overlay (needed so iPad allows camera, full screen and wake lock) -------------

$("#start-btn").addEventListener("click", () => {
  started = true;
  $("#start").hidden = true;
  goFullscreen();
  keepAwake();
  render();
});

function goFullscreen() {
  const el = document.documentElement;
  const request = el.requestFullscreen || el.webkitRequestFullscreen;
  try {
    request?.call(el)?.catch?.(() => {});
  } catch {
    // Full screen isn't available (e.g. iPhone); "Add to Home Screen" gives the same effect.
  }
}

// -- rendering --------------------------------------------------------------------------

function render() {
  if (!state) return;
  const { phase, prefs, photo } = state;
  const theme = themes[prefs.theme_id] || {};
  applyThemeColors(theme);
  els.body.dataset.phase = phase;
  els.body.style.setProperty("--ar", aspectFor(prefs.orientation));

  $("#event-name").textContent = prefs.event_name || "Fun Booth";
  const name = theme.id === "custom" ? "Something special" : theme.name;
  $("#theme-emoji").textContent = theme.emoji || "";
  $("#theme-name").textContent = name || "";
  $("#attract-emoji").textContent = theme.emoji || "📸";
  $("#attract-title").textContent = name || "Fun Booth";
  const blocked = prefs.camera_source === "display" && camera.error;
  $("#attract-tag").textContent = blocked
    ? "Camera blocked: allow access in Safari, then tap here"
    : prefs.camera_source === "display" ? theme.tagline || "" : "Get ready for your close-up!";

  syncCamera(started && prefs.camera_source === "display");
  els.body.classList.toggle("has-camera", !!camera.stream);

  if (phase === "processing") {
    setStill(localCapture || photo?.original_url);
    startProcessingMessages(name);
  } else {
    stopProcessingMessages();
  }
  if (phase === "result" && photo?.result_url) setStill(photo.result_url);

  // Result panel: QR for phones, AirDrop for iPhones nearby.
  const showQr = phase === "result" && prefs.show_qr && photo;
  els.qr.hidden = els.qrHint.hidden = !showQr;
  if (showQr && els.qr.dataset.src !== photo.qr_url) {
    els.qr.src = els.qr.dataset.src = photo.qr_url;
  }
  if (phase === "result") {
    sharer.prepare(photo, printUrlFor(photo, prefs)).then(updateSide);
  }
  updateSide();
}

function updateSide() {
  const canAirdrop = state?.phase === "result" && sharer.ready;
  els.airdrop.hidden = !canAirdrop;
  els.body.classList.toggle("show-side", !!(state?.prefs.show_qr || canAirdrop));
}

function setStill(src) {
  if (src && els.still.dataset.src !== src) {
    els.still.src = els.still.dataset.src = src;
  }
}

function clearLocalCapture() {
  if (localCapture) URL.revokeObjectURL(localCapture);
  localCapture = null;
}

// -- camera -----------------------------------------------------------------------------

function syncCamera(want) {
  camera.sync(want).then((changed) => {
    if (!changed) return;
    link.send({ type: "camera", ready: camera.ready });
    if (camera.error) toast(`Camera unavailable: ${camera.error.message}`, "error");
    render();
  });
}

camera.onended = () => {
  link.send({ type: "camera", ready: false });
  render();
};

$("#attract").addEventListener("click", () => {
  if (!camera.error) return;
  camera.retry();
  render();
});

// -- countdown & capture ----------------------------------------------------------------

function runCountdown(msg) {
  stopCountdown();
  clearLocalCapture();
  let n = msg.seconds;
  const tick = () => {
    if (n <= 0) {
      stopCountdown();
      els.flash.classList.remove("go");
      void els.flash.offsetWidth;
      els.flash.classList.add("go");
      if (msg.capturer === myId) captureAndUpload();
      return;
    }
    els.count.textContent = n;
    els.count.classList.add("ticking");
    els.count.classList.remove("pop");
    void els.count.offsetWidth; // restart the animation
    els.count.classList.add("pop");
    n -= 1;
    countdownTimer = setTimeout(tick, 1000);
  };
  tick();
}

function stopCountdown() {
  clearTimeout(countdownTimer);
  countdownTimer = null;
  els.count.classList.remove("ticking", "pop");
}

async function captureAndUpload() {
  if (!camera.ready) {
    toast("Camera isn't ready", "error");
    return;
  }
  const blob = await camera.capture(aspectFor(state.prefs.orientation));
  clearLocalCapture();
  localCapture = URL.createObjectURL(blob);
  setStill(localCapture);
  els.body.dataset.phase = "processing"; // show the frozen frame straight away
  try {
    await uploadPhoto(blob);
  } catch (err) {
    toast(`Upload failed: ${err.message}`, "error");
  }
}

// -- "creating your photo" messages -----------------------------------------------------

function startProcessingMessages(themeName) {
  if (procTimer) return;
  const lines = [
    `Summoning the ${themeName || "booth"} magic…`,
    "Setting up the lights…",
    "Picking the perfect outfits…",
    "Painting the background…",
    "Adding the finishing touches…",
    "Almost there…",
  ];
  let i = 0;
  const show = () => {
    els.procText.textContent = lines[Math.min(i, lines.length - 1)];
    els.procText.classList.remove("swap");
    void els.procText.offsetWidth;
    els.procText.classList.add("swap");
    i += 1;
  };
  show();
  procTimer = setInterval(show, 3000);
}

function stopProcessingMessages() {
  clearInterval(procTimer);
  procTimer = null;
}

// -- AirDrop / share ----------------------------------------------------------------------

els.airdrop.addEventListener("click", async () => {
  try {
    await sharer.share(state?.prefs.event_name || "Fun Booth");
  } catch (err) {
    toast(`Couldn't share: ${err.message}`, "error");
  }
});

// -- hidden settings ----------------------------------------------------------------------

$("#gear").addEventListener("click", () => {
  markFacing();
  els.settings.showModal();
});
$$("#facing button").forEach((btn) =>
  btn.addEventListener("click", async () => {
    store(FACING_KEY, btn.dataset.v);
    camera.facing = btn.dataset.v;
    markFacing();
    camera.retry();
    if (camera.stream) camera.stop();
    render();
  }),
);
function markFacing() {
  $$("#facing button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.v === camera.facing)));
}
$("#fullscreen").addEventListener("click", goFullscreen);
$("#forget").addEventListener("click", () => {
  forgetPin();
  location.reload();
});
