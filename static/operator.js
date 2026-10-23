import {
  $, $$, Camera, Sharer, api, aspectFor, connect, ensurePin, forgetPin, loadThemes,
  printUrlFor, store, toast, uploadPhoto,
} from "/static/common.js";

const FACING_KEY = "funbooth.operator.facing";
const PHASE_LABELS = { idle: "Ready", countdown: "Smile!", processing: "Creating…", result: "Ready to print", error: "Error" };
const CUSTOM_COLORS = { frame: "#2a2d3a", accent: "#7c5cff", ink: "#ffffff" };

const els = {
  body: document.body,
  video: $("#video"),
  still: $("#still"),
  count: $("#count"),
  prompt: $("#custom-prompt"),
  strip: $("#strip"),
  settings: $("#settings"),
  printDialog: $("#print-dialog"),
  printImg: $("#print-img"),
  shoot: $("#shoot"),
  restyle: $("#restyle"),
  print: $("#print"),
  share: $("#share"),
  next: $("#next"),
};

const camera = new Camera(els.video);
camera.facing = store(FACING_KEY) || "environment";
const sharer = new Sharer();
const gallery = new Map();
const thumbs = new Map();

let themes = {};
let state = null;
let myId = null;
let localCapture = null;
let countdownTimer = null;

await ensurePin();
themes = await loadThemes();
buildThemeGrid();

const link = connect(
  "operator",
  {
    welcome(msg) {
      myId = msg.client_id;
      link.send({ type: "camera", ready: camera.ready });
      loadGallery();
    },
    state(msg) {
      const previousPhase = state?.phase;
      state = msg;
      if (state.phase !== "countdown") stopCountdown();
      if (state.phase !== "processing" && previousPhase === "processing") clearLocalCapture();
      if (state.photo) upsertPhoto(state.photo);
      render();
    },
    countdown: runCountdown,
    photo(msg) {
      upsertPhoto(msg.photo);
    },
    toast(msg) {
      toast(msg.text, msg.level);
    },
  },
  (online) => $("#dot-link").classList.toggle("on", online),
);

function setPrefs(partial) {
  if (!state) return;
  state.prefs = { ...state.prefs, ...partial };
  render();
  link.send({ type: "prefs", prefs: partial });
}

function debounce(fn, ms) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

// -- themes -----------------------------------------------------------------------------

function buildThemeGrid() {
  const grid = $("#theme-grid");
  grid.innerHTML = "";
  for (const theme of Object.values(themes)) {
    const colors = theme.id === "custom" ? CUSTOM_COLORS : theme;
    const btn = document.createElement("button");
    btn.className = "o-theme";
    btn.dataset.id = theme.id;
    btn.style.setProperty("--t-frame", colors.frame);
    btn.style.setProperty("--t-accent", colors.accent);
    btn.style.setProperty("--t-ink", colors.ink);
    btn.innerHTML = `<span class="o-theme-emoji"></span><span class="o-theme-name"></span><span class="o-theme-tag"></span>`;
    btn.querySelector(".o-theme-emoji").textContent = theme.emoji;
    btn.querySelector(".o-theme-name").textContent = theme.name;
    btn.querySelector(".o-theme-tag").textContent = theme.tagline;
    btn.addEventListener("click", () => setPrefs({ theme_id: theme.id }));
    grid.append(btn);
  }
}

els.prompt.addEventListener("input", debounce(() => setPrefs({ custom_prompt: els.prompt.value }), 500));

// -- rendering --------------------------------------------------------------------------

function render() {
  if (!state) return;
  const { phase, prefs, photo, devices } = state;
  const usingOwnCamera = prefs.camera_source === "operator";
  const cameraReady = usingOwnCamera ? camera.ready : devices.display_camera;

  els.body.dataset.phase = phase;
  els.body.style.setProperty("--ar", aspectFor(prefs.orientation));
  els.body.classList.toggle("custom-theme", prefs.theme_id === "custom");
  $("#event-name").textContent = prefs.event_name || "Fun Booth";

  // Status chips
  $("#dot-display").classList.toggle("on", devices.display > 0);
  $("#dot-camera").classList.toggle("on", cameraReady);
  $("#camera-label").textContent = usingOwnCamera ? "This camera" : "Display camera";
  $("#ai-mode").textContent = `AI: ${state.ai_mode}`;

  // Themes + prompt
  $$(".o-theme").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.id === prefs.theme_id)));
  const custom = prefs.theme_id === "custom";
  $("#prompt-label").textContent = custom ? "Describe the scene" : "Extra details (optional)";
  els.prompt.placeholder = custom ? "e.g. a medieval castle banquet with knights and banners" : "e.g. add a birthday cake and balloons";
  if (document.activeElement !== els.prompt) els.prompt.value = prefs.custom_prompt;

  // Stage
  syncCamera(usingOwnCamera);
  els.body.classList.toggle("has-camera", !!camera.stream);
  renderPlaceholder(prefs, devices, usingOwnCamera);
  if (phase === "processing") setStill(localCapture || photo?.original_url);
  if (phase === "result" && photo?.result_url) setStill(photo.result_url);
  $("#err-text").textContent = state.message || "Something went wrong.";
  $("#phase-label").textContent = PHASE_LABELS[phase] || phase;

  // Actions
  const theme = themes[prefs.theme_id];
  els.shoot.disabled = phase === "countdown" || !cameraReady;
  els.restyle.disabled = !photo || photo.status === "processing";
  els.restyle.title = theme ? `Restyle this photo as ${theme.name}` : "";
  els.print.disabled = !(phase === "result" && photo?.print_url);
  els.next.disabled = phase === "idle";

  if (phase === "result" && photo?.print_url) {
    const printUrl = printUrlFor(photo, prefs);
    if (els.printImg.dataset.src !== printUrl) els.printImg.src = els.printImg.dataset.src = printUrl;
    sharer.prepare(photo, printUrl).then(updateShareButtons);
  }
  updateShareButtons();
  syncSettings();
  markCurrentThumb();
}

function renderPlaceholder(prefs, devices, usingOwnCamera) {
  let emoji = "🖥️";
  let title = "Live camera is on the display iPad";
  let sub = "Tap “Take photo” when your guests are ready.";
  if (usingOwnCamera && camera.error) {
    emoji = "🚫";
    title = "This iPad's camera is blocked";
    sub = "Allow camera access in Safari (aA menu → Website Settings), then tap here to retry.";
  } else if (usingOwnCamera) {
    emoji = "📷";
    title = "Starting this iPad's camera…";
    sub = "Allow camera access if Safari asks.";
  } else if (!devices.display) {
    title = "Display iPad not connected";
    sub = `Open ${location.host}/display on the guest-facing iPad.`;
  } else if (!devices.display_camera) {
    title = "Display camera is off";
    sub = "Tap “Start display” on the guest iPad and allow camera access.";
  }
  $("#ph-emoji").textContent = emoji;
  $("#ph-title").textContent = title;
  $("#ph-sub").textContent = sub;
}

function setStill(src) {
  if (src && els.still.dataset.src !== src) els.still.src = els.still.dataset.src = src;
}

function clearLocalCapture() {
  if (localCapture) URL.revokeObjectURL(localCapture);
  localCapture = null;
}

function updateShareButtons() {
  const result = state?.phase === "result" && state.photo?.result_url;
  const label = sharer.supported ? "AirDrop" : "Open link";
  for (const btn of [els.share, $("#print-share")]) {
    btn.lastElementChild.textContent = label;
    btn.disabled = !result || (sharer.supported && !sharer.ready);
  }
}

// -- camera (only when this iPad is the one taking photos) ------------------------------

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

$("#placeholder").addEventListener("click", () => {
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
      if (msg.capturer === myId) captureAndUpload();
      return;
    }
    els.count.textContent = n;
    els.count.classList.add("ticking");
    n -= 1;
    countdownTimer = setTimeout(tick, 1000);
  };
  tick();
}

function stopCountdown() {
  clearTimeout(countdownTimer);
  countdownTimer = null;
  els.count.classList.remove("ticking");
}

async function captureAndUpload() {
  if (!camera.ready) {
    toast("Camera isn't ready", "error");
    return;
  }
  const blob = await camera.capture(aspectFor(state.prefs.orientation));
  localCapture = URL.createObjectURL(blob);
  setStill(localCapture);
  els.body.dataset.phase = "processing";
  try {
    await uploadPhoto(blob);
  } catch (err) {
    toast(`Upload failed: ${err.message}`, "error");
  }
}

// -- actions ----------------------------------------------------------------------------

els.shoot.addEventListener("click", () => link.send({ type: "start" }));
els.next.addEventListener("click", () => link.send({ type: "reset" }));
els.restyle.addEventListener("click", () => {
  if (state?.photo) link.send({ type: "regenerate", photo_id: state.photo.id });
});

els.print.addEventListener("click", () => {
  const { photo, prefs } = state;
  $("#print-preview").src = printUrlFor(photo, prefs);
  $("#print-size").textContent = prefs.orientation === "portrait" ? "4 × 6 in, portrait" : "6 × 4 in, landscape";
  els.printDialog.showModal();
});
$("#close-print").addEventListener("click", () => els.printDialog.close());
$("#do-print").addEventListener("click", async () => {
  try {
    await els.printImg.decode();
  } catch {
    toast("The print image didn't load yet. Try again in a moment.", "error");
    return;
  }
  const portrait = state.prefs.orientation === "portrait";
  $("#page-size").textContent = `@page { size: ${portrait ? "4in 6in" : "6in 4in"}; margin: 0; }`;
  els.printDialog.close();
  window.print();
});

async function shareCurrent() {
  try {
    if (await sharer.share(state?.prefs.event_name || "Fun Booth")) return;
  } catch (err) {
    toast(`Couldn't share: ${err.message}`, "error");
    return;
  }
  if (state?.photo) window.open(state.photo.share_path, "_blank", "noopener");
}
els.share.addEventListener("click", shareCurrent);
$("#print-share").addEventListener("click", shareCurrent);

// -- gallery ----------------------------------------------------------------------------

async function loadGallery() {
  try {
    const photos = await api("/api/photos?limit=60");
    photos.forEach((p) => gallery.set(p.id, p));
    renderGallery();
  } catch (err) {
    toast(`Couldn't load recent photos: ${err.message}`, "error");
  }
}

function upsertPhoto(photo) {
  gallery.set(photo.id, photo);
  renderGallery();
}

function renderGallery() {
  const photos = [...gallery.values()].sort((a, b) => b.created_at - a.created_at).slice(0, 60);
  if (!photos.length) return;
  els.strip.querySelector(".o-empty")?.remove();

  photos.forEach((photo, index) => {
    let btn = thumbs.get(photo.id);
    if (!btn) {
      btn = document.createElement("button");
      btn.className = "o-thumb";
      btn.innerHTML = `<img alt="" loading="lazy"><span class="badge" hidden></span>`;
      btn.addEventListener("click", () => link.send({ type: "show", photo_id: photo.id }));
      thumbs.set(photo.id, btn);
    }
    btn.classList.toggle("portrait", photo.orientation === "portrait");
    const img = btn.querySelector("img");
    if (img.dataset.src !== photo.thumb_url) img.src = img.dataset.src = photo.thumb_url;
    const badge = btn.querySelector(".badge");
    badge.hidden = photo.status === "done";
    badge.textContent = photo.status === "error" ? "⚠️" : "⏳";
    if (els.strip.children[index] !== btn) els.strip.insertBefore(btn, els.strip.children[index] || null);
  });
  markCurrentThumb();
}

function markCurrentThumb() {
  const current = state?.photo?.id;
  thumbs.forEach((btn, id) => btn.setAttribute("aria-current", String(id === current)));
}

// -- settings ---------------------------------------------------------------------------

$("#open-settings").addEventListener("click", () => {
  $("#test-result").textContent = "";
  syncSettings();
  els.settings.showModal();
});

function syncSettings() {
  if (!state) return;
  const { prefs } = state;
  const eventInput = $("#set-event");
  if (document.activeElement !== eventInput) eventInput.value = prefs.event_name;
  $$("#settings .segmented[data-pref]").forEach((group) => {
    const value = String(prefs[group.dataset.pref]);
    $$("button", group).forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.v === value)));
  });
  $$("#settings input[type=checkbox][data-pref]").forEach((box) => (box.checked = !!prefs[box.dataset.pref]));
  $$("#facing button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.v === camera.facing)));
  $("#facing-field").hidden = prefs.camera_source !== "operator";
}

$("#set-event").addEventListener("input", debounce((e) => setPrefs({ event_name: e.target.value }), 600));

$$("#settings .segmented[data-pref]").forEach((group) => {
  $$("button", group).forEach((btn) =>
    btn.addEventListener("click", () => {
      const key = group.dataset.pref;
      setPrefs({ [key]: key === "countdown" ? Number(btn.dataset.v) : btn.dataset.v });
    }),
  );
});

$$("#settings input[type=checkbox][data-pref]").forEach((box) =>
  box.addEventListener("change", () => setPrefs({ [box.dataset.pref]: box.checked })),
);

$$("#facing button").forEach((btn) =>
  btn.addEventListener("click", () => {
    store(FACING_KEY, btn.dataset.v);
    camera.facing = btn.dataset.v;
    camera.retry();
    if (camera.stream) camera.stop();
    render();
  }),
);

$("#upload").addEventListener("change", async (e) => {
  const file = e.target.files?.[0];
  e.target.value = "";
  if (!file) return;
  els.settings.close();
  try {
    await uploadPhoto(file);
    toast("Photo uploaded. Creating it now…");
  } catch (err) {
    toast(`Upload failed: ${err.message}`, "error");
  }
});

$("#test-ai").addEventListener("click", async (e) => {
  const btn = e.currentTarget;
  const out = $("#test-result");
  btn.disabled = true;
  out.textContent = "Testing… this makes one real AI image (a few cents).";
  try {
    const res = await api("/api/test-ai", { method: "POST" });
    out.textContent = res.ok ? `✅ Working: ${res.mode} answered in ${res.seconds}s.` : `❌ ${res.error}`;
  } catch (err) {
    out.textContent = `❌ ${err.message}`;
  } finally {
    btn.disabled = false;
  }
});

$("#lock").addEventListener("click", () => {
  forgetPin();
  location.reload();
});
