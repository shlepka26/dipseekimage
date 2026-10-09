# -*- coding: utf-8 -*-
"""Демо: неоновый постер. Стиль neon-glow."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "python")))

from dipkit import ArtCanvas

SEED = 20240501
W, H = 1200, 1600
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "art.png")

c = ArtCanvas(W, H, bg="#05010f", palette="neon")
c.meta = {"prompt": "неоновый постер с кольцами", "style": "neon-glow", "seed": SEED}

# --- фон и атмосфера
c.gradient(["#05010f", "#150733", "#3a0ca3"], angle=100)
c.blobs(5, ["#f72585", "#4cc9f0"], r=(0.26 * W, 0.62 * W), alpha=0.26,
        seed=SEED, falloff=1.8)
c.flow(["#4cc9f0", "#f72585"], lines=110, steps=80, scale=2.4, width=2,
       alpha=0.16, seed=SEED + 1, curl=2.6)

# --- световой центр и объект
c.light(W * 0.5, H * 0.42, 0.42 * W, "#4cc9f0", intensity=0.32, falloff=2.4)
for i, r in enumerate(range(150, 470, 52)):
    c.ring(W * 0.5, H * 0.42, r, "#4cc9f0", width=3, alpha=0.55 - i * 0.07)
c.wedge(W * 0.5 - 520, H * 0.42 - 520, W * 0.5 + 520, H * 0.42 + 520,
        -55, 35, "#f72585", alpha=0.22)
c.circle(W * 0.5, H * 0.42, 46, "#e0fbfc", alpha=0.95)

# --- типографика
sz = c.fit_size("НЕОН", int(0.80 * W), "display", start=460)
c.text(W // 2, int(0.665 * H), "НЕОН", family="display", size=sz, color="#e0fbfc",
       anchor="mm", stroke=5, stroke_color="#f72585")
c.text(W // 2, int(0.875 * H), "генеративная графика · dipkit", family="mono",
       size=32, color="#9fd0ff", alpha=0.85, anchor="mm")

# --- финиш
c.bloom(0.58, 38, 0.75).chromatic(2).scanlines(4, 0.10).vignette(0.52)
c.grain(0.032, seed=SEED)
c.save(OUT)
print("готово:", OUT)
