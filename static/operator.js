import {
  $, $$, Camera, PreviewStreamer, Sharer, api, aspectFor, connect, ensurePin, forgetPin, loadThemes,
  printPhoto, printUrlFor, shareEntries, store, toast, uploadPhoto,
} from "/static/common.js";

const FACING_KEY = "funbooth.operator.facing";
const GUEST_SCREEN = {
  idle: "Guest screen: choosing a theme",
  countdown: "Guest screen: countdown",
  processing: "Guest screen: creating…",
  result: "Guest screen: showing the result",
  error: "Guest screen: error",
};
const CAMERA_NAMES = { operator: "This device", display: "Guest iPad", camera: "Phone" };
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
  sendDialog: $("#send-dialog"),
  shoot: $("#shoot"),
  restyle: $("#restyle"),
  print: $("#print"),
  send: $("#send"),
  makeVideo: $("#make-video"),
  next: $("#next"),
  stageGif: $("#stage-gif"),
  stageVideo: $("#stage-video"),
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
let selectedId = null; // photo the Print / Send / Restyle buttons act on
let pinned = false; // operator tapped a thumbnail, so show it instead of the live camera
let view = "photo"; // what the stage shows for a finished photo: photo | gif | video
let lastBoothPhotoId = null;

await ensurePin();
themes = await loadThemes();
buildThemeGrid();
buildGuestThemeChips();

const link = connect(
  "operator",
  {
    welcome(msg) {
      myId = msg.client_id;
      link.send({ type: "camera", ready: camera.ready });
      loadGallery();
    },
    state(msg) {
      const previous = state;
      state = msg;
      if (state.phase !== "countdown") stopCountdown();
      if (state.phase !== "processing" && previous?.phase === "processing") clearLocalCapture();
      if (state.phase === "countdown" || (state.phase === "idle" && previous?.phase !== "idle")) pinned = false;
      if (state.photo) {
        upsertPhoto(state.photo);
        if (state.photo.id !== lastBoothPhotoId) {
          selectedId = state.photo.id; // follow new shots
          view = "photo";
        }
      }
      lastBoothPhotoId = state.photo?.id ?? lastBoothPhotoId;
      render();
    },
    countdown: runCountdown,
    photo(msg) {
      upsertPhoto(msg.photo);
      render();
    },
    toast(msg) {
      toast(msg.text, msg.level);
    },
  },
  (online) => $("#dot-link").classList.toggle("on", online),
);

const streamer = new PreviewStreamer(camera, link);

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

const selected = () => (selectedId ? gallery.get(selectedId) : null);

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
  const { phase, prefs, devices } = state;
  const photo = selected();
  const isCamera = !!myId && state.camera_id === myId;

  els.body.dataset.phase = phase;
  els.body.style.setProperty("--ar", aspectFor(prefs.orientation));
  els.body.classList.toggle("custom-theme", prefs.theme_id === "custom");
  $("#event-name").textContent = prefs.event_name || "Fun Booth";

  // Status chips
  $("#dot-display").classList.toggle("on", devices.display > 0);
  $("#dot-camera").classList.toggle("on", !!state.camera_id);
  $("#camera-label").textContent = `${CAMERA_NAMES[prefs.camera_source]} camera`;
  $("#ai-mode").textContent = `AI: ${state.ai_mode}`;

  // Themes + prompt
  $$(".o-theme").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.id === prefs.theme_id)));
  const custom = prefs.theme_id === "custom";
  $("#prompt-label").textContent = custom ? "Describe the scene" : "Extra details (optional)";
  els.prompt.placeholder = custom ? "e.g. a medieval castle banquet with knights and banners" : "e.g. add a birthday cake and balloons";
  if (document.activeElement !== els.prompt) els.prompt.value = prefs.custom_prompt;

  // This device as the camera
  syncCamera(prefs.camera_source === "operator");
  els.body.classList.toggle("has-camera", !!camera.stream && isCamera);
  streamer.update(isCamera && state.preview_wanted, aspectFor(prefs.orientation));

  // Stage: live camera while this device is shooting, otherwise the selected photo.
  const live = isCamera && (phase === "countdown" || (phase === "idle" && !pinned));
  let stage = "empty";
  if (live) stage = "live";
  else if (photo) stage = `photo-${photo.status}`;
  els.body.dataset.stage = stage;
  if (photo?.status === "processing") setStill(photo.id === state.photo?.id && localCapture ? localCapture : photo.original_url);
  if (photo?.status === "done") setStill(photo.result_url);
  renderMediaView(photo);
  $("#err-text").textContent = photo?.error || "Something went wrong.";
  $("#phase-label").textContent = GUEST_SCREEN[phase] || phase;
  renderPlaceholder(prefs, devices);
  renderCaption(photo, live);

  // Actions
  const theme = themes[prefs.theme_id];
  const done = photo?.status === "done";
  els.shoot.disabled = phase === "countdown" || !state.camera_id;
  els.restyle.disabled = !photo || photo.status === "processing";
  els.restyle.title = theme && photo ? `Restyle the selected photo as ${theme.name}` : "";
  els.print.disabled = !done;
  els.send.disabled = !done;
  els.next.disabled = phase === "idle";
  renderVideoButton(photo);

  if (done && els.sendDialog.open) sharer.prepare(shareEntries(photo, prefs)).then(renderSend);
  renderSend();
  syncSettings();
  markCurrentThumb();
}

function renderPlaceholder(prefs, devices) {
  let emoji = "📷";
  let title = "";
  let sub = "";
  const source = prefs.camera_source;
  if (source === "operator") {
    if (camera.error) {
      emoji = "🚫";
      title = "This device's camera is blocked";
      sub = "Allow camera access in the browser's site settings, then tap here to retry.";
    } else {
      title = "Starting this device's camera…";
      sub = "Allow camera access if the browser asks.";
    }
  } else if (source === "display") {
    emoji = "🖥️";
    title = !devices.display ? "Guest iPad not connected" : state.camera_id ? "The guest iPad is the camera" : "Guest iPad camera is off";
    sub = !devices.display
      ? `Open ${location.host}/display on the guest iPad.`
      : state.camera_id
        ? "Guests pick a theme and tap “Take my photo”, or tap Take photo here."
        : "Tap “Camera + guest screen” on the guest iPad and allow camera access.";
  } else {
    emoji = "📱";
    title = !devices.camera ? "No phone camera connected" : state.camera_id ? "The phone is the camera" : "Phone camera isn't started";
    sub = !devices.camera
      ? `Open ${location.host}/camera on the phone and tap Start camera.`
      : "Shoot with the phone's shutter button, or tap Take photo here.";
  }
  $("#ph-emoji").textContent = emoji;
  $("#ph-title").textContent = title;
  $("#ph-sub").textContent = sub;
}

function renderCaption(photo, live) {
  const caption = $("#caption");
  caption.hidden = live || !photo;
  if (!photo) return;
  const theme = themes[photo.theme_id];
  const time = new Date(photo.created_at * 1000).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  const status = { processing: " · creating…", error: " · failed" }[photo.status] || "";
  const cost = photo.video_cost ? ` $${photo.video_cost.toFixed(2)}` : "";
  const video = { processing: " · 🎬 making video…", done: ` · 🎬${cost}`, error: " · 🎬 video failed" }[photo.video_status] || "";
  $("#caption-text").textContent = `${theme?.emoji ?? ""} ${theme?.name ?? ""} · ${time}${status}${video}`;
  $("#caption-text").title = photo.video_status === "error" ? photo.video_error : photo.video_model || "";
  $("#views").hidden = photo.status !== "done";
  $("#set-sample").hidden = photo.status !== "done" || photo.theme_id === "custom";
}

// Photo / before-after GIF / video clip on the stage.
function renderMediaView(photo) {
  if (view === "video" && !photo?.video_url) view = "photo";
  els.body.dataset.view = view;
  $$("#views button").forEach((b) => {
    b.setAttribute("aria-pressed", String(b.dataset.view === view));
    b.disabled = b.dataset.view === "video" && !photo?.video_url;
  });
  if (view === "gif" && photo?.reveal_url && els.stageGif.dataset.src !== photo.reveal_url) {
    els.stageGif.src = els.stageGif.dataset.src = photo.reveal_url;
  }
  if (view === "video" && els.stageVideo.dataset.src !== photo.video_url) {
    els.stageVideo.src = els.stageVideo.dataset.src = photo.video_url;
    els.stageVideo.play().catch(() => {});
  }
  if (view !== "video") els.stageVideo.pause();
}

function renderVideoButton(photo) {
  const label = els.makeVideo.lastElementChild;
  const status = photo?.status === "done" ? photo.video_status : "unavailable";
  els.makeVideo.disabled = status === "unavailable" || status === "processing";
  label.textContent = { processing: "Making…", done: "Play video", error: "Retry video" }[status] || "Video";
  els.makeVideo.title = status === "error" ? photo.video_error : "Turn this photo into a short video clip";
}

$$("#views button").forEach((b) =>
  b.addEventListener("click", () => {
    view = b.dataset.view;
    render();
  }),
);

function setStill(src) {
  if (src && els.still.dataset.src !== src) els.still.src = els.still.dataset.src = src;
}

function clearLocalCapture() {
  if (localCapture) URL.revokeObjectURL(localCapture);
  localCapture = null;
}

// -- camera (only when this device takes the photos) ------------------------------------

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
  if (selectedId) link.send({ type: "regenerate", photo_id: selectedId });
});
$("#set-sample").addEventListener("click", () => link.send({ type: "set_sample", photo_id: selectedId }));
els.makeVideo.addEventListener("click", videoAction);
function videoAction() {
  const photo = selected();
  if (photo?.status !== "done" || photo.video_status === "processing") return;
  if (photo.video_status === "done") {
    view = "video";
    render();
  } else {
    link.send({ type: "make_video", photo_id: photo.id });
  }
}

els.print.addEventListener("click", openPrint);
function openPrint() {
  const photo = selected();
  if (photo?.status !== "done") return;
  $("#print-preview").src = printUrlFor(photo, state.prefs);
  $("#print-size").textContent = photo.orientation === "portrait" ? "4 × 6 in, portrait" : "6 × 4 in, landscape";
  els.printDialog.showModal();
}
$("#close-print").addEventListener("click", () => els.printDialog.close());
$("#do-print").addEventListener("click", () => {
  els.printDialog.close();
  printPhoto(selected(), state.prefs);
});

// Send: QR for guests to scan from here, AirDrop where the browser supports it, the
// guest screen, or plain downloads (handy on a laptop).
els.send.addEventListener("click", openSend);
function openSend() {
  const photo = selected();
  if (photo?.status !== "done") return;
  renderSend();
  els.sendDialog.showModal();
  sharer.prepare(shareEntries(photo, state.prefs)).then(renderSend);
}
function renderSend() {
  const photo = selected();
  if (!photo || photo.status !== "done" || !state) return;
  $("#send-qr").src = photo.qr_url;
  $("#send-download").href = photo.result_url;
  $("#send-download").download = `funbooth-${photo.id.slice(0, 8)}.jpg`;
  $("#send-download-print").href = printUrlFor(photo, state.prefs);
  $("#send-download-print").download = `funbooth-${photo.id.slice(0, 8)}-print.jpg`;
  $("#send-download-gif").href = photo.reveal_url;
  $("#send-download-gif").download = `funbooth-${photo.id.slice(0, 8)}-before-after.gif`;
  $("#send-download-video").hidden = !photo.video_url;
  if (photo.video_url) {
    $("#send-download-video").href = photo.video_url;
    $("#send-download-video").download = `funbooth-${photo.id.slice(0, 8)}.mp4`;
  }
  $("#send-airdrop").hidden = !sharer.supported;
  $("#send-airdrop").disabled = !sharer.ready;
  const onGuest = state.qr?.id === photo.id;
  $("#send-guest-qr").lastElementChild.textContent = onGuest ? "Hide QR on guest screen" : "Show QR on guest screen";
  $("#send-guest-qr").disabled = !state.devices.display;
}
$("#send-airdrop").addEventListener("click", async () => {
  try {
    await sharer.share(state.prefs.event_name || "Fun Booth");
  } catch (err) {
    toast(`Couldn't share: ${err.message}`, "error");
  }
});
$("#send-guest-qr").addEventListener("click", () => {
  const photo = selected();
  link.send({ type: "send_qr", photo_id: state.qr?.id === photo.id ? null : photo.id });
});
$("#close-send").addEventListener("click", () => els.sendDialog.close());

// Laptop shortcuts
document.addEventListener("keydown", (e) => {
  if (e.metaKey || e.ctrlKey || e.altKey || document.querySelector("dialog[open]")) return;
  if (e.target.closest("input, textarea, select")) return;
  const key = e.key.toLowerCase();
  if (key === " " && !els.shoot.disabled) link.send({ type: "start" });
  else if (key === "p") openPrint();
  else if (key === "s") openSend();
  else if (key === "v") videoAction();
  else if (key === "n" && !els.next.disabled) link.send({ type: "reset" });
  else return;
  e.preventDefault();
});

// -- gallery ----------------------------------------------------------------------------

async function loadGallery() {
  try {
    const photos = await api("/api/photos?limit=60");
    photos.forEach((p) => gallery.set(p.id, p));
    selectedId = selectedId || photos[0]?.id || null;
    renderGallery();
    render();
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
      btn.addEventListener("click", () => {
        selectedId = photo.id;
        pinned = true;
        view = "photo";
        render();
      });
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
  thumbs.forEach((btn, id) => btn.setAttribute("aria-current", String(id === selectedId)));
}

// -- settings ---------------------------------------------------------------------------

$("#open-settings").addEventListener("click", () => {
  $("#test-result").textContent = "";
  syncSettings();
  els.settings.showModal();
});

function buildGuestThemeChips() {
  const box = $("#guest-themes");
  for (const theme of Object.values(themes)) {
    if (theme.id === "custom") continue;
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "o-chip";
    chip.dataset.id = theme.id;
    chip.textContent = `${theme.emoji} ${theme.name}`;
    chip.addEventListener("click", () => {
      const current = new Set(state.prefs.guest_themes);
      if (current.has(theme.id)) {
        if (current.size === 1) return toast("Guests need at least one theme.");
        current.delete(theme.id);
      } else {
        current.add(theme.id);
      }
      setPrefs({ guest_themes: [...current] });
    });
    box.append(chip);
  }
}

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
  $("#camera-hint").textContent = {
    operator: "This iPad or laptop's camera. Its live view is shown to guests on the guest screen.",
    display: "The guest iPad's front camera. Also the setting for a single iPad doing everything.",
    camera: `Open ${location.host}/camera on an iPhone or other device to use it as the camera.`,
  }[prefs.camera_source];

  $$("#guest-themes .o-chip").forEach((c) => c.setAttribute("aria-pressed", String(prefs.guest_themes.includes(c.dataset.id))));

  const samples = $("#samples");
  const sampleKey = JSON.stringify(state.samples);
  if (samples.dataset.key !== sampleKey) {
    samples.dataset.key = sampleKey;
    samples.innerHTML = "";
    for (const theme of Object.values(themes)) {
      if (theme.id === "custom") continue;
      const tile = document.createElement("div");
      tile.className = "o-sample";
      const url = state.samples[theme.id];
      tile.innerHTML = url ? `<img alt="">` : `<span class="o-sample-none">${theme.emoji}</span>`;
      if (url) tile.querySelector("img").src = url;
      tile.title = `${theme.name}: ${url ? "has a sample" : "no sample yet"}`;
      samples.append(tile);
    }
  }
  const make = $("#make-samples");
  make.disabled = state.making_samples || !selected();
  make.lastElementChild.textContent = state.making_samples
    ? "Making samples…"
    : "Make samples for every theme from the selected photo";
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

$("#make-samples").addEventListener("click", () => {
  if (selectedId) link.send({ type: "make_samples", photo_id: selectedId });
});

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
