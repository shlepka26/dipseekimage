# -*- coding: utf-8 -*-
"""Демо: рисограф — две краски и несовпадение приводки. Стиль risograph."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "python")))

from dipkit import ArtCanvas

SEED = 909
W, H = 1200, 1500
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "art.png")

c = ArtCanvas(W, H, bg="#f6f1e5", palette="risograph")
c.meta = {"prompt": "плакат в две краски", "style": "risograph", "seed": SEED}

c.fill("#f6f1e5")

# --- две краски со сдвигом: характерный брак печати
c.circle(540, 630, 330, "#1f4e79", alpha=0.90)
c.circle(553, 640, 330, "#e8552f", alpha=0.40)
c.rect(120, 980, 1080, 1190, "#e8552f", alpha=0.88)
c.rect(131, 988, 1091, 1198, "#1f4e79", alpha=0.32)
c.wedge(900, 250, 1290, 640, 95, 255, "#f2c14e", alpha=0.80)
c.line([(120, 300), (120, 900)], "#1f4e79", width=8, alpha=0.70)

# --- типографика
sz = c.fit_size("РИСОГРАФ", 880, "sans-bold", 170)
c.text(160, 1015, "РИСОГРАФ", family="sans-bold", size=sz, color="#f6f1e5")
c.text(160, 1240, "две краски  ·  несовпадение приводки", family="mono",
       size=30, color="#1f4e79", alpha=0.85)
c.text(160, 1290, "dipkit / стиль risograph", family="mono", size=24,
       color="#1f4e79", alpha=0.55)

# --- фактура бумаги
c.noise(amount=0.10, scale=2, octaves=3, seed=SEED)
c.grain(0.04, seed=SEED).posterize(14).saturate(0.95)
c.save(OUT)
print("готово:", OUT)
