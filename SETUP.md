# Ridgeford Star Pop — Mac setup

Star Pop is a small motion game for a Mac. In the default mode it uses
Google MediaPipe Pose to track 33 body landmarks and lets you pop
falling stars with either hand. The color image comes from, in order:

1. The Xbox 360 Kinect (Kinect v1) color camera, through libfreenect
2. The Mac’s built-in or USB webcam, through OpenCV
3. The mouse, if no camera is available

The older closest-point depth mode is still available with `--depth`.
You can also force the mouse with `--mouse`, or skip the Kinect and use
the webcam with `--webcam`.

This Kinect support is for the original Xbox 360 Kinect only. The newer
Xbox One / Kinect v2 sensor needs a different library (libfreenect2),
and this project does not use it. Pose tracking on a webcam does not
need a Kinect at all.

## Quick start

From this folder in Terminal:

```bash
./setup.sh
./run.sh
```

`setup.sh` is the one-step installer. It is safe to run more than once.
It checks that you are on Apple Silicon with a native arm64 Python 3.9
through 3.14 (and warns clearly if you are not), installs Homebrew if
you agree, installs libfreenect and the build tools, creates the
virtualenv, installs the Python packages, builds the official `freenect`
module into that virtualenv, downloads the Pose model if it is missing,
and verifies each import. If an earlier run failed while building the
wrapper (for example with `No module named 'distutils'`), just run
`./setup.sh` again. It clears the stale build and uses a Python 3.12+
compatible compile path.

`./run.sh` turns on the virtualenv and starts the game. You can pass the
same flags as `star_pop.py`:

```bash
./run.sh
./run.sh --mouse
./run.sh --webcam
./run.sh --depth
./run.sh --avatar robot
./run.sh --avatar none
./run.sh --no-skeleton
```

To run only the checks later:

```bash
./setup.sh --verify-only
```

If the files are not already executable, run `chmod +x setup.sh run.sh`
once. The rest of this file is the same setup, step by step, if you
prefer to do it yourself or need to debug a failed step.

## Parts you need

For Kinect play:

1. An Xbox 360 Kinect sensor (Kinect v1).
2. A **Kinect USB power adapter**. The cable that came with the Xbox 360
   console uses a proprietary plug, so it will not go straight into a Mac.
   The adapter is a short brick and cable that splits that plug into a
   standard USB-A data plug and a wall-power plug. Search for “Xbox 360
   Kinect USB adapter” or “Kinect sensor power supply.” They are usually
   about $10–15.
3. On a Mac with only USB-C ports, a USB-C to USB-A adapter or hub that
   can run at USB 2.0 High Speed (480 Mbps). Some cheap adapters only
   negotiate Full Speed (12 Mbps). That is enough for the Kinect’s motor,
   but the camera will never appear. A known-good USB-C to USB-A dongle
   (for example an Anker one) or a decent powered hub is the usual fix.
   Plug the Kinect into the Mac or that adapter; avoid a poorly powered
   or very cheap hub if you can.

Plug the adapter into wall power, connect USB to the Mac, then go on to
the software steps.

For webcam-only play, you just need a Mac with a camera. You can skip
the libfreenect sections below. The setup script still installs
libfreenect; that is harmless if you only use the webcam or the mouse.

## Manual setup

Use these steps if you prefer not to run `./setup.sh`, or if the script
stopped and you want to finish by hand.

## 1. Install Homebrew

If you do not already have Homebrew, paste this into Terminal:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Follow the on-screen steps. On Apple Silicon Macs, Homebrew lives in
`/opt/homebrew`. The installer will tell you if you need to add that to
your PATH.

## 2. Install libfreenect (needed only for the Kinect)

[libfreenect](https://github.com/OpenKinect/libfreenect) is the open-source
driver for the Xbox 360 Kinect. The current Homebrew package includes the
library and the test tools (`freenect-glview` and others). As of this
writing, the stable formula is 0.7.5, and Homebrew publishes official
bottles for both Apple Silicon and Intel Macs.

```bash
brew install libfreenect cmake
```

`cmake` is needed later to build the Python module. Homebrew does **not**
install that module for you.

## 3. Test the sensor (Kinect only)

With the Kinect powered and plugged in, run:

```bash
freenect-glview
```

You should get a window with a live color image and a depth image. Press
Escape or close the window to quit.

If it says no devices were found, or only the motor works:

- Confirm the power adapter’s wall plug is in, not just the USB cable.
- Open **System Information → USB** (Apple menu → About This Mac →
  System Report → USB). You want the Xbox NUI Camera to show up at
  **High Speed (480 Mbps)**. If the device is stuck at 12 Mbps, or you
  only see the “Xbox NUI Motor,” try a different USB-C adapter or hub.
  This has shown up on some M-series Macs with certain dongles.
- Unplug the Kinect, wait a few seconds, and plug it back in.
- This project does not need audio firmware. Some older Kinect models
  need extra firmware for the motor or LED; depth and color usually
  still work without it.

## 4. Create a Python 3 virtualenv

Use a native (non-Rosetta) Python 3 so it matches Homebrew’s libraries
and MediaPipe’s Apple Silicon wheel. Homebrew’s `python3` is a solid
choice. MediaPipe’s current Python package supports Python 3.9 through
3.14.

From this project folder:

```bash
cd /path/to/kinect-game
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

That installs pygame-ce (imported as pygame), NumPy, MediaPipe, and OpenCV. Official pygame 2.6.x is not used; its font module is broken on Python 3.14. Stay in this
virtualenv for the rest of the setup (`which python` should point inside
`.venv`).

## 5. MediaPipe Pose

The game uses Google’s current **Tasks** API,
`mp.tasks.vision.PoseLandmarker`, not the older
`mp.solutions.pose` interface. Google ended support for the legacy
Solutions APIs on March 1, 2023, and `mp.solutions` was removed from
the Python package in mediapipe 0.10.31 (December 2025). The current
API needs a separate `.task` model file; the models are no longer
bundled inside the pip package.

This project already includes the official lite model at:

```text
models/pose_landmarker_lite.task
```

It was downloaded from Google’s model storage:

```text
https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task
```

If that file is missing, the game will try to download it on the first
pose-mode launch. Official docs also list `pose_landmarker_full.task` and
`pose_landmarker_heavy.task` if you later want a heavier model.

The game runs the landmarker on the **CPU**. That is the portable,
stable choice. Enabling the GPU delegate has caused high memory use on
some Apple Silicon Macs.

### macOS and Apple Silicon

Google’s current MediaPipe Python setup guide (updated 20 November 2026)
lists these desktop platforms: Windows (`x86_64` and `arm64`), **macOS
Apple Silicon (`arm64`)**, and Linux (`x86_64` and `arm64`). Python
3.9–3.14 is the stated range.

Current `mediapipe` wheels on PyPI for macOS are **Apple Silicon only**
(`macosx_11_0_arm64`). As of December 2025, the MediaPipe maintainers
said they only support arm64 on Mac going forward. There is no current
Intel Mac wheel. On an Intel Mac you can still play with `--mouse`, and
you can still use the Kinect with libfreenect (`--depth`, or color
frames if you somehow have an older MediaPipe build), but current
`pip install mediapipe` is for Apple Silicon.

Use a native arm64 Python, not a Rosetta (x86_64) interpreter, so the
wheel and your other libraries match.

### Webcam permission

The first time you use the Mac camera, macOS will ask for Camera access.
If the game skips the webcam, open **System Settings → Privacy &
Security → Camera** and allow Terminal (or iTerm, or whatever app you
used to launch Python).

## 6. Install the `freenect` Python module (Kinect only)

`brew install libfreenect` gives you the C library and tools, but not
the importable Python module named `freenect`. Do **not** run
`pip install libfreenect` — there is no official package by that name
on PyPI.

The official `wrappers/python/setup.py` and the wrapper CMake files still
call `distutils`, which was removed in Python 3.12. `./setup.sh` does
not use those as-is. It compiles the official `freenect.pyx` with Cython
and setuptools, then links it against Homebrew's libfreenect. If that
fails, it patches the vendored CMake file to use `sysconfig` and retries
a CMake build.

To do the same by hand, with your virtualenv activated:

```bash
pip install setuptools cython numpy
git clone --depth 1 https://github.com/OpenKinect/libfreenect.git vendor/libfreenect
python build_freenect.py --src vendor/libfreenect \
  --prefix "$(brew --prefix libfreenect)" \
  --prefix "$(brew --prefix libusb)"
```

Then check that it imports:

```bash
cd /path/to/kinect-game
python -c "import freenect; print('freenect module OK')"
```

If that fails with a “Library not loaded” or image-not-found error for
`libfreenect`, tell macOS where Homebrew’s libraries are and try again:

```bash
export DYLD_LIBRARY_PATH="$(brew --prefix)/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
python -c "import freenect; print('freenect module OK')"
```

You can add that `export` line to your shell startup file, or run it
each time before the game.

### Apple Silicon notes for libfreenect

- Homebrew’s libfreenect bottles are native arm64. That works, as long
  as **Python and libfreenect are the same architecture**. A Rosetta
  (x86_64) Python trying to load an arm64 library, or the reverse,
  fails with a Mach-O architecture error (`have 'arm64', need 'x86_64'`
  or the other way around). Use a native Terminal and a native Python.
- The USB speed issue in section 3 is the more common M-series snag:
  the camera never enumerates if the USB-C adapter stays at 12 Mbps.
- Keep the Kinect on its own powered adapter. The Mac’s USB port
  cannot power the sensor by itself.

### An unofficial pip package

There is a third-party package on PyPI also named `freenect` (a 2025
port of the official wrapper). `pip install freenect` may work after
`brew install libfreenect`, but it is not the OpenKinect project, and
the build_freenect.py path above is what this project uses.

## 7. Run the game

The short way, after `./setup.sh` has finished:

```bash
./run.sh
```

Or, from this folder with the virtualenv activated (`source .venv/bin/activate`):

```bash
# Default: MediaPipe pose tracking.
# Uses the Kinect color camera if it is available, otherwise the webcam,
# otherwise the mouse.
python star_pop.py

# Pose tracking from the Mac webcam, even if a Kinect is plugged in.
python star_pop.py --webcam

# Closest-point depth tracking from the Kinect (the original mode).
# Falls back to the mouse if the depth stream is not available.
python star_pop.py --depth

# Mouse only, no cameras or pose tracking.
python star_pop.py --mouse

# Hide the stick-figure overlay (already the default). Press S to cycle views.
python star_pop.py --no-skeleton

# Use the bonus robot avatar, or start with no avatar (skeleton only).
python star_pop.py --avatar robot
python star_pop.py --avatar none

# Draw a synthetic astronaut and save a PNG, then exit (no camera needed).
python star_pop.py --preview-avatar avatar_preview.png
```

**How to play:** stand far enough back that your upper body is in the
frame. Reach with either hand. The game uses your wrists and index
fingertips as cursors. A cartoon astronaut is drawn over your pose on a
dimmed camera view (press **S** to cycle avatar, avatar+skeleton,
skeleton, or none). In depth mode, hold a hand out toward the Kinect so
it is the closest point in the depth image. In mouse mode, just move the
pointer; the full-body avatar is skipped because there is no pose.
Escape quits.

The avatar is drawn with pygame shapes, so you do not need any image
files. If you want to use your own art, drop PNGs into `assets/avatar/`
(see the README in that folder). You can copy an updated `star_pop.py`,
`avatar.py`, and `assets/avatar/` over an existing install without
rerunning `./setup.sh`.

## What this stack can and cannot do

libfreenect gives you the Kinect’s depth image, color camera, tilt
motor, LED, and accelerometer. It does **not** do skeleton or joint
tracking. Microsoft’s Kinect for Windows SDK 1.8 has that, but it is
Windows-only and not open source.

On a Mac, this game uses MediaPipe Pose Landmarker instead: 33 body
landmarks estimated from a color image, which can come from the Kinect
or a webcam. That is software pose tracking, not the official Kinect
skeleton. The original closest-point depth trick is still available as
`--depth` if you want it.
