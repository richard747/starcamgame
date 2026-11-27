// Copy MediaPipe's wasm into public/ and download the lite pose model.
// The browser then loads both from this origin. Nothing is fetched from a CDN at runtime.
import { createWriteStream, existsSync, mkdirSync, statSync } from "node:fs";
import { cp, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const wasmSrc = resolve(root, "node_modules/@mediapipe/tasks-vision/wasm");
const wasmDest = resolve(root, "public/mediapipe/wasm");
const modelDest = resolve(root, "public/models/pose_landmarker_lite.task");
const modelUrl =
  "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task";

if (!existsSync(wasmSrc)) {
  console.error("MediaPipe wasm is missing. Run npm install in web/ first.");
  process.exit(1);
}

await mkdir(wasmDest, { recursive: true });
await cp(wasmSrc, wasmDest, { recursive: true });
console.log("Copied MediaPipe wasm to public/mediapipe/wasm");

if (existsSync(modelDest) && statSync(modelDest).size > 1000) {
  console.log("Pose model already present.");
} else {
  mkdirSync(dirname(modelDest), { recursive: true });
  console.log("Downloading pose_landmarker_lite.task");
  const response = await fetch(modelUrl);
  if (!response.ok) {
    throw new Error(`Could not download the pose model (${response.status})`);
  }
  await pipeline(Readable.fromWeb(response.body), createWriteStream(modelDest));
  console.log(`Saved ${statSync(modelDest).size} bytes`);
}
