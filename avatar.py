#!/usr/bin/env python3
"""Procedural pose-driven avatars for Star Pop.

The default style is a cartoon space explorer. The robot style is a
sleek humanoid android in the same steel-blue and cyan colors. Both are
drawn with pygame shapes, following MediaPipe Pose landmarks (33-point
BlazePose). Optional PNG sprites in assets/avatar/ are used when
present; see that folder's README.
"""

from __future__ import annotations

import math
from pathlib import Path

import pygame

try:
    import pygame.gfxdraw as gfxdraw
except Exception:  # pragma: no cover - pygame-ce ships gfxdraw
    gfxdraw = None

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


def _lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _mix(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def _basis(tilt):
    """Ear-to-ear axis, then the axis that points toward the chin."""
    return (math.cos(tilt), math.sin(tilt)), (-math.sin(tilt), math.cos(tilt))


def _local(center, basis_x, basis_y, lx, ly):
    return (
        center[0] + basis_x[0] * lx + basis_y[0] * ly,
        center[1] + basis_x[1] * lx + basis_y[1] * ly,
    )


def _aa_polygon(surface, points, fill, outline=None, stroke=1):
    ip = [_i(p) for p in points]
    if len(ip) < 3:
        return
    pygame.draw.polygon(surface, fill, ip)
    if outline is not None and stroke:
        pygame.draw.polygon(surface, outline, ip, stroke)
    if gfxdraw is not None:
        try:
            gfxdraw.aapolygon(surface, ip, outline or fill)
        except Exception:
            pass


def _aa_circle(surface, center, radius, fill, outline=None):
    r = max(1, int(round(radius)))
    c = _i(center)
    if outline is not None:
        pygame.draw.circle(surface, outline, c, r + 1, 1)
    pygame.draw.circle(surface, fill, c, r)
    if gfxdraw is not None:
        try:
            gfxdraw.aacircle(surface, c[0], c[1], r, outline or fill)
        except Exception:
            pass


def _oval_points(center, rx, ry, tilt, steps=20):
    basis_x, basis_y = _basis(tilt)
    points = []
    for i in range(steps):
        angle = (i / steps) * math.tau
        points.append(
            _local(center, basis_x, basis_y, math.cos(angle) * rx, math.sin(angle) * ry)
        )
    return points


def _oval_arc(center, rx, ry, tilt, a0, a1, steps=10):
    basis_x, basis_y = _basis(tilt)
    points = []
    for i in range(steps + 1):
        angle = a0 + (a1 - a0) * (i / steps)
        points.append(
            _local(center, basis_x, basis_y, math.cos(angle) * rx, math.sin(angle) * ry)
        )
    return points


def _cross_section(l_sh, r_sh, l_hip, r_hip, t, scale):
    left = _lerp(l_sh, l_hip, t)
    right = _lerp(r_sh, r_hip, t)
    mid = _mid(left, right)
    left = (mid[0] + (left[0] - mid[0]) * scale, mid[1] + (left[1] - mid[1]) * scale)
    right = (mid[0] + (right[0] - mid[0]) * scale, mid[1] + (right[1] - mid[1]) * scale)
    return left, right


def draw_tapered_limb(surface, p1, p2, r1, r2, fill, outline=None):
    """A rounded limb that narrows from r1 at p1 to r2 at p2."""
    length = _dist(p1, p2)
    if length < 2:
        return
    r1 = max(1.5, r1)
    r2 = max(1.2, r2)
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    ax, ay = _perp(dx, dy, r1)
    bx, by = _perp(dx, dy, r2)
    quad = [
        (p1[0] + ax, p1[1] + ay),
        (p2[0] + bx, p2[1] + by),
        (p2[0] - bx, p2[1] - by),
        (p1[0] - ax, p1[1] - ay),
    ]
    _aa_polygon(surface, quad, fill, outline, 1)
    _aa_circle(surface, p1, r1, fill, outline)
    _aa_circle(surface, p2, r2, fill, outline)
    # A thin highlight so the limb reads as round instead of flat.
    light = _mix(fill, (255, 255, 255), 0.28)
    shift = min(r1, r2) * 0.32
    ox, oy = _perp(dx, dy, shift)
    pygame.draw.aaline(
        surface,
        light,
        _i((p1[0] + ox, p1[1] + oy)),
        _i((p2[0] + ox, p2[1] + oy)),
    )


def _robot_taper(length, kind):
    """Proximal and distal thickness. Upper segments stay thicker."""
    length = max(8.0, length)
    table = {
        "upper_arm": (0.20, 0.13, 7.0, 15.0, 4.5, 10.0),
        "lower_arm": (0.14, 0.075, 4.5, 10.0, 3.0, 7.0),
        "thigh": (0.22, 0.15, 8.0, 18.0, 5.5, 12.0),
        "shin": (0.15, 0.09, 5.5, 12.0, 3.5, 8.0),
    }
    near, far, near_lo, near_hi, far_lo, far_hi = table.get(
        kind, (0.16, 0.10, 5.0, 12.0, 3.5, 8.0)
    )
    r1 = min(near_hi, max(near_lo, length * near))
    r2 = min(far_hi, max(far_lo, length * far))
    return r1, r2


def draw_robot_limb(surface, p1, p2, kind, colors):
    length = _dist(p1, p2)
    if length < 3:
        return
    r1, r2 = _robot_taper(length, kind)
    draw_tapered_limb(surface, p1, p2, r1, r2, colors["suit"], colors["outline"])


def draw_robot_hinge(surface, points, joint, proximal, distal, colors):
    """A small pin at the elbow or knee, skipped when that joint is hidden."""
    center = _pt(points, joint)
    if center is None:
        return
    span = 0.0
    for other in (proximal, distal):
        end = _pt(points, other)
        if end is not None:
            span = max(span, _dist(center, end))
    if span < 4:
        return
    radius = min(11.0, max(5.0, span * 0.15))
    _aa_circle(surface, center, radius, colors["joint"], colors["outline"])
    _aa_circle(surface, center, radius * 0.52, colors["suit_shadow"], None)
    pygame.draw.circle(surface, colors["accent"], _i(center), max(1, int(radius * 0.22)))


def draw_robot_torso(surface, points, colors):
    """Shoulders taper to a waist, then ease back out at the hips."""
    l_sh, r_sh = _pt(points, L_SHOULDER), _pt(points, R_SHOULDER)
    l_hip, r_hip = _pt(points, L_HIP), _pt(points, R_HIP)
    if not all((l_sh, r_sh, l_hip, r_hip)):
        return
    samples = (
        (0.00, 1.06),
        (0.14, 0.98),
        (0.32, 0.78),
        (0.50, 0.58),
        (0.66, 0.46),
        (0.84, 0.82),
        (1.00, 1.10),
    )
    left, right = [], []
    for t, scale in samples:
        side_l, side_r = _cross_section(l_sh, r_sh, l_hip, r_hip, t, scale)
        left.append(side_l)
        right.append(side_r)
    mid = _mid(left[0], right[0])
    hip_mid = _mid(left[-1], right[-1])
    peak = _offset(mid, _angle(hip_mid, mid), _dist(l_sh, r_sh) * 0.06)
    _aa_polygon(surface, left + list(reversed(right)) + [peak], colors["suit"], colors["outline"], 2)

    chest_l, chest_r = [], []
    for t, scale in ((0.16, 0.58), (0.28, 0.50), (0.40, 0.42), (0.50, 0.36)):
        side_l, side_r = _cross_section(l_sh, r_sh, l_hip, r_hip, t, scale)
        chest_l.append(side_l)
        chest_r.append(side_r)
    _aa_polygon(
        surface,
        chest_l + list(reversed(chest_r)),
        colors["suit_shadow"],
        colors["outline"],
        1,
    )
    sternum_top = _lerp(_mid(chest_l[0], chest_r[0]), _mid(chest_l[-1], chest_r[-1]), 0.18)
    sternum_bot = _lerp(_mid(chest_l[0], chest_r[0]), _mid(chest_l[-1], chest_r[-1]), 0.78)
    draw_tapered_limb(surface, sternum_top, sternum_bot, 3.4, 2.2, colors["accent"], colors["outline"])

    span = _dist(l_hip, r_hip)
    axis = _angle(l_hip, r_hip)
    hip_mid = _mid(l_hip, r_hip)
    for hip in (l_hip, r_hip):
        plate = _lerp(hip, hip_mid, 0.28)
        _aa_polygon(
            surface,
            _oval_points(plate, max(7.0, span * 0.15), max(5.0, span * 0.10), axis, 14),
            colors["pack"],
            colors["outline"],
            1,
        )
    socket = max(6.0, _dist(l_sh, r_sh) * 0.09)
    for shoulder in (l_sh, r_sh):
        _aa_circle(surface, shoulder, socket, colors["suit"], colors["outline"])


def draw_robot_head(surface, points, colors):
    """Oval face: eye visor, jaw line, no box and no antenna."""
    frame = head_frame(points)
    if frame is None:
        return
    center, radius, tilt = frame
    basis_x, basis_y = _basis(tilt)
    rx, ry = radius * 0.86, radius * 1.08
    _aa_polygon(surface, _oval_points(center, rx, ry, tilt, 22), colors["helmet"], colors["outline"], 2)
    # Lower face plate. Parameter 0 is ear-to-ear; pi/2 points at the chin.
    chin = _oval_arc(center, rx * 0.90, ry * 0.94, tilt, 0.45, math.pi - 0.45, 12)
    if len(chin) >= 3:
        _aa_polygon(surface, chin, colors["suit_shadow"], None, 0)
        pygame.draw.aaline(surface, colors["outline"], _i(chin[0]), _i(chin[-1]))
        jaw = _oval_arc(center, rx * 0.62, ry * 0.42, tilt, 0.70, math.pi - 0.70, 8)
        if len(jaw) >= 2:
            pygame.draw.aalines(surface, colors["outline"], False, [_i(p) for p in jaw])

    visor_c = _local(center, basis_x, basis_y, 0, -ry * 0.10)
    _aa_polygon(
        surface,
        _oval_points(visor_c, rx * 0.60, ry * 0.30, tilt, 16),
        colors["visor"],
        colors["visor_rim"],
        1,
    )
    for side in (-1, 1):
        eye = _local(visor_c, basis_x, basis_y, side * rx * 0.26, ry * 0.02)
        _aa_polygon(
            surface,
            _oval_points(eye, max(2.5, rx * 0.15), max(2.0, ry * 0.09), tilt, 12),
            colors["accent"],
            None,
            0,
        )
        glint = _local(eye, basis_x, basis_y, -rx * 0.04, -ry * 0.025)
        pygame.draw.circle(surface, colors["visor_shine"], _i(glint), max(1, int(rx * 0.045)))
    for side in (-1, 1):
        node = _local(center, basis_x, basis_y, side * rx * 0.92, ry * 0.02)
        _aa_circle(surface, node, max(2.5, rx * 0.10), colors["suit_shadow"], colors["outline"])


def draw_robot_neck(surface, points, colors):
    frame = head_frame(points)
    l_sh, r_sh = _pt(points, L_SHOULDER), _pt(points, R_SHOULDER)
    if frame is None or l_sh is None or r_sh is None:
        return
    center, radius, tilt = frame
    mid = _mid(l_sh, r_sh)
    chin = _offset(center, tilt + math.pi / 2, radius * 0.96)
    if _dist(chin, mid) < 4:
        return
    span = _dist(l_sh, r_sh)
    draw_tapered_limb(
        surface,
        chin,
        mid,
        max(3.5, span * 0.055),
        max(5.0, span * 0.09),
        colors["suit"],
        colors["outline"],
    )
    pygame.draw.circle(surface, colors["outline"], _i(mid), max(4, int(span * 0.10)), 1)


def draw_robot_hand(surface, points, wrist_id, elbow_id, colors):
    """Palm, three fingers, and a thumb. Hidden when the wrist is hidden."""
    wrist = _pt(points, wrist_id)
    if wrist is None:
        return
    elbow = _pt(points, elbow_id)
    index_id = 19 if wrist_id == L_WRIST else 20
    index = _pt(points, index_id)
    if index is not None and _dist(wrist, index) > 4:
        direction = _angle(wrist, index)
        reach = _dist(wrist, index)
    elif elbow is not None:
        direction = _angle(elbow, wrist)
        reach = max(12.0, _dist(elbow, wrist) * 0.28)
    else:
        direction = math.pi / 2
        reach = 14.0
    palm_r = min(13.0, max(6.0, reach * 0.62))
    palm = _offset(wrist, direction, palm_r * 0.35)
    _aa_circle(surface, palm, palm_r, _mix(colors["glove"], colors["suit"], 0.55), colors["outline"])
    finger_len = min(18.0, max(9.0, reach * 0.95))
    knuckle = _offset(palm, direction, palm_r * 0.78)
    side = direction + math.pi / 2
    for slot in (-1, 0, 1):
        base = _offset(knuckle, side, slot * max(4.5, palm_r * 0.62))
        tip = _offset(base, direction + slot * 0.34, finger_len)
        pygame.draw.line(surface, colors["suit"], _i(base), _i(tip), 3)
        pygame.draw.circle(surface, colors["joint"], _i(tip), 2)
        pygame.draw.circle(surface, colors["outline"], _i(tip), 2, 1)
    thumb_sign = -1 if wrist_id == L_WRIST else 1
    thumb_base = _offset(palm, direction + thumb_sign * 1.35, palm_r * 0.2)
    thumb_tip = _offset(thumb_base, direction + thumb_sign * 0.95, finger_len * 0.78)
    pygame.draw.line(surface, colors["suit"], _i(thumb_base), _i(thumb_tip), 3)
    pygame.draw.circle(surface, colors["joint"], _i(thumb_tip), 2)
    pygame.draw.circle(surface, colors["outline"], _i(thumb_tip), 2, 1)


def draw_robot_foot(surface, ankle, toe, colors):
    if ankle is None:
        return
    if toe is None or _dist(ankle, toe) < 4:
        toe = (ankle[0], ankle[1] + 16)
    direction = _angle(ankle, toe)
    heel = _offset(ankle, direction + math.pi, 4)
    toe = _offset(toe, direction, 7)
    draw_tapered_limb(surface, heel, toe, 6.5, 4.2, colors["boot"], colors["outline"])
    sole = _offset(toe, direction, 1.5)
    pygame.draw.circle(surface, colors["boot_sole"], _i(sole), 3)
    pygame.draw.circle(surface, colors["outline"], _i(sole), 3, 1)


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
    if style == "robot":
        draw_robot_torso(surface, points, colors)
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
        draw_robot_head(surface, points, colors)
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


def _dist_point_segment(px, py, ax, ay, bx, by):
    abx, aby = bx - ax, by - ay
    ab2 = abx * abx + aby * aby
    if ab2 <= 1e-6:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * abx + (py - ay) * aby) / ab2))
    return math.hypot(px - (ax + abx * t), py - (ay + aby * t))


def hit_regions(points):
    """Body shapes used for meteor hits, matched to the drawn avatar.

    Each region is ("circle", x, y, r) or ("capsule", x1, y1, x2, y2, r).
    Hands and boots are included, so a hit is not limited to the palms.
    """
    regions = []
    frame = head_frame(points)
    if frame is not None:
        center, radius, _tilt = frame
        regions.append(("circle", center[0], center[1], radius * 0.92))

    l_sh, r_sh = _pt(points, L_SHOULDER), _pt(points, R_SHOULDER)
    l_hip, r_hip = _pt(points, L_HIP), _pt(points, R_HIP)
    if all((l_sh, r_sh, l_hip, r_hip)):
        top, bottom = _mid(l_sh, r_sh), _mid(l_hip, r_hip)
        span = max(_dist(l_sh, r_sh), _dist(l_hip, r_hip))
        regions.append(
            ("capsule", top[0], top[1], bottom[0], bottom[1], max(18.0, span * 0.28))
        )

    for a, b, kind in LIMB_BONES:
        p1, p2 = _pt(points, a), _pt(points, b)
        if not p1 or not p2:
            continue
        length = _dist(p1, p2)
        regions.append(
            ("capsule", p1[0], p1[1], p2[0], p2[1], _limb_radius(length, kind, 1.0))
        )

    for ankle, foot in ((L_ANKLE, L_FOOT), (R_ANKLE, R_FOOT)):
        p1, p2 = _pt(points, ankle), _pt(points, foot)
        if p1 and p2:
            regions.append(("capsule", p1[0], p1[1], p2[0], p2[1], 11.0))

    for _name, wrist, elbow in HANDS:
        wrist_p, elbow_p = _pt(points, wrist), _pt(points, elbow)
        if not wrist_p:
            continue
        radius = 12.0
        if elbow_p:
            radius = max(10.0, min(16.0, _dist(wrist_p, elbow_p) * 0.22))
        regions.append(("circle", wrist_p[0], wrist_p[1], radius))
    return regions


def region_hit(regions, x, y, extra=0.0):
    """True when a circle at (x, y) with padding `extra` overlaps a body region."""
    for region in regions:
        if region[0] == "circle":
            _kind, cx, cy, radius = region
            if math.hypot(x - cx, y - cy) <= radius + extra:
                return True
        else:
            _kind, ax, ay, bx, by, radius = region
            if _dist_point_segment(x, y, ax, ay, bx, by) <= radius + extra:
                return True
    return False


def shift_points(points, dx, dy):
    """Move a pose dict by a pixel offset."""
    return {index: (x + dx, y + dy) for index, (x, y) in points.items()}


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
                elif style == "robot":
                    draw_robot_limb(surface, p1, p2, name, colors)
                else:
                    draw_capsule(surface, p1, p2, radius, colors["suit"], colors["outline"])
            elif kind == "glove":
                radius = 11
                if p2:
                    radius = max(9, min(16, _dist(p1, p2) * 0.22))
                if "glove" in sprites:
                    ang = _angle(p2, p1) if p2 else 0.0
                    blit_centered(surface, sprites["glove"], p1, radius * 2.4, radius * 2.4, ang)
                elif style == "robot":
                    draw_robot_hand(surface, points, a, b, colors)
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
                elif style == "robot":
                    draw_robot_foot(surface, p1, direction, colors)
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
    if style == "robot":
        for joint, proximal, distal in (
            (L_KNEE, L_HIP, L_ANKLE),
            (R_KNEE, R_HIP, R_ANKLE),
        ):
            draw_robot_hinge(surface, points, joint, proximal, distal, colors)
    draw_torso(surface, points, colors, sprites, style)
    _draw_subset(arms, glove_items)
    if style == "robot":
        for joint, proximal, distal in (
            (L_ELBOW, L_SHOULDER, L_WRIST),
            (R_ELBOW, R_SHOULDER, R_WRIST),
        ):
            draw_robot_hinge(surface, points, joint, proximal, distal, colors)
        draw_robot_neck(surface, points, colors)
    else:
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
