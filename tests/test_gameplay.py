"""Rules for two-player meteor dodge, plus a headless game run.

The display tests use SDL's dummy driver. Pose identity and hits are
checked without a camera.
"""

from __future__ import annotations

import math
import os
import subprocess
import sys
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import avatar  # noqa: E402
import gameplay  # noqa: E402
import star_pop  # noqa: E402


def pose_at(x, shoulder=80, y=220):
    half = shoulder / 2
    points = {
        23: (x - 20, y),
        24: (x + 20, y),
        11: (x - half, y - 80),
        12: (x + half, y - 80),
        0: (x, y - 140),
    }
    return points, {}


class IdentityTests(unittest.TestCase):
    def test_left_and_right_are_p1_and_p2_regardless_of_order(self):
        tracker = gameplay.PoseTracker(2)
        tracks = tracker.update([pose_at(420), pose_at(140)], dt=1)
        by_slot = {track.slot: track.anchor[0] for track in tracks}
        self.assertLess(by_slot[0], by_slot[1])
        self.assertAlmostEqual(by_slot[0], 140)
        self.assertAlmostEqual(by_slot[1], 420)

    def test_person_alone_on_the_right_starts_as_p2(self):
        tracker = gameplay.PoseTracker(2)
        tracks = tracker.update([pose_at(500)], dt=1)
        self.assertEqual([track.slot for track in tracks], [1])
        tracks = tracker.update([pose_at(120), pose_at(500)], dt=1)
        by_slot = {track.slot: track.anchor[0] for track in tracks}
        self.assertAlmostEqual(by_slot[0], 120)
        self.assertAlmostEqual(by_slot[1], 500)

    def test_identities_hold_when_two_people_cross(self):
        tracker = gameplay.PoseTracker(2, smooth=1)
        first_slot = None
        for step in range(80):
            ax = 240 + math.sin(step / 12) * 150
            bx = 240 + math.sin(step / 12 + math.pi) * 150
            dets = [pose_at(ax, shoulder=70), pose_at(bx, shoulder=110)]
            if step % 2:
                dets = list(reversed(dets))
            tracks = tracker.update(dets, dt=1)
            wide = [track for track in tracks if track.signature and track.signature > 90]
            self.assertEqual(len(wide), 1, step)
            if first_slot is None:
                first_slot = wide[0].slot
            else:
                self.assertEqual(wide[0].slot, first_slot, step)

    def test_equal_size_cross_does_not_jump_slots(self):
        tracker = gameplay.PoseTracker(2, smooth=1)
        previous = {}
        for step in range(70):
            ax = 90 + step * 6
            bx = 520 - step * 6
            dets = [pose_at(bx), pose_at(ax)]
            tracks = tracker.update(dets, dt=1)
            current = {track.slot: track.anchor[0] for track in tracks}
            for slot, x in current.items():
                if slot in previous:
                    self.assertLess(abs(x - previous[slot]), 30, (step, slot, previous, current))
            previous = current
        self.assertGreater(previous[0], previous[1])

    def test_a_brief_loss_does_not_give_the_slot_away(self):
        tracker = gameplay.PoseTracker(2, smooth=1)
        tracker.update([pose_at(100), pose_at(400)], dt=1)
        for _ in range(8):
            tracker.update([pose_at(406)], dt=1)
        tracks = tracker.update([pose_at(110), pose_at(404)], dt=1)
        by_slot = {track.slot: track.anchor[0] for track in tracks}
        self.assertAlmostEqual(by_slot[0], 110, delta=2)
        self.assertAlmostEqual(by_slot[1], 404, delta=2)


class RoundTests(unittest.TestCase):
    def setUp(self):
        self.points = avatar.synthetic_pose()

    def test_classic_center_cursor_pops_one_star(self):
        match = gameplay.Match("stars", 1, ["astronaut"], seed=1, sticky_cursors=True)
        star = gameplay.Star(match.rng)
        star.x, star.y = match.pilots[0].cursors[0]
        star.speed = 0
        match.stars = [star]
        match.step(1 / 30)
        self.assertEqual(match.total_score, 1)
        self.assertEqual(len(match.stars), gameplay.STAR_COUNT)
        self.assertFalse(match.over)

    def test_star_goes_to_the_player_whose_hand_is_closer(self):
        match = gameplay.Match("stars", 2, ["astronaut", "robot"], seed=2)
        left = avatar.shift_points(self.points, -160, 0)
        right = avatar.shift_points(avatar.synthetic_pose(reach="right"), 160, 0)
        match.observe_body(0, left)
        match.observe_body(1, right)
        star = gameplay.Star(match.rng)
        hand = right[19]
        star.x, star.y = hand
        star.speed = 0
        match.stars = [star]
        match.step(1 / 30)
        self.assertEqual(match.pilots[0].score, 0)
        self.assertEqual(match.pilots[1].score, 1)

    def test_meteor_hits_the_torso_and_not_empty_space(self):
        match = self._meteor_match()
        match.observe_body(0, self.points)
        anchor = gameplay.pose_anchor(self.points)
        self._drop(match, anchor[0], anchor[1])
        match.step(1 / 30)
        self.assertEqual(match.pilots[0].lives, gameplay.START_LIVES - 1)
        self.assertTrue(match.impacts)
        # Still invulnerable, so a second rock in the same place does nothing.
        self._drop(match, anchor[0], anchor[1])
        match.step(1 / 30)
        self.assertEqual(match.pilots[0].lives, gameplay.START_LIVES - 1)

        safe = gameplay.Match("meteors", 1, ["astronaut"], seed=5)
        safe.observe_body(0, self.points)
        safe.elapsed = 2
        safe.spawn_timer = 100
        self._drop(safe, 8, 8)
        safe.step(1 / 30)
        self.assertEqual(safe.pilots[0].lives, gameplay.START_LIVES)

    def test_hand_and_head_count_as_body(self):
        regions = avatar.hit_regions(self.points)
        nose = self.points[0]
        hand = self.points[15]
        self.assertTrue(avatar.region_hit(regions, nose[0], nose[1], 4))
        self.assertTrue(avatar.region_hit(regions, hand[0], hand[1], 4))
        self.assertFalse(avatar.region_hit(regions, 4, 4, 4))

    def test_last_player_standing_wins_even_with_a_lower_score(self):
        match = gameplay.Match("meteors", 2, ["astronaut", "robot"], seed=6)
        match.observe_body(0, avatar.shift_points(self.points, -180, 0))
        match.observe_body(1, avatar.shift_points(self.points, 180, 0))
        match.pilots[0].score = 9
        match.pilots[1].score = 1
        match.pilots[0].lives = 1
        match.elapsed = 2
        match.spawn_timer = 100
        anchor = match.pilots[0].anchor
        self._drop(match, anchor[0], anchor[1])
        match.step(1 / 30)
        self.assertTrue(match.over)
        self.assertEqual(match.reason, "last")
        self.assertEqual(match.title, "P2 wins")

    def test_timer_uses_score_then_lives(self):
        match = gameplay.Match("meteors", 2, ["astronaut", "robot"], seed=7)
        match.observe_body(0, self.points)
        match.observe_body(1, avatar.shift_points(self.points, 200, 0))
        match.pilots[0].score = 4
        match.pilots[1].score = 4
        match.pilots[1].lives = 1
        match.elapsed = gameplay.ROUND_SECONDS - 0.01
        match.spawn_timer = 100
        match.meteors.clear()
        match.step(0.02)
        self.assertEqual(match.reason, "time")
        self.assertEqual(match.title, "P1 wins")

    def test_solo_round_can_be_survived_or_lost(self):
        survived = self._meteor_match()
        survived.observe_body(0, self.points)
        survived.elapsed = gameplay.ROUND_SECONDS - 0.01
        survived.step(0.02)
        self.assertEqual(survived.title, "You made it")

        lost = self._meteor_match()
        lost.observe_body(0, self.points)
        lost.pilots[0].lives = 1
        anchor = lost.pilots[0].anchor
        self._drop(lost, anchor[0], anchor[1])
        lost.step(1 / 30)
        self.assertEqual(lost.title, "Out of lives")

    def test_raised_hands_restart_once_until_they_drop(self):
        match = self._meteor_match()
        match.observe_body(0, self.points)
        match.pilots[0].score = 3
        match.finish("lives")
        self.assertFalse(match.note_gesture(True, 0.2))
        self.assertTrue(match.over)
        self.assertTrue(match.note_gesture(True, 0.4))
        self.assertFalse(match.over)
        self.assertEqual(match.pilots[0].score, 0)
        self.assertEqual(match.pilots[0].lives, gameplay.START_LIVES)
        # Still holding both hands must not skip the next round.
        self.assertFalse(match.note_gesture(True, 1.0))
        match.finish("time")
        self.assertFalse(match.note_gesture(True, 1.0))
        match.note_gesture(False, 0.1)
        self.assertTrue(match.over)
        self.assertTrue(match.note_gesture(True, 0.5))
        self.assertFalse(match.over)

    def test_both_hands_raised_needs_wrists_above_shoulders(self):
        self.assertFalse(gameplay.both_hands_raised(self.points))
        raised = dict(self.points)
        raised[15] = (raised[11][0], raised[11][1] - 80)
        raised[16] = (raised[12][0], raised[12][1] - 80)
        self.assertTrue(gameplay.both_hands_raised(raised))

    def test_synthetic_round_runs_hundreds_of_frames_without_swapping(self):
        match = gameplay.Match(
            "meteors", 2, ["astronaut", "robot"], seed=3, smooth=1
        )
        previous = {}
        for frame in range(1, 301):
            match.observe_poses(star_pop.synthetic_detections(frame, 2), 1 / 30)
            current = {
                pilot.slot: pilot.anchor[0]
                for pilot in match.pilots
                if pilot.present and pilot.anchor is not None
            }
            self.assertEqual(set(current), {0, 1})
            for slot, x in current.items():
                if slot in previous:
                    self.assertLess(abs(x - previous[slot]), 40, (frame, slot))
            previous = current
            match.step(1 / 30)
        self.assertTrue(match.pilots[0].joined and match.pilots[1].joined)
        self.assertGreater(len(match.meteors) + match.pilots[0].score + match.pilots[1].score, 0)

    def _meteor_match(self):
        match = gameplay.Match("meteors", 1, ["astronaut"], seed=4)
        match.elapsed = 2
        match.spawn_timer = 100
        return match

    def _drop(self, match, x, y):
        rock = gameplay.Meteor(match.rng, match.elapsed, x=x, y=y)
        rock.speed = 0
        rock.vx = 0
        rock.radius = 16
        match.meteors.append(rock)


class ShellTests(unittest.TestCase):
    def test_defaults_stay_one_player_stars(self):
        args = star_pop.parse_args([])
        self.assertEqual(args.mode, "stars")
        self.assertEqual(args.players, 1)
        self.assertFalse(args.synthetic)
        self.assertEqual(
            star_pop.make_hint("pose-webcam", "avatar", "stars", 1),
            "Pose · Webcam  ·  Esc to quit  ·  S view: avatar",
        )
        self.assertEqual(
            star_pop.make_hint("mouse", "avatar", "stars", 1),
            "Mouse  ·  Esc to quit",
        )

    def test_headless_mouse_stars_and_two_player_meteors(self):
        mouse = self._run(
            ["--mouse", "--frames", "40", "--seed", "1"]
        )
        self.assertEqual(mouse.returncode, 0, mouse.stderr)
        self.assertIn("Done. Frames: 40. Score:", mouse.stdout)
        self.assertIn("Mode: mouse.", mouse.stdout)

        shot = ROOT / "tests" / "_meteor_frame.png"
        if shot.exists():
            shot.unlink()
        meteors = self._run(
            [
                "--synthetic",
                "--mode",
                "meteors",
                "--players",
                "2",
                "--frames",
                "300",
                "--seed",
                "3",
                "--screenshot",
                str(shot),
                "--screenshot-frame",
                "20",
            ]
        )
        self.assertEqual(meteors.returncode, 0, meteors.stderr)
        self.assertIn("Done. Frames: 300. Score:", meteors.stdout)
        self.assertIn("Mode: synthetic.", meteors.stdout)
        self.assertIn("P1 score", meteors.stdout)
        self.assertIn("P2 score", meteors.stdout)
        self._assert_frame_has_two_suits(shot)
        shot.unlink()

    def test_preview_png_is_a_real_picture(self):
        dest = ROOT / "meteor_preview.png"
        if dest.exists():
            dest.unlink()
        result = self._run(["--preview-meteors", str(dest)])
        self.assertEqual(result.returncode, 0, result.stderr)
        self._assert_frame_has_two_suits(dest)
        self.assertGreater(dest.stat().st_size, 3000)

    def _run(self, args):
        env = os.environ.copy()
        env["SDL_VIDEODRIVER"] = "dummy"
        env["SDL_AUDIODRIVER"] = "dummy"
        return subprocess.run(
            [sys.executable, str(ROOT / "star_pop.py"), *args],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def _assert_frame_has_two_suits(self, path):
        self.assertTrue(path.is_file(), path)
        import pygame

        pygame.init()
        image = pygame.image.load(str(path))
        self.assertEqual(image.get_size(), (640, 480))
        white = robot = orange = 0
        for y in range(0, 480, 2):
            for x in range(0, 640, 2):
                r, g, b, *_rest = image.get_at((x, y))
                if r > 220 and g > 220 and b > 220:
                    white += 1
                if 50 < r < 140 and 90 < g < 190 and b > 130:
                    robot += 1
                if r > 200 and 70 < g < 190 and b < 90:
                    orange += 1
        pygame.quit()
        self.assertGreater(white, 30, "astronaut suit pixels")
        self.assertGreater(robot, 30, "robot suit pixels")
        self.assertGreater(orange, 5, "meteor pixels")


if __name__ == "__main__":
    unittest.main()
