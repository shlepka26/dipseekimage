# -*- coding: utf-8 -*-
"""Нарисовать иконку приложения движком dipkit.

Иконка рисуется тем же кодом, что и картины — отдельный повод убедиться,
что рендер работает. Скрипт создаёт:

* mipmap-*/ic_launcher.png        — обычная иконка (для Android < 8)
* mipmap-*/ic_launcher_round.png  — круглая (RGBA с прозрачностью)
* mipmap-*/ic_launcher_foreground.png — слой для адаптивной иконки Android 8+
* art/icon-preview.png            — превью 512 px, чтобы посмотреть глазами

Запуск: .\\dip.cmd icons
"""

from __future__ import annotations

import os
import shutil
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "python"))

from dipkit import ArtCanvas  # noqa: E402

RES = os.path.join(ROOT, "android", "app", "src", "main", "res")
WORK = os.path.join(ROOT, "art", "_icons")

#: Плотности Android: имя папки -> размер обычной иконки, размер слоя адаптивной.
DENSITIES = {
    "mdpi": (48, 108),
    "hdpi": (72, 162),
    "xhdpi": (96, 216),
    "xxhdpi": (144, 324),
    "xxxhdpi": (192, 432),
}

S = 512          # рисуем в большом размере, потом уменьшаем — так чище края


def draw_icon(path: str, inner: float) -> str:
    """Мотив «горы и солнце». inner — какую долю холста занимает рисунок."""
    c = ArtCanvas(S, S, bg="#0B0B10", palette="neon")
    c.gradient(["#2A1152", "#0B0B10"], angle=105)
    c.light(S * 0.68, S * 0.38, S * 0.58, "#F72585", intensity=0.42, falloff=2.4)

    half = inner / 2.0
    left, right = S * (0.5 - half), S * (0.5 + half)
    top, bottom = S * (0.5 - half), S * (0.5 + half)
    w, h = right - left, bottom - top

    # солнце
    c.circle(left + w * 0.70, top + h * 0.33, w * 0.16, "#F72585")
    # дальняя гора
    c.polygon([(left, bottom),
               (left + w * 0.30, top + h * 0.47),
               (left + w * 0.62, bottom)], "#4CC9F0")
    # ближняя гора
    c.polygon([(left + w * 0.33, bottom),
               (left + w * 0.66, top + h * 0.27),
               (right, bottom)], "#E0FBFC")
    c.save(path, thumb=None)
    return path


def circular(src: str, dst: str) -> None:
    """Круглая иконка: обрезаем квадрат кругом и сохраняем с прозрачностью."""
    img = Image.open(src).convert("RGBA")
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, img.size[0] - 1, img.size[1] - 1), fill=255)
    img.putalpha(mask)
    img.save(dst)


def main() -> int:
    os.makedirs(WORK, exist_ok=True)
    if not os.path.isdir(RES):
        print(f"нет папки ресурсов: {RES}")
        return 1

    base = draw_icon(os.path.join(WORK, "base.png"), inner=0.94)
    fg = draw_icon(os.path.join(WORK, "foreground.png"), inner=0.62)
    for extra in (".json",):
        p = os.path.splitext(base)[0] + extra
        if os.path.exists(p):
            os.remove(p)

    made: list[str] = []
    for density, (legacy_px, fg_px) in DENSITIES.items():
        folder = os.path.join(RES, f"mipmap-{density}")
        os.makedirs(folder, exist_ok=True)

        legacy = os.path.join(folder, "ic_launcher.png")
        Image.open(base).convert("RGB").resize((legacy_px, legacy_px), Image.LANCZOS) \
            .save(legacy)
        made.append(legacy)

        round_png = os.path.join(folder, "ic_launcher_round.png")
        tmp = os.path.join(WORK, f"round-{density}.png")
        Image.open(base).convert("RGB").resize((legacy_px, legacy_px), Image.LANCZOS) \
            .save(tmp)
        circular(tmp, round_png)
        made.append(round_png)

        fg_out = os.path.join(folder, "ic_launcher_foreground.png")
        Image.open(fg).convert("RGB").resize((fg_px, fg_px), Image.LANCZOS).save(fg_out)
        made.append(fg_out)

    preview = os.path.join(ROOT, "art", "icon-preview.png")
    Image.open(base).convert("RGB").resize((512, 512), Image.LANCZOS).save(preview)
    made.append(preview)

    print(f"готово: {len(made)} файлов")
    for p in made:
        print(f"  {p.replace(ROOT + os.sep, '')}  ({os.path.getsize(p)} Б)")
    shutil.rmtree(WORK, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
