// Shared pose math. Coordinates are pixels in the 640×480 game window.
export const WIDTH = 640;
export const HEIGHT = 480;

export const NOSE = 0;
export const L_EYE = 2;
export const R_EYE = 5;
export const L_EAR = 7;
export const R_EAR = 8;
export const L_SHOULDER = 11;
export const R_SHOULDER = 12;
export const L_ELBOW = 13;
export const R_ELBOW = 14;
export const L_WRIST = 15;
export const R_WRIST = 16;
export const L_INDEX = 19;
export const R_INDEX = 20;
export const L_HIP = 23;
export const R_HIP = 24;
export const L_KNEE = 25;
export const R_KNEE = 26;
export const L_ANKLE = 27;
export const R_ANKLE = 28;
export const L_FOOT = 31;
export const R_FOOT = 32;

export const HAND_LANDMARKS = [L_WRIST, R_WRIST, L_INDEX, R_INDEX];

export function pt(points, index) {
  const pos = points?.[index];
  if (!pos) return null;
  return [pos[0], pos[1]];
}

export function mid(a, b) {
  return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
}

export function dist(a, b) {
  return Math.hypot(b[0] - a[0], b[1] - a[1]);
}

export function angle(a, b) {
  return Math.atan2(b[1] - a[1], b[0] - a[0]);
}

export function offset(point, radians, distance) {
  return [point[0] + Math.cos(radians) * distance, point[1] + Math.sin(radians) * distance];
}

export function lerp(a, b, t) {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
}

export function poseAnchor(points) {
  if (!points || Object.keys(points).length === 0) return null;
  const hips = pair(points, L_HIP, R_HIP);
  if (hips) return hips;
  const shoulders = pair(points, L_SHOULDER, R_SHOULDER);
  if (shoulders) return shoulders;
  if (points[NOSE]) return [points[NOSE][0], points[NOSE][1]];
  const values = Object.values(points);
  const x = values.reduce((sum, p) => sum + p[0], 0) / values.length;
  const y = values.reduce((sum, p) => sum + p[1], 0) / values.length;
  return [x, y];
}

export function poseSignature(points) {
  const left = points[L_SHOULDER];
  const right = points[R_SHOULDER];
  if (!left || !right) return null;
  return Math.hypot(right[0] - left[0], right[1] - left[1]);
}

export function handsFrom(points) {
  return HAND_LANDMARKS.filter((index) => points[index]).map((index) => points[index]);
}

export function bothHandsRaised(points) {
  if (!points) return false;
  const leftS = points[L_SHOULDER];
  const rightS = points[R_SHOULDER];
  const leftW = points[L_WRIST];
  const rightW = points[R_WRIST];
  if (!leftS || !rightS || !leftW || !rightW) return false;
  const line = (leftS[1] + rightS[1]) / 2;
  return leftW[1] < line - 28 && rightW[1] < line - 28;
}

function pair(points, a, b) {
  if (!points[a] || !points[b]) return null;
  return mid(points[a], points[b]);
}

export function headFrame(points) {
  const lEar = pt(points, L_EAR);
  const rEar = pt(points, R_EAR);
  const lEye = pt(points, L_EYE);
  const rEye = pt(points, R_EYE);
  const nose = pt(points, NOSE);
  const lSh = pt(points, L_SHOULDER);
  const rSh = pt(points, R_SHOULDER);
  let tilt = 0;
  let center = null;
  let radius = 0;
  if (lEar && rEar) {
    tilt = angle(lEar, rEar);
    center = mid(lEar, rEar);
    radius = dist(lEar, rEar) * 0.72;
  } else if (lEye && rEye) {
    tilt = angle(lEye, rEye);
    center = mid(lEye, rEye);
    radius = dist(lEye, rEye) * 1.15;
  } else if (nose && lSh && rSh) {
    const midSh = mid(lSh, rSh);
    center = [nose[0] * 0.65 + midSh[0] * 0.35, nose[1] * 0.75 + midSh[1] * 0.25];
    radius = dist(lSh, rSh) * 0.38;
    tilt = angle(midSh, nose) - Math.PI / 2;
  } else if (lSh && rSh) {
    const midSh = mid(lSh, rSh);
    const shoulder = dist(lSh, rSh);
    center = [midSh[0], midSh[1] - shoulder * 0.42];
    radius = shoulder * 0.36;
  } else {
    return null;
  }
  if (lSh && rSh) {
    radius = Math.max(radius, dist(lSh, rSh) * 0.3);
    radius = Math.min(radius, dist(lSh, rSh) * 0.55);
  }
  radius = Math.max(16, Math.min(64, radius));
  if (nose) {
    center = [center[0] * 0.6 + nose[0] * 0.4, center[1] * 0.7 + nose[1] * 0.3];
  }
  return { center, radius, tilt };
}

function limbRadius(length, kind) {
  const ratios = { upper_arm: 0.18, lower_arm: 0.16, thigh: 0.2, shin: 0.17 };
  return Math.max(6, Math.min(22, length * (ratios[kind] ?? 0.17)));
}

function pointSegmentDistance(px, py, ax, ay, bx, by) {
  const abx = bx - ax;
  const aby = by - ay;
  const ab2 = abx * abx + aby * aby;
  if (ab2 <= 1e-6) return Math.hypot(px - ax, py - ay);
  const t = Math.max(0, Math.min(1, ((px - ax) * abx + (py - ay) * aby) / ab2));
  return Math.hypot(px - (ax + abx * t), py - (ay + aby * t));
}

const LIMB_BONES = [
  [L_SHOULDER, L_ELBOW, "upper_arm"],
  [R_SHOULDER, R_ELBOW, "upper_arm"],
  [L_ELBOW, L_WRIST, "lower_arm"],
  [R_ELBOW, R_WRIST, "lower_arm"],
  [L_HIP, L_KNEE, "thigh"],
  [R_HIP, R_KNEE, "thigh"],
  [L_KNEE, L_ANKLE, "shin"],
  [R_KNEE, R_ANKLE, "shin"],
];

export function hitRegions(points) {
  const regions = [];
  const frame = headFrame(points);
  if (frame) regions.push({ kind: "circle", x: frame.center[0], y: frame.center[1], r: frame.radius * 0.92 });
  const lSh = pt(points, L_SHOULDER);
  const rSh = pt(points, R_SHOULDER);
  const lHip = pt(points, L_HIP);
  const rHip = pt(points, R_HIP);
  if (lSh && rSh && lHip && rHip) {
    const top = mid(lSh, rSh);
    const bottom = mid(lHip, rHip);
    const span = Math.max(dist(lSh, rSh), dist(lHip, rHip));
    regions.push({
      kind: "capsule",
      a: top,
      b: bottom,
      r: Math.max(18, span * 0.28),
    });
  }
  for (const [a, b, kind] of LIMB_BONES) {
    const p1 = pt(points, a);
    const p2 = pt(points, b);
    if (!p1 || !p2) continue;
    regions.push({ kind: "capsule", a: p1, b: p2, r: limbRadius(dist(p1, p2), kind) });
  }
  for (const [ankle, foot] of [
    [L_ANKLE, L_FOOT],
    [R_ANKLE, R_FOOT],
  ]) {
    const p1 = pt(points, ankle);
    const p2 = pt(points, foot);
    if (p1 && p2) regions.push({ kind: "capsule", a: p1, b: p2, r: 11 });
  }
  for (const wrist of [L_WRIST, R_WRIST]) {
    const wristP = pt(points, wrist);
    if (!wristP) continue;
    const elbow = pt(points, wrist === L_WRIST ? L_ELBOW : R_ELBOW);
    let radius = 12;
    if (elbow) radius = Math.max(10, Math.min(16, dist(wristP, elbow) * 0.22));
    regions.push({ kind: "circle", x: wristP[0], y: wristP[1], r: radius });
  }
  return regions;
}

export function regionHit(regions, x, y, extra = 0) {
  for (const region of regions) {
    if (region.kind === "circle") {
      if (Math.hypot(x - region.x, y - region.y) <= region.r + extra) return true;
    } else if (
      pointSegmentDistance(x, y, region.a[0], region.a[1], region.b[0], region.b[1]) <=
      region.r + extra
    ) {
      return true;
    }
  }
  return false;
}
