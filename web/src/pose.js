// Self-hosted MediaPipe. The wasm directory and the .task model are served
// from this origin; the page does not call a CDN while it is running.
import { FilesetResolver, PoseLandmarker } from "@mediapipe/tasks-vision";
import { HEIGHT, WIDTH } from "./geometry.js";

const MIN_VISIBILITY = 0.4;

export async function createLandmarker(numPoses) {
  const base = import.meta.env.BASE_URL;
  const vision = await FilesetResolver.forVisionTasks(`${base}mediapipe/wasm`);
  const modelAssetPath = `${base}models/pose_landmarker_lite.task`;
  const options = (delegate) => ({
    baseOptions: { modelAssetPath, delegate },
    runningMode: "VIDEO",
    numPoses,
    minPoseDetectionConfidence: 0.5,
    minPosePresenceConfidence: 0.5,
    minTrackingConfidence: 0.5,
  });
  try {
    return await PoseLandmarker.createFromOptions(vision, options("GPU"));
  } catch (gpuError) {
    console.warn("GPU pose delegate failed, using CPU.", gpuError);
    return PoseLandmarker.createFromOptions(vision, options("CPU"));
  }
}

export function landmarksToPoses(result) {
  const poses = result?.landmarks ?? [];
  return poses.map((pose) => {
    const points = {};
    pose.forEach((landmark, index) => {
      const visible = landmark.visibility == null || landmark.visibility >= MIN_VISIBILITY;
      const present = landmark.presence == null || landmark.presence >= MIN_VISIBILITY;
      if (!visible && !present) return;
      // The camera image is mirrored on screen, so flip x to match.
      points[index] = [(1 - landmark.x) * WIDTH, landmark.y * HEIGHT];
    });
    return points;
  });
}
