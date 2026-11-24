# Star Pop

Star Pop is a Python motion game in the spirit of an Xbox Kinect title. It tracks your whole body and lets you pop falling stars with either hand. A cartoon astronaut or robot is drawn over the tracked pose.

The color image comes from an Xbox 360 Kinect (Kinect v1, through libfreenect), a webcam, or the mouse if no camera is available. Pose tracking uses Google MediaPipe Pose Landmarker. The game is built for Apple Silicon Macs with Python 3.9–3.14 and pygame-ce (the stack it is developed on is Python 3.14).

![Astronaut avatar over a starfield](avatar_preview.png)

## Quick start

From this folder in Terminal, on a Mac:

```bash
./setup.sh
./run.sh
```

`./setup.sh` is safe to run more than once. It installs Homebrew packages (including libfreenect), creates `.venv`, installs the Python packages, builds the `freenect` module, downloads the pose model if it is not already there, and checks the imports. `./run.sh` activates that virtualenv and starts the game. Extra arguments are passed through to `star_pop.py`.

Hardware, the Kinect USB adapter, manual install steps, and Apple Silicon notes are in [SETUP.md](SETUP.md).

## Flags

```bash
./run.sh                      # Kinect color camera, else webcam, else mouse
./run.sh --webcam             # webcam pose tracking, even if a Kinect is plugged in
./run.sh --depth              # closest-point Kinect depth tracking
./run.sh --mouse              # mouse only
./run.sh --avatar astronaut   # default cartoon suit
./run.sh --avatar robot       # bonus robot
./run.sh --avatar none        # no avatar
./run.sh --preview-avatar     # draw a synthetic astronaut, save avatar_preview.png, and exit
./run.sh --preview-avatar out.png
```

## Views

In pose mode, **S** cycles the overlay: avatar, avatar plus skeleton, skeleton, then none. The default is the astronaut with no stick figure. Mouse and depth modes have no pose, so the avatar is skipped and the cursor still pops stars. Escape quits.

## Pose model

`models/pose_landmarker_lite.task` (about 5 MB) is not stored in git. `./setup.sh` downloads the official MediaPipe lite model when the file is missing, and leaves an existing copy alone. The game does the same on the first pose-mode launch. A fresh clone only needs `./setup.sh` (or a pose-mode launch) to fetch it.
