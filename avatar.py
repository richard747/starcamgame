#!/usr/bin/env python3
"""Procedural pose-driven avatars for Star Pop.

The default style is a cartoon space explorer. A robot style is also
included. Both are drawn with pygame shapes, following MediaPipe Pose
landmarks (33-point BlazePose). Optional PNG sprites in assets/avatar/
are used when present; see that folder's README.
"""

from __future__ import annotations

import math
from pathlib import Path

import pygame

# MediaPipe Pose landmark indices.
NOSE, L_EYE, R_EYE = 0, 2, 5
L_EAR, R_EAR = 7, 8
L_SHOULDER, R_SHOULDER = 11, 12
L_ELBOW, R_ELBOW = 13, 14
L_WRIST, R_WRIST = 15, 16
L_HIP, R_HIP = 23, 24
L_KNEE, R_KNEE = 25, 26
L_ANKLE, R_ANKLE = 27, 28
L_FOOT, R_FOOT = 31, 32

# Bone segments: (proximal, distal, kind)
LIMB_BONES = [
    (L_SHOULDER, L_ELBOW, "upper_arm"),
    (R_SHOULDER, R_ELBOW, "upper_arm"),
    (L_ELBOW, L_WRIST, "lower_arm"),
    (R_ELBOW, R_WRIST, "lower_arm"),
    (L_HIP, L_KNEE, "thigh"),
    (R_HIP, R_KNEE, "thigh"),
    (L_KNEE, L_ANKLE, "shin"),
    (R_KNEE, R_ANKLE, "shin"),
]

HANDS = [("glove", L_WRIST, L_ELBOW), ("glove", R_WRIST, R_ELBOW)]
FEET = [
    ("boot", L_ANKLE, L_FOOT, L_KNEE),
    ("boot", R_ANKLE, R_FOOT, R_KNEE),
]

STYLES = {
    "astronaut": {
        "suit": (236, 240, 248),
        "suit_shadow": (188, 198, 216),
        "outline": (46, 58, 84),
        "helmet": (248, 250, 253),
        "visor": (16, 42, 72),
        "visor_shine": (170, 220, 235),
        "visor_rim": (222, 176, 72),
        "glove": (244, 246, 250),
        "cuff": (232, 108, 42),
        "boot": (48, 54, 70),
        "boot_sole": (232, 108, 42),
        "pack": (62, 72, 92),
        "badge": (232, 108, 42),
        "joint": (210, 216, 228),
        "accent": (70, 150, 220),
    },
    "robot": {
        "suit": (86, 128, 164),
        "suit_shadow": (42, 66, 88),
        "outline": (18, 28, 40),
        "helmet": (110, 150, 180),
        "visor": (16, 24, 32),
        "visor_shine": (80, 255, 190),
        "visor_rim": (70, 230, 255),
        "glove": (64, 84, 104),
        "cuff": (70, 230, 255),
        "boot": (36, 48, 62),
        "boot_sole": (70, 230, 255),
        "pack": (30, 44, 58),
        "badge": (80, 255, 190),
        "joint": (200, 210, 220),
        "accent": (70, 230, 255),
    },
}

SPRITE_NAMES = {
    "head": "head.png",
    "torso": "torso.png",
    "upper_arm": "upper_arm.png",
    "lower_arm": "lower_arm.png",
    "thigh": "thigh.png",
    "shin": "shin.png",
    "glove": "glove.png",
    "boot": "boot.png",
}

ASSETS_DIR = Path(__file__).resolve().parent / "assets" / "avatar"


def _pt(points, index):
    pos = points.get(index)
    if pos is None:
        return None
    return float(pos[0]), float(pos[1])


def _mid(a, b):
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)


def _dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _angle(a, b):
    return math.atan2(b[1] - a[1], b[0] - a[0])


def _offset(point, angle, distance):
    return (point[0] + math.cos(angle) * distance, point[1] + math.sin(angle) * distance)


def _perp(dx, dy, radius):
    length = math.hypot(dx, dy) or 1.0
    return (-dy / length * radius, dx / length * radius)


def _i(point):
    return int(round(point[0])), int(round(point[1]))


def _limb_radius(length, kind, scale):
    ratios = {
        "upper_arm": 0.18,
        "lower_arm": 0.16,
        "thigh": 0.20,
        "shin": 0.17,
    }
    base = max(6.0, min(22.0, length * ratios.get(kind, 0.17)))
    return base * scale


def draw_capsule(surface, p1, p2, radius, fill, outline=None, outline_width=2):
    """A thick rounded limb: two end-caps and a connecting rectangle."""
    radius = max(2, int(round(radius)))
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    px, py = _perp(dx, dy, radius)
    poly = [
        (p1[0] + px, p1[1] + py),
        (p2[0] + px, p2[1] + py),
        (p2[0] - px, p2[1] - py),
        (p1[0] - px, p1[1] - py),
    ]
    pygame.draw.polygon(surface, fill, poly)
    pygame.draw.circle(surface, fill, _i(p1), radius)
    pygame.draw.circle(surface, fill, _i(p2), radius)
    if outline is not None:
        pygame.draw.polygon(surface, outline, poly, outline_width)
        pygame.draw.circle(surface, outline, _i(p1), radius, outline_width)
        pygame.draw.circle(surface, outline, _i(p2), radius, outline_width)


def _expand_quad(corners, padding):
    cx = sum(p[0] for p in corners) / 4.0
    cy = sum(p[1] for p in corners) / 4.0
    out = []
    for x, y in corners:
        dx, dy = x - cx, y - cy
        length = math.hypot(dx, dy) or 1.0
        out.append((x + dx / length * padding, y + dy / length * padding))
    return out


def load_sprites(style: str, assets_dir: Path | None = None) -> dict[str, pygame.Surface]:
    """Load optional PNGs. Missing files are skipped and drawn procedurally."""
    root = Path(assets_dir) if assets_dir else ASSETS_DIR
    search = []
    if style:
        search.append(root / style)
    search.append(root)
    sprites: dict[str, pygame.Surface] = {}
    for folder in search:
        if not folder.is_dir():
            continue
        for key, filename in SPRITE_NAMES.items():
            if key in sprites:
                continue
            path = folder / filename
            if not path.is_file():
                continue
            try:
                image = pygame.image.load(str(path)).convert_alpha()
            except Exception as exc:
                print(f"Could not load avatar sprite {path}: {exc}")
                continue
            sprites[key] = image
    return sprites


def blit_along_bone(surface, sprite, p1, p2, thickness=None):
    """Place a horizontal sprite along p1→p2 (left = proximal, right = distal)."""
    length = max(2.0, _dist(p1, p2))
    src_w, src_h = sprite.get_width(), sprite.get_height()
    if src_w < 1 or src_h < 1:
        return
    height = int(round(thickness * 2)) if thickness else max(4, int(round(src_h * (length / src_w))))
    height = max(4, height)
    scaled = pygame.transform.smoothscale(sprite, (int(round(length)), height))
    angle = -math.degrees(_angle(p1, p2))
    rotated = pygame.transform.rotate(scaled, angle)
    mid = _mid(p1, p2)
    rect = rotated.get_rect(center=(int(mid[0]), int(mid[1])))
    surface.blit(rotated, rect)


def blit_centered(surface, sprite, center, width, height, angle_rad=0.0):
    width, height = max(2, int(round(width))), max(2, int(round(height)))
    scaled = pygame.transform.smoothscale(sprite, (width, height))
    rotated = pygame.transform.rotate(scaled, -math.degrees(angle_rad))
    rect = rotated.get_rect(center=_i(center))
    surface.blit(rotated, rect)


def head_frame(points):
    """Helmet center, radius, and tilt (radians, 0 = upright / ears level)."""
    l_ear, r_ear = _pt(points, L_EAR), _pt(points, R_EAR)
    l_eye, r_eye = _pt(points, L_EYE), _pt(points, R_EYE)
    nose = _pt(points, NOSE)
    l_sh, r_sh = _pt(points, L_SHOULDER), _pt(points, R_SHOULDER)

    tilt = 0.0
    if l_ear and r_ear:
        tilt = _angle(l_ear, r_ear)
        center = _mid(l_ear, r_ear)
        radius = _dist(l_ear, r_ear) * 0.72
    elif l_eye and r_eye:
        tilt = _angle(l_eye, r_eye)
        center = _mid(l_eye, r_eye)
        radius = _dist(l_eye, r_eye) * 1.15
    elif nose and l_sh and r_sh:
        mid_sh = _mid(l_sh, r_sh)
        center = (nose[0] * 0.65 + mid_sh[0] * 0.35, nose[1] * 0.75 + mid_sh[1] * 0.25)
        radius = _dist(l_sh, r_sh) * 0.38
        tilt = _angle(mid_sh, nose) - math.pi / 2
    elif l_sh and r_sh:
        mid_sh = _mid(l_sh, r_sh)
        shoulder = _dist(l_sh, r_sh)
        center = (mid_sh[0], mid_sh[1] - shoulder * 0.42)
        radius = shoulder * 0.36
    else:
        return None

    if l_sh and r_sh:
        radius = max(radius, _dist(l_sh, r_sh) * 0.30)
        radius = min(radius, _dist(l_sh, r_sh) * 0.55)
    radius = max(16.0, min(64.0, radius))

    # Nudge the helmet slightly toward the nose so it sits on the head, not the neck.
    if nose:
        center = (center[0] * 0.6 + nose[0] * 0.4, center[1] * 0.7 + nose[1] * 0.3)
    return center, radius, tilt


def _part_z(zmap, *ids):
    vals = [zmap[i] for i in ids if i in zmap]
    if not vals:
        return 0.0
    return sum(vals) / len(vals)


def draw_torso(surface, points, colors, sprites, style):
    l_sh, r_sh = _pt(points, L_SHOULDER), _pt(points, R_SHOULDER)
    l_hip, r_hip = _pt(points, L_HIP), _pt(points, R_HIP)
    if not all((l_sh, r_sh, l_hip, r_hip)):
        return
    if "torso" in sprites:
        top, bottom = _mid(l_sh, r_sh), _mid(l_hip, r_hip)
        width = max(_dist(l_sh, r_sh), _dist(l_hip, r_hip)) * 1.25
        blit_along_bone(surface, sprites["torso"], top, bottom, thickness=width / 2)
        return
    corners = _expand_quad([l_sh, r_sh, r_hip, l_hip], 10)
    pygame.draw.polygon(surface, colors["suit"], corners)
    pygame.draw.polygon(surface, colors["outline"], corners, 3)
    mid_sh, mid_hip = _mid(l_sh, r_sh), _mid(l_hip, r_hip)
    # Subtle suit shadow down the middle.
    inner = _expand_quad(corners, -8)
    if len(inner) == 4:
        pygame.draw.line(surface, colors["suit_shadow"], inner[0], inner[3], 2)
        pygame.draw.line(surface, colors["suit_shadow"], inner[1], inner[2], 2)

    pack_h = max(16.0, _dist(mid_sh, mid_hip) * 0.38)
    pack_w = max(14.0, _dist(l_sh, r_sh) * 0.28)
    pack_c = (mid_sh[0] * 0.55 + mid_hip[0] * 0.45, mid_sh[1] * 0.55 + mid_hip[1] * 0.45)
    pack = pygame.Rect(0, 0, int(pack_w), int(pack_h))
    pack.center = _i(pack_c)
    pygame.draw.rect(surface, colors["pack"], pack, border_radius=4)
    pygame.draw.rect(surface, colors["outline"], pack, 2, border_radius=4)
    if style == "astronaut":
        badge = (pack.centerx + pack.width // 3, pack.top + 8)
        pygame.draw.circle(surface, colors["badge"], badge, 5)
        pygame.draw.circle(surface, colors["outline"], badge, 5, 1)
        # Belt
        belt_y = int(mid_hip[1] - _dist(mid_sh, mid_hip) * 0.12)
        pygame.draw.line(
            surface,
            colors["cuff"],
            (int(corners[3][0]), belt_y),
            (int(corners[2][0]), belt_y),
            4,
        )
    else:
        # Robot chest LED row
        for i, frac in enumerate((0.3, 0.5, 0.7)):
            cx = pack.left + int(pack.width * frac)
            cy = pack.centery
            pygame.draw.circle(surface, colors["accent"], (cx, cy), 3)


def draw_head(surface, points, colors, sprites, style):
    frame = head_frame(points)
    if frame is None:
        return
    center, radius, tilt = frame
    if "head" in sprites:
        blit_centered(surface, sprites["head"], center, radius * 2.1, radius * 2.1, tilt)
        return

    dx, dy = math.cos(tilt), math.sin(tilt)
    px, py = -dy, dx

    if style == "robot":
        hw, hh = radius * 0.95, radius * 0.9
        corners = [
            (center[0] + dx * hw + px * hh, center[1] + dy * hw + py * hh),
            (center[0] - dx * hw + px * hh, center[1] - dy * hw + py * hh),
            (center[0] - dx * hw - px * hh, center[1] - dy * hw - py * hh),
            (center[0] + dx * hw - px * hh, center[1] + dy * hw - py * hh),
        ]
        pygame.draw.polygon(surface, colors["helmet"], corners)
        pygame.draw.polygon(surface, colors["outline"], corners, 3)
        bar_c = _offset(center, tilt + math.pi / 2, radius * 0.08)
        bar_w, bar_h = radius * 1.15, radius * 0.32
        bar = []
        for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            bar.append(
                (
                    bar_c[0] + dx * bar_w * 0.5 * sx + px * bar_h * 0.5 * sy,
                    bar_c[1] + dy * bar_w * 0.5 * sx + py * bar_h * 0.5 * sy,
                )
            )
        pygame.draw.polygon(surface, colors["visor"], bar)
        pygame.draw.polygon(surface, colors["visor_rim"], bar, 2)
        shine = _offset(bar_c, tilt, -bar_w * 0.15)
        pygame.draw.circle(surface, colors["visor_shine"], _i(shine), max(2, int(radius * 0.08)))
        tip = _offset(center, tilt - math.pi / 2, radius * 1.35)
        base = _offset(center, tilt - math.pi / 2, radius * 0.95)
        pygame.draw.line(surface, colors["outline"], _i(base), _i(tip), 3)
        pygame.draw.circle(surface, colors["accent"], _i(tip), 5)
        pygame.draw.circle(surface, colors["outline"], _i(tip), 5, 1)
        return

    # Astronaut helmet: white sphere, gold band, dark visor.
    pygame.draw.circle(surface, colors["helmet"], _i(center), int(radius))
    pygame.draw.circle(surface, colors["outline"], _i(center), int(radius), 3)
    band_l = _offset(center, tilt + math.pi, radius * 0.92)
    band_r = _offset(center, tilt, radius * 0.92)
    pygame.draw.line(surface, colors["visor_rim"], _i(band_l), _i(band_r), 4)

    visor_c = _offset(center, tilt + math.pi / 2, radius * 0.12)
    visor_w, visor_h = radius * 0.78, radius * 0.55
    oval = pygame.Surface((int(visor_w * 2) + 4, int(visor_h * 2) + 4), pygame.SRCALPHA)
    ox, oy = oval.get_width() // 2, oval.get_height() // 2
    pygame.draw.ellipse(
        oval, colors["visor"] + (255,), pygame.Rect(2, 2, int(visor_w * 2), int(visor_h * 2))
    )
    pygame.draw.ellipse(
        oval,
        colors["visor_rim"] + (255,),
        pygame.Rect(2, 2, int(visor_w * 2), int(visor_h * 2)),
        3,
    )
    shine_rect = pygame.Rect(0, 0, int(visor_w * 0.7), int(visor_h * 0.35))
    shine_rect.topleft = (ox - int(visor_w * 0.55), oy - int(visor_h * 0.45))
    pygame.draw.ellipse(oval, colors["visor_shine"] + (90,), shine_rect)
    rotated = pygame.transform.rotate(oval, -math.degrees(tilt))
    surface.blit(rotated, rotated.get_rect(center=_i(visor_c)))

    for side in (tilt + math.pi, tilt):
        ear = _offset(center, side, radius * 0.95)
        pygame.draw.circle(surface, colors["suit_shadow"], _i(ear), max(4, int(radius * 0.18)))
        pygame.draw.circle(surface, colors["outline"], _i(ear), max(4, int(radius * 0.18)), 2)
    base = _offset(center, tilt - 2.3, radius * 0.85)
    tip = _offset(base, tilt - math.pi / 2, radius * 0.45)
    pygame.draw.line(surface, colors["outline"], _i(base), _i(tip), 2)
    pygame.draw.circle(surface, colors["cuff"], _i(tip), 4)
    pygame.draw.circle(surface, colors["outline"], _i(tip), 4, 1)



def draw_neck(surface, points, colors):
    """A short collar and neck so the helmet does not float above the suit."""
    frame = head_frame(points)
    l_sh, r_sh = _pt(points, L_SHOULDER), _pt(points, R_SHOULDER)
    if frame is None or not l_sh or not r_sh:
        return
    center, radius, tilt = frame
    mid_sh = _mid(l_sh, r_sh)
    collar_r = max(10, int(_dist(l_sh, r_sh) * 0.16))
    pygame.draw.circle(surface, colors["suit"], _i(mid_sh), collar_r)
    pygame.draw.circle(surface, colors["outline"], _i(mid_sh), collar_r, 2)
    chin = _offset(center, tilt + math.pi / 2, radius * 0.82)
    neck_r = max(7.0, _dist(l_sh, r_sh) * 0.11)
    draw_capsule(surface, mid_sh, chin, neck_r, colors["suit"], colors["outline"])


def draw_avatar(surface, points, style="astronaut", sprites=None, zmap=None):
    """Draw the chosen avatar over a dict of {index: (x, y)} landmarks."""
    if not points:
        return
    style = style if style in STYLES else "astronaut"
    colors = STYLES[style]
    if sprites is None:
        sprites = load_sprites(style)
    zmap = zmap or {}

    # Far-to-near: legs (already in draw_limbs), torso, arms/hands, head.
    # draw_limbs handles its own z sort among limbs, gloves, and boots.
    # Draw torso after the far legs and before the near arms by splitting:
    legs = [(a, b, k) for a, b, k in LIMB_BONES if k in ("thigh", "shin")]
    arms = [(a, b, k) for a, b, k in LIMB_BONES if k in ("upper_arm", "lower_arm")]

    def _draw_subset(kinds, extras=None):
        subset_points_used = True
        items = []
        for a, b, kind in kinds:
            p1, p2 = _pt(points, a), _pt(points, b)
            if p1 and p2:
                items.append((_part_z(zmap, a, b), "bone", a, b, kind, p1, p2))
        for extra in extras or ():
            items.append(extra)
        items.sort(key=lambda item: -item[0])
        for _z, kind, a, b, name, p1, p2 in items:
            if kind == "bone":
                length = _dist(p1, p2)
                radius = _limb_radius(length, name, 1.0)
                if name in sprites:
                    blit_along_bone(surface, sprites[name], p1, p2, thickness=radius)
                else:
                    draw_capsule(surface, p1, p2, radius, colors["suit"], colors["outline"])
                if style == "robot":
                    pygame.draw.circle(surface, colors["joint"], _i(p1), max(4, int(radius * 0.7)))
                    pygame.draw.circle(surface, colors["outline"], _i(p1), max(4, int(radius * 0.7)), 2)
            elif kind == "glove":
                radius = 11
                if p2:
                    radius = max(9, min(16, _dist(p1, p2) * 0.22))
                if "glove" in sprites:
                    ang = _angle(p2, p1) if p2 else 0.0
                    blit_centered(surface, sprites["glove"], p1, radius * 2.4, radius * 2.4, ang)
                else:
                    pygame.draw.circle(surface, colors["glove"], _i(p1), int(radius))
                    pygame.draw.circle(surface, colors["outline"], _i(p1), int(radius), 2)
                    if p2:
                        cuff = _offset(p1, _angle(p1, p2), radius * 0.85)
                        pygame.draw.circle(surface, colors["cuff"], _i(cuff), max(4, int(radius * 0.55)))
                        pygame.draw.circle(surface, colors["outline"], _i(cuff), max(4, int(radius * 0.55)), 2)
            elif kind == "boot":
                shin_start = _pt(points, L_KNEE if a == L_ANKLE else R_KNEE)
                direction = p2 if p2 and _dist(p1, p2) > 4 else None
                if direction is None and shin_start:
                    direction = _offset(p1, _angle(shin_start, p1), 22)
                if direction is None:
                    direction = (p1[0], p1[1] + 20)
                if "boot" in sprites:
                    blit_along_bone(surface, sprites["boot"], p1, direction, thickness=13)
                else:
                    draw_capsule(surface, p1, direction, 10, colors["boot"], colors["outline"])
                    sole = _offset(direction, _angle(p1, direction), 4)
                    pygame.draw.circle(surface, colors["boot_sole"], _i(sole), 5)
                    pygame.draw.circle(surface, colors["outline"], _i(sole), 5, 1)

    boot_items = []
    for name, ankle, foot, knee in FEET:
        p = _pt(points, ankle)
        if not p:
            continue
        boot_items.append(
            (_part_z(zmap, ankle), "boot", ankle, foot, name, p, _pt(points, foot) or _pt(points, knee))
        )
    glove_items = []
    for name, wrist, elbow in HANDS:
        p = _pt(points, wrist)
        if not p:
            continue
        glove_items.append((_part_z(zmap, wrist), "glove", wrist, elbow, name, p, _pt(points, elbow)))

    _draw_subset(legs, boot_items)
    draw_torso(surface, points, colors, sprites, style)
    _draw_subset(arms, glove_items)
    draw_neck(surface, points, colors)
    draw_head(surface, points, colors, sprites, style)


def synthetic_pose(width=640, height=480, reach="left"):
    """A natural standing pose, one arm raised as if popping a star.

    Coordinates assume a mirrored camera: the viewer's left is +x? After
    the game flips the camera, anatomical left appears on the right of
    the screen. These numbers are simply a well-framed front view.
    """
    # Person centered, slightly below mid-frame so the raised hand has room.
    cx, sy = width * 0.50, height * 0.38
    sw, hw = 78, 54  # half-widths of shoulders / hips
    points = {}
    # Head
    points[NOSE] = (cx, sy - 78)
    points[L_EYE] = (cx + 12, sy - 86)
    points[R_EYE] = (cx - 12, sy - 86)
    points[1] = (cx + 8, sy - 88)
    points[3] = (cx + 18, sy - 84)
    points[4] = (cx - 8, sy - 88)
    points[6] = (cx - 18, sy - 84)
    points[L_EAR] = (cx + 26, sy - 80)
    points[R_EAR] = (cx - 26, sy - 80)
    points[9] = (cx + 8, sy - 68)
    points[10] = (cx - 8, sy - 68)
    # Torso
    points[L_SHOULDER] = (cx + sw, sy)
    points[R_SHOULDER] = (cx - sw, sy)
    points[L_HIP] = (cx + hw, sy + 118)
    points[R_HIP] = (cx - hw, sy + 118)
    # Left arm (viewer's right) hangs slightly out
    points[L_ELBOW] = (cx + sw + 36, sy + 72)
    points[L_WRIST] = (cx + sw + 48, sy + 132)
    points[19] = (cx + sw + 54, sy + 148)  # left index
    points[17] = (cx + sw + 42, sy + 146)
    points[21] = (cx + sw + 46, sy + 144)
    # Right arm (viewer's left) reaches up toward a star
    if reach == "left":
        points[R_ELBOW] = (cx - sw - 20, sy - 40)
        points[R_WRIST] = (cx - sw - 10, sy - 108)
        points[20] = (cx - sw - 6, sy - 128)
        points[18] = (cx - sw - 18, sy - 122)
        points[22] = (cx - sw - 12, sy - 122)
    else:
        points[R_ELBOW] = (cx - sw - 36, sy + 72)
        points[R_WRIST] = (cx - sw - 48, sy + 132)
        points[20] = (cx - sw - 54, sy + 148)
        points[L_ELBOW] = (cx + sw + 20, sy - 40)
        points[L_WRIST] = (cx + sw + 10, sy - 108)
        points[19] = (cx + sw + 6, sy - 128)
    # Legs
    points[L_KNEE] = (cx + hw + 6, sy + 198)
    points[R_KNEE] = (cx - hw - 6, sy + 198)
    points[L_ANKLE] = (cx + hw + 4, sy + 268)
    points[R_ANKLE] = (cx - hw - 4, sy + 268)
    points[29] = (cx + hw, sy + 276)
    points[30] = (cx - hw, sy + 276)
    points[L_FOOT] = (cx + hw + 16, sy + 282)
    points[R_FOOT] = (cx - hw - 16, sy + 282)
    return points


def render_preview(path, size=(640, 480), style="astronaut"):
    """Draw a synthetic pose onto a starry background and save a PNG."""
    width, height = size
    surface = pygame.Surface((width, height))
    surface.fill((8, 12, 28))
    # Scattered background stars
    rng_positions = [
        (40, 36), (90, 80), (150, 24), (200, 110), (260, 48),
        (310, 18), (380, 70), (430, 30), (500, 90), (560, 40),
        (70, 200), (180, 250), (520, 220), (600, 160), (40, 400),
        (120, 430), (300, 450), (480, 410), (580, 370), (540, 300),
    ]
    for i, (x, y) in enumerate(rng_positions):
        r = 1 + (i % 3)
        shade = 180 + (i * 13) % 75
        pygame.draw.circle(surface, (shade, shade, 255), (x, y), r)

    points = synthetic_pose(width, height, reach="left")
    draw_avatar(surface, points, style=style, sprites=load_sprites(style), zmap={})

    # A star just above the raised hand, as in the game.
    hx, hy = points[20]
    star_c = (int(hx - 6), int(hy - 28))
    pygame.draw.circle(surface, (255, 214, 90), star_c, 14)
    pygame.draw.circle(surface, (255, 255, 255), star_c, 5)
    pygame.draw.line(surface, (255, 255, 255), (star_c[0], star_c[1] - 18), (star_c[0], star_c[1] + 18), 1)
    pygame.draw.line(surface, (255, 255, 255), (star_c[0] - 18, star_c[1]), (star_c[0] + 18, star_c[1]), 1)

    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(surface, str(dest))
    return dest
