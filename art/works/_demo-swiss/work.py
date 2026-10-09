# -*- coding: utf-8 -*-
"""Демо: швейцарский минимализм. Стиль minimal-geometry."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "python")))

from dipkit import ArtCanvas

SEED = 12
W, H = 1200, 1500
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "art.png")

c = ArtCanvas(W, H, bg="#f4f1ea", palette="ink")
c.meta = {"prompt": "швейцарский постер: круг, купол, плашка", "style": "minimal-geometry",
          "seed": SEED}

c.fill("#f4f1ea")
c.grid(step=100, color="#0b0b0f", alpha=0.05)

# --- чёрная плашка с заголовком
c.rect(100, 120, 1100, 430, "#0b0b0f")
sz = c.fit_size("ФОРМА", 900, "sans-bold", 340)
c.text(140, 275, "ФОРМА", family="sans-bold", size=sz, color="#f4f1ea", anchor="lm")

# --- фигуры
c.circle(600, 780, 260, "#c8452f")
c.line([(100, 1050), (1100, 1050)], "#0b0b0f", width=3)
c.wedge(280, 1100, 920, 1420, 180, 360, "#0b0b0f")

# --- подписи
c.text(100, 1370, "минимум средств", family="sans", size=34, color="#0b0b0f", alpha=0.75)
c.text(100, 1425, "dipkit / палитра ink", family="mono", size=26,
       color="#0b0b0f", alpha=0.50)
c.save(OUT)
print("готово:", OUT)
