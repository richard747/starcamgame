import "./style.css";
import { HEIGHT, WIDTH, bothHandsRaised } from "./geometry.js";
import { Match } from "./game.js";
import { syntheticDetections } from "./demo.js";
import { VIEW_MODES, drawWorld } from "./render.js";
import { createLandmarker, landmarksToPoses } from "./pose.js";

const canvas = document.querySelector("#game");
const ctx = canvas.getContext("2d");
const video = document.querySelector("#camera");
const startPanel = document.querySelector("#start");
const toolbar = document.querySelector("#toolbar");
const statusEl = document.querySelector("#status");
const restartBtn = document.querySelector("#restart-btn");

const state = {
  mode: "stars",
  players: 1,
  suit: "astronaut",
  demo: new URLSearchParams(location.search).has("demo"),
  playing: false,
  view: 0,
  match: null,
  landmarker: null,
  stream: null,
  frame: 0,
  last: 0,
};

function setPressed(group, value, attr) {
  for (const button of document.querySelectorAll(`[${attr}]`)) {
    button.setAttribute("aria-pressed", String(button.dataset[group] === String(value)));
  }
}

function fitCanvas() {
  const scale = Math.min(window.innerWidth / WIDTH, window.innerHeight / HEIGHT);
  canvas.style.width = `${Math.floor(WIDTH * scale)}px`;
  canvas.style.height = `${Math.floor(HEIGHT * scale)}px`;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.round(WIDTH * dpr);
  canvas.height = Math.round(HEIGHT * dpr);
  ctx.setTransform(canvas.width / WIDTH, 0, 0, canvas.height / HEIGHT, 0, 0);
}

function setStatus(text) {
  statusEl.textContent = text;
}

function stopCamera() {
  if (state.stream) {
    for (const track of state.stream.getTracks()) track.stop();
    state.stream = null;
  }
  video.srcObject = null;
  if (state.landmarker) {
    state.landmarker.close?.();
    state.landmarker = null;
  }
}

function showMenu() {
  state.playing = false;
  stopCamera();
  startPanel.hidden = false;
  toolbar.hidden = true;
  restartBtn.hidden = true;
  setStatus(state.demo ? "Demo bodies are ready. No camera needed." : "Allow the camera when the browser asks.");
}

let starting = false;

async function begin(demo) {
  if (starting || state.playing) return;
  starting = true;
  try {
    await startRound(demo);
  } finally {
    starting = false;
  }
}

async function startRound(demo) {
  state.demo = demo;
  state.match = new Match({
    kind: state.mode,
    players: state.players,
    suit: state.suit,
    seed: demo ? 3 : null,
  });
  state.view = 0;
  state.frame = 0;
  state.last = 0;
  startPanel.hidden = true;
  toolbar.hidden = false;
  restartBtn.hidden = true;
  if (!demo) {
    setStatus("Starting the camera…");
    try {
      state.stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } },
        audio: false,
      });
      video.srcObject = state.stream;
      await video.play();
      setStatus("Loading pose tracking…");
      state.landmarker = await createLandmarker(state.players);
      setStatus("Camera on. Step back so your whole body fits.");
    } catch (error) {
      console.error(error);
      stopCamera();
      startPanel.hidden = false;
      toolbar.hidden = true;
      setStatus(error?.message || "The camera could not start.");
      return;
    }
  } else {
    setStatus("Demo bodies. No camera.");
  }
  state.playing = true;
  requestAnimationFrame(loop);
}

function loop(now) {
  if (!state.playing) return;
  const dt = state.last ? Math.min(0.05, (now - state.last) / 1000) : 1 / 30;
  state.last = now;
  state.frame += 1;
  const match = state.match;
  if (state.demo) {
    match.observePoses(syntheticDetections(state.frame, state.players), dt);
  } else if (state.landmarker && video.readyState >= 2) {
    const result = state.landmarker.detectForVideo(video, now);
    match.observePoses(landmarksToPoses(result), dt);
  }
  const raised = match.pilots.some((body) => body.present && bothHandsRaised(body.points));
  match.noteGesture(raised, dt);
  match.step(dt);
  restartBtn.hidden = !match.over;
  drawWorld(ctx, match, state.demo ? null : video, VIEW_MODES[state.view]);
  requestAnimationFrame(loop);
}

document.querySelector("#mode-stars").addEventListener("click", () => {
  state.mode = "stars";
  setPressed("mode", "stars", "data-mode");
});
document.querySelector("#mode-meteors").addEventListener("click", () => {
  state.mode = "meteors";
  setPressed("mode", "meteors", "data-mode");
});
document.querySelector("#players-1").addEventListener("click", () => {
  state.players = 1;
  setPressed("players", "1", "data-players");
});
document.querySelector("#players-2").addEventListener("click", () => {
  state.players = 2;
  setPressed("players", "2", "data-players");
});
document.querySelector("#suit-astronaut").addEventListener("click", () => {
  state.suit = "astronaut";
  setPressed("suit", "astronaut", "data-suit");
});
document.querySelector("#suit-robot").addEventListener("click", () => {
  state.suit = "robot";
  setPressed("suit", "robot", "data-suit");
});
document.querySelector("#start-camera").addEventListener("click", () => begin(false));
document.querySelector("#start-demo").addEventListener("click", () => begin(true));
document.querySelector("#view-btn").addEventListener("click", () => {
  state.view = (state.view + 1) % VIEW_MODES.length;
});
document.querySelector("#menu-btn").addEventListener("click", showMenu);
restartBtn.addEventListener("click", () => state.match?.restart());

document.addEventListener("keydown", (event) => {
  if (!state.playing) {
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      state.mode = state.mode === "stars" ? "meteors" : "stars";
      setPressed("mode", state.mode, "data-mode");
    } else if (event.key === "ArrowUp" || event.key === "ArrowDown") {
      state.players = state.players === 1 ? 2 : 1;
      setPressed("players", String(state.players), "data-players");
    } else if (event.key === "a" || event.key === "A") {
      state.suit = state.suit === "astronaut" ? "robot" : "astronaut";
      setPressed("suit", state.suit, "data-suit");
    } else if (event.key === "Enter") {
      event.preventDefault();
      begin(state.demo);
    } else if (event.key === "d" || event.key === "D") {
      begin(true);
    }
    return;
  }
  if (event.key === "s" || event.key === "S") {
    state.view = (state.view + 1) % VIEW_MODES.length;
  } else if ((event.key === "r" || event.key === "R" || event.key === " ") && state.match?.over) {
    event.preventDefault();
    state.match.restart();
  } else if (event.key === "Escape") {
    showMenu();
  }
});

window.addEventListener("resize", fitCanvas);
fitCanvas();
setStatus(state.demo ? "Demo bodies are ready. No camera needed." : "Allow the camera when the browser asks.");
