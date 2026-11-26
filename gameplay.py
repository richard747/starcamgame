"""Round rules for Star Pop.

Stars mode is the original game: falling stars, popped by the hands, one
shared score, no clock. Meteor mode adds falling rocks that hit the whole
body (head, torso, and limbs). Each player has a score and three lives.
A round lasts 45 seconds. With two players, the last one standing wins
immediately; if both last until the clock, the higher score wins.

P1 starts as whoever is on the left, P2 on the right. After that, identity
follows the body, so the two do not swap when they cross.
"""

from __future__ import annotations

import math
import random

import pygame

import avatar

WIDTH, HEIGHT = 640, 480

START_LIVES = 3
ROUND_SECONDS = 45.0
START_GRACE = 0.75
INVULN_SECONDS = 1.0
GESTURE_SECONDS = 0.5
STAR_REACH = 28
STAR_COUNT = 6
METEOR_STAR_COUNT = 4
MAX_METEORS = 12
MISSING_LIMIT = 18
MATCH_GATE = 260.0
MAX_SPEED = 900.0

# MediaPipe hand landmarks: wrists and index fingertips.
HAND_LANDMARKS = (15, 16, 19, 20)

PLAYER_COLORS = (
    (255, 186, 92),
    (90, 220, 255),
)


def smooth_points(previous, current, alpha):
    """Exponential smoothing: out = prev + (new - prev) * alpha."""
    out = {}
    for key, pos in current.items():
        if key in previous:
            px, py = previous[key]
            out[key] = (px + (pos[0] - px) * alpha, py + (pos[1] - py) * alpha)
        else:
            out[key] = pos
    return out


def pose_anchor(points):
    """A stable body center: hips, then shoulders, then nose."""
    if not points:
        return None
    hips = _pair(points, 23, 24)
    if hips is not None:
        return hips
    shoulders = _pair(points, 11, 12)
    if shoulders is not None:
        return shoulders
    if 0 in points:
        return points[0]
    xs = [p[0] for p in points.values()]
    ys = [p[1] for p in points.values()]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def pose_signature(points):
    """Shoulder width, used as a weak hint when two people overlap."""
    left, right = points.get(11), points.get(12)
    if left is None or right is None:
        return None
    return math.hypot(right[0] - left[0], right[1] - left[1])


def hands_from(points):
    return [points[index] for index in HAND_LANDMARKS if index in points]


def format_clock(remaining):
    ticks = max(0, int(math.ceil(remaining - 1e-6)))
    return f"{ticks // 60}:{ticks % 60:02d}"


def both_hands_raised(points):
    """True when both wrists are clearly above the shoulders."""
    if not points:
        return False
    left_s, right_s = points.get(11), points.get(12)
    left_w, right_w = points.get(15), points.get(16)
    if not all((left_s, right_s, left_w, right_w)):
        return False
    line = (left_s[1] + right_s[1]) / 2.0
    return left_w[1] < line - 28 and right_w[1] < line - 28


def _pair(points, a, b):
    pa, pb = points.get(a), points.get(b)
    if pa is None or pb is None:
        return None
    return ((pa[0] + pb[0]) / 2.0, (pa[1] + pb[1]) / 2.0)


def _dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


class Star:
    def __init__(self, rng, width=WIDTH, height=HEIGHT):
        self.x = rng.uniform(30, width - 30)
        self.y = rng.uniform(-80, -10)
        self.speed = rng.uniform(80, 180)
        self.radius = rng.randint(12, 20)
        self.color = rng.choice(
            [(255, 214, 90), (255, 245, 200), (255, 170, 80), (200, 220, 255)]
        )
        self.height = height

    def update(self, dt):
        self.y += self.speed * dt

    def offscreen(self):
        return self.y - self.radius > self.height

    def draw(self, surface):
        pygame.draw.circle(surface, self.color, (int(self.x), int(self.y)), self.radius)
        pygame.draw.circle(
            surface, (255, 255, 255), (int(self.x), int(self.y)), max(3, self.radius // 3)
        )
        reach = self.radius + 4
        cx, cy = int(self.x), int(self.y)
        pygame.draw.line(surface, (255, 255, 255), (cx, cy - reach), (cx, cy + reach), 1)
        pygame.draw.line(surface, (255, 255, 255), (cx - reach, cy), (cx + reach, cy), 1)


class Meteor:
    def __init__(self, rng, elapsed, width=WIDTH, height=HEIGHT, x=None, y=None):
        lo, hi = meteor_speed_range(elapsed)
        self.x = rng.uniform(36, width - 36) if x is None else float(x)
        self.y = rng.uniform(-120, -24) if y is None else float(y)
        self.speed = rng.uniform(lo, hi)
        self.vx = rng.uniform(-28, 28)
        self.radius = rng.randint(13, 22)
        self.height = height
        self.dead = False
        self.spin = rng.uniform(0, math.tau)

    def update(self, dt):
        self.y += self.speed * dt
        self.x += self.vx * dt
        self.spin += dt * 1.4

    def offscreen(self):
        return self.y - self.radius > self.height

    def draw(self, surface):
        x, y = int(self.x), int(self.y)
        radius = max(4, int(self.radius))
        # A short tail so a still frame still reads as falling.
        for index, scale in enumerate((0.55, 0.34, 0.18)):
            tail_y = y - int(radius * (1.15 + index * 0.65))
            pygame.draw.circle(surface, (110, 62, 36), (x, tail_y), max(2, int(radius * scale)))
        pygame.draw.circle(surface, (88, 60, 46), (x, y), radius)
        pygame.draw.circle(surface, (255, 146, 54), (x, y), radius, 2)
        crater = (
            x + int(math.cos(self.spin) * radius * 0.28),
            y + int(math.sin(self.spin) * radius * 0.22),
        )
        pygame.draw.circle(surface, (54, 38, 30), crater, max(2, radius // 4))
        pygame.draw.circle(
            surface,
            (68, 46, 34),
            (x - radius // 4, y + radius // 5),
            max(2, radius // 5),
        )


class Impact:
    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
        self.age = 0.0
        self.life = 0.42
        rng = random.Random(int(abs(x) * 13 + abs(y) * 7))
        self.sparks = [
            (rng.random() * math.tau, rng.uniform(36, 78))
            for _ in range(8)
        ]

    def update(self, dt):
        self.age += dt

    @property
    def alive(self):
        return self.age < self.life

    def draw(self, surface):
        t = max(0.0, min(1.0, self.age / self.life))
        alpha = int(230 * (1.0 - t))
        radius = int(8 + 48 * t)
        ring = pygame.Surface((radius * 2 + 6, radius * 2 + 6), pygame.SRCALPHA)
        center = radius + 3
        pygame.draw.circle(ring, (255, 176, 64, alpha), (center, center), radius, 3)
        pygame.draw.circle(ring, (255, 236, 200, alpha), (center, center), max(2, radius // 3))
        surface.blit(ring, (self.x - center, self.y - center))
        for angle, speed in self.sparks:
            dist = speed * t
            sx = int(self.x + math.cos(angle) * dist)
            sy = int(self.y + math.sin(angle) * dist)
            pygame.draw.circle(surface, (255, 214, 140), (sx, sy), 2)


def meteor_speed_range(elapsed):
    t = max(0.0, min(1.0, elapsed / 40.0))
    return (78 + 110 * t, 140 + 170 * t)


def meteor_interval(elapsed):
    t = max(0.0, min(1.0, elapsed / 40.0))
    return 1.15 - 0.78 * t


def meteor_cap(elapsed):
    t = max(0.0, min(1.0, elapsed / 40.0))
    return min(MAX_METEORS, 6 + int(6 * t))


class Track:
    """One body across frames. Slot 0 is P1, slot 1 is P2."""

    def __init__(self, slot, points, zmap, anchor, signature):
        self.slot = slot
        self.points = dict(points)
        self.smooth = dict(points)
        self.zmap = dict(zmap or {})
        self.anchor = anchor
        self.signature = signature
        self.velocity = (0.0, 0.0)
        self.missing = 0
        self.visible = True

    def predict(self, dt):
        if self.missing:
            return self.anchor
        return (
            self.anchor[0] + self.velocity[0] * dt,
            self.anchor[1] + self.velocity[1] * dt,
        )

    def follow(self, points, zmap, anchor, signature, dt, smooth):
        if dt > 1e-6 and self.missing == 0:
            vx = (anchor[0] - self.anchor[0]) / dt
            vy = (anchor[1] - self.anchor[1]) / dt
            speed = math.hypot(vx, vy)
            if speed > MAX_SPEED:
                scale = MAX_SPEED / speed
                vx, vy = vx * scale, vy * scale
            self.velocity = (vx, vy)
        else:
            self.velocity = (0.0, 0.0)
        self.anchor = anchor
        if signature is not None:
            self.signature = signature
        self.points = smooth_points(self.smooth, points, smooth)
        self.smooth = self.points
        self.zmap = dict(zmap or {})
        self.missing = 0
        self.visible = True

    @property
    def hands(self):
        return hands_from(self.points)


class PoseTracker:
    """Assign detections to P1/P2 without swapping them when they cross.

    The first frame sorts by horizontal position (left is P1). Later frames
    match each detection to the track it was predicted to reach. Two people
    get both possible pairings compared, with a small bias toward keeping
    the previous pairing, so an overlap does not flip the labels.
    """

    def __init__(self, max_players=2, smooth=0.28):
        self.max_players = max(1, int(max_players))
        self.smooth = smooth
        self.tracks = {}

    def update(self, detections, dt=1 / 30):
        dets = []
        for item in detections:
            points, zmap = item[0], item[1] if len(item) > 1 else {}
            anchor = pose_anchor(points)
            if anchor is None:
                continue
            dets.append((points, zmap or {}, anchor, pose_signature(points)))

        slot_ids = sorted(self.tracks)
        pairs = []
        if dets and slot_ids:
            if len(dets) >= 2 and len(slot_ids) >= 2:
                pairs = self._pair_two(dets, slot_ids, dt)
            else:
                pairs = self._pair_greedy(dets, slot_ids, dt)
        pairs = [
            (index, slot)
            for index, slot in pairs
            if self._cost(dets[index], self.tracks[slot], dt) <= MATCH_GATE
        ]

        matched_dets = set()
        matched_slots = set()
        for index, slot in pairs:
            points, zmap, anchor, signature = dets[index]
            self.tracks[slot].follow(points, zmap, anchor, signature, dt, self.smooth)
            matched_dets.add(index)
            matched_slots.add(slot)

        for slot, track in list(self.tracks.items()):
            if slot in matched_slots:
                continue
            track.missing += 1
            track.visible = False
            track.velocity = (0.0, 0.0)
            if track.missing > MISSING_LIMIT:
                del self.tracks[slot]

        leftovers = [index for index in range(len(dets)) if index not in matched_dets]
        leftovers.sort(key=lambda index: dets[index][2][0])
        for index, slot in self._new_slots(leftovers, dets):
            points, zmap, anchor, signature = dets[index]
            self.tracks[slot] = Track(slot, points, zmap, anchor, signature)

        return [self.tracks[slot] for slot in sorted(self.tracks)]

    def _new_slots(self, leftovers, dets):
        """Give new bodies a side. Alone on the right starts as P2."""
        if not leftovers:
            return []
        if not self.tracks and len(leftovers) == 1 and self.max_players >= 2:
            anchor_x = dets[leftovers[0]][2][0]
            slot = 0 if anchor_x <= WIDTH / 2 else 1
            return [(leftovers[0], slot)]
        free = [slot for slot in range(self.max_players) if slot not in self.tracks]
        return list(zip(leftovers, free))

    def _pair_two(self, dets, slot_ids, dt):
        """Pick the pairing whose predicted positions fit better.

        On a tie, stick to the last anchors so a frame of total overlap
        does not follow whichever order the detector returned.
        """
        first, second = slot_ids[0], slot_ids[1]
        if len(dets) > 2:
            ranked = sorted(
                range(len(dets)),
                key=lambda index: min(
                    self._cost(dets[index], self.tracks[first], dt),
                    self._cost(dets[index], self.tracks[second], dt),
                ),
            )
            indexes = ranked[:2]
        else:
            indexes = [0, 1]
        i, j = indexes
        keep = [(i, first), (j, second)]
        swap = [(i, second), (j, first)]
        keep_cost = self._pair_cost(keep, dets, dt, predicted=True)
        swap_cost = self._pair_cost(swap, dets, dt, predicted=True)
        if abs(keep_cost - swap_cost) <= 1e-6:
            keep_last = self._pair_cost(keep, dets, dt, predicted=False)
            swap_last = self._pair_cost(swap, dets, dt, predicted=False)
            return swap if swap_last < keep_last else keep
        return swap if swap_cost < keep_cost else keep

    def _pair_cost(self, pairing, dets, dt, predicted):
        total = 0.0
        for index, slot in pairing:
            if predicted:
                total += self._cost(dets[index], self.tracks[slot], dt)
            else:
                total += _dist(dets[index][2], self.tracks[slot].anchor)
        return total

    def _pair_greedy(self, dets, slot_ids, dt):
        pool = list(slot_ids)
        order = sorted(
            range(len(dets)),
            key=lambda index: min(self._cost(dets[index], self.tracks[slot], dt) for slot in pool),
        )
        used = set()
        pairs = []
        for index in order:
            best_slot = None
            best_cost = None
            for slot in pool:
                if slot in used:
                    continue
                cost = self._cost(dets[index], self.tracks[slot], dt)
                if best_cost is None or cost < best_cost:
                    best_slot, best_cost = slot, cost
            if best_slot is not None and best_cost <= MATCH_GATE:
                pairs.append((index, best_slot))
                used.add(best_slot)
        return pairs

    def _cost(self, det, track, dt):
        _points, _zmap, anchor, signature = det
        predicted = track.predict(dt)
        cost = _dist(anchor, predicted)
        if signature is not None and track.signature is not None:
            cost += abs(signature - track.signature) * 0.35
        return cost


class Pilot:
    def __init__(self, slot, style, color):
        self.slot = slot
        self.name = f"P{slot + 1}"
        self.style = style
        self.color = color
        self.score = 0
        self.lives = START_LIVES
        self.invuln = 0.0
        self.joined = False
        self.present = False
        self.points = {}
        self.zmap = {}
        self.cursors = []
        self.anchor = None
        self.hit_radius = 0.0


class Match:
    """Scores, lives, stars, and meteors for one round."""

    def __init__(self, kind, player_count, styles, seed=None, sticky_cursors=False, smooth=0.28):
        self.kind = kind
        self.player_count = player_count
        self.sticky_cursors = sticky_cursors
        self.rng = random.Random(seed)
        self.tracker = PoseTracker(player_count, smooth=smooth)
        self.pilots = []
        for slot in range(player_count):
            style = styles[slot] if slot < len(styles) else "astronaut"
            color = PLAYER_COLORS[slot % len(PLAYER_COLORS)]
            pilot = Pilot(slot, style, color)
            if sticky_cursors and slot == 0:
                # The original one-player game pops stars at the center until a hand arrives.
                pilot.cursors = [(WIDTH / 2, HEIGHT / 2)]
            self.pilots.append(pilot)
        self.star_cap = STAR_COUNT if kind == "stars" else METEOR_STAR_COUNT
        self.stars = [Star(self.rng) for _ in range(self.star_cap)]
        self.meteors = []
        self.impacts = []
        self.elapsed = 0.0
        self.spawn_timer = 0.55
        self.over = False
        self.reason = ""
        self.title = ""
        self.detail = ""
        self.gesture = 0.0
        self.gesture_latched = False

    @property
    def total_score(self):
        return sum(pilot.score for pilot in self.pilots)

    @property
    def remaining(self):
        return max(0.0, ROUND_SECONDS - self.elapsed)

    def observe_poses(self, detections, dt):
        tracks = self.tracker.update(detections, dt)
        seen = set()
        for track in tracks:
            if track.slot >= len(self.pilots):
                continue
            seen.add(track.slot)
            pilot = self.pilots[track.slot]
            if track.visible:
                pilot.present = True
                pilot.joined = True
                pilot.points = track.points
                pilot.zmap = track.zmap
                pilot.anchor = pose_anchor(track.points) or track.anchor
                if track.hands:
                    pilot.cursors = track.hands
            else:
                pilot.present = False
                pilot.points = {}
                pilot.anchor = track.anchor
                if not self.sticky_cursors:
                    pilot.cursors = []
        for pilot in self.pilots:
            if pilot.slot in seen:
                continue
            pilot.present = False
            pilot.points = {}
            if not self.sticky_cursors:
                pilot.cursors = []

    def observe_body(self, slot, points, zmap=None):
        """Place a fully posed test or mouse-driven body on a slot."""
        pilot = self.pilots[slot]
        pilot.points = dict(points)
        pilot.zmap = dict(zmap or {})
        pilot.anchor = pose_anchor(points)
        pilot.cursors = hands_from(points)
        pilot.present = bool(points)
        pilot.hit_radius = 0.0
        if pilot.present:
            pilot.joined = True

    def observe_cursors(self, slot, cursors, hit_radius=0.0):
        """A hand point with no skeleton (mouse or Kinect depth)."""
        pilot = self.pilots[slot]
        pilot.points = {}
        pilot.hit_radius = hit_radius
        if cursors:
            pilot.cursors = list(cursors)
            pilot.anchor = cursors[0]
            pilot.present = True
            pilot.joined = True
        else:
            pilot.present = False
            pilot.anchor = None
            if not self.sticky_cursors:
                pilot.cursors = []
                pilot.hit_radius = 0.0

    def note_gesture(self, raised, dt):
        """Hold both hands up on the game-over screen to play again.

        Hands have to drop before the gesture can fire a second time, so a
        held pose does not immediately skip the next round.
        """
        if not self.over:
            self.gesture = 0.0
            if not raised:
                self.gesture_latched = False
            return False
        if not raised:
            self.gesture = 0.0
            self.gesture_latched = False
            return False
        if self.gesture_latched:
            return False
        self.gesture += dt
        if self.gesture < GESTURE_SECONDS:
            return False
        self.gesture_latched = True
        self.restart()
        return True

    def restart(self):
        for pilot in self.pilots:
            pilot.score = 0
            pilot.lives = START_LIVES
            pilot.invuln = 0.0
        self.elapsed = 0.0
        self.over = False
        self.reason = ""
        self.title = ""
        self.detail = ""
        self.gesture = 0.0
        self.spawn_timer = 0.8
        self.meteors.clear()
        self.impacts.clear()
        self.stars = [Star(self.rng) for _ in range(self.star_cap)]

    def step(self, dt):
        if self.over:
            return
        dt = max(0.0, dt)
        self.elapsed += dt
        for pilot in self.pilots:
            if pilot.invuln > 0:
                pilot.invuln = max(0.0, pilot.invuln - dt)
        for star in self.stars:
            star.update(dt)
        self._collect_stars()
        self.stars = [star for star in self.stars if not star.offscreen()]
        while len(self.stars) < self.star_cap:
            self.stars.append(Star(self.rng))
        if self.kind == "meteors":
            self._simulate_meteors(dt)
            for impact in self.impacts:
                impact.update(dt)
            self.impacts = [impact for impact in self.impacts if impact.alive]
            self._check_end()

    def _can_score(self, pilot):
        if not pilot.cursors:
            return False
        if self.kind == "meteors" and pilot.lives <= 0:
            return False
        if not pilot.present and not self.sticky_cursors:
            return False
        return True

    def _collect_stars(self):
        keep = []
        for star in self.stars:
            winner = self._nearest_pop(star)
            if winner is None:
                keep.append(star)
                continue
            winner.score += 1
        self.stars = keep

    def _nearest_pop(self, star):
        best = None
        best_d = None
        reach = star.radius + STAR_REACH
        for pilot in self.pilots:
            if not self._can_score(pilot):
                continue
            for cursor in pilot.cursors:
                dx = star.x - cursor[0]
                dy = star.y - cursor[1]
                dist2 = dx * dx + dy * dy
                if dist2 <= reach * reach and (best_d is None or dist2 < best_d):
                    best = pilot
                    best_d = dist2
        return best

    def _simulate_meteors(self, dt):
        steps = 2 if dt > (1 / 30) + 1e-4 else 1
        slice_dt = dt / steps if steps else dt
        for _ in range(steps):
            if self.over:
                return
            self.spawn_timer -= slice_dt
            if self.spawn_timer <= 0 and len(self.meteors) < meteor_cap(self.elapsed):
                self._spawn_meteor()
                self.spawn_timer = meteor_interval(self.elapsed)
            for meteor in self.meteors:
                meteor.update(slice_dt)
            self._collide()
            self.meteors = [
                meteor for meteor in self.meteors if not meteor.dead and not meteor.offscreen()
            ]

    def _spawn_meteor(self):
        chosen = None
        for _ in range(6):
            meteor = Meteor(self.rng, self.elapsed)
            if not self._crowds_a_player(meteor):
                chosen = meteor
                break
            chosen = meteor
        if chosen is not None:
            self.meteors.append(chosen)

    def _crowds_a_player(self, meteor):
        for pilot in self.pilots:
            if not pilot.present or pilot.anchor is None:
                continue
            if abs(meteor.x - pilot.anchor[0]) < 64:
                return True
        return False

    def _collide(self):
        if self.elapsed < START_GRACE:
            return
        for meteor in self.meteors:
            if meteor.dead:
                continue
            victims = []
            for pilot in self.pilots:
                if pilot.lives <= 0 or pilot.invuln > 0 or not pilot.present:
                    continue
                if self._pilot_hit(pilot, meteor):
                    victims.append(pilot)
            if not victims:
                continue
            victim = min(
                victims,
                key=lambda pilot: _dist(
                    pilot.anchor or pilot.cursors[0], (meteor.x, meteor.y)
                ),
            )
            victim.lives -= 1
            victim.invuln = INVULN_SECONDS
            meteor.dead = True
            self.impacts.append(Impact(meteor.x, meteor.y))
            self._check_end()
            if self.over:
                return

    def _pilot_hit(self, pilot, meteor):
        if pilot.points:
            return avatar.region_hit(
                avatar.hit_regions(pilot.points), meteor.x, meteor.y, meteor.radius
            )
        if pilot.hit_radius <= 0 or not pilot.cursors:
            return False
        limit = pilot.hit_radius + meteor.radius
        return any(_dist(cursor, (meteor.x, meteor.y)) <= limit for cursor in pilot.cursors)

    def _check_end(self):
        if self.over or self.kind != "meteors":
            return
        joined = [pilot for pilot in self.pilots if pilot.joined]
        if len(joined) >= 2:
            alive = [pilot for pilot in joined if pilot.lives > 0]
            if len(alive) <= 1:
                self.finish("last")
                return
        elif len(joined) == 1 and joined[0].lives <= 0:
            self.finish("lives")
            return
        if self.elapsed >= ROUND_SECONDS:
            self.finish("time")

    def finish(self, reason):
        if self.over:
            return
        self.over = True
        self.reason = reason
        joined = [pilot for pilot in self.pilots if pilot.joined]
        field = joined or list(self.pilots)
        if reason == "lives":
            self.title = "Out of lives"
        elif reason == "last":
            alive = [pilot for pilot in field if pilot.lives > 0]
            self.title = f"{alive[0].name} wins" if len(alive) == 1 else "Draw"
        elif len(field) <= 1:
            pilot = field[0]
            self.title = "You made it" if pilot.lives > 0 else "Out of lives"
        else:
            ranked = sorted(field, key=lambda pilot: (pilot.score, pilot.lives), reverse=True)
            tied = ranked[0].score == ranked[1].score and ranked[0].lives == ranked[1].lives
            self.title = "Draw" if tied else f"{ranked[0].name} wins"
        if self.player_count == 1:
            self.detail = f"Score {self.pilots[0].score}"
        else:
            bits = []
            for pilot in self.pilots:
                shown = pilot.score if pilot.joined else "--"
                bits.append(f"{pilot.name} {shown}")
            self.detail = "   ·   ".join(bits)
