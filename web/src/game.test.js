import assert from "node:assert/strict";
import test from "node:test";
import { syntheticDetections, syntheticPose } from "./demo.js";
import { START_LIVES, Match, bothHandsRaised } from "./game.js";
import { L_SHOULDER, R_SHOULDER, poseAnchor } from "./geometry.js";

function poseAt(x, shoulder = 80) {
  const half = shoulder / 2;
  return {
    23: [x - 20, 220],
    24: [x + 20, 220],
    11: [x - half, 140],
    12: [x + half, 140],
    0: [x, 80],
  };
}

test("two people keep their sides when they cross", () => {
  const match = new Match({ kind: "stars", players: 2, seed: 1 });
  let wideSlot = null;
  for (let step = 0; step < 80; step += 1) {
    const ax = 240 + Math.sin(step / 12) * 150;
    const bx = 240 + Math.sin(step / 12 + Math.PI) * 150;
    let dets = [poseAt(ax, 70), poseAt(bx, 110)];
    if (step % 2) dets = dets.reverse();
    match.observePoses(dets, 1);
    const wide = match.pilots.find((body) => {
      const left = body.points[L_SHOULDER];
      const right = body.points[R_SHOULDER];
      if (!left || !right) return false;
      return Math.hypot(right[0] - left[0], right[1] - left[1]) > 90;
    });
    assert.ok(wide, `wide body missing at ${step}`);
    if (wideSlot == null) wideSlot = wide.slot;
    else assert.equal(wide.slot, wideSlot, `swapped at ${step}`);
  }
});

test("a meteor on the torso costs one life and the next is blocked", () => {
  const match = new Match({ kind: "meteors", players: 1, seed: 4 });
  const points = syntheticPose();
  match.observePoses([points], 1 / 30);
  match.elapsed = 2;
  match.spawnTimer = 100;
  const anchor = poseAnchor(points);
  match.meteors.push({
    x: anchor[0],
    y: anchor[1],
    speed: 0,
    vx: 0,
    radius: 16,
    dead: false,
    spin: 0,
    update() {},
    offscreen() {
      return false;
    },
  });
  match.step(1 / 30);
  assert.equal(match.pilots[0].lives, START_LIVES - 1);
  assert.ok(match.impacts.length);
  match.meteors.push({
    x: anchor[0],
    y: anchor[1],
    speed: 0,
    vx: 0,
    radius: 16,
    dead: false,
    spin: 0,
    update() {},
    offscreen() {
      return false;
    },
  });
  match.step(1 / 30);
  assert.equal(match.pilots[0].lives, START_LIVES - 1);
});

test("last player standing wins, and raised hands restart once", () => {
  const match = new Match({ kind: "meteors", players: 2, seed: 6 });
  const left = syntheticPose();
  const right = Object.fromEntries(Object.entries(syntheticPose()).map(([k, p]) => [k, [p[0] + 220, p[1]]]));
  match.observePoses([left, right], 1 / 30);
  match.pilots[0].lives = 1;
  match.elapsed = 2;
  match.spawnTimer = 100;
  const anchor = match.pilots[0].anchor;
  match.meteors.push({
    x: anchor[0],
    y: anchor[1],
    speed: 0,
    vx: 0,
    radius: 20,
    dead: false,
    spin: 0,
    update() {},
    offscreen() {
      return false;
    },
  });
  match.step(1 / 30);
  assert.equal(match.title, "P2 wins");
  const raised = structuredClone(match.pilots[1].points);
  raised[15] = [raised[11][0], raised[11][1] - 80];
  raised[16] = [raised[12][0], raised[12][1] - 80];
  assert.equal(bothHandsRaised(raised), true);
  match.pilots[1].points = raised;
  assert.equal(match.noteGesture(true, 0.2), false);
  assert.equal(match.noteGesture(true, 0.4), true);
  assert.equal(match.over, false);
  assert.equal(match.pilots[0].lives, START_LIVES);
  assert.equal(match.noteGesture(true, 1), false);
});

test("a star goes to the nearer hand", () => {
  const match = new Match({ kind: "stars", players: 2, seed: 2 });
  const left = syntheticPose(640, 480, "left");
  const right = Object.fromEntries(
    Object.entries(syntheticPose(640, 480, "right")).map(([k, p]) => [k, [p[0] + 200, p[1]]]),
  );
  match.observePoses([left, right], 1 / 30);
  const hand = right[19];
  match.stars = [{ x: hand[0], y: hand[1], radius: 14, speed: 0, color: "#fff", update() {}, offscreen() { return false; } }];
  match.step(1 / 30);
  assert.equal(match.pilots[0].score, 0);
  assert.equal(match.pilots[1].score, 1);
});

test("demo bodies move for a few hundred frames", () => {
  const match = new Match({ kind: "meteors", players: 2, seed: 3 });
  const previous = {};
  for (let frame = 1; frame <= 300; frame += 1) {
    match.observePoses(syntheticDetections(frame, 2), 1 / 30);
    for (const body of match.pilots) {
      assert.equal(body.present, true);
      if (previous[body.slot] != null) {
        assert.ok(Math.abs(body.anchor[0] - previous[body.slot]) < 40);
      }
      previous[body.slot] = body.anchor[0];
    }
    match.step(1 / 30);
  }
});
