// Canvas avatars. The astronaut is the white suit. The robot is the humanoid android.
import {
  L_ANKLE,
  L_ELBOW,
  L_FOOT,
  L_HIP,
  L_INDEX,
  L_KNEE,
  L_SHOULDER,
  L_WRIST,
  R_ANKLE,
  R_ELBOW,
  R_FOOT,
  R_HIP,
  R_INDEX,
  R_KNEE,
  R_SHOULDER,
  R_WRIST,
  angle,
  dist,
  headFrame,
  lerp,
  mid,
  offset,
  pt,
} from "./geometry.js";

const STYLES = {
  astronaut: {
    suit: "#ecf0f8",
    shadow: "#bcc6d8",
    outline: "#2e3a54",
    helmet: "#f8fafd",
    visor: "#102a48",
    shine: "#aadceb",
    rim: "#deb048",
    glove: "#f4f6fa",
    cuff: "#e86c2a",
    boot: "#303646",
    sole: "#e86c2a",
    pack: "#3e485c",
    joint: "#d2d8e4",
  },
  robot: {
    suit: "#5680a4",
    shadow: "#2a4258",
    outline: "#121c28",
    helmet: "#6e96b4",
    visor: "#101820",
    shine: "#50ffbe",
    rim: "#46e6ff",
    glove: "#405468",
    cuff: "#46e6ff",
    boot: "#24303e",
    sole: "#46e6ff",
    pack: "#1e2c3a",
    joint: "#c8d2dc",
    accent: "#46e6ff",
  },
};

const BONES = [
  [L_SHOULDER, L_ELBOW, "upper_arm"],
  [R_SHOULDER, R_ELBOW, "upper_arm"],
  [L_ELBOW, L_WRIST, "lower_arm"],
  [R_ELBOW, R_WRIST, "lower_arm"],
  [L_HIP, L_KNEE, "thigh"],
  [R_HIP, R_KNEE, "thigh"],
  [L_KNEE, L_ANKLE, "shin"],
  [R_KNEE, R_ANKLE, "shin"],
];

function mix(hex, toward, t) {
  const n = parseInt(hex.slice(1), 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  const ch = (channel, dest) => Math.round(channel + (dest - channel) * t);
  return `rgb(${ch(r, toward[0])}, ${ch(g, toward[1])}, ${ch(b, toward[2])})`;
}

function poly(ctx, points, fill, stroke = null, width = 2) {
  if (points.length < 3) return;
  ctx.beginPath();
  ctx.moveTo(points[0][0], points[0][1]);
  for (let i = 1; i < points.length; i += 1) ctx.lineTo(points[i][0], points[i][1]);
  ctx.closePath();
  ctx.fillStyle = fill;
  ctx.fill();
  if (stroke) {
    ctx.strokeStyle = stroke;
    ctx.lineWidth = width;
    ctx.lineJoin = "round";
    ctx.stroke();
  }
}

function circle(ctx, point, radius, fill, stroke = null) {
  ctx.beginPath();
  ctx.arc(point[0], point[1], Math.max(1, radius), 0, Math.PI * 2);
  ctx.fillStyle = fill;
  ctx.fill();
  if (stroke) {
    ctx.strokeStyle = stroke;
    ctx.lineWidth = 2;
    ctx.stroke();
  }
}

function capsule(ctx, p1, p2, radius, fill, stroke) {
  const dx = p2[0] - p1[0];
  const dy = p2[1] - p1[1];
  const length = Math.hypot(dx, dy) || 1;
  const px = (-dy / length) * radius;
  const py = (dx / length) * radius;
  poly(
    ctx,
    [
      [p1[0] + px, p1[1] + py],
      [p2[0] + px, p2[1] + py],
      [p2[0] - px, p2[1] - py],
      [p1[0] - px, p1[1] - py],
    ],
    fill,
    stroke,
  );
  circle(ctx, p1, radius, fill, stroke);
  circle(ctx, p2, radius, fill, stroke);
}

function tapered(ctx, p1, p2, r1, r2, fill, stroke) {
  const dx = p2[0] - p1[0];
  const dy = p2[1] - p1[1];
  const length = Math.hypot(dx, dy) || 1;
  const ax = (-dy / length) * r1;
  const ay = (dx / length) * r1;
  const bx = (-dy / length) * r2;
  const by = (dx / length) * r2;
  poly(
    ctx,
    [
      [p1[0] + ax, p1[1] + ay],
      [p2[0] + bx, p2[1] + by],
      [p2[0] - bx, p2[1] - by],
      [p1[0] - ax, p1[1] - ay],
    ],
    fill,
    stroke,
    1.5,
  );
  circle(ctx, p1, r1, fill, stroke);
  circle(ctx, p2, r2, fill, stroke);
  const light = mix(fill, [255, 255, 255], 0.28);
  const shift = Math.min(r1, r2) * 0.32;
  ctx.strokeStyle = light;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(p1[0] + (-dy / length) * shift, p1[1] + (dx / length) * shift);
  ctx.lineTo(p2[0] + (-dy / length) * shift, p2[1] + (dx / length) * shift);
  ctx.stroke();
}

function robotTaper(length, kind) {
  const table = {
    upper_arm: [0.2, 0.13, 7, 15, 4.5, 10],
    lower_arm: [0.14, 0.075, 4.5, 10, 3, 7],
    thigh: [0.22, 0.15, 8, 18, 5.5, 12],
    shin: [0.15, 0.09, 5.5, 12, 3.5, 8],
  };
  const [near, far, nearLo, nearHi, farLo, farHi] = table[kind] ?? [0.16, 0.1, 5, 12, 3.5, 8];
  const safe = Math.max(8, length);
  return [
    Math.min(nearHi, Math.max(nearLo, safe * near)),
    Math.min(farHi, Math.max(farLo, safe * far)),
  ];
}

function crossSection(lSh, rSh, lHip, rHip, t, scale) {
  const left = lerp(lSh, lHip, t);
  const right = lerp(rSh, rHip, t);
  const center = mid(left, right);
  return [
    [center[0] + (left[0] - center[0]) * scale, center[1] + (left[1] - center[1]) * scale],
    [center[0] + (right[0] - center[0]) * scale, center[1] + (right[1] - center[1]) * scale],
  ];
}

function ellipse(ctx, center, rx, ry, tilt, fill, stroke = null) {
  ctx.save();
  ctx.translate(center[0], center[1]);
  ctx.rotate(tilt);
  ctx.beginPath();
  ctx.ellipse(0, 0, Math.max(1, rx), Math.max(1, ry), 0, 0, Math.PI * 2);
  ctx.fillStyle = fill;
  ctx.fill();
  if (stroke) {
    ctx.strokeStyle = stroke;
    ctx.lineWidth = 2;
    ctx.stroke();
  }
  ctx.restore();
}

function limbRadius(length, kind) {
  const ratios = { upper_arm: 0.18, lower_arm: 0.16, thigh: 0.2, shin: 0.17 };
  return Math.max(6, Math.min(22, length * (ratios[kind] ?? 0.17)));
}

function drawAstronaut(ctx, points, colors) {
  for (const [a, b, kind] of BONES.filter((bone) => bone[2] === "thigh" || bone[2] === "shin")) {
    const p1 = pt(points, a);
    const p2 = pt(points, b);
    if (p1 && p2) capsule(ctx, p1, p2, limbRadius(dist(p1, p2), kind), colors.suit, colors.outline);
  }
  drawBoots(ctx, points, colors, false);
  drawAstronautTorso(ctx, points, colors);
  for (const [a, b, kind] of BONES.filter((bone) => bone[2] === "upper_arm" || bone[2] === "lower_arm")) {
    const p1 = pt(points, a);
    const p2 = pt(points, b);
    if (p1 && p2) capsule(ctx, p1, p2, limbRadius(dist(p1, p2), kind), colors.suit, colors.outline);
  }
  drawGloves(ctx, points, colors, false);
  drawNeck(ctx, points, colors, false);
  drawAstronautHead(ctx, points, colors);
}

function drawRobot(ctx, points, colors) {
  for (const [a, b, kind] of BONES.filter((bone) => bone[2] === "thigh" || bone[2] === "shin")) {
    const p1 = pt(points, a);
    const p2 = pt(points, b);
    if (!p1 || !p2 || dist(p1, p2) < 3) continue;
    const [r1, r2] = robotTaper(dist(p1, p2), kind);
    tapered(ctx, p1, p2, r1, r2, colors.suit, colors.outline);
  }
  drawBoots(ctx, points, colors, true);
  for (const [joint, proximal, distal] of [
    [L_KNEE, L_HIP, L_ANKLE],
    [R_KNEE, R_HIP, R_ANKLE],
  ]) {
    drawHinge(ctx, points, joint, proximal, distal, colors);
  }
  drawRobotTorso(ctx, points, colors);
  for (const [a, b, kind] of BONES.filter((bone) => bone[2] === "upper_arm" || bone[2] === "lower_arm")) {
    const p1 = pt(points, a);
    const p2 = pt(points, b);
    if (!p1 || !p2 || dist(p1, p2) < 3) continue;
    const [r1, r2] = robotTaper(dist(p1, p2), kind);
    tapered(ctx, p1, p2, r1, r2, colors.suit, colors.outline);
  }
  drawGloves(ctx, points, colors, true);
  for (const [joint, proximal, distal] of [
    [L_ELBOW, L_SHOULDER, L_WRIST],
    [R_ELBOW, R_SHOULDER, R_WRIST],
  ]) {
    drawHinge(ctx, points, joint, proximal, distal, colors);
  }
  drawNeck(ctx, points, colors, true);
  drawRobotHead(ctx, points, colors);
}

function drawAstronautTorso(ctx, points, colors) {
  const lSh = pt(points, L_SHOULDER);
  const rSh = pt(points, R_SHOULDER);
  const lHip = pt(points, L_HIP);
  const rHip = pt(points, R_HIP);
  if (!lSh || !rSh || !lHip || !rHip) return;
  const corners = expand([lSh, rSh, rHip, lHip], 10);
  poly(ctx, corners, colors.suit, colors.outline, 3);
  const midSh = mid(lSh, rSh);
  const midHip = mid(lHip, rHip);
  const packH = Math.max(16, dist(midSh, midHip) * 0.38);
  const packW = Math.max(14, dist(lSh, rSh) * 0.28);
  const packC = [midSh[0] * 0.55 + midHip[0] * 0.45, midSh[1] * 0.55 + midHip[1] * 0.45];
  roundRect(ctx, packC[0] - packW / 2, packC[1] - packH / 2, packW, packH, 4, colors.pack, colors.outline);
  circle(ctx, [packC[0] + packW / 3, packC[1] - packH / 2 + 8], 5, colors.cuff, colors.outline);
  const beltY = midHip[1] - dist(midSh, midHip) * 0.12;
  ctx.strokeStyle = colors.cuff;
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.moveTo(corners[3][0], beltY);
  ctx.lineTo(corners[2][0], beltY);
  ctx.stroke();
}

function drawRobotTorso(ctx, points, colors) {
  const lSh = pt(points, L_SHOULDER);
  const rSh = pt(points, R_SHOULDER);
  const lHip = pt(points, L_HIP);
  const rHip = pt(points, R_HIP);
  if (!lSh || !rSh || !lHip || !rHip) return;
  const samples = [
    [0, 1.06],
    [0.14, 0.98],
    [0.32, 0.78],
    [0.5, 0.58],
    [0.66, 0.46],
    [0.84, 0.82],
    [1, 1.1],
  ];
  const left = [];
  const right = [];
  for (const [t, scale] of samples) {
    const [sideL, sideR] = crossSection(lSh, rSh, lHip, rHip, t, scale);
    left.push(sideL);
    right.push(sideR);
  }
  const top = mid(left[0], right[0]);
  const hipMid = mid(left.at(-1), right.at(-1));
  const peak = offset(top, angle(hipMid, top), dist(lSh, rSh) * 0.06);
  poly(ctx, [...left, ...right.reverse(), peak], colors.suit, colors.outline, 2);
  const chestL = [];
  const chestR = [];
  for (const [t, scale] of [
    [0.16, 0.58],
    [0.28, 0.5],
    [0.4, 0.42],
    [0.5, 0.36],
  ]) {
    const [sideL, sideR] = crossSection(lSh, rSh, lHip, rHip, t, scale);
    chestL.push(sideL);
    chestR.push(sideR);
  }
  const chestTop = mid(chestL[0], chestR[0]);
  const chestBot = mid(chestL.at(-1), chestR.at(-1));
  poly(ctx, [...chestL, ...[...chestR].reverse()], colors.shadow, colors.outline, 1);
  tapered(ctx, lerp(chestTop, chestBot, 0.18), lerp(chestTop, chestBot, 0.78), 3.4, 2.2, colors.accent, colors.outline);
  const span = dist(lHip, rHip);
  const axis = angle(lHip, rHip);
  const hips = mid(lHip, rHip);
  for (const hip of [lHip, rHip]) {
    ellipse(ctx, lerp(hip, hips, 0.28), Math.max(7, span * 0.15), Math.max(5, span * 0.1), axis, colors.pack, colors.outline);
  }
  const socket = Math.max(6, dist(lSh, rSh) * 0.09);
  circle(ctx, lSh, socket, colors.suit, colors.outline);
  circle(ctx, rSh, socket, colors.suit, colors.outline);
}

function drawAstronautHead(ctx, points, colors) {
  const frame = headFrame(points);
  if (!frame) return;
  const { center, radius, tilt } = frame;
  circle(ctx, center, radius, colors.helmet, colors.outline);
  const left = offset(center, tilt + Math.PI, radius * 0.92);
  const right = offset(center, tilt, radius * 0.92);
  ctx.strokeStyle = colors.rim;
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.moveTo(left[0], left[1]);
  ctx.lineTo(right[0], right[1]);
  ctx.stroke();
  const visor = offset(center, tilt + Math.PI / 2, radius * 0.12);
  ellipse(ctx, visor, radius * 0.78, radius * 0.55, tilt, colors.visor, colors.rim);
  for (const side of [tilt + Math.PI, tilt]) {
    circle(ctx, offset(center, side, radius * 0.95), Math.max(4, radius * 0.18), colors.shadow, colors.outline);
  }
}

function drawRobotHead(ctx, points, colors) {
  const frame = headFrame(points);
  if (!frame) return;
  const { center, radius, tilt } = frame;
  const rx = radius * 0.86;
  const ry = radius * 1.08;
  ellipse(ctx, center, rx, ry, tilt, colors.helmet, colors.outline);
  ctx.save();
  ctx.translate(center[0], center[1]);
  ctx.rotate(tilt);
  ctx.beginPath();
  ctx.ellipse(0, ry * 0.22, rx * 0.72, ry * 0.48, 0, 0.15, Math.PI - 0.15);
  ctx.fillStyle = colors.shadow;
  ctx.fill();
  ctx.beginPath();
  ctx.ellipse(0, ry * 0.16, rx * 0.5, ry * 0.28, 0, 0.55, Math.PI - 0.55);
  ctx.strokeStyle = colors.outline;
  ctx.lineWidth = 1.5;
  ctx.stroke();
  ctx.restore();
  const visor = offset(center, tilt + Math.PI / 2, -ry * 0.1);
  ellipse(ctx, visor, rx * 0.6, ry * 0.3, tilt, colors.visor, colors.rim);
  for (const side of [-1, 1]) {
    const eye = [
      visor[0] + Math.cos(tilt) * side * rx * 0.26 + -Math.sin(tilt) * ry * 0.02,
      visor[1] + Math.sin(tilt) * side * rx * 0.26 + Math.cos(tilt) * ry * 0.02,
    ];
    ellipse(ctx, eye, Math.max(2.5, rx * 0.15), Math.max(2, ry * 0.09), tilt, colors.accent);
    circle(ctx, [eye[0] - Math.cos(tilt) * rx * 0.04, eye[1] - Math.sin(tilt) * rx * 0.04], Math.max(1, rx * 0.045), colors.shine);
  }
  for (const side of [-1, 1]) {
    const node = offset(center, tilt + (side < 0 ? Math.PI : 0), rx * 0.92);
    circle(ctx, node, Math.max(2.5, rx * 0.1), colors.shadow, colors.outline);
  }
}

function drawNeck(ctx, points, colors, robot) {
  const frame = headFrame(points);
  const lSh = pt(points, L_SHOULDER);
  const rSh = pt(points, R_SHOULDER);
  if (!frame || !lSh || !rSh) return;
  const shoulders = mid(lSh, rSh);
  const chin = offset(frame.center, frame.tilt + Math.PI / 2, frame.radius * (robot ? 0.96 : 0.82));
  const span = dist(lSh, rSh);
  if (dist(chin, shoulders) < 4) return;
  if (robot) {
    tapered(ctx, chin, shoulders, Math.max(3.5, span * 0.055), Math.max(5, span * 0.09), colors.suit, colors.outline);
  } else {
    capsule(ctx, shoulders, chin, Math.max(7, span * 0.11), colors.suit, colors.outline);
    circle(ctx, shoulders, Math.max(10, span * 0.16), colors.suit, colors.outline);
  }
}

function drawHinge(ctx, points, joint, proximal, distal, colors) {
  const center = pt(points, joint);
  if (!center) return;
  let span = 0;
  for (const other of [proximal, distal]) {
    const end = pt(points, other);
    if (end) span = Math.max(span, dist(center, end));
  }
  if (span < 4) return;
  const radius = Math.min(11, Math.max(5, span * 0.15));
  circle(ctx, center, radius, colors.joint, colors.outline);
  circle(ctx, center, radius * 0.52, colors.shadow);
  circle(ctx, center, Math.max(1.5, radius * 0.22), colors.accent);
}

function drawGloves(ctx, points, colors, robot) {
  for (const [wristId, elbowId, indexId] of [
    [L_WRIST, L_ELBOW, L_INDEX],
    [R_WRIST, R_ELBOW, R_INDEX],
  ]) {
    const wrist = pt(points, wristId);
    if (!wrist) continue;
    if (!robot) {
      const elbow = pt(points, elbowId);
      const radius = elbow ? Math.max(9, Math.min(16, dist(wrist, elbow) * 0.22)) : 11;
      circle(ctx, wrist, radius, colors.glove, colors.outline);
      if (elbow) circle(ctx, offset(wrist, angle(wrist, elbow), radius * 0.85), Math.max(4, radius * 0.55), colors.cuff, colors.outline);
      continue;
    }
    drawRobotHand(ctx, points, wristId, elbowId, indexId, colors);
  }
}

function drawRobotHand(ctx, points, wristId, elbowId, indexId, colors) {
  const wrist = pt(points, wristId);
  const elbow = pt(points, elbowId);
  const index = pt(points, indexId);
  let direction;
  let reach;
  if (index && dist(wrist, index) > 4) {
    direction = angle(wrist, index);
    reach = dist(wrist, index);
  } else if (elbow) {
    direction = angle(elbow, wrist);
    reach = Math.max(12, dist(elbow, wrist) * 0.28);
  } else {
    direction = Math.PI / 2;
    reach = 14;
  }
  const palmR = Math.min(13, Math.max(6, reach * 0.62));
  const palm = offset(wrist, direction, palmR * 0.35);
  circle(ctx, palm, palmR, mix(colors.glove, [86, 128, 164], 0.45), colors.outline);
  const fingerLen = Math.min(18, Math.max(9, reach * 0.95));
  const knuckle = offset(palm, direction, palmR * 0.78);
  for (const slot of [-1, 0, 1]) {
    const base = offset(knuckle, direction + Math.PI / 2, slot * Math.max(4.5, palmR * 0.62));
    const tip = offset(base, direction + slot * 0.34, fingerLen);
    stroke(ctx, base, tip, colors.suit, 3);
    circle(ctx, tip, 2, colors.joint, colors.outline);
  }
  const sign = wristId === L_WRIST ? -1 : 1;
  const thumbBase = offset(palm, direction + sign * 1.35, palmR * 0.2);
  const thumbTip = offset(thumbBase, direction + sign * 0.95, fingerLen * 0.78);
  stroke(ctx, thumbBase, thumbTip, colors.suit, 3);
  circle(ctx, thumbTip, 2, colors.joint, colors.outline);
}

function drawBoots(ctx, points, colors, robot) {
  for (const [ankleId, footId, kneeId] of [
    [L_ANKLE, L_FOOT, L_KNEE],
    [R_ANKLE, R_FOOT, R_KNEE],
  ]) {
    const ankle = pt(points, ankleId);
    if (!ankle) continue;
    let toe = pt(points, footId);
    const knee = pt(points, kneeId);
    if (!toe || dist(ankle, toe) < 4) {
      toe = knee ? offset(ankle, angle(knee, ankle), 22) : [ankle[0], ankle[1] + 20];
    }
    if (robot) {
      const direction = angle(ankle, toe);
      const heel = offset(ankle, direction + Math.PI, 4);
      const end = offset(toe, direction, 7);
      tapered(ctx, heel, end, 6.5, 4.2, colors.boot, colors.outline);
      circle(ctx, offset(end, direction, 1.5), 3, colors.sole, colors.outline);
    } else {
      capsule(ctx, ankle, toe, 10, colors.boot, colors.outline);
      circle(ctx, offset(toe, angle(ankle, toe), 4), 5, colors.sole, colors.outline);
    }
  }
}

function expand(corners, padding) {
  const cx = corners.reduce((sum, p) => sum + p[0], 0) / corners.length;
  const cy = corners.reduce((sum, p) => sum + p[1], 0) / corners.length;
  return corners.map(([x, y]) => {
    const dx = x - cx;
    const dy = y - cy;
    const length = Math.hypot(dx, dy) || 1;
    return [x + (dx / length) * padding, y + (dy / length) * padding];
  });
}

function roundRect(ctx, x, y, w, h, radius, fill, stroke) {
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, radius);
  ctx.fillStyle = fill;
  ctx.fill();
  ctx.strokeStyle = stroke;
  ctx.lineWidth = 2;
  ctx.stroke();
}

function stroke(ctx, a, b, color, width) {
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.lineCap = "round";
  ctx.beginPath();
  ctx.moveTo(a[0], a[1]);
  ctx.lineTo(b[0], b[1]);
  ctx.stroke();
}

const SKELETON = [
  [11, 12],
  [11, 23],
  [12, 24],
  [23, 24],
  [11, 13],
  [13, 15],
  [12, 14],
  [14, 16],
  [15, 19],
  [16, 20],
  [23, 25],
  [25, 27],
  [24, 26],
  [26, 28],
  [0, 11],
  [0, 12],
];

export function drawSkeleton(ctx, points, color = "#a0dcff") {
  ctx.strokeStyle = color;
  ctx.lineWidth = 3;
  ctx.lineCap = "round";
  for (const [a, b] of SKELETON) {
    if (!points[a] || !points[b]) continue;
    ctx.beginPath();
    ctx.moveTo(points[a][0], points[a][1]);
    ctx.lineTo(points[b][0], points[b][1]);
    ctx.stroke();
  }
  for (const [index, pos] of Object.entries(points)) {
    circle(ctx, pos, [15, 16, 19, 20].includes(Number(index)) ? 6 : 4, color);
  }
}

export function drawAvatar(ctx, points, style) {
  if (!points || Object.keys(points).length === 0) return;
  const colors = STYLES[style] ?? STYLES.astronaut;
  if (style === "robot") drawRobot(ctx, points, colors);
  else drawAstronaut(ctx, points, colors);
}
