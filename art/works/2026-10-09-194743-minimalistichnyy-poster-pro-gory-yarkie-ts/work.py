# -*- coding: utf-8 -*-
"""Минималистичный постер про горы. Стиль minimal-geometry, яркая палитра.

Плоские фигуры, модульная сетка, ни одного размытия и ни одной песчинки шума —
всё держится на композиции, контрасте и пустоте.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "python")))

from dipkit import ArtCanvas

SEED = 707
W, H = 1200, 1500
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "art.png")

SKY_TOP, SKY_BOT = "#FFE066", "#FFB703"   # яркое небо
SUN = "#EF476F"                           # солнце
FAR, MID = "#118AB2", "#06D6A0"           # дальний и средний хребты
DARK = "#073B4C"                          # силуэт, плашка, текст

c = ArtCanvas(W, H, bg=SKY_TOP, palette=[SKY_TOP, SUN, MID, FAR, DARK])
c.meta = {"prompt": "минималистичный постер про горы, яркие цвета",
          "style": "minimal-geometry", "seed": SEED}

# --- небо и модульная сетка (она живёт только на небе: фигуры её перекроют)
c.gradient([SKY_TOP, SKY_BOT], angle=90)
c.grid(step=100, color=DARK, alpha=0.05)

# --- солнце: хребты нарисуются поверх и подрежут его снизу
c.circle(835, 620, 175, SUN)

# --- три плана: дальний хребет, средний, ближний силуэт
c.polygon([(0, 935), (250, 655), (520, 935)], FAR)
c.polygon([(390, 935), (705, 605), (1015, 935)], MID)
c.polygon([(0, 935), (200, 805), (500, 885), (830, 700), (1200, 905),
           (1200, 1000), (0, 1000)], DARK)

# --- нижняя плашка
c.rect(0, 1000, W, H, "#06D6A0")

# --- типографика
sz = c.fit_size("ГОРЫ", 880, "display", start=330)
c.text(100, 1210, "ГОРЫ", family="display", size=sz, color=DARK, anchor="lm")
c.line([(100, 1400), (270, 1400)], SUN, width=8)
c.text(100, 1435, "яркий минимализм · dipkit", family="mono", size=30,
       color=DARK, alpha=0.7)

c.save(OUT)
print("готово:", OUT)
