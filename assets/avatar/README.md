# Optional avatar sprites

Star Pop draws a cartoon astronaut (or robot) with pygame shapes. You do
not need any files here for that to work.

If you would rather use your own art, drop PNG images in this folder, or
in a style subfolder (`assets/avatar/astronaut/` or
`assets/avatar/robot/`). The game looks in the style folder first, then
here. Missing names are still drawn procedurally, so you can replace
just the helmet or just the boots.

## File names

| File          | Drawn over                                      |
|---------------|--------------------------------------------------|
| `head.png`    | Helmet / head, centered and tilted with the face |
| `torso.png`   | Shoulders down to the hips                       |
| `upper_arm.png` | Shoulder → elbow                               |
| `lower_arm.png` | Elbow → wrist                                  |
| `thigh.png`   | Hip → knee                                       |
| `shin.png`    | Knee → ankle                                     |
| `glove.png`   | Centered on the wrist                            |
| `boot.png`    | Ankle → foot                                     |

PNG files should have a transparent background (RGBA).

## How each sprite is placed

- **Limb sprites** (`upper_arm`, `lower_arm`, `thigh`, `shin`, and
  `boot`): draw them **horizontal**. The left edge is the proximal
  joint (shoulder, elbow, hip, knee, ankle) and the right edge is the
  distal joint. The game scales the image to the bone length and
  thickness, then rotates it to the bone angle.
- **Head**: draw it **upright**, facing forward. The game scales it to
  the helmet size (from ear / eye / shoulder width) and rotates it to
  the head tilt.
- **Torso**: draw it **upright**, top = shoulders, bottom = hips. It is
  placed along the mid-shoulder → mid-hip line and scaled to the
  shoulder/hip width.
- **Glove**: draw it centered in the file, facing right if it has a
  direction. It is scaled to the wrist and rotated along the forearm.

After you add or change PNGs, just restart the game. No setup rerun is
needed.
