#!/usr/bin/env python3
"""Star Pop — a motion game with MediaPipe body tracking.

By default the game finds your pose in a color image (33 body landmarks)
and lets either hand pop falling stars, using the wrists and index
fingertips. The color image comes from, in order:

  1. The Xbox 360 Kinect RGB camera, via libfreenect
  2. The Mac webcam, via OpenCV
  3. The mouse, if no camera is available

Closest-point depth tracking from the first version is still here
as --depth. Force the mouse with --mouse. Quit with Escape.

    python star_pop.py
    python star_pop.py --webcam
    python star_pop.py --depth
    python star_pop.py --mouse
    python star_pop.py --avatar robot
    python star_pop.py --avatar none
    python star_pop.py --preview-avatar avatar_preview.png
    python star_pop.py --mode meteors --players 2
    python star_pop.py --preview-meteors meteor_preview.png

In pose mode, S cycles the overlay: avatar, avatar+skeleton, skeleton, none.
The default is the astronaut avatar with no stick figure. Mouse and depth
modes have no pose, so the avatar is skipped and the cursor still pops stars.

--mode meteors adds falling rocks and per-player lives. --players 2 tracks
two bodies (P1 starts on the left). With --mouse, WASD or the arrow keys
move a second test player.

Headless test:

    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python star_pop.py --mouse --frames 30
    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python star_pop.py --synthetic --mode meteors --players 2 --frames 300
    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python star_pop.py --preview-avatar avatar_preview.png
    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python star_pop.py --preview-meteors meteor_preview.png
"""

from __future__ import annotations

import argparse
import math
import random
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pygame

import avatar
import gameplay

# Window matches the Kinect v1 color/depth size (640x480).
WIDTH, HEIGHT = gameplay.WIDTH, gameplay.HEIGHT
FPS = 30

# Depth-mode near-range gate, in millimeters.
MAX_HAND_MM = 1500
MIN_HAND_MM = 400

# Soften jumpy readings by blending toward the new position.
# Body landmarks use a slightly stronger blend to quiet avatar jitter.
CURSOR_SMOOTH = 0.35
BODY_SMOOTH = 0.28

# MediaPipe Pose landmark indices (BlazePose 33-point set).
# https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker
LEFT_WRIST, RIGHT_WRIST = 15, 16
LEFT_INDEX, RIGHT_INDEX = 19, 20
HAND_LANDMARKS = (LEFT_WRIST, RIGHT_WRIST, LEFT_INDEX, RIGHT_INDEX)

# A simple stick figure: torso, arms, hands, legs, and a neck to the nose.
POSE_BONES = [
    (11, 12),  # shoulders
    (11, 23), (12, 24), (23, 24),  # torso
    (11, 13), (13, 15),  # left arm
    (12, 14), (14, 16),  # right arm
    (15, 19), (16, 20),  # wrist to index
    (23, 25), (25, 27),  # left leg
    (24, 26), (26, 28),  # right leg
    (0, 11), (0, 12),  # nose to shoulders
]

# Official lite model, pinned to the /1/ bundle (same bytes as /latest/ when checked).
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
)
MODEL_PATH = Path(__file__).resolve().parent / "models" / "pose_landmarker_lite.task"

# Skip a landmark if MediaPipe is this unsure about it.
MIN_VISIBILITY = 0.4

# S cycles these overlays. Default is the astronaut avatar alone.
VIEW_MODES = ("avatar", "avatar+skeleton", "skeleton", "none")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Pop falling stars with your hands, a Kinect, a webcam, or the mouse."
    )
    parser.add_argument(
        "--mouse",
        action="store_true",
        help="Use the mouse and skip cameras and pose tracking.",
    )
    parser.add_argument(
        "--depth",
        action="store_true",
        help="Use closest-point Kinect depth tracking instead of pose tracking.",
    )
    parser.add_argument(
        "--webcam",
        action="store_true",
        help="Use the Mac webcam for pose tracking, even if a Kinect is plugged in.",
    )
    parser.add_argument(
        "--camera",
        type=int,
        default=0,
        metavar="INDEX",
        help="Webcam device index for OpenCV (default: 0).",
    )
    parser.add_argument(
        "--no-skeleton",
        action="store_true",
        help="Start without the stick-figure overlay (already the default view).",
    )
    parser.add_argument(
        "--avatar",
        choices=("astronaut", "robot", "none"),
        default="astronaut",
        help="Cartoon avatar drawn over the pose (default: astronaut). "
        "Use 'none' to start without an avatar.",
    )
    parser.add_argument(
        "--preview-avatar",
        nargs="?",
        const="avatar_preview.png",
        default=None,
        metavar="PATH",
        help="Draw a synthetic pose of the avatar, save a PNG, and exit.",
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=0,
        help="Exit after this many frames (useful for automated tests).",
    )
    parser.add_argument(
        "--mode",
        choices=("stars", "meteors"),
        default="stars",
        help="stars pops falling stars. meteors adds rocks to dodge (default: stars).",
    )
    parser.add_argument(
        "--players",
        type=int,
        choices=(1, 2),
        default=1,
        help="How many bodies to track. 2 uses MediaPipe num_poses=2 (default: 1).",
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Drive the game with built-in poses instead of a camera (tests and demos).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for stars and meteors (tests).",
    )
    parser.add_argument(
        "--preview-meteors",
        nargs="?",
        const="meteor_preview.png",
        default=None,
        metavar="PATH",
        help="Draw two players dodging meteors, save a PNG, and exit.",
    )
    parser.add_argument(
        "--screenshot",
        default=None,
        metavar="PATH",
        help="Save a frame to this path (use with --frames).",
    )
    parser.add_argument(
        "--screenshot-frame",
        type=int,
        default=0,
        help="Which frame --screenshot saves. 0 saves the last frame.",
    )
    return parser.parse_args(argv)


def try_import_freenect():
    try:
        import freenect
    except ImportError:
        return None
    return freenect


def try_import_cv2():
    try:
        import cv2
    except ImportError:
        return None
    return cv2


def ensure_pose_model():
    """Return the path to the lite .task model, downloading it if needed."""
    if MODEL_PATH.is_file() and MODEL_PATH.stat().st_size > 1000:
        return MODEL_PATH
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading Pose Landmarker lite model to {MODEL_PATH} ...")
    urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    return MODEL_PATH


def create_pose_landmarker(num_poses=1):
    """Build a MediaPipe Tasks PoseLandmarker in VIDEO mode (CPU).

    The current API is mp.tasks.vision.PoseLandmarker. The older
    mp.solutions.pose interface is no longer present in current
    mediapipe packages. num_poses stays 1 unless --players 2, and the
    lite model stays on the CPU so a Mac Mini can track two people.
    """
    import mediapipe as mp

    model = ensure_pose_model()
    BaseOptions = mp.tasks.BaseOptions
    PoseLandmarker = mp.tasks.vision.PoseLandmarker
    PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
    VisionRunningMode = mp.tasks.vision.RunningMode
    Delegate = getattr(BaseOptions, "Delegate", None)

    base_kwargs = {"model_asset_path": str(model)}
    # CPU is the portable, stable choice on a Mac. GPU has caused high
    # memory use on some Apple Silicon machines.
    if Delegate is not None:
        base_kwargs["delegate"] = Delegate.CPU

    options = PoseLandmarkerOptions(
        base_options=BaseOptions(**base_kwargs),
        running_mode=VisionRunningMode.VIDEO,
        num_poses=max(1, int(num_poses)),
        min_pose_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    return PoseLandmarker.create_from_options(options)


def rgb_to_mp_image(rgb):
    """Wrap a uint8 RGB frame as a MediaPipe Image."""
    import mediapipe as mp

    frame = np.ascontiguousarray(rgb, dtype=np.uint8)
    return mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)


def pose_list(result):
    """Return the list of poses from a PoseLandmarker result."""
    if result is None:
        return []
    poses = getattr(result, "pose_landmarks", None)
    if not poses:
        poses = getattr(result, "landmarks", None)
    return poses or []


def landmark_ok(lm):
    vis = getattr(lm, "visibility", None)
    pres = getattr(lm, "presence", None)
    if vis is None and pres is None:
        return True
    if vis is not None and vis >= MIN_VISIBILITY:
        return True
    if pres is not None and pres >= MIN_VISIBILITY:
        return True
    return False


def landmarks_to_points(pose, width, height):
    """Map visible landmarks to pixel coordinates and optional z values."""
    points = {}
    zmap = {}
    for index, lm in enumerate(pose):
        if not landmark_ok(lm):
            continue
        points[index] = (lm.x * width, lm.y * height)
        z = getattr(lm, "z", None)
        if z is not None:
            zmap[index] = float(z)
    return points, zmap


def open_kinect_rgb(freenect):
    """Return True if a color frame can be read from the Kinect."""
    try:
        frame = read_kinect_rgb(freenect)
        return frame is not None
    except Exception as exc:
        print(f"Could not open the Kinect color stream ({exc}).")
        return False


def read_kinect_rgb(freenect):
    fmt = getattr(freenect, "VIDEO_RGB", None)
    if fmt is not None:
        video, _timestamp = freenect.sync_get_video(format=fmt)
    else:
        video, _timestamp = freenect.sync_get_video()
    if video is None:
        return None
    return np.asarray(video)


def open_kinect_depth(freenect):
    try:
        depth = read_kinect_depth(freenect)
        return depth is not None
    except Exception as exc:
        print(f"Could not open the Kinect depth stream ({exc}).")
        return False


def read_kinect_depth(freenect):
    fmt = getattr(freenect, "DEPTH_MM", None)
    if fmt is not None:
        depth, _timestamp = freenect.sync_get_depth(format=fmt)
        return depth, True
    depth, _timestamp = freenect.sync_get_depth()
    return depth, False


def closest_hand_point(depth, millimeters=True):
    """Return (x, y) of the closest valid depth pixel, or None."""
    depth = np.asarray(depth)
    raw = not millimeters
    if raw:
        valid = (depth > 0) & (depth < 2047)
        if not np.any(valid):
            return None
        work = np.where(valid, depth, 2047)
    else:
        valid = (depth >= MIN_HAND_MM) & (depth <= MAX_HAND_MM)
        if not np.any(valid):
            return None
        work = np.where(valid, depth, np.iinfo(np.uint16).max)

    block = 8
    h, w = work.shape
    trimmed = work[: h - h % block, : w - w % block]
    blocks = trimmed.reshape(h // block, block, w // block, block).min(axis=(1, 3))
    by, bx = np.unravel_index(int(np.argmin(blocks)), blocks.shape)
    if raw and blocks[by, bx] >= 2047:
        return None
    if not raw and blocks[by, bx] > MAX_HAND_MM:
        return None
    y0, x0 = by * block, bx * block
    region = work[y0 : y0 + block, x0 : x0 + block]
    ry, rx = np.unravel_index(int(np.argmin(region)), region.shape)
    return int(x0 + rx), int(y0 + ry)


def open_webcam(cv2, index):
    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
    ok, _frame = cap.read()
    if not ok:
        cap.release()
        return None
    return cap


def read_webcam_rgb(cv2, cap):
    ok, frame = cap.read()
    if not ok or frame is None:
        return None
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)


def mirror_rgb(rgb):
    """Flip the image left-to-right so motion feels like a mirror."""
    return np.ascontiguousarray(np.fliplr(rgb))


def blit_camera(screen, rgb):
    """Draw a dimmed camera frame behind the game."""
    frame = np.ascontiguousarray(rgb, dtype=np.uint8)
    h, w = frame.shape[:2]
    surface = pygame.image.frombuffer(frame.tobytes(), (w, h), "RGB")
    if (w, h) != (WIDTH, HEIGHT):
        surface = pygame.transform.smoothscale(surface, (WIDTH, HEIGHT))
    else:
        surface = surface.convert()
    screen.blit(surface, (0, 0))
    dim = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    dim.fill((8, 12, 28, 160))
    screen.blit(dim, (0, 0))


def draw_skeleton(screen, points, color=None):
    bone = color or (160, 220, 255)
    joint = color or (220, 240, 255)
    for a, b in POSE_BONES:
        if a in points and b in points:
            pygame.draw.line(screen, bone, points[a], points[b], 3)
    for index, pos in points.items():
        radius = 6 if index in HAND_LANDMARKS else 4
        ink = (255, 220, 90) if index in HAND_LANDMARKS and color is None else joint
        pygame.draw.circle(screen, ink, (int(pos[0]), int(pos[1])), radius)


def initial_view_mode(args):
    """Pick the starting overlay from --avatar and --no-skeleton."""
    want_avatar = args.avatar != "none"
    want_skeleton = not args.no_skeleton
    if want_avatar and not want_skeleton:
        return "avatar"
    if want_avatar and want_skeleton:
        # Default is avatar-only; --no-skeleton is already the default look.
        # Showing both at start is only useful if the user asks for a skeleton
        # and an avatar. --no-skeleton is the flag that hides the stick figure,
        # so without it we still start on avatar (the requested default).
        return "avatar"
    if want_skeleton:
        return "skeleton"
    return "none"


def choose_source(args):
    """Pick an input source. Returns (mode, extras).

    mode is one of: 'synthetic', 'pose-kinect', 'pose-webcam', 'depth', 'mouse'.
    """
    if args.synthetic:
        print("Synthetic mode: built-in poses, no camera.")
        return "synthetic", {}

    if args.mouse:
        print("Mouse mode (--mouse).")
        return "mouse", {}

    if args.depth:
        freenect = try_import_freenect()
        if freenect is not None and open_kinect_depth(freenect):
            print("Depth mode: closest point in the Kinect depth image.")
            return "depth", {"freenect": freenect}
        print("Depth mode was requested, but the Kinect depth stream is not available. Using the mouse.")
        return "mouse", {}

    # Default: MediaPipe pose tracking, Kinect RGB then webcam then mouse.
    try:
        landmarker = create_pose_landmarker(num_poses=args.players)
    except Exception as exc:
        print(f"Could not start MediaPipe Pose Landmarker ({exc}).")
        print("Falling back to the mouse. See SETUP.md for install notes.")
        return "mouse", {}

    tracking = " Tracking two players." if args.players == 2 else ""
    extras = {"landmarker": landmarker}
    freenect = None if args.webcam else try_import_freenect()
    if freenect is not None and open_kinect_rgb(freenect):
        print(f"Pose mode: Kinect color camera + MediaPipe Pose Landmarker.{tracking}")
        return "pose-kinect", {**extras, "freenect": freenect}

    if not args.webcam and freenect is None:
        print("The freenect module is not installed, so the Kinect color camera is skipped.")

    cv2 = try_import_cv2()
    if cv2 is None:
        print("OpenCV is not installed, so the webcam is skipped. Using the mouse.")
        return "mouse", extras

    cap = open_webcam(cv2, args.camera)
    if cap is None:
        print(f"Could not open webcam {args.camera}. Using the mouse.")
        print("On a Mac, allow Camera access for Terminal in System Settings → Privacy & Security.")
        return "mouse", extras

    print(f"Pose mode: webcam {args.camera} + MediaPipe Pose Landmarker.{tracking}")
    return "pose-webcam", {**extras, "cv2": cv2, "cap": cap}


class ScreenText:
    """Render score and hints. pygame 2.6.x on Python 3.14 can fail to
    import pygame.font; try freetype, then skip text so the game still runs.
    """

    def __init__(self):
        self.mode = "none"
        self._font = None
        self._small = None
        self._setup()

    def _setup(self):
        if self._try_pygame_font():
            return
        if self._try_freetype():
            return
        print("On-screen text is disabled; the game is still playable.")
        print("This is a known problem with pygame 2.6.x on Python 3.14.")
        print(
            "Fix:  pip uninstall -y pygame && pip install --force-reinstall pygame-ce"
        )

    def _try_pygame_font(self) -> bool:
        try:
            if hasattr(pygame.font, "get_init") and not pygame.font.get_init():
                pygame.font.init()
            font = pygame.font.Font(None, 32)
            small = pygame.font.Font(None, 22)
            font.render("0", True, (255, 255, 255))
            self._font, self._small, self.mode = font, small, "font"
            return True
        except Exception as exc:
            print(f"pygame.font is not available ({exc}).")
            return False

    def _try_freetype(self) -> bool:
        try:
            import pygame.freetype as freetype

            if hasattr(freetype, "get_init") and not freetype.get_init():
                freetype.init()
            font = freetype.Font(None, 24)
            small = freetype.Font(None, 16)
            font.render("0", (255, 255, 255))
            self._font, self._small, self.mode = font, small, "freetype"
            print("Using pygame.freetype for on-screen text.")
            return True
        except Exception as exc:
            print(f"pygame.freetype is also unavailable ({exc}).")
            return False

    def blit(self, screen, text, pos, color, *, small=False):
        if self.mode == "none":
            return
        try:
            if self.mode == "font":
                face = self._small if small else self._font
                screen.blit(face.render(text, True, color), pos)
            elif self.mode == "freetype":
                face = self._small if small else self._font
                surface, _rect = face.render(text, color)
                if surface is not None:
                    screen.blit(surface, pos)
        except Exception:
            pass

    def size(self, text, *, small=False):
        if self.mode == "none":
            return (0, 0)
        face = self._small if small else self._font
        try:
            if self.mode == "font":
                return face.size(text)
            rect = face.get_rect(text)
            return (rect.width, rect.height)
        except Exception:
            return (0, 0)


def run_avatar_preview(args):
    """Render a synthetic astronaut/robot pose to a PNG and exit."""
    dest = Path(args.preview_avatar)
    if not dest.is_absolute():
        dest = Path(__file__).resolve().parent / dest
    pygame.init()
    try:
        pygame.display.set_mode((1, 1))
    except Exception:
        pass
    style = args.avatar if args.avatar != "none" else "astronaut"
    saved = avatar.render_preview(dest, size=(WIDTH, HEIGHT), style=style)
    print(f"Wrote avatar preview ({style}) to {saved}")
    pygame.quit()
    return 0


def styles_for(avatar_name, count):
    """P1 wears the requested suit. P2 wears the other one."""
    if count <= 1:
        return [avatar_name]
    if avatar_name == "robot":
        return ["robot", "astronaut"]
    if avatar_name == "none":
        return ["none", "none"]
    return ["astronaut", "robot"]


def load_style_sprites(styles):
    sprites = {}
    for style in styles:
        if not style or style == "none" or style in sprites:
            continue
        sprites[style] = avatar.load_sprites(style)
    return sprites


def make_starfield(count=48, seed=2):
    rng = random.Random(seed)
    specks = []
    for _ in range(count):
        specks.append(
            (
                rng.randrange(WIDTH),
                rng.randrange(HEIGHT),
                rng.choice((1, 1, 2)),
                rng.randrange(140, 220),
            )
        )
    return specks


def draw_starfield(surface, specks):
    surface.fill((8, 12, 28))
    for x, y, radius, shade in specks:
        pygame.draw.circle(surface, (shade, shade, min(255, shade + 25)), (x, y), radius)


def make_hint(source, view_mode, kind, players):
    labels = {
        "pose-kinect": "Pose · Kinect",
        "pose-webcam": "Pose · Webcam",
        "depth": "Depth",
        "mouse": "Mouse",
        "synthetic": "Synthetic",
    }
    short = {
        "pose-kinect": "Kinect",
        "pose-webcam": "Webcam",
        "depth": "Depth",
        "mouse": "Mouse",
        "synthetic": "Synthetic",
    }
    if kind == "meteors":
        hint = f"Meteors · {short.get(source, source)}  ·  Esc to quit"
    else:
        hint = f"{labels.get(source, source)}  ·  Esc to quit"
    if source in ("pose-kinect", "pose-webcam", "synthetic"):
        hint += f"  ·  S view: {view_mode}"
    if source == "mouse" and players == 2:
        hint += "  ·  WASD/arrows: P2"
    return hint


def draw_centered(screen, text, message, y, color, *, small=False):
    width, _height = text.size(message, small=small)
    x = (WIDTH - width) // 2 if width else 16
    text.blit(screen, message, (x, y), color, small=small)


def draw_pips(screen, origin, lives, color, total=gameplay.START_LIVES):
    for index in range(total):
        ink = color if index < lives else (70, 76, 96)
        center = (int(origin[0] + index * 16), int(origin[1]))
        pygame.draw.circle(screen, ink, center, 5)
        pygame.draw.circle(screen, (20, 24, 36), center, 5, 1)


def draw_hud(screen, text, match, hint, classic):
    if classic:
        text.blit(screen, f"Score  {match.total_score}", (16, 12), (255, 255, 255))
        text.blit(screen, hint, (16, 44), (160, 170, 190), small=True)
        return

    if match.kind == "meteors":
        draw_centered(screen, text, gameplay.format_clock(match.remaining), 10, (255, 228, 190))

    if match.player_count == 1:
        pilot = match.pilots[0]
        text.blit(screen, f"Score  {pilot.score}", (16, 12), (255, 255, 255))
        draw_pips(screen, (16, 46), pilot.lives, pilot.color)
        _draw_bottom_hint(screen, text, hint)
        return

    for pilot, align in zip(match.pilots, ("left", "right")):
        score = str(pilot.score) if pilot.joined else "--"
        label = f"{pilot.name}  {score}"
        if align == "left":
            x = 16
            pip_x = 16
        else:
            width, _height = text.size(label)
            x = WIDTH - 16 - width
            pip_x = WIDTH - 16 - (gameplay.START_LIVES - 1) * 16
        text.blit(screen, label, (x, 10), pilot.color)
        if pilot.joined:
            draw_pips(screen, (pip_x, 40), pilot.lives, pilot.color)
    _draw_bottom_hint(screen, text, hint)


def _draw_bottom_hint(screen, text, hint):
    bar = pygame.Surface((WIDTH, 26), pygame.SRCALPHA)
    bar.fill((6, 8, 18, 190))
    screen.blit(bar, (0, HEIGHT - 26))
    text.blit(screen, hint, (16, HEIGHT - 22), (186, 194, 210), small=True)


def draw_game_over(screen, text, match):
    shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    shade.fill((5, 8, 18, 170))
    screen.blit(shade, (0, 0))
    draw_centered(screen, text, match.title or "Round over", 168, (255, 236, 210))
    draw_centered(screen, text, match.detail, 208, (220, 226, 236))
    if match.gesture > 0.05:
        prompt = "Hold both hands up"
    else:
        prompt = "R, Space, or both hands up"
    draw_centered(screen, text, prompt, 268, (255, 196, 120), small=True)
    draw_centered(screen, text, "Esc to quit", 296, (160, 170, 190), small=True)


def draw_world(screen, text, match, camera, view_mode, sprites, hint, classic, specks, background):
    if camera is not None:
        blit_camera(screen, camera)
    elif background == "starfield":
        draw_starfield(screen, specks)
    else:
        screen.fill((8, 12, 28))

    pilots = [pilot for pilot in match.pilots if pilot.present and pilot.points]
    pilots.sort(key=lambda pilot: pilot.anchor[1] if pilot.anchor else 0)
    show_avatar = view_mode in ("avatar", "avatar+skeleton")
    show_skeleton = view_mode in ("skeleton", "avatar+skeleton")
    for pilot in pilots:
        if show_avatar and pilot.style in avatar.STYLES:
            avatar.draw_avatar(
                screen,
                pilot.points,
                style=pilot.style,
                sprites=sprites.get(pilot.style) or {},
                zmap=pilot.zmap,
            )
        if show_skeleton:
            color = None if classic else pilot.color
            draw_skeleton(screen, pilot.points, color=color)
        if pilot.invuln > 0 and pilot.anchor is not None:
            pulse = 2 + int((math.sin(match.elapsed * 22) + 1) * 1.5)
            ink = (255, 96, 72) if int(match.elapsed * 12) % 2 == 0 else (255, 255, 255)
            pygame.draw.circle(
                screen, ink, (int(pilot.anchor[0]), int(pilot.anchor[1])), 46, pulse
            )

    for meteor in match.meteors:
        meteor.draw(screen)
    for star in match.stars:
        star.draw(screen)
    for impact in match.impacts:
        impact.draw(screen)

    for pilot in match.pilots:
        if classic:
            ring, core, radius = (80, 200, 255), (180, 240, 255), 22
        else:
            ring, core, radius = pilot.color, (255, 255, 255), 16
        for cursor in pilot.cursors:
            cx, cy = int(cursor[0]), int(cursor[1])
            pygame.draw.circle(screen, ring, (cx, cy), radius, 2)
            pygame.draw.circle(screen, core, (cx, cy), 5 if not classic else 6)

    draw_hud(screen, text, match, hint, classic)
    if match.over:
        draw_game_over(screen, text, match)


def body_at(cursor, reach):
    """A full test body whose torso sits on the cursor."""
    pose = avatar.synthetic_pose(WIDTH, HEIGHT, reach=reach)
    anchor = gameplay.pose_anchor(pose) or (WIDTH / 2, HEIGHT / 2)
    return avatar.shift_points(pose, cursor[0] - anchor[0], cursor[1] - anchor[1])


def move_point(pos, keys, dt, speed=300.0):
    vx = float((keys[pygame.K_RIGHT] or keys[pygame.K_d]) - (keys[pygame.K_LEFT] or keys[pygame.K_a]))
    vy = float((keys[pygame.K_DOWN] or keys[pygame.K_s]) - (keys[pygame.K_UP] or keys[pygame.K_w]))
    if vx and vy:
        vx *= 0.7071
        vy *= 0.7071
    x = min(WIDTH - 24, max(24, pos[0] + vx * speed * dt))
    y = min(HEIGHT - 24, max(24, pos[1] + vy * speed * dt))
    return (x, y)


def synthetic_detections(frame_index, players):
    """Two built-in bodies that cross the screen, for headless play."""
    t = frame_index / float(FPS)
    if players <= 1:
        centers = [WIDTH * 0.5 + math.sin(t * 0.8) * 120]
        reaches = ["left"]
    else:
        swing = math.sin(t * 0.65) * 170
        centers = [WIDTH * 0.5 + swing, WIDTH * 0.5 - swing]
        reaches = ["left", "right"]
    detections = []
    for index, (cx, reach) in enumerate(zip(centers, reaches)):
        pose = avatar.synthetic_pose(WIDTH, HEIGHT, reach=reach)
        anchor = gameplay.pose_anchor(pose) or (WIDTH / 2, HEIGHT / 2)
        dx = cx - anchor[0]
        dy = math.sin(t * 2.0 + index) * 10
        detections.append((avatar.shift_points(pose, dx, dy), {}))
    return detections


def read_pose_detections(mode, extras, state):
    """Read one camera frame and return (rgb or None, pose detections)."""
    rgb = None
    try:
        if mode == "pose-kinect":
            rgb = read_kinect_rgb(extras["freenect"])
        elif mode == "pose-webcam":
            rgb = read_webcam_rgb(extras["cv2"], extras["cap"])
    except Exception:
        rgb = None
    if rgb is None:
        return None, []
    rgb = mirror_rgb(rgb)
    # VIDEO mode needs a strictly increasing millisecond timestamp.
    timestamp_ms = int(time.time() * 1000.0 - state["start_ms"])
    if timestamp_ms <= state["last_timestamp_ms"]:
        timestamp_ms = state["last_timestamp_ms"] + 1
    state["last_timestamp_ms"] = timestamp_ms
    try:
        result = extras["landmarker"].detect_for_video(rgb_to_mp_image(rgb), timestamp_ms)
    except Exception as exc:
        if state["frame"] == 1:
            print(f"Pose detection error: {exc}")
        return rgb, []
    height, width = rgb.shape[:2]
    detections = []
    for pose in pose_list(result):
        raw, zmap = landmarks_to_points(pose, width, height)
        if (width, height) != (WIDTH, HEIGHT):
            raw = {i: (x * WIDTH / width, y * HEIGHT / height) for i, (x, y) in raw.items()}
        detections.append((raw, zmap))
    return rgb, detections


def render_meteor_preview(path):
    """Save a still of two players, stars, meteors, and a hit flash."""
    dest = Path(path)
    if not dest.is_absolute():
        dest = Path(__file__).resolve().parent / dest
    pygame.init()
    try:
        pygame.display.set_mode((1, 1))
    except Exception:
        pass
    surface = pygame.Surface((WIDTH, HEIGHT))
    text = ScreenText()
    styles = styles_for("astronaut", 2)
    match = gameplay.Match("meteors", 2, styles, seed=4)
    left = avatar.shift_points(avatar.synthetic_pose(WIDTH, HEIGHT, reach="left"), -155, 8)
    right = avatar.shift_points(avatar.synthetic_pose(WIDTH, HEIGHT, reach="right"), 155, 4)
    match.observe_body(0, left)
    match.observe_body(1, right)
    match.pilots[0].score = 5
    match.pilots[1].score = 8
    match.pilots[0].lives = 2
    match.elapsed = gameplay.ROUND_SECONDS - 27
    match.stars.clear()
    reaching = right.get(19) or right.get(20) or (520, 70)
    star_near_hand = gameplay.Star(match.rng)
    star_near_hand.x, star_near_hand.y = reaching[0] - 8, reaching[1] - 34
    star_mid = gameplay.Star(match.rng)
    star_mid.x, star_mid.y = 248, 96
    match.stars = [star_near_hand, star_mid]
    match.meteors = []
    for x, y, radius in ((96, 210, 16), (318, 168, 18), (318, 40, 14), (575, 188, 17)):
        rock = gameplay.Meteor(match.rng, 12, x=x, y=y)
        rock.radius = radius
        match.meteors.append(rock)
    impact = gameplay.Impact(168, 292)
    impact.age = 0.16
    match.impacts = [impact]
    draw_world(
        surface,
        text,
        match,
        None,
        "avatar",
        load_style_sprites(styles),
        make_hint("pose-webcam", "avatar", "meteors", 2),
        False,
        make_starfield(),
        "starfield",
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(surface, str(dest))
    print(f"Wrote meteor preview to {dest}")
    pygame.quit()
    return 0


def release_inputs(extras):
    if extras.get("cap") is not None:
        extras["cap"].release()
    landmarker = extras.get("landmarker")
    if landmarker is not None and hasattr(landmarker, "close"):
        try:
            landmarker.close()
        except Exception:
            pass
    freenect = extras.get("freenect")
    if freenect is not None and hasattr(freenect, "sync_stop"):
        try:
            freenect.sync_stop()
        except Exception:
            pass


def main():
    args = parse_args()

    if args.preview_avatar is not None:
        return run_avatar_preview(args)
    if args.preview_meteors is not None:
        return render_meteor_preview(args.preview_meteors)

    mode, extras = choose_source(args)
    player_count = args.players
    if mode == "depth" and player_count > 1:
        print("Depth mode tracks one closest point, so this round is single-player.")
        player_count = 1

    view_mode = initial_view_mode(args)
    styles = styles_for(args.avatar, player_count)
    classic = args.mode == "stars" and player_count == 1
    match = gameplay.Match(
        args.mode,
        player_count,
        styles,
        seed=args.seed,
        sticky_cursors=classic,
        smooth=BODY_SMOOTH,
    )
    sprites = load_style_sprites(styles)
    loaded = sorted({name for group in sprites.values() for name in group})
    if loaded:
        print("Loaded avatar sprites: " + ", ".join(loaded))

    pygame.init()
    titles = {
        "pose-kinect": "Star Pop — Pose (Kinect)",
        "pose-webcam": "Star Pop — Pose (Webcam)",
        "depth": "Star Pop — Depth",
        "mouse": "Star Pop — Mouse",
        "synthetic": "Star Pop — Synthetic",
    }
    caption = "Star Pop — Meteors" if args.mode == "meteors" else titles.get(mode, "Star Pop")
    pygame.display.set_caption(caption)
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()
    text = ScreenText()
    specks = make_starfield()
    background = "starfield" if args.mode == "meteors" or mode == "synthetic" else "flat"
    smoothed_depth = {}
    p2_pos = (WIDTH * 0.73, HEIGHT * 0.56)
    pose_state = {"start_ms": time.time() * 1000.0, "last_timestamp_ms": -1, "frame": 0}
    frame = 0
    running = True
    saved_shot = False
    pose_sources = ("pose-kinect", "pose-webcam", "synthetic")

    try:
        while running:
            dt = clock.tick(FPS) / 1000.0
            if dt <= 0:
                dt = 1.0 / FPS
            dt = min(dt, 0.05)
            frame += 1
            pose_state["frame"] = frame
            restart_key = False

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_s and mode in pose_sources:
                        view_mode = VIEW_MODES[(VIEW_MODES.index(view_mode) + 1) % len(VIEW_MODES)]
                    elif event.key in (pygame.K_r, pygame.K_SPACE) and match.over:
                        restart_key = True

            camera = None
            if mode == "synthetic":
                match.observe_poses(synthetic_detections(frame, player_count), dt)
            elif mode == "mouse":
                pointer = pygame.mouse.get_pos()
                if player_count >= 2:
                    p2_pos = move_point(p2_pos, pygame.key.get_pressed(), dt)
                if args.mode == "meteors":
                    match.observe_body(0, body_at(pointer, "left"))
                    if player_count >= 2:
                        match.observe_body(1, body_at(p2_pos, "right"))
                else:
                    match.observe_cursors(0, [pointer])
                    if player_count >= 2:
                        match.observe_cursors(1, [p2_pos])
            elif mode == "depth":
                try:
                    depth, millimeters = read_kinect_depth(extras["freenect"])
                except Exception:
                    depth, millimeters = None, True
                point = closest_hand_point(depth, millimeters=millimeters) if depth is not None else None
                if point is not None:
                    smoothed_depth = gameplay.smooth_points(
                        smoothed_depth, {"depth": point}, CURSOR_SMOOTH
                    )
                    point = smoothed_depth["depth"]
                    hit_radius = 36 if args.mode == "meteors" else 0
                    match.observe_cursors(0, [point], hit_radius=hit_radius)
                else:
                    match.observe_cursors(0, None)
            else:
                camera, detections = read_pose_detections(mode, extras, pose_state)
                match.observe_poses(detections, dt)

            raised = any(
                gameplay.both_hands_raised(pilot.points)
                for pilot in match.pilots
                if pilot.present
            )
            if restart_key and match.over:
                match.restart()
            else:
                match.note_gesture(raised, dt)
            match.step(dt)

            hint = make_hint(mode, view_mode, args.mode, player_count)
            draw_world(
                screen, text, match, camera, view_mode, sprites, hint, classic, specks, background
            )
            pygame.display.flip()

            if args.screenshot and args.screenshot_frame and frame == args.screenshot_frame:
                pygame.image.save(screen, args.screenshot)
                saved_shot = True
            if args.frames and frame >= args.frames:
                running = False
    finally:
        if args.screenshot and not saved_shot:
            try:
                pygame.image.save(screen, args.screenshot)
            except Exception:
                pass
        release_inputs(extras)
        pygame.quit()

    print(f"Done. Frames: {frame}. Score: {match.total_score}. Mode: {mode}.")
    if player_count > 1 or args.mode == "meteors":
        summary = "  ".join(
            f"{pilot.name} score {pilot.score} lives {pilot.lives}" for pilot in match.pilots
        )
        print(summary)
        if match.over:
            print(match.title)
    return 0


if __name__ == "__main__":
    sys.exit(main())
