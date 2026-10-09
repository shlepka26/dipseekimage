# -*- coding: utf-8 -*-
"""Демо: генеративные линии вдоль поля шума. Стиль flow-field."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "python")))

from dipkit import ArtCanvas

SEED = 31337
W = H = 1400
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "art.png")

c = ArtCanvas(W, H, bg="#02121f", palette="ocean")
c.meta = {"prompt": "течения, генеративные линии", "style": "flow-field", "seed": SEED}

# --- подложка
c.fill("#02121f")
c.blobs(3, ["#04395e", "#0f7a8c"], r=(420, 860), alpha=0.30, seed=SEED, falloff=1.9)

# --- три прохода линий: плотный, тонкий и тёмный
c.flow(["#0f7a8c", "#4fd1c5"], lines=320, steps=170, scale=2.6, width=2,
       alpha=0.28, seed=SEED + 1, curl=2.4)
c.flow(["#e8fffe"], lines=90, steps=120, scale=4.2, width=1,
       alpha=0.20, seed=SEED + 2, curl=1.8)
c.flow(["#04395e"], lines=200, steps=200, scale=1.7, width=3,
       alpha=0.16, seed=SEED + 3, curl=3.0)

# --- объём и финиш
c.light(0.5 * W, 0.5 * H, 0.5 * W, "#4fd1c5", intensity=0.16, falloff=2.6)
c.bloom(0.70, 24, 0.45).vignette(0.52).grain(0.018, seed=SEED)
c.save(OUT)
print("готово:", OUT)
