# -*- coding: utf-8 -*-
"""dipkit.gallery — индекс работ и контактный лист.

Контактный лист — одна картинка со всеми работами: удобно окинуть взглядом
всё, что нарисовано, не открывая десяток файлов.
"""

from __future__ import annotations

import os
from datetime import datetime

from PIL import Image, ImageDraw

from .canvas import font
from .paths import data_root
from .runner import list_works

DEFAULT_OUT_NAME = os.path.join("art", "index.png")


def default_out() -> str:
    """Путь контактного листа.

    Считается лениво, а не на импорте: на Android `os.environ["HOME"]`
    появляется только после старта Python, и взятое заранее значение
    оказалось бы неверным.
    """
    return os.path.join(data_root(), DEFAULT_OUT_NAME)


def contact_sheet(out: str | None = None, cols: int = 4, cell: int = 440,
                  bg: str = "#12141a", pad: int = 18, caption: int = 34,
                  max_items: int = 40) -> str | None:
    """Собрать контактный лист из art/works/*/art.png. Вернуть путь или None."""
    out = out or default_out()
    works = [w for w in list_works() if w["png"]][:max_items]
    if not works:
        return None

    cols = max(1, int(cols))
    rows = (len(works) + cols - 1) // cols
    cw = cell + pad
    ch = cell + caption + pad
    sheet = Image.new("RGB", (cols * cw + pad, rows * ch + pad), bg)
    draw = ImageDraw.Draw(sheet)
    f_title = font("sans-bold", 18)
    f_sub = font("mono", 15)

    for i, w in enumerate(works):
        r, c = divmod(i, cols)
        x = pad + c * cw
        y = pad + r * ch
        try:
            im = Image.open(w["png"]).convert("RGB")
        except Exception:
            continue
        im.thumbnail((cell, cell), Image.LANCZOS)
        # вписываем в клетку по центру
        ox = x + (cell - im.width) // 2
        oy = y + (cell - im.height) // 2
        sheet.paste(im, (ox, oy))
        draw.rectangle((x, y, x + cell, y + cell), outline="#2a2f3a", width=1)

        meta = w["meta"] or {}
        title = (meta.get("prompt") or w["name"])[:46]
        style = meta.get("style") or "-"
        draw.text((x + 2, y + cell + 6), title, font=f_title, fill="#e8ecf4")
        draw.text((x + 2, y + cell + 6 + 20), f"{style}  ·  {w['name'][:22]}",
                  font=f_sub, fill="#7d8899")

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    sheet.save(out)
    return os.path.abspath(out)


def text_index(limit: int = 60) -> str:
    """Текстовый список работ для консоли."""
    works = list_works()[:limit]
    if not works:
        return "Работ пока нет. Создай первую: .\\dip.cmd new \"описание\" --style neon-glow"
    lines = [f"Работ: {len(list_works())} (показаны последние {len(works)})", ""]
    for w in works:
        meta = w["meta"] or {}
        when = meta.get("created") or datetime.fromtimestamp(w["mtime"]).strftime("%Y-%m-%d %H:%M")
        mark = "ok " if w["png"] else "!! "
        secs = meta.get("seconds")
        dur = f"{secs:g}s" if isinstance(secs, (int, float)) else "-"
        prompt = (meta.get("prompt") or "")[:40]
        lines.append(f"  {mark} {w['name']:<38} {when:<17} {dur:>6}  {prompt}")
    return "\n".join(lines)


def open_work(name_or_path: str) -> str | None:
    """Найти PNG работы по части имени папки."""
    works = list_works()
    for w in works:
        if name_or_path in w["name"] and w["png"]:
            return w["png"]
    return None
