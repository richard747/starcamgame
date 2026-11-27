// Built-in bodies for the demo button and headless tests. No camera required.
import { HEIGHT, WIDTH, poseAnchor } from "./geometry.js";

export function syntheticPose(width = WIDTH, height = HEIGHT, reach = "left") {
  const cx = width * 0.5;
  const sy = height * 0.38;
  const sw = 78;
  const hw = 54;
  const points = {};
  points[0] = [cx, sy - 78];
  points[2] = [cx + 12, sy - 86];
  points[5] = [cx - 12, sy - 86];
  points[7] = [cx + 26, sy - 80];
  points[8] = [cx - 26, sy - 80];
  points[11] = [cx + sw, sy];
  points[12] = [cx - sw, sy];
  points[23] = [cx + hw, sy + 118];
  points[24] = [cx - hw, sy + 118];
  points[13] = [cx + sw + 36, sy + 72];
  points[15] = [cx + sw + 48, sy + 132];
  points[19] = [cx + sw + 54, sy + 148];
  if (reach === "left") {
    points[14] = [cx - sw - 20, sy - 40];
    points[16] = [cx - sw - 10, sy - 108];
    points[20] = [cx - sw - 6, sy - 128];
  } else {
    points[14] = [cx - sw - 36, sy + 72];
    points[16] = [cx - sw - 48, sy + 132];
    points[20] = [cx - sw - 54, sy + 148];
    points[13] = [cx + sw + 20, sy - 40];
    points[15] = [cx + sw + 10, sy - 108];
    points[19] = [cx + sw + 6, sy - 128];
  }
  points[25] = [cx + hw + 6, sy + 198];
  points[26] = [cx - hw - 6, sy + 198];
  points[27] = [cx + hw + 4, sy + 268];
  points[28] = [cx - hw - 4, sy + 268];
  points[31] = [cx + hw + 16, sy + 282];
  points[32] = [cx - hw - 16, sy + 282];
  return points;
}

function shift(points, dx, dy) {
  const moved = {};
  for (const [index, pos] of Object.entries(points)) {
    moved[index] = [pos[0] + dx, pos[1] + dy];
  }
  return moved;
}

export function syntheticDetections(frame, players) {
  const t = frame / 30;
  const centers =
    players <= 1
      ? [WIDTH * 0.5 + Math.sin(t * 0.8) * 120]
      : [WIDTH * 0.5 + Math.sin(t * 0.65) * 170, WIDTH * 0.5 - Math.sin(t * 0.65) * 170];
  const reaches = players <= 1 ? ["left"] : ["left", "right"];
  return centers.slice(0, players).map((cx, index) => {
    const pose = syntheticPose(WIDTH, HEIGHT, reaches[index]);
    const anchor = poseAnchor(pose) ?? [WIDTH / 2, HEIGHT / 2];
    const dx = cx - anchor[0];
    const dy = Math.sin(t * 2 + index) * 10;
    return shift(pose, dx, dy);
  });
}
