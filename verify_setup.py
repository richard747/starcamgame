#!/usr/bin/env python3
"""Check that Star Pop's Python dependencies import and the pose model loads.

Used by setup.sh at the end of install, and by itself:

    .venv/bin/python verify_setup.py
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
failures = 0
notes: list[str] = []

# So PASS/FAIL lines are not delayed behind MediaPipe's stderr logs.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)


def report(name: str, ok: bool, detail: str = "") -> None:
    global failures
    if ok:
        suffix = f"  ({detail})" if detail else ""
        print(f"PASS  {name}{suffix}")
    else:
        failures += 1
        suffix = f": {detail}" if detail else ""
        print(f"FAIL  {name}{suffix}")


def check(name: str, fn) -> None:
    try:
        detail = fn() or ""
        report(name, True, detail)
    except Exception as exc:
        report(name, False, str(exc))
        # Keep the last line of the traceback for awkward load errors.
        if not isinstance(exc, (ImportError, ModuleNotFoundError)):
            tb = traceback.format_exc().strip().splitlines()
            if tb:
                print(f"      {tb[-1]}")


def check_pygame() -> str:
    import pygame

    name = "pygame"
    # pygame-ce still imports as pygame; expose which fork is installed.
    ver = getattr(pygame, "version", None)
    ver_str = getattr(ver, "ver", getattr(pygame, "__version__", "unknown"))
    pkg = getattr(ver, "rev", "") or ""
    return f"{name} {ver_str}"


def check_pygame_font() -> str:
    import pygame

    if hasattr(pygame, "init"):
        # Display is not required, but some SDL builds want a video driver.
        try:
            pygame.font.init()
        except Exception:
            if hasattr(pygame, "init"):
                pygame.init()
            pygame.font.init()
    font = pygame.font.Font(None, 32)
    surface = font.render("Score  0", True, (255, 255, 255))
    width, height = surface.get_size()
    if width < 1 or height < 1:
        raise RuntimeError("Font(None, 32) rendered an empty surface")
    return f"Font(None, 32) rendered {width}x{height}"


def check_numpy() -> str:
    import numpy as np

    return f"numpy {np.__version__}"


def check_cv2() -> str:
    import cv2

    return f"OpenCV {cv2.__version__}"


def check_mediapipe() -> str:
    import mediapipe as mp

    if not hasattr(mp, "tasks") or not hasattr(mp.tasks, "vision"):
        raise RuntimeError("mediapipe.tasks.vision is missing")
    if not hasattr(mp.tasks.vision, "PoseLandmarker"):
        raise RuntimeError(
            "mp.tasks.vision.PoseLandmarker is missing. "
            "This project needs the current Tasks API, not the old mp.solutions.pose."
        )
    return f"mediapipe {getattr(mp, '__version__', 'unknown')}"


def check_model() -> str:
    path = ROOT / "models" / "pose_landmarker_lite.task"
    if not path.is_file() or path.stat().st_size < 1000:
        raise RuntimeError(f"model file missing or too small: {path}")
    return f"{path.name}, {path.stat().st_size} bytes"


def check_landmarker() -> str:
    import numpy as np

    from star_pop import create_pose_landmarker, rgb_to_mp_image

    landmarker = create_pose_landmarker()
    try:
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        landmarker.detect_for_video(rgb_to_mp_image(frame), 0)
    finally:
        if hasattr(landmarker, "close"):
            landmarker.close()
    return "PoseLandmarker loaded and ran on a dummy frame"


def check_freenect() -> str:
    try:
        import freenect
    except Exception as exc:
        message = str(exc)
        if "Library not loaded" in message or "image not found" in message or "libfreenect" in message:
            notes.append(
                "freenect loaded the Python module but could not find libfreenect. "
                "Try:  export DYLD_LIBRARY_PATH=\"$(brew --prefix)/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}\""
            )
        raise
    bits = ["module imported"]
    if hasattr(freenect, "sync_get_depth"):
        bits.append("sync_get_depth")
    if hasattr(freenect, "sync_get_video"):
        bits.append("sync_get_video")
    return ", ".join(bits)


def main() -> int:
    print("Star Pop setup check")
    print(f"Python {sys.version.split()[0]}  ({sys.executable})")
    check("pygame", check_pygame)
    check("pygame.font", check_pygame_font)
    check("numpy", check_numpy)
    check("cv2", check_cv2)
    check("mediapipe", check_mediapipe)
    check("pose model", check_model)
    check("PoseLandmarker", check_landmarker)
    check("freenect", check_freenect)

    for note in notes:
        print(f"Note: {note}")

    if failures:
        print(f"\n{failures} check(s) failed.")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
