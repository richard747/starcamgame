#!/usr/bin/env python3
"""Draw the PWA icons. Run from web/: python3 scripts/make_icons.py"""

from pathlib import Path

import pygame

OUT = Path(__file__).resolve().parents[1] / "public" / "icons"
NAVY = (8, 12, 28)
GOLD = (255, 214, 90)
WHITE = (244, 247, 255)
CYAN = (90, 220, 255)
INK = (18, 28, 40)


def draw(size, pad=0.0):
    surface = pygame.Surface((size, size))
    surface.fill(NAVY)
    margin = int(size * pad)
    inner = size - margin * 2
    cx, cy = size // 2, size // 2 + int(inner * 0.02)
    helmet = int(inner * 0.30)
    pygame.draw.circle(surface, WHITE, (cx, cy - int(inner * 0.02)), helmet)
    pygame.draw.circle(surface, INK, (cx, cy - int(inner * 0.02)), helmet, max(2, size // 64))
    visor = pygame.Rect(0, 0, int(helmet * 1.35), int(helmet * 0.72))
    visor.center = (cx, cy - int(inner * 0.02))
    pygame.draw.ellipse(surface, (16, 42, 72), visor)
    pygame.draw.ellipse(surface, GOLD, visor, max(2, size // 80))
    star = (cx + int(inner * 0.28), cy - int(inner * 0.30))
    radius = max(4, int(inner * 0.07))
    pygame.draw.circle(surface, GOLD, star, radius)
    pygame.draw.circle(surface, WHITE, star, max(2, radius // 3))
    pygame.draw.circle(surface, CYAN, (cx - int(inner * 0.30), cy + int(inner * 0.22)), max(4, int(inner * 0.045)))
    return surface


def main():
    pygame.init()
    OUT.mkdir(parents=True, exist_ok=True)
    pygame.image.save(draw(192), OUT / "icon-192.png")
    pygame.image.save(draw(512), OUT / "icon-512.png")
    pygame.image.save(draw(512, pad=0.12), OUT / "icon-maskable-512.png")
    pygame.image.save(draw(180), OUT / "apple-touch-icon.png")
    print(f"Wrote icons to {OUT}")
    pygame.quit()


if __name__ == "__main__":
    main()
