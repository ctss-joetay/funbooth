import {
  $, Camera, PreviewStreamer, aspectFor, connect, ensurePin, forgetPin, getPin, keepAwake, loadThemes,
  store, toast, uploadPhoto,
} from "/static/common.js";

const FACING_KEY = "funbooth.camera.facing";

const camera = new Camera($("#video"));
camera.facing = store(FACING_KEY) || "environment";

let themes = {};
let state = null;
let myId = null;
let started = false;
let countdownTimer = null;

await ensurePin();
themes = await loadThemes();

const link = connect(
  "camera",
  {
    welcome(msg) {
      myId = msg.client_id;
      link.send({ type: "camera", ready: camera.ready });
    },
    state(msg) {
      state = msg;
      if (state.phase !== "countdown") stopCountdown();
      render();
    },
    countdown: runCountdown,
    toast(msg) {
      toast(msg.text, msg.level);
    },
  },
  (online) => $("#conn").classList.toggle("on", online),
);

const streamer = new PreviewStreamer(camera, link);

$("#start-btn").addEventListener("click", () => {
  started = true;
  $("#start").hidden = true;
  keepAwake();
  if ($("#make-active").checked && state?.prefs.camera_source !== "camera") {
    link.send({ type: "prefs", pin: getPin(), prefs: { camera_source: "camera" } });
  }
  render();
});

function render() {
  if (!state) return;
  const { phase, prefs } = state;
  const theme = themes[prefs.theme_id];
  const active = !!myId && state.camera_id === myId;

  document.body.dataset.phase = phase;
  document.body.style.setProperty("--ar", aspectFor(prefs.orientation));
  document.body.classList.toggle("landscape-photos", prefs.orientation !== "portrait");
  $("#theme").textContent = theme ? `${theme.emoji} ${theme.id === "custom" ? "Custom" : theme.name}` : "";

  camera.sync(started).then((changed) => {
    if (!changed) return;
    link.send({ type: "camera", ready: camera.ready });
    if (camera.error) toast(`Camera unavailable: ${camera.error.message}`, "error");
    render();
  });
  streamer.update(active && state.preview_wanted, aspectFor(prefs.orientation));

  const status = $("#status");
  status.classList.toggle("warn", !active);
  if (camera.error) status.textContent = "Camera blocked: allow access, then tap 🔄";
  else if (prefs.camera_source !== "camera") status.textContent = "Standby: the operator has chosen a different camera";
  else if (!active) status.textContent = camera.ready ? "Standby: another camera device is active" : "Starting camera…";
  else status.textContent = { processing: "Creating the photo…", result: "Done! It's on the guest screen" }[phase] || "Booth camera · live";

  $("#shutter").disabled = !active || phase === "countdown" || phase === "processing";
}

camera.onended = () => {
  link.send({ type: "camera", ready: false });
  render();
};

$("#shutter").addEventListener("click", () => link.send({ type: "start" }));

$("#flip").addEventListener("click", () => {
  camera.facing = camera.facing === "user" ? "environment" : "user";
  store(FACING_KEY, camera.facing);
  camera.retry();
  camera.stop();
  render();
});

$("#lock").addEventListener("click", () => {
  forgetPin();
  location.reload();
});

function runCountdown(msg) {
  stopCountdown();
  let n = msg.seconds;
  const tick = () => {
    if (n <= 0) {
      stopCountdown();
      const flash = $("#flash");
      flash.classList.remove("go");
      void flash.offsetWidth;
      flash.classList.add("go");
      if (msg.capturer === myId) captureAndUpload();
      return;
    }
    $("#count").textContent = n;
    $("#count").classList.add("ticking");
    n -= 1;
    countdownTimer = setTimeout(tick, 1000);
  };
  tick();
}

function stopCountdown() {
  clearTimeout(countdownTimer);
  $("#count").classList.remove("ticking");
}

async function captureAndUpload() {
  if (!camera.ready) {
    toast("Camera isn't ready", "error");
    return;
  }
  const blob = await camera.capture(aspectFor(state.prefs.orientation));
  document.body.dataset.phase = "processing";
  try {
    await uploadPhoto(blob);
  } catch (err) {
    toast(`Upload failed: ${err.message}`, "error");
  }
}
