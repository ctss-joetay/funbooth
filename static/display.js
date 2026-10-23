import {
  $, $$, Camera, PreviewStreamer, RemotePreview, Sharer, api, applyThemeColors, askPin, aspectFor,
  connect, ensurePin, forgetPin, getPin, keepAwake, loadThemes, printPhoto, shareEntries, store, toast,
  uploadPhoto,
} from "/static/common.js";

const FACING_KEY = "funbooth.display.facing";
const POSE_TIMEOUT = 60_000; // back to the theme carousel if nobody shoots
const RESULT_TIMEOUT = 120_000; // clear the result screen for the next guests

const els = {
  body: document.body,
  video: $("#video"),
  remote: $("#remote"),
  still: $("#still"),
  clip: $("#clip"),
  before: $("#before"),
  count: $("#count"),
  flash: $("#flash"),
  procText: $("#proc-text"),
  carousel: $("#carousel"),
  shoot: $("#shoot"),
  qrOverlay: $("#qr-overlay"),
  host: $("#host"),
  conn: $("#conn"),
};

const camera = new Camera(els.video);
camera.facing = store(FACING_KEY) || "user";

let themes = {};
let state = null;
let myId = null;
let started = false;
let view = "choose"; // what guests see while the booth is idle: choose | pose
let nextView = null; // where to go after the result is cleared
let localCapture = null; // blob URL of the frame this iPad just shot
let countdownTimer = null;
let procTimer = null;
let lastTouch = Date.now();
let carouselKey = "";
let wantPreview = false;
let localQr = null; // photo whose QR the host chose to show from this iPad
let dismissedQr = null;
let revealedKey = null; // photo id + version whose before/after wipe already played

await ensurePin();
themes = await loadThemes();

const remote = new RemotePreview(els.remote, (live) => {
  els.body.classList.toggle("has-remote", live);
});

const link = connect(
  "display",
  {
    welcome(msg) {
      myId = msg.client_id;
      wantPreview = false;
      link.send({ type: "camera", ready: camera.ready });
    },
    state(msg) {
      const previous = state;
      state = msg;
      if (state.phase !== "countdown") stopCountdown();
      if (state.phase !== "processing" && previous?.phase === "processing") clearLocalCapture();
      if (state.phase === "idle" && previous && previous.phase !== "idle") {
        view = nextView || "choose";
        nextView = null;
      }
      if (state.phase === "result" && previous?.phase !== "result") lastTouch = Date.now();
      render();
    },
    countdown: runCountdown,
    frame: (blob) => remote.show(blob),
    photo(msg) {
      if (!els.host.open) return;
      hostPhotos = hostPhotos.map((p) => (p.id === msg.photo.id ? msg.photo : p));
      if (hostPhoto?.id === msg.photo.id) hostPhoto = msg.photo;
      renderHost();
    },
    toast(msg) {
      toast(msg.text, msg.level);
    },
  },
  (online) => els.conn.classList.toggle("on", online),
);

const streamer = new PreviewStreamer(camera, link);

// -- start screen: choose how this iPad is used -----------------------------------------

$$(".d-start-option").forEach((btn) =>
  btn.addEventListener("click", () => {
    setCameraSource(btn.dataset.setup === "camera" ? "display" : "remote", getPin());
    started = true;
    $("#start").hidden = true;
    goFullscreen();
    keepAwake();
    render();
  }),
);

/** "remote" keeps whichever other device is chosen, or falls back to the operator device. */
function setCameraSource(choice, pin) {
  const current = state?.prefs.camera_source;
  const source = choice === "display" ? "display" : current === "display" || !current ? "operator" : current;
  if (source !== current) link.send({ type: "prefs", pin, prefs: { camera_source: source } });
}

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
  const screen = phase === "idle" ? view : phase;
  const cameraHere = prefs.camera_source === "display";
  const isCamera = !!myId && state.camera_id === myId;

  applyThemeColors(theme);
  els.body.dataset.phase = phase;
  if (els.body.dataset.screen !== screen && screen === "choose") requestAnimationFrame(updateArrows);
  els.body.dataset.screen = screen;
  els.body.style.setProperty("--ar", aspectFor(prefs.orientation));
  els.body.classList.toggle("portrait-photos", prefs.orientation === "portrait");
  $$(".d-start-option").forEach((b) =>
    b.classList.toggle("current", (b.dataset.setup === "camera") === cameraHere),
  );

  $("#event-name").textContent = prefs.event_name || "Fun Booth";
  const name = theme.id === "custom" ? "Something special" : theme.name;
  $("#theme-emoji").textContent = theme.emoji || "";
  $("#theme-name").textContent = name || "";

  renderCarousel(prefs);

  // Live preview: this iPad's own camera, or frames relayed from the camera device.
  syncCamera(started && cameraHere);
  els.body.classList.toggle("has-camera", !!camera.stream && isCamera);
  const live = screen === "pose" || screen === "countdown";
  setWantPreview(started && live && !!state.camera_id && !isCamera);
  streamer.update(isCamera && state.preview_wanted, aspectFor(prefs.orientation));

  $("#attract-emoji").textContent = theme.emoji || "📸";
  $("#attract-title").textContent = name || "Fun Booth";
  $("#attract-tag").textContent = attractText(cameraHere);
  $("#banner").textContent = cameraHere ? "Strike a pose! 📸" : "Look at the camera! 📸";
  els.shoot.disabled = !state.camera_id;
  $("#shoot-label").textContent = state.camera_id ? "Take my photo!" : "Waiting for the camera…";

  if (phase === "processing") {
    setStill(localCapture || photo?.original_url);
    if (photo) els.before.src = photo.original_url; // preload for the reveal
    startProcessingMessages(name);
  } else {
    stopProcessingMessages();
  }
  if (phase === "result" && photo?.result_url) {
    setStill(photo.result_url);
    playReveal(photo);
  }
  renderClip(phase === "result" ? photo : null);

  renderQr();
}

function attractText(cameraHere) {
  if (cameraHere && camera.error) return "Camera blocked: allow access in Safari, then tap here";
  if (!state.camera_id) return "Waiting for the camera…";
  return cameraHere ? "Get ready!" : "Smile at the camera!";
}

function setStill(src) {
  if (src && els.still.dataset.src !== src) els.still.src = els.still.dataset.src = src;
}

/** Wipe from the real photo to the AI version, once per new result. */
function playReveal(photo) {
  const key = `${photo.id}:${photo.version}`;
  if (revealedKey === key) return;
  revealedKey = key;
  els.before.src = photo.original_url;
  els.body.classList.remove("revealing");
  void els.body.offsetWidth;
  els.body.classList.add("revealing");
  setTimeout(() => els.body.classList.remove("revealing"), 2300);
}

/** Loop the video clip over the photo once it's ready. */
function renderClip(photo) {
  const url = photo?.video_url || "";
  $("#video-note").hidden = photo?.video_status !== "processing";
  if (els.clip.dataset.src === url) return;
  els.clip.dataset.src = url;
  els.body.classList.remove("has-clip");
  $("#play-clip").hidden = true;
  if (!url) {
    els.clip.removeAttribute("src");
    els.clip.load();
    return;
  }
  els.clip.src = url;
  els.clip.play().catch(() => {});
  // iPads in Low Power Mode don't autoplay video; offer a button instead.
  setTimeout(() => {
    const stuck = els.clip.dataset.src === url && !els.body.classList.contains("has-clip") && !els.clip.error;
    $("#play-clip").hidden = !stuck;
  }, 2500);
}
els.clip.addEventListener("playing", () => {
  els.body.classList.add("has-clip");
  $("#play-clip").hidden = true;
});
$("#play-clip").addEventListener("click", () => els.clip.play().catch(() => {}));

function clearLocalCapture() {
  if (localCapture) URL.revokeObjectURL(localCapture);
  localCapture = null;
}

function setWantPreview(want) {
  if (want === wantPreview) return;
  wantPreview = want;
  link.send({ type: "preview", want });
}

// -- theme carousel ---------------------------------------------------------------------

function guestThemes(prefs) {
  const ids = [...prefs.guest_themes];
  if (!ids.includes(prefs.theme_id)) ids.unshift(prefs.theme_id); // operator's pick, e.g. Custom
  return ids.map((id) => themes[id]).filter(Boolean);
}

function renderCarousel(prefs) {
  const list = guestThemes(prefs);
  const key = JSON.stringify([list.map((t) => t.id), list.map((t) => state.samples[t.id])]);
  if (key !== carouselKey) {
    carouselKey = key;
    els.carousel.innerHTML = "";
    for (const theme of list) els.carousel.append(themeCard(theme));
    updateArrows();
  }
  $$(".d-card", els.carousel).forEach((c) => c.setAttribute("aria-pressed", String(c.dataset.id === prefs.theme_id)));
}

function themeCard(theme) {
  const colors = theme.id === "custom" ? { frame: "#2a2d3a", accent: "#7c5cff", ink: "#ffffff" } : theme;
  const card = document.createElement("button");
  card.className = "d-card";
  card.dataset.id = theme.id;
  card.style.setProperty("--c-frame", colors.frame);
  card.style.setProperty("--c-accent", colors.accent);
  card.style.setProperty("--c-ink", colors.ink);
  card.innerHTML = `<div class="d-card-img"></div><div class="d-card-body"><div class="d-card-name"></div><div class="d-card-tag"></div></div>`;
  const sample = state.samples[theme.id];
  const imgBox = card.querySelector(".d-card-img");
  if (sample) {
    imgBox.innerHTML = `<img alt="" loading="lazy"><span class="d-card-sample">Sample</span>`;
    imgBox.querySelector("img").src = sample;
  } else {
    imgBox.innerHTML = `<div class="d-card-art"><span></span></div>`;
    imgBox.querySelector("span").textContent = theme.emoji;
  }
  card.querySelector(".d-card-name").textContent = `${theme.emoji} ${theme.id === "custom" ? "Something special" : theme.name}`;
  card.querySelector(".d-card-tag").textContent = theme.tagline;
  card.addEventListener("click", () => pickTheme(theme.id));
  return card;
}

function pickTheme(themeId) {
  if (state.prefs.theme_id !== themeId) {
    state.prefs.theme_id = themeId; // optimistic; the server confirms
    link.send({ type: "theme", theme_id: themeId });
  }
  view = "pose";
  render();
}

function updateArrows() {
  const c = els.carousel;
  $("#prev").disabled = c.scrollLeft < 10;
  $("#next").disabled = c.scrollLeft + c.clientWidth > c.scrollWidth - 10;
}
els.carousel.addEventListener("scroll", updateArrows, { passive: true });
window.addEventListener("resize", updateArrows);
$("#prev").addEventListener("click", () => els.carousel.scrollBy({ left: -els.carousel.clientWidth * 0.8, behavior: "smooth" }));
$("#next").addEventListener("click", () => els.carousel.scrollBy({ left: els.carousel.clientWidth * 0.8, behavior: "smooth" }));

// -- guest buttons ----------------------------------------------------------------------

els.shoot.addEventListener("click", () => link.send({ type: "start" }));
$("#change-theme").addEventListener("click", () => {
  view = "choose";
  render();
});
$("#again").addEventListener("click", () => clearResult("pose"));
$("#done").addEventListener("click", () => clearResult("choose"));
$("#retry").addEventListener("click", () => clearResult("pose"));

function clearResult(where) {
  nextView = where;
  link.send({ type: "reset" });
}

// Return to the carousel when guests walk away.
document.addEventListener("pointerdown", () => (lastTouch = Date.now()), { capture: true });
setInterval(() => {
  if (!state || els.host.open) return;
  const idle = Date.now() - lastTouch;
  if (state.phase === "idle" && view === "pose" && idle > POSE_TIMEOUT) {
    view = "choose";
    render();
  } else if (state.phase === "result" && idle > RESULT_TIMEOUT) {
    lastTouch = Date.now();
    clearResult("choose");
  }
}, 5000);

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
  els.qrOverlay.hidden = true;
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
  els.body.dataset.screen = "processing"; // show the frozen frame straight away
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

// -- QR code from the host --------------------------------------------------------------

function renderQr() {
  const photo = localQr || state.qr;
  const show = !!photo && photo.id !== dismissedQr;
  els.qrOverlay.hidden = !show;
  if (!show) return;
  $("#qr").src = photo.qr_url;
  $("#qr-photo").src = photo.thumb_url;
}

$("#qr-done").addEventListener("click", () => {
  dismissedQr = (localQr || state.qr)?.id ?? null;
  localQr = null;
  render();
});

// -- host menu (PIN) --------------------------------------------------------------------

const sharer = new Sharer();
let hostPin = null;
let hostPhoto = null;
let hostPhotos = [];

$("#gear").addEventListener("click", async () => {
  hostPin = await askPin({ title: "Host menu", cancellable: true });
  if (!hostPin) return;
  hostPhoto = state?.photo?.status === "done" ? state.photo : null;
  await loadHostPhotos();
  renderHost();
  els.host.showModal();
});

$("#host-close").addEventListener("click", () => els.host.close());
els.host.addEventListener("close", () => (hostPin = null));

async function loadHostPhotos() {
  try {
    hostPhotos = (await api("/api/photos?limit=24")).filter((p) => p.status === "done");
  } catch {
    hostPhotos = [];
  }
  hostPhoto = hostPhoto || hostPhotos[0] || null;
}

function renderHost() {
  const photo = hostPhoto;
  $("#host-photo").hidden = !photo;
  $("#host-empty").hidden = !!photo;
  if (photo) $("#host-photo").src = photo.result_url;
  for (const id of ["#host-print", "#host-airdrop", "#host-qr"]) $(id).disabled = !photo;
  $("#host-airdrop").hidden = !sharer.supported;
  if (photo) sharer.prepare(shareEntries(photo, state.prefs));
  const video = photo?.video_status;
  $("#host-video").disabled = !photo || video === "processing";
  $("#host-video").lastElementChild.textContent =
    { processing: "Making video…", done: "Make a new video", error: "Retry video" }[video] || "Make video";

  const strip = $("#host-strip");
  strip.innerHTML = "";
  for (const p of hostPhotos) {
    const btn = document.createElement("button");
    btn.className = p.orientation === "portrait" ? "portrait" : "";
    btn.setAttribute("aria-current", String(p.id === photo?.id));
    btn.innerHTML = `<img alt="" loading="lazy">`;
    btn.querySelector("img").src = p.thumb_url;
    btn.addEventListener("click", () => {
      hostPhoto = p;
      renderHost();
    });
    strip.append(btn);
  }

  const cameraHere = state.prefs.camera_source === "display";
  $$("#host-camera button").forEach((b) => b.setAttribute("aria-pressed", String((b.dataset.v === "display") === cameraHere)));
  $$("#facing button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.v === camera.facing)));
}

$("#host-print").addEventListener("click", () => hostPhoto && printPhoto(hostPhoto, state.prefs));
$("#host-airdrop").addEventListener("click", async () => {
  try {
    if (!(await sharer.share(state.prefs.event_name || "Fun Booth"))) toast("Still preparing the photo. Try again in a second.");
  } catch (err) {
    toast(`Couldn't share: ${err.message}`, "error");
  }
});
$("#host-video").addEventListener("click", () => {
  if (hostPhoto) link.send({ type: "make_video", pin: hostPin, photo_id: hostPhoto.id });
});
$("#host-qr").addEventListener("click", () => {
  localQr = hostPhoto;
  dismissedQr = null;
  els.host.close();
  render();
});

$$("#host-camera button").forEach((btn) =>
  btn.addEventListener("click", () => {
    setCameraSource(btn.dataset.v, hostPin);
    setTimeout(renderHost, 300);
  }),
);
$$("#facing button").forEach((btn) =>
  btn.addEventListener("click", () => {
    store(FACING_KEY, btn.dataset.v);
    camera.facing = btn.dataset.v;
    camera.retry();
    if (camera.stream) camera.stop();
    render();
    renderHost();
  }),
);
$("#fullscreen").addEventListener("click", goFullscreen);
$("#forget").addEventListener("click", () => {
  forgetPin();
  location.reload();
});
