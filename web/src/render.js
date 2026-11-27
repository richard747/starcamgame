import { HEIGHT, WIDTH } from "./geometry.js";
import { START_LIVES, formatClock } from "./game.js";
import { drawAvatar, drawSkeleton } from "./avatar.js";

const SPECKS = Array.from({ length: 48 }, (_, i) => ({
  x: (i * 97) % WIDTH,
  y: (i * 53) % HEIGHT,
  r: i % 3 === 0 ? 2 : 1,
  shade: 140 + (i * 17) % 80,
}));

export function drawWorld(ctx, match, video, viewMode) {
  if (video && video.readyState >= 2) {
    ctx.save();
    ctx.translate(WIDTH, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(video, 0, 0, WIDTH, HEIGHT);
    ctx.restore();
    ctx.fillStyle = "rgba(8, 12, 28, 0.62)";
    ctx.fillRect(0, 0, WIDTH, HEIGHT);
  } else {
    ctx.fillStyle = "#080c1c";
    ctx.fillRect(0, 0, WIDTH, HEIGHT);
    for (const speck of SPECKS) {
      ctx.fillStyle = `rgb(${speck.shade}, ${speck.shade}, 255)`;
      ctx.beginPath();
      ctx.arc(speck.x, speck.y, speck.r, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  const showAvatar = viewMode === "avatar" || viewMode === "avatar+skeleton";
  const showSkeleton = viewMode === "skeleton" || viewMode === "avatar+skeleton";
  const bodies = match.pilots
    .filter((body) => body.present && Object.keys(body.points).length)
    .sort((a, b) => (a.anchor?.[1] ?? 0) - (b.anchor?.[1] ?? 0));
  for (const body of bodies) {
    if (showAvatar) drawAvatar(ctx, body.points, body.style);
    if (showSkeleton) drawSkeleton(ctx, body.points, body.color);
    if (body.invuln > 0 && body.anchor) {
      ctx.strokeStyle = Math.floor(match.elapsed * 12) % 2 === 0 ? "#ff6048" : "#ffffff";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(body.anchor[0], body.anchor[1], 46, 0, Math.PI * 2);
      ctx.stroke();
    }
  }

  for (const meteor of match.meteors) drawMeteor(ctx, meteor);
  for (const star of match.stars) drawStar(ctx, star);
  for (const impact of match.impacts) drawImpact(ctx, impact);

  for (const body of match.pilots) {
    for (const cursor of body.cursors) {
      ctx.strokeStyle = body.color;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(cursor[0], cursor[1], 16, 0, Math.PI * 2);
      ctx.stroke();
    }
  }

  drawHud(ctx, match);
  if (match.over) drawGameOver(ctx, match);
}

function drawStar(ctx, star) {
  ctx.fillStyle = star.color;
  ctx.beginPath();
  ctx.arc(star.x, star.y, star.radius, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#ffffff";
  ctx.beginPath();
  ctx.arc(star.x, star.y, Math.max(3, star.radius / 3), 0, Math.PI * 2);
  ctx.fill();
}

function drawMeteor(ctx, meteor) {
  const { x, y, radius } = meteor;
  for (const [index, scale] of [0.55, 0.34, 0.18].entries()) {
    ctx.fillStyle = "#6e3e24";
    ctx.beginPath();
    ctx.arc(x, y - radius * (1.15 + index * 0.65), Math.max(2, radius * scale), 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.fillStyle = "#583c2e";
  ctx.beginPath();
  ctx.arc(x, y, radius, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = "#ff9236";
  ctx.lineWidth = 2;
  ctx.stroke();
  ctx.fillStyle = "#36261e";
  ctx.beginPath();
  ctx.arc(x + Math.cos(meteor.spin) * radius * 0.28, y + Math.sin(meteor.spin) * radius * 0.22, Math.max(2, radius / 4), 0, Math.PI * 2);
  ctx.fill();
}

function drawImpact(ctx, impact) {
  const t = Math.max(0, Math.min(1, impact.age / impact.life));
  const alpha = 0.9 * (1 - t);
  const radius = 8 + 48 * t;
  ctx.strokeStyle = `rgba(255, 176, 64, ${alpha})`;
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.arc(impact.x, impact.y, radius, 0, Math.PI * 2);
  ctx.stroke();
  for (const [angle, speed] of impact.sparks) {
    ctx.fillStyle = "#ffd68c";
    ctx.beginPath();
    ctx.arc(impact.x + Math.cos(angle) * speed * t, impact.y + Math.sin(angle) * speed * t, 2, 0, Math.PI * 2);
    ctx.fill();
  }
}

function drawHud(ctx, match) {
  ctx.font = "22px 'Avenir Next', 'Segoe UI', sans-serif";
  ctx.textBaseline = "top";
  if (match.kind === "meteors") {
    const clock = formatClock(match.remaining);
    ctx.fillStyle = "#ffe4be";
    ctx.textAlign = "center";
    ctx.fillText(clock, WIDTH / 2, 10);
    ctx.textAlign = "left";
  }
  if (match.playerCount === 1) {
    const body = match.pilots[0];
    ctx.fillStyle = "#ffffff";
    ctx.fillText(`Score  ${body.score}`, 16, 12);
    drawPips(ctx, 16, 46, body.lives, body.color);
    return;
  }
  for (const body of match.pilots) {
    const label = `${body.name}  ${body.joined ? body.score : "--"}`;
    ctx.fillStyle = body.color;
    if (body.slot === 0) {
      ctx.textAlign = "left";
      ctx.fillText(label, 16, 10);
      if (body.joined) drawPips(ctx, 16, 40, body.lives, body.color);
    } else {
      ctx.textAlign = "right";
      ctx.fillText(label, WIDTH - 16, 10);
      if (body.joined) drawPips(ctx, WIDTH - 16 - (START_LIVES - 1) * 16, 40, body.lives, body.color);
    }
  }
  ctx.textAlign = "left";
}

function drawPips(ctx, x, y, lives, color) {
  for (let i = 0; i < START_LIVES; i += 1) {
    ctx.beginPath();
    ctx.arc(x + i * 16, y, 5, 0, Math.PI * 2);
    ctx.fillStyle = i < lives ? color : "#464c60";
    ctx.fill();
  }
}

function drawGameOver(ctx, match) {
  ctx.fillStyle = "rgba(5, 8, 18, 0.72)";
  ctx.fillRect(0, 0, WIDTH, HEIGHT);
  ctx.fillStyle = "#ffecd2";
  ctx.font = "32px 'Avenir Next', 'Segoe UI', sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(match.title || "Round over", WIDTH / 2, 180);
  ctx.font = "22px 'Avenir Next', 'Segoe UI', sans-serif";
  ctx.fillStyle = "#dce2ec";
  ctx.fillText(match.detail, WIDTH / 2, 220);
  ctx.fillStyle = "#ffc478";
  ctx.font = "18px 'Avenir Next', 'Segoe UI', sans-serif";
  const prompt = match.gesture > 0.05 ? "Hold both hands up" : "Play again, or raise both hands";
  ctx.fillText(prompt, WIDTH / 2, 270);
  ctx.textAlign = "left";
  ctx.textBaseline = "top";
}

export const VIEW_MODES = ["avatar", "avatar+skeleton", "skeleton", "none"];
