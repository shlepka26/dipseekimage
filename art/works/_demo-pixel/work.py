# -*- coding: utf-8 -*-
"""Демо: пиксель-арт пейзаж. Стиль pixel-scene.

Рисуем на маленьком холсте (150x150), в конце увеличиваем в 8 раз
без сглаживания — так получаются честные крупные пиксели.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "python")))

from dipkit import ArtCanvas

SEED = 404
S = 150                      # «пиксельное» разрешение
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "art.png")

c = ArtCanvas(S, S, bg="#2b1055", palette="sunset")
c.meta = {"prompt": "пиксельный закат над морем", "style": "pixel-scene", "seed": SEED}

# --- небо полосами
for col, y0, y1 in [("#2b1055", 0, 42), ("#4b2a7a", 42, 72), ("#7597de", 72, 88),
                    ("#ff8c42", 88, 99), ("#ffd166", 99, 107)]:
    c.rect(0, y0, S, y1, col)

# --- солнце
c.circle(75, 101, 13, "#fff3b0")
c.circle(75, 101, 8, "#ffffff", alpha=0.9)

# --- горы
c.polygon([(0, 107), (26, 74), (54, 107)], "#3b2350")
c.polygon([(30, 107), (72, 56), (116, 107)], "#57306b")
c.polygon([(92, 107), (124, 80), (150, 107)], "#3b2350")

# --- море и блики
c.rect(0, 107, S, S, "#1a0f33")
for i, x in enumerate(range(0, S, 6)):
    off = (i % 3) * 3
    c.rect(x, 110 + off, x + 3, 112 + off, "#ffd166", alpha=0.30)
    c.rect(x + 2, 122 + off, x + 5, 124 + off, "#7597de", alpha=0.22)

# --- дорожка отражения
c.rect(69, 107, 82, S, "#c9762f", alpha=0.28)
c.rect(72, 108, 79, S, "#ffd166", alpha=0.22)

# --- ограничение палитры и увеличение: именно это делает стиль
c.quantize_to_palette(["#2b1055", "#4b2a7a", "#7597de", "#ff8c42", "#ffd166",
                       "#1a0f33", "#0b0716", "#fff3b0"])
c.upscale(8)
c.save(OUT)
print("готово:", OUT, c.w, c.h)
