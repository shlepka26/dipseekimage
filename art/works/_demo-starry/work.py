# -*- coding: utf-8 -*-
"""Демо: ночное небо над хребтом. Стиль starry-night."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "python")))

from dipkit import ArtCanvas

SEED = 771
W, H = 1400, 1000
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "art.png")

c = ArtCanvas(W, H, bg="#05070f", palette="midnight")
c.meta = {"prompt": "ночь над горным хребтом, луна", "style": "starry-night", "seed": SEED}

# --- небо и дымка у горизонта
c.gradient(["#05070f", "#0d1633", "#1b2a5b", "#3b5cc4"], angle=90)
c.light(0.45 * W, 0.92 * H, 0.62 * W, "#4f7cff", intensity=0.16, falloff=2.2)

# --- звёзды
c.scatter(1200, "#f4f7ff", r=(0.5, 2.3), alpha=0.9, seed=SEED, glow=0.9)
c.scatter(70, "#9fd0ff", r=(1.5, 3.4), alpha=0.9, seed=SEED + 1, glow=2.6)

# --- луна
mx, my = 0.76 * W, 0.23 * H
c.light(mx, my, 0.44 * W, "#4f7cff", intensity=0.50, falloff=2.6)
c.light(mx, my, 0.15 * W, "#f4f7ff", intensity=0.60, falloff=1.8)
c.circle(mx, my, 62, "#f4f7ff", alpha=0.98)
c.ring(mx, my, 80, "#9fd0ff", width=2, alpha=0.30)

# --- два хребта: дальний светлее, ближний почти чёрный
c.polygon([(0, 760), (150, 610), (320, 700), (500, 560), (690, 730), (870, 600),
           (1070, 750), (1250, 650), (1400, 770), (1400, 1000), (0, 1000)],
          "#131c38")
c.polygon([(0, 880), (230, 770), (430, 860), (640, 730), (880, 870), (1130, 800),
           (1400, 900), (1400, 1000), (0, 1000)], "#070c1a")

# --- финиш
c.bloom(0.74, 22, 0.40).vignette(0.42).grain(0.022, seed=SEED)
c.save(OUT)
print("готово:", OUT)
