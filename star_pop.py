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

In pose mode, S cycles the overlay: avatar, avatar+skeleton, skeleton, none.
The default is the astronaut avatar with no stick figure. Mouse and depth
modes have no pose, so the avatar is skipped and the cursor still pops stars.

Headless test:

    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python star_pop.py --mouse --frames 30
    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python star_pop.py --preview-avatar avatar_preview.png
"""

from __future__ import annotations

import argparse
import random
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pygame

import avatar

# Window matches the Kinect v1 color/depth size (640x480).
WIDTH, HEIGHT = 640, 480
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


def parse_args():
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
    return parser.parse_args()


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


def create_pose_landmarker():
    """Build a MediaPipe Tasks PoseLandmarker in VIDEO mode (CPU).

    The current API is mp.tasks.vision.PoseLandmarker. The older
    mp.solutions.pose interface is no longer present in current
    mediapipe packages.
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
        num_poses=1,
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


def draw_skeleton(screen, points):
    for a, b in POSE_BONES:
        if a in points and b in points:
            pygame.draw.line(screen, (160, 220, 255), points[a], points[b], 3)
    for index, pos in points.items():
        radius = 6 if index in HAND_LANDMARKS else 4
        color = (255, 220, 90) if index in HAND_LANDMARKS else (220, 240, 255)
        pygame.draw.circle(screen, color, (int(pos[0]), int(pos[1])), radius)


class Star:
    def __init__(self):
        self.x = random.uniform(30, WIDTH - 30)
        self.y = random.uniform(-80, -10)
        self.speed = random.uniform(80, 180)
        self.radius = random.randint(12, 20)
        self.color = random.choice(
            [(255, 214, 90), (255, 245, 200), (255, 170, 80), (200, 220, 255)]
        )

    def update(self, dt):
        self.y += self.speed * dt

    def offscreen(self):
        return self.y - self.radius > HEIGHT

    def hit(self, cursors, reach=28):
        for cursor in cursors:
            dx = self.x - cursor[0]
            dy = self.y - cursor[1]
            if dx * dx + dy * dy <= (self.radius + reach) ** 2:
                return True
        return False

    def draw(self, surface):
        pygame.draw.circle(surface, self.color, (int(self.x), int(self.y)), self.radius)
        pygame.draw.circle(
            surface, (255, 255, 255), (int(self.x), int(self.y)), max(3, self.radius // 3)
        )
        r = self.radius + 4
        cx, cy = int(self.x), int(self.y)
        pygame.draw.line(surface, (255, 255, 255), (cx, cy - r), (cx, cy + r), 1)
        pygame.draw.line(surface, (255, 255, 255), (cx - r, cy), (cx + r, cy), 1)


def smooth_points(previous, current, alpha=CURSOR_SMOOTH):
    """Exponential smoothing: out = prev + (new - prev) * alpha."""
    out = {}
    for key, pos in current.items():
        if key in previous:
            px, py = previous[key]
            out[key] = (px + (pos[0] - px) * alpha, py + (pos[1] - py) * alpha)
        else:
            out[key] = pos
    return out


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

    mode is one of: 'pose-kinect', 'pose-webcam', 'depth', 'mouse'.
    """
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
        landmarker = create_pose_landmarker()
    except Exception as exc:
        print(f"Could not start MediaPipe Pose Landmarker ({exc}).")
        print("Falling back to the mouse. See SETUP.md for install notes.")
        return "mouse", {}

    extras = {"landmarker": landmarker}
    freenect = None if args.webcam else try_import_freenect()
    if freenect is not None and open_kinect_rgb(freenect):
        print("Pose mode: Kinect color camera + MediaPipe Pose Landmarker.")
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

    print(f"Pose mode: webcam {args.camera} + MediaPipe Pose Landmarker.")
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


def main():
    args = parse_args()

    if args.preview_avatar is not None:
        return run_avatar_preview(args)

    mode, extras = choose_source(args)
    view_mode = initial_view_mode(args)
    avatar_style = args.avatar if args.avatar != "none" else "astronaut"
    avatar_sprites = {}

    pygame.init()
    titles = {
        "pose-kinect": "Star Pop — Pose (Kinect)",
        "pose-webcam": "Star Pop — Pose (Webcam)",
        "depth": "Star Pop — Depth",
        "mouse": "Star Pop — Mouse",
    }
    pygame.display.set_caption(titles.get(mode, "Star Pop"))
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()
    text = ScreenText()
    if args.avatar != "none":
        avatar_sprites = avatar.load_sprites(avatar_style)
        if avatar_sprites:
            print("Loaded avatar sprites: " + ", ".join(sorted(avatar_sprites)))

    stars = [Star() for _ in range(6)]
    score = 0
    cursors = [(WIDTH // 2, HEIGHT // 2)]
    smoothed = {}
    pose_points = {}
    extras.setdefault("pose_z", {})
    camera_frame = None
    start_ms = time.time() * 1000.0
    last_timestamp_ms = -1
    frame = 0
    running = True

    labels = {
        "pose-kinect": "Pose · Kinect",
        "pose-webcam": "Pose · Webcam",
        "depth": "Depth",
        "mouse": "Mouse",
    }

    while running:
        dt = clock.tick(FPS) / 1000.0
        frame += 1

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_s:
                    view_mode = VIEW_MODES[(VIEW_MODES.index(view_mode) + 1) % len(VIEW_MODES)]

        camera_frame = None
        pose_points = {}

        if mode == "mouse":
            cursors = [pygame.mouse.get_pos()]
        elif mode == "depth":
            try:
                depth, millimeters = read_kinect_depth(extras["freenect"])
            except Exception:
                depth, millimeters = None, True
            point = closest_hand_point(depth, millimeters=millimeters) if depth is not None else None
            if point is not None:
                smoothed = smooth_points(smoothed, {"depth": point})
                cursors = [smoothed["depth"]]
        else:
            rgb = None
            try:
                if mode == "pose-kinect":
                    rgb = read_kinect_rgb(extras["freenect"])
                elif mode == "pose-webcam":
                    rgb = read_webcam_rgb(extras["cv2"], extras["cap"])
            except Exception:
                rgb = None
            if rgb is not None:
                rgb = mirror_rgb(rgb)
                camera_frame = rgb
                # VIDEO mode needs a strictly increasing millisecond timestamp.
                timestamp_ms = int(time.time() * 1000.0 - start_ms)
                if timestamp_ms <= last_timestamp_ms:
                    timestamp_ms = last_timestamp_ms + 1
                last_timestamp_ms = timestamp_ms
                try:
                    result = extras["landmarker"].detect_for_video(
                        rgb_to_mp_image(rgb), timestamp_ms
                    )
                except Exception as exc:
                    result = None
                    if frame == 1:
                        print(f"Pose detection error: {exc}")
                poses = pose_list(result)
                if poses:
                    h, w = rgb.shape[:2]
                    raw_points, pose_z = landmarks_to_points(poses[0], w, h)
                    # Scale from the camera frame onto the game window.
                    if (w, h) != (WIDTH, HEIGHT):
                        raw_points = {
                            i: (x * WIDTH / w, y * HEIGHT / h) for i, (x, y) in raw_points.items()
                        }
                    pose_points = smooth_points(smoothed, raw_points, alpha=BODY_SMOOTH)
                    smoothed = pose_points
                    extras["pose_z"] = pose_z
                    hands = {
                        i: pose_points[i] for i in HAND_LANDMARKS if i in pose_points
                    }
                    if hands:
                        cursors = list(hands.values())

        for star in stars:
            star.update(dt)
        popped = [star for star in stars if star.hit(cursors)]
        score += len(popped)
        stars = [star for star in stars if star not in popped and not star.offscreen()]
        while len(stars) < 6:
            stars.append(Star())

        if camera_frame is not None:
            blit_camera(screen, camera_frame)
        else:
            screen.fill((8, 12, 28))

        if pose_points:
            if view_mode in ("avatar", "avatar+skeleton") and args.avatar != "none":
                avatar.draw_avatar(
                    screen,
                    pose_points,
                    style=avatar_style,
                    sprites=avatar_sprites,
                    zmap=extras.get("pose_z") or {},
                )
            if view_mode in ("skeleton", "avatar+skeleton"):
                draw_skeleton(screen, pose_points)

        for star in stars:
            star.draw(screen)

        for cursor in cursors:
            cx, cy = int(cursor[0]), int(cursor[1])
            pygame.draw.circle(screen, (80, 200, 255), (cx, cy), 22, 2)
            pygame.draw.circle(screen, (180, 240, 255), (cx, cy), 6)

        hint = labels.get(mode, mode) + "  ·  Esc to quit"
        if mode.startswith("pose"):
            hint += f"  ·  S view: {view_mode}"
        text.blit(screen, f"Score  {score}", (16, 12), (255, 255, 255))
        text.blit(screen, hint, (16, 44), (160, 170, 190), small=True)

        pygame.display.flip()

        if args.frames and frame >= args.frames:
            running = False

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

    pygame.quit()
    print(f"Done. Frames: {frame}. Score: {score}. Mode: {mode}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
