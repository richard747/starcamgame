// Round rules for the browser game. They follow gameplay.py:
// stars are popped by the hands; meteors hit the whole body.
import {
  HAND_LANDMARKS,
  HEIGHT,
  WIDTH,
  bothHandsRaised,
  dist,
  handsFrom,
  hitRegions,
  poseAnchor,
  poseSignature,
  regionHit,
} from "./geometry.js";

export { bothHandsRaised };

export const START_LIVES = 3;
export const ROUND_SECONDS = 45;
const START_GRACE = 0.75;
const INVULN_SECONDS = 1;
const GESTURE_SECONDS = 0.5;
const STAR_REACH = 28;
const STAR_COUNT = 6;
const METEOR_STAR_COUNT = 4;
const MAX_METEORS = 12;
const MISSING_LIMIT = 18;
const MATCH_GATE = 260;
const MAX_SPEED = 900;
const BODY_SMOOTH = 0.28;

const PLAYER_COLORS = ["rgb(255, 186, 92)", "rgb(90, 220, 255)"];
const STAR_COLORS = ["#ffd65a", "#fff5c8", "#ffaa50", "#c8dcff"];

export function stylesFor(count, primary = "astronaut") {
  if (count <= 1) return [primary === "robot" ? "robot" : "astronaut"];
  return primary === "robot" ? ["robot", "astronaut"] : ["astronaut", "robot"];
}

function makeRng(seed) {
  if (seed == null) return Math.random;
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function range(rng, a, b) {
  return a + rng() * (b - a);
}

function randint(rng, a, b) {
  return a + Math.floor(rng() * (b - a + 1));
}

function smoothPoints(previous, current, alpha) {
  const out = {};
  for (const key of Object.keys(current)) {
    const pos = current[key];
    const prev = previous[key];
    if (prev) out[key] = [prev[0] + (pos[0] - prev[0]) * alpha, prev[1] + (pos[1] - prev[1]) * alpha];
    else out[key] = pos;
  }
  return out;
}

class Star {
  constructor(rng) {
    this.x = range(rng, 30, WIDTH - 30);
    this.y = range(rng, -80, -10);
    this.speed = range(rng, 80, 180);
    this.radius = randint(rng, 12, 20);
    this.color = STAR_COLORS[Math.floor(rng() * STAR_COLORS.length)];
  }

  update(dt) {
    this.y += this.speed * dt;
  }

  offscreen() {
    return this.y - this.radius > HEIGHT;
  }
}

function meteorSpeed(elapsed) {
  const t = Math.max(0, Math.min(1, elapsed / 40));
  return [78 + 110 * t, 140 + 170 * t];
}

function meteorInterval(elapsed) {
  const t = Math.max(0, Math.min(1, elapsed / 40));
  return 1.15 - 0.78 * t;
}

function meteorCap(elapsed) {
  const t = Math.max(0, Math.min(1, elapsed / 40));
  return Math.min(MAX_METEORS, 6 + Math.floor(6 * t));
}

class Meteor {
  constructor(rng, elapsed, x = null, y = null) {
    const [lo, hi] = meteorSpeed(elapsed);
    this.x = x == null ? range(rng, 36, WIDTH - 36) : x;
    this.y = y == null ? range(rng, -120, -24) : y;
    this.speed = range(rng, lo, hi);
    this.vx = range(rng, -28, 28);
    this.radius = randint(rng, 13, 22);
    this.dead = false;
    this.spin = range(rng, 0, Math.PI * 2);
  }

  update(dt) {
    this.y += this.speed * dt;
    this.x += this.vx * dt;
    this.spin += dt * 1.4;
  }

  offscreen() {
    return this.y - this.radius > HEIGHT;
  }
}

class Impact {
  constructor(x, y) {
    this.x = x;
    this.y = y;
    this.age = 0;
    this.life = 0.42;
    this.sparks = Array.from({ length: 8 }, (_, i) => [(i / 8) * Math.PI * 2 + 0.2, 36 + (i % 4) * 12]);
  }

  update(dt) {
    this.age += dt;
  }

  get alive() {
    return this.age < this.life;
  }
}

class Track {
  constructor(slot, points, anchor, signature) {
    this.slot = slot;
    this.points = { ...points };
    this.smooth = { ...points };
    this.anchor = anchor;
    this.signature = signature;
    this.velocity = [0, 0];
    this.missing = 0;
    this.visible = true;
  }

  predict(dt) {
    if (this.missing) return this.anchor;
    return [this.anchor[0] + this.velocity[0] * dt, this.anchor[1] + this.velocity[1] * dt];
  }

  follow(points, anchor, signature, dt, smooth) {
    if (dt > 1e-6 && this.missing === 0) {
      let vx = (anchor[0] - this.anchor[0]) / dt;
      let vy = (anchor[1] - this.anchor[1]) / dt;
      const speed = Math.hypot(vx, vy);
      if (speed > MAX_SPEED) {
        vx *= MAX_SPEED / speed;
        vy *= MAX_SPEED / speed;
      }
      this.velocity = [vx, vy];
    } else {
      this.velocity = [0, 0];
    }
    this.anchor = anchor;
    if (signature != null) this.signature = signature;
    this.points = smoothPoints(this.smooth, points, smooth);
    this.smooth = this.points;
    this.missing = 0;
    this.visible = true;
  }

  get hands() {
    return HAND_LANDMARKS.filter((index) => this.points[index]).map((index) => this.points[index]);
  }
}

class PoseTracker {
  constructor(maxPlayers, smooth = BODY_SMOOTH) {
    this.maxPlayers = Math.max(1, maxPlayers);
    this.smooth = smooth;
    this.tracks = new Map();
  }

  update(detections, dt) {
    const dets = [];
    for (const points of detections) {
      const anchor = poseAnchor(points);
      if (!anchor) continue;
      dets.push({ points, anchor, signature: poseSignature(points) });
    }
    const slotIds = [...this.tracks.keys()].sort((a, b) => a - b);
    let pairs = [];
    if (dets.length && slotIds.length) {
      pairs =
        dets.length >= 2 && slotIds.length >= 2
          ? this.#pairTwo(dets, slotIds, dt)
          : this.#pairGreedy(dets, slotIds, dt);
      pairs = pairs.filter(([index, slot]) => this.#cost(dets[index], this.tracks.get(slot), dt) <= MATCH_GATE);
    }
    const matchedDets = new Set();
    const matchedSlots = new Set();
    for (const [index, slot] of pairs) {
      const det = dets[index];
      this.tracks.get(slot).follow(det.points, det.anchor, det.signature, dt, this.smooth);
      matchedDets.add(index);
      matchedSlots.add(slot);
    }
    for (const [slot, track] of [...this.tracks]) {
      if (matchedSlots.has(slot)) continue;
      track.missing += 1;
      track.visible = false;
      track.velocity = [0, 0];
      if (track.missing > MISSING_LIMIT) this.tracks.delete(slot);
    }
    const leftovers = dets
      .map((_, index) => index)
      .filter((index) => !matchedDets.has(index))
      .sort((a, b) => dets[a].anchor[0] - dets[b].anchor[0]);
    for (const [index, slot] of this.#newSlots(leftovers, dets)) {
      const det = dets[index];
      this.tracks.set(slot, new Track(slot, det.points, det.anchor, det.signature));
    }
    return slotIds
      .concat([...this.tracks.keys()].filter((slot) => !slotIds.includes(slot)))
      .filter((slot) => this.tracks.has(slot))
      .sort((a, b) => a - b)
      .map((slot) => this.tracks.get(slot));
  }

  #newSlots(leftovers, dets) {
    if (!leftovers.length) return [];
    if (this.tracks.size === 0 && leftovers.length === 1 && this.maxPlayers >= 2) {
      const slot = dets[leftovers[0]].anchor[0] <= WIDTH / 2 ? 0 : 1;
      return [[leftovers[0], slot]];
    }
    const free = [];
    for (let slot = 0; slot < this.maxPlayers; slot += 1) {
      if (!this.tracks.has(slot)) free.push(slot);
    }
    return leftovers.slice(0, free.length).map((index, i) => [index, free[i]]);
  }

  #pairTwo(dets, slotIds, dt) {
    const [first, second] = slotIds;
    let indexes = [0, 1];
    if (dets.length > 2) {
      indexes = dets
        .map((_, index) => index)
        .sort(
          (a, b) =>
            Math.min(this.#cost(dets[a], this.tracks.get(first), dt), this.#cost(dets[a], this.tracks.get(second), dt)) -
            Math.min(this.#cost(dets[b], this.tracks.get(first), dt), this.#cost(dets[b], this.tracks.get(second), dt)),
        )
        .slice(0, 2);
    }
    const [i, j] = indexes;
    const keep = [
      [i, first],
      [j, second],
    ];
    const swap = [
      [i, second],
      [j, first],
    ];
    const keepCost = this.#pairCost(keep, dets, dt, true);
    const swapCost = this.#pairCost(swap, dets, dt, true);
    if (Math.abs(keepCost - swapCost) <= 1e-6) {
      return this.#pairCost(swap, dets, dt, false) < this.#pairCost(keep, dets, dt, false) ? swap : keep;
    }
    return swapCost < keepCost ? swap : keep;
  }

  #pairGreedy(dets, slotIds, dt) {
    const pool = [...slotIds];
    const order = dets
      .map((_, index) => index)
      .sort(
        (a, b) =>
          Math.min(...pool.map((slot) => this.#cost(dets[a], this.tracks.get(slot), dt))) -
          Math.min(...pool.map((slot) => this.#cost(dets[b], this.tracks.get(slot), dt))),
      );
    const used = new Set();
    const pairs = [];
    for (const index of order) {
      let best = null;
      let bestCost = Infinity;
      for (const slot of pool) {
        if (used.has(slot)) continue;
        const cost = this.#cost(dets[index], this.tracks.get(slot), dt);
        if (cost < bestCost) {
          best = slot;
          bestCost = cost;
        }
      }
      if (best != null && bestCost <= MATCH_GATE) {
        pairs.push([index, best]);
        used.add(best);
      }
    }
    return pairs;
  }

  #pairCost(pairing, dets, dt, predicted) {
    let total = 0;
    for (const [index, slot] of pairing) {
      const track = this.tracks.get(slot);
      total += predicted ? this.#cost(dets[index], track, dt) : dist(dets[index].anchor, track.anchor);
    }
    return total;
  }

  #cost(det, track, dt) {
    const predicted = track.predict(dt);
    let cost = dist(det.anchor, predicted);
    if (det.signature != null && track.signature != null) cost += Math.abs(det.signature - track.signature) * 0.35;
    return cost;
  }
}

function pilot(slot, style) {
  return {
    slot,
    name: `P${slot + 1}`,
    style,
    color: PLAYER_COLORS[slot % PLAYER_COLORS.length],
    score: 0,
    lives: START_LIVES,
    invuln: 0,
    joined: false,
    present: false,
    points: {},
    cursors: [],
    anchor: null,
  };
}

export class Match {
  constructor({ kind, players, suit = "astronaut", seed = null }) {
    this.kind = kind;
    this.playerCount = players;
    this.rng = makeRng(seed);
    this.tracker = new PoseTracker(players);
    const styles = stylesFor(players, suit);
    this.pilots = styles.map((style, slot) => pilot(slot, style));
    this.starCap = kind === "stars" ? STAR_COUNT : METEOR_STAR_COUNT;
    this.stars = Array.from({ length: this.starCap }, () => new Star(this.rng));
    this.meteors = [];
    this.impacts = [];
    this.elapsed = 0;
    this.spawnTimer = 0.55;
    this.over = false;
    this.reason = "";
    this.title = "";
    this.detail = "";
    this.gesture = 0;
    this.gestureLatched = false;
  }

  get totalScore() {
    return this.pilots.reduce((sum, item) => sum + item.score, 0);
  }

  get remaining() {
    return Math.max(0, ROUND_SECONDS - this.elapsed);
  }

  observePoses(detections, dt) {
    const tracks = this.tracker.update(detections, dt);
    const seen = new Set();
    for (const track of tracks) {
      if (track.slot >= this.pilots.length) continue;
      seen.add(track.slot);
      const body = this.pilots[track.slot];
      if (track.visible) {
        body.present = true;
        body.joined = true;
        body.points = track.points;
        body.anchor = poseAnchor(track.points) || track.anchor;
        if (track.hands.length) body.cursors = track.hands;
      } else {
        body.present = false;
        body.points = {};
        body.anchor = track.anchor;
        body.cursors = [];
      }
    }
    for (const body of this.pilots) {
      if (seen.has(body.slot)) continue;
      body.present = false;
      body.points = {};
      body.cursors = [];
    }
  }

  noteGesture(raised, dt) {
    if (!this.over) {
      this.gesture = 0;
      if (!raised) this.gestureLatched = false;
      return false;
    }
    if (!raised) {
      this.gesture = 0;
      this.gestureLatched = false;
      return false;
    }
    if (this.gestureLatched) return false;
    this.gesture += dt;
    if (this.gesture < GESTURE_SECONDS) return false;
    this.gestureLatched = true;
    this.restart();
    return true;
  }

  restart() {
    for (const body of this.pilots) {
      body.score = 0;
      body.lives = START_LIVES;
      body.invuln = 0;
    }
    this.elapsed = 0;
    this.over = false;
    this.reason = "";
    this.title = "";
    this.detail = "";
    this.gesture = 0;
    this.spawnTimer = 0.8;
    this.meteors = [];
    this.impacts = [];
    this.stars = Array.from({ length: this.starCap }, () => new Star(this.rng));
  }

  step(dt) {
    if (this.over) return;
    dt = Math.max(0, dt);
    this.elapsed += dt;
    for (const body of this.pilots) {
      if (body.invuln > 0) body.invuln = Math.max(0, body.invuln - dt);
    }
    for (const star of this.stars) star.update(dt);
    this.#collectStars();
    this.stars = this.stars.filter((star) => !star.offscreen());
    while (this.stars.length < this.starCap) this.stars.push(new Star(this.rng));
    if (this.kind === "meteors") {
      this.#simulateMeteors(dt);
      for (const impact of this.impacts) impact.update(dt);
      this.impacts = this.impacts.filter((impact) => impact.alive);
      this.#checkEnd();
    }
  }

  #canScore(body) {
    if (!body.cursors.length) return false;
    if (this.kind === "meteors" && body.lives <= 0) return false;
    if (!body.present) return false;
    return true;
  }

  #collectStars() {
    const keep = [];
    for (const star of this.stars) {
      const winner = this.#nearestPop(star);
      if (!winner) keep.push(star);
      else winner.score += 1;
    }
    this.stars = keep;
  }

  #nearestPop(star) {
    let best = null;
    let bestD = Infinity;
    const reach = star.radius + STAR_REACH;
    for (const body of this.pilots) {
      if (!this.#canScore(body)) continue;
      for (const cursor of body.cursors) {
        const d2 = (star.x - cursor[0]) ** 2 + (star.y - cursor[1]) ** 2;
        if (d2 <= reach * reach && d2 < bestD) {
          best = body;
          bestD = d2;
        }
      }
    }
    return best;
  }

  #simulateMeteors(dt) {
    const steps = dt > 1 / 30 + 1e-4 ? 2 : 1;
    const slice = dt / steps;
    for (let step = 0; step < steps; step += 1) {
      if (this.over) return;
      this.spawnTimer -= slice;
      if (this.spawnTimer <= 0 && this.meteors.length < meteorCap(this.elapsed)) {
        this.#spawnMeteor();
        this.spawnTimer = meteorInterval(this.elapsed);
      }
      for (const meteor of this.meteors) meteor.update(slice);
      this.#collide();
      this.meteors = this.meteors.filter((meteor) => !meteor.dead && !meteor.offscreen());
    }
  }

  #spawnMeteor() {
    let chosen = null;
    for (let attempt = 0; attempt < 6; attempt += 1) {
      const meteor = new Meteor(this.rng, this.elapsed);
      chosen = meteor;
      const crowded = this.pilots.some(
        (body) => body.present && body.anchor && Math.abs(meteor.x - body.anchor[0]) < 64,
      );
      if (!crowded) break;
    }
    if (chosen) this.meteors.push(chosen);
  }

  #collide() {
    if (this.elapsed < START_GRACE) return;
    for (const meteor of this.meteors) {
      if (meteor.dead) continue;
      const victims = this.pilots.filter(
        (body) => body.lives > 0 && body.invuln <= 0 && body.present && body.points && regionHit(hitRegions(body.points), meteor.x, meteor.y, meteor.radius),
      );
      if (!victims.length) continue;
      victims.sort((a, b) => dist(a.anchor || a.cursors[0], [meteor.x, meteor.y]) - dist(b.anchor || b.cursors[0], [meteor.x, meteor.y]));
      const victim = victims[0];
      victim.lives -= 1;
      victim.invuln = INVULN_SECONDS;
      meteor.dead = true;
      this.impacts.push(new Impact(meteor.x, meteor.y));
      this.#checkEnd();
      if (this.over) return;
    }
  }

  #checkEnd() {
    if (this.over || this.kind !== "meteors") return;
    const joined = this.pilots.filter((body) => body.joined);
    if (joined.length >= 2) {
      const alive = joined.filter((body) => body.lives > 0);
      if (alive.length <= 1) {
        this.finish("last");
        return;
      }
    } else if (joined.length === 1 && joined[0].lives <= 0) {
      this.finish("lives");
      return;
    }
    if (this.elapsed >= ROUND_SECONDS) this.finish("time");
  }

  finish(reason) {
    if (this.over) return;
    this.over = true;
    this.reason = reason;
    const joined = this.pilots.filter((body) => body.joined);
    const field = joined.length ? joined : this.pilots;
    if (reason === "lives") this.title = "Out of lives";
    else if (reason === "last") {
      const alive = field.filter((body) => body.lives > 0);
      this.title = alive.length === 1 ? `${alive[0].name} wins` : "Draw";
    } else if (field.length <= 1) this.title = field[0].lives > 0 ? "You made it" : "Out of lives";
    else {
      const ranked = [...field].sort((a, b) => b.score - a.score || b.lives - a.lives);
      const tied = ranked[0].score === ranked[1].score && ranked[0].lives === ranked[1].lives;
      this.title = tied ? "Draw" : `${ranked[0].name} wins`;
    }
    this.detail =
      this.playerCount === 1
        ? `Score ${this.pilots[0].score}`
        : this.pilots.map((body) => `${body.name} ${body.joined ? body.score : "--"}`).join("   ·   ");
  }
}

export function formatClock(remaining) {
  const ticks = Math.max(0, Math.ceil(remaining - 1e-6));
  return `${Math.floor(ticks / 60)}:${String(ticks % 60).padStart(2, "0")}`;
}

export { handsFrom };
