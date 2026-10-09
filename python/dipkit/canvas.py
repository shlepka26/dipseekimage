# -*- coding: utf-8 -*-
"""dipkit.canvas — движок кодо-арта для проекта «ДИПСИК ХУДОЖНИК».

Идея: художник (DeepSeek) пишет короткий код, а этот модуль даёт ему
выразительные примитивы — градиенты, шум, свечение, слои, типографику, —
чтобы даже 30 строк давали картинку, а не цветной прямоугольник.

Устройство:
    _Painter   — общая логика рисования (примитивы, поля, эффекты).
                 Наследуется и холстом, и слоем, поэтому ЛЮБОЙ примитив
                 и ЛЮБОЙ эффект доступны в обоих режимах.
    Layer      — слой с premultiplied alpha, накладывается на холст.
    ArtCanvas  — холст: создаёт слои, композитит, сохраняет.

Пиксели хранятся в float32-массиве формы (H, W, 3) в диапазоне 0..1.
"""

from __future__ import annotations

import json
import math
import os
from typing import Sequence

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

__all__ = [
    "ArtCanvas", "Layer", "PALETTES", "DEFAULT_PALETTE", "hex2rgb",
    "lerp_colors", "fbm", "value_noise", "font", "find_font",
    "available_families", "covers", "resolve_family",
]

# --------------------------------------------------------------------------
# Шрифты
# --------------------------------------------------------------------------

_FONT_DIRS = [
    "/system/fonts",                  # Android
    "/system/fonts/noto",
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),   # Windows
    "/usr/share/fonts/truetype/dejavu",                              # Linux
    "/usr/share/fonts/truetype/liberation",
    os.path.expanduser("~/Library/Fonts"),                           # macOS
    "/System/Library/Fonts",
    os.path.expanduser("~/.fonts"),
]

#: Кандидаты по семействам. Первый существующий файл выигрывает, поэтому
#: на Android подхватятся Roboto/Noto, на Windows — Segoe/Impact.
_FONT_FILES: dict[str, list[str]] = {
    "sans":       ["Roboto-Regular.ttf", "segoeui.ttf", "arial.ttf",
                   "DejaVuSans.ttf", "Helvetica.ttc"],
    "sans-bold":  ["Roboto-Bold.ttf", "Roboto-Black.ttf", "segoeuib.ttf",
                   "arialbd.ttf", "DejaVuSans-Bold.ttf"],
    "sans-light": ["Roboto-Light.ttf", "segoeuil.ttf", "segoeui.ttf", "arial.ttf"],
    "serif":      ["NotoSerif-Regular.ttf", "georgia.ttf", "times.ttf",
                   "DejaVuSerif.ttf"],
    "serif-bold": ["NotoSerif-Bold.ttf", "georgiab.ttf", "timesbd.ttf",
                   "DejaVuSerif-Bold.ttf"],
    "mono":       ["DroidSansMono.ttf", "CutiveMono.ttf", "consola.ttf",
                   "cour.ttf", "DejaVuSansMono.ttf"],
    "mono-bold":  ["DroidSansMono.ttf", "consolab.ttf", "courbd.ttf",
                   "DejaVuSansMono-Bold.ttf"],
    "display":    ["Roboto-Black.ttf", "RobotoCondensed-Bold.ttf", "impact.ttf",
                   "segoeuib.ttf", "arialbd.ttf"],
    "script":     ["Roboto-Italic.ttf", "FRSCRIPT.TTF", "Inkfree.ttf", "segoeuis.ttf"],
    "hand":       ["Roboto-Italic.ttf", "Inkfree.ttf", "FRSCRIPT.TTF", "segoeui.ttf"],
    "narrow":     ["RobotoCondensed-Regular.ttf", "DroidSansMono.ttf",
                   "consola.ttf", "segoeui.ttf"],
}

#: Куда отступать, если в шрифте нет нужных глифов (например, кириллицы
#: в моноширинном DroidSansMono). Значение — другое семейство.
_FALLBACK_FAMILY = {
    "mono": "sans", "mono-bold": "sans-bold",
    "display": "sans-bold", "script": "sans", "hand": "sans", "narrow": "sans",
    "serif": "sans", "serif-bold": "sans-bold", "sans-light": "sans",
}


DEFAULT_PALETTE = ["#070b1a", "#1b2a5b", "#4f7cff", "#9fd0ff", "#f4f7ff"]

_FONT_CACHE: dict[str, str | None] = {}
_GLYPH_CACHE: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def find_font(family: str = "sans") -> str | None:
    """Путь к первому доступному файлу шрифта для семейства (или None)."""
    if family in _FONT_CACHE:
        return _FONT_CACHE[family]
    candidates = _FONT_FILES.get(family, [])
    if family.lower().endswith((".ttf", ".otf", ".ttc")):
        candidates = [family]
    found = None
    for name in candidates:
        for d in _FONT_DIRS:
            p = os.path.join(d, name)
            if os.path.exists(p):
                found = p
                break
        if found:
            break
    _FONT_CACHE[family] = found
    return found


def font(family: str = "sans", size: int = 48) -> ImageFont.FreeTypeFont:
    """Шрифт нужного размера (с кэшем и запасным встроенным вариантом)."""
    key = (family, int(size))
    if key in _GLYPH_CACHE:
        return _GLYPH_CACHE[key]
    path = find_font(family)
    f: ImageFont.FreeTypeFont
    try:
        f = ImageFont.truetype(path, int(size)) if path else ImageFont.load_default(int(size))
    except Exception:
        f = ImageFont.load_default(int(size))
    _GLYPH_CACHE[key] = f
    return f


def available_families() -> dict[str, str | None]:
    """Какие семейства шрифтов реально есть на машине."""
    return {k: find_font(k) for k in _FONT_FILES}


# --- покрытие глифов ------------------------------------------------------
# На Android нет Impact и French Script, а моноширинный DroidSansMono может не
# содержать кириллицы. Поэтому перед рисованием проверяем, что в шрифте есть
# все нужные символы, и при необходимости берём запасное семейство.

#: Приватная область Unicode — глифа почти наверняка нет ни в одном шрифте.
_PROBE_CHAR = "\ue000"
_COVER_CACHE: dict[tuple[str, str], bool] = {}


def _glyph_pixels(f: ImageFont.FreeTypeFont, ch: str) -> bytes:
    """Как выглядит символ в этом шрифте (для сравнения с «квадратиком» .notdef)."""
    img = Image.new("L", (48, 48), 0)
    ImageDraw.Draw(img).text((4, 4), ch, font=f, fill=255)
    return img.tobytes()


def covers(family: str, text: str) -> bool:
    """Есть ли в шрифте семейства глифы для всех символов текста."""
    key = (family, text)
    cached = _COVER_CACHE.get(key)
    if cached is not None:
        return cached
    if not find_font(family):
        _COVER_CACHE[key] = True          # встроенный шрифт — считаем годным
        return True
    try:
        f = font(family, 32)
        probe = _glyph_pixels(f, _PROBE_CHAR)
        ok = True
        for ch in dict.fromkeys(text):
            if ch.isspace():
                continue
            if _glyph_pixels(f, ch) == probe:   # тот же .notdef, что и у пробы
                ok = False
                break
    except Exception:
        ok = True
    _COVER_CACHE[key] = ok
    return ok


def resolve_family(family: str, text: str) -> str:
    """Семейство, которым реально можно нарисовать этот текст."""
    if covers(family, text):
        return family
    alt = _FALLBACK_FAMILY.get(family, "sans")
    if covers(alt, text):
        return alt
    return "sans"



# --------------------------------------------------------------------------
# Цвет и шум
# --------------------------------------------------------------------------

def hex2rgb(c) -> np.ndarray:
    """'#ff8800' | '#f80' | (r,g,b) | np.array -> np.array([r,g,b]) float32 0..1."""
    if isinstance(c, np.ndarray):
        return c.astype(np.float32).reshape(3)
    if isinstance(c, (tuple, list)):
        vals = [float(v) for v in c]
        if any(abs(v) > 1.0 for v in vals):      # запись в 0..255
            vals = [v / 255.0 for v in vals]
        return np.array(vals, dtype=np.float32)
    s = str(c).strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) in (6, 8):
        return np.array([int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], dtype=np.float32)
    raise ValueError(f"не понимаю цвет: {c!r}")


def lerp_colors(colors: Sequence, t: np.ndarray) -> np.ndarray:
    """Многоступенчатая интерполяция палитры по t (0..1). Результат (..., 3)."""
    stops = np.stack([hex2rgb(c) for c in colors])
    k = len(stops)
    if k == 1:
        return np.broadcast_to(stops[0], t.shape + (3,)).astype(np.float32)
    t = np.clip(t, 0.0, 1.0) * (k - 1)
    i0 = np.floor(t).astype(np.int32)
    i1 = np.minimum(i0 + 1, k - 1)
    frac = (t - i0)[..., None]
    return (stops[i0] * (1 - frac) + stops[i1] * frac).astype(np.float32)


def _upscale_smooth(a: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Апскейл float-поля (бикубика).

    Запасной путь через uint8 нужен для Android: если режим "F" там окажется
    недоступен, без него падал бы весь фрактальный шум (а на нём держатся
    эффекты noise и flow). Точность на запасном пути ниже, зато движок жив.
    """
    try:
        img = Image.fromarray(np.ascontiguousarray(a, dtype=np.float32), mode="F")
        return np.asarray(img.resize(size, Image.BICUBIC), dtype=np.float32)
    except Exception:
        u8 = np.clip(a * 255.0, 0, 255).astype(np.uint8)
        out = Image.fromarray(u8, "L").resize(size, Image.BICUBIC)
        return np.asarray(out, dtype=np.float32) / 255.0


def value_noise(w: int, h: int, cells: int, seed: int | None = None) -> np.ndarray:
    """Гладкий value-noise: случайная сетка cells x cells, растянутая бикубикой."""
    rng = np.random.default_rng(seed)
    cells = max(2, int(cells))
    return np.clip(_upscale_smooth(rng.random((cells, cells)).astype(np.float32), (w, h)), 0, 1)


def fbm(w: int, h: int, cells: int = 4, octaves: int = 5, gain: float = 0.5,
        lacunarity: float = 2.0, seed: int | None = None) -> np.ndarray:
    """Фрактальный шум (сумма октав) — облака, дым, рельеф, текстуры. Поле (H, W)."""
    rng = np.random.default_rng(seed)
    total = np.zeros((h, w), dtype=np.float32)
    amp, norm, c = 1.0, 0.0, float(cells)
    for _ in range(max(1, int(octaves))):
        s = int(rng.integers(0, 2 ** 31 - 1))
        total += amp * value_noise(w, h, max(2, int(round(c))), s)
        norm += amp
        amp *= gain
        c *= lacunarity
    return np.clip(total / max(norm, 1e-6), 0.0, 1.0)


def _blur2d(a: np.ndarray, radius: float) -> np.ndarray:
    """Гауссово размытие float-поля (с запасным путём через uint8)."""
    if radius <= 0.01:
        return a
    try:
        img = Image.fromarray(np.ascontiguousarray(a, dtype=np.float32), mode="F")
        return np.asarray(img.filter(ImageFilter.GaussianBlur(radius)), dtype=np.float32)
    except Exception:
        u8 = np.clip(a * 255.0, 0, 255).astype(np.uint8)
        return np.asarray(Image.fromarray(u8, "L").filter(ImageFilter.GaussianBlur(radius)),
                          dtype=np.float32) / 255.0


def _blur_rgb(px: np.ndarray, radius: float) -> np.ndarray:
    return np.stack([_blur2d(px[..., i], radius) for i in range(3)], -1)


# --------------------------------------------------------------------------
# Палитры
# --------------------------------------------------------------------------

PALETTES: dict[str, list[str]] = {
    "ink":       ["#0b0b0f", "#f4f1ea", "#c8452f", "#7a8ca3"],
    "midnight":  ["#070b1a", "#1b2a5b", "#4f7cff", "#9fd0ff", "#f4f7ff"],
    "sunset":    ["#2b1055", "#7597de", "#ff8c42", "#ffd166", "#fff3b0"],
    "risograph": ["#f6f1e5", "#1f4e79", "#e8552f", "#f2c14e"],
    "forest":    ["#0d1b12", "#1f4d33", "#5c9e63", "#c9e7a4", "#f3f7e8"],
    "neon":      ["#05010f", "#3a0ca3", "#f72585", "#4cc9f0", "#e0fbfc"],
    "paper":     ["#f7f3ec", "#e3dccd", "#2f2a25", "#b4553a"],
    "pastel":    ["#fdf6f0", "#ffd6e0", "#c1e1dc", "#ffe6a7", "#b8b8ff"],
    "desert":    ["#2b1d14", "#8c5a2b", "#d9a15b", "#f0d9a8", "#fdf3e3"],
    "ocean":     ["#02121f", "#04395e", "#0f7a8c", "#4fd1c5", "#e8fffe"],
    "ember":     ["#0a0505", "#3d0c02", "#a6260f", "#e8622c", "#ffc46b"],
    "blueprint": ["#0b2545", "#13315c", "#8da9c4", "#eef4ed"],
    "mono":      ["#000000", "#404040", "#808080", "#c0c0c0", "#ffffff"],
}

_SEED_COUNTER = [0]


def _fresh_seed() -> int:
    _SEED_COUNTER[0] += 1
    return int(np.random.SeedSequence(_SEED_COUNTER[0]).entropy % (2 ** 31))


# --------------------------------------------------------------------------
# _Painter — всё, что умеет рисовать
# --------------------------------------------------------------------------

class _Painter:
    """Общая логика рисования. Наследник обязан дать w, h, px и _paint()."""

    w: int
    h: int
    px: np.ndarray
    a: np.ndarray | None
    palette: list[str]

    # --- точки расширения -------------------------------------------------
    def _paint(self, color: np.ndarray, cov: np.ndarray) -> None:
        raise NotImplementedError

    def col(self, c) -> np.ndarray:
        """Цвет: '#hex', индекс палитры (int), '@2' или имя палитры."""
        if isinstance(c, str) and not c.startswith("#") and c in PALETTES:
            return hex2rgb(PALETTES[c][0])
        if isinstance(c, int) and not isinstance(c, bool):
            return hex2rgb(self.palette[c % len(self.palette)])
        if isinstance(c, str) and c.startswith("@"):
            return hex2rgb(self.palette[int(c[1:]) % len(self.palette)])
        return hex2rgb(c)

    def _rng(self, seed=None) -> np.random.Generator:
        return np.random.default_rng(_fresh_seed() if seed is None else int(seed))

    # --- маски ------------------------------------------------------------
    def _mask(self, fn, size: tuple[int, int] | None = None) -> np.ndarray:
        m = Image.new("L", size or (self.w, self.h), 0)
        fn(ImageDraw.Draw(m))
        return np.asarray(m, dtype=np.float32) / 255.0

    # --- фигуры -----------------------------------------------------------
    def _shape(self, kind: str, args: tuple, color, alpha=1.0, width=0,
               antialias=True) -> None:
        col = self.col(color)
        use_ss = bool(antialias) and kind in ("ellipse", "circle", "polygon",
                                              "line", "arc", "wedge")
        ss = 2 if use_ss else 1
        if ss == 1:
            mask = self._mask(lambda d: self._draw(d, kind, args, width, 1.0))
        else:
            small = Image.new("L", (max(1, self.w // ss), max(1, self.h // ss)), 0)
            self._draw(ImageDraw.Draw(small), kind, args, width, 1.0 / ss)
            mask = np.asarray(small.resize((self.w, self.h), Image.LANCZOS),
                              dtype=np.float32) / 255.0
        self._paint(col, mask * float(alpha))

    @staticmethod
    def _draw(d: ImageDraw.ImageDraw, kind: str, args: tuple, width, k: float) -> None:
        v = [x * k for x in args]
        wd = max(1, int(round(width * k))) if width else 0
        if kind == "rect":
            d.rectangle(v[:4], fill=255, width=wd)
        elif kind == "ellipse":
            d.ellipse(v[:4], fill=255, width=wd)
        elif kind == "polygon":
            d.polygon(v, fill=255)
        elif kind == "line":
            d.line(v, fill=255, width=max(1, wd))
        elif kind == "arc":
            d.arc(tuple(v[:4]), v[4], v[5], fill=255, width=max(1, wd))
        elif kind == "wedge":
            d.pieslice(tuple(v[:4]), v[4], v[5], fill=255)
        else:
            raise ValueError(f"неизвестная фигура: {kind}")

    def rect(self, x0, y0, x1, y1, color, alpha=1.0, width=0, antialias=True):
        self._shape("rect", (x0, y0, x1, y1), color, alpha, width, antialias); return self

    def ellipse(self, x0, y0, x1, y1, color, alpha=1.0, width=0, antialias=True):
        self._shape("ellipse", (x0, y0, x1, y1), color, alpha, width, antialias); return self

    def circle(self, cx, cy, r, color, **kw):
        return self.ellipse(cx - r, cy - r, cx + r, cy + r, color, **kw)

    def ring(self, cx, cy, r, color, width=8, **kw):
        return self.ellipse(cx - r, cy - r, cx + r, cy + r, color, width=width, **kw)

    def polygon(self, points, color, alpha=1.0, antialias=True):
        flat = tuple(v for p in points for v in p)
        self._shape("polygon", flat, color, alpha, 0, antialias); return self

    def line(self, points, color, width=4, alpha=1.0, antialias=True):
        flat = tuple(v for p in points for v in p)
        self._shape("line", flat, color, alpha, width, antialias); return self

    def arc(self, x0, y0, x1, y1, start, end, color, width=6, alpha=1.0):
        self._shape("arc", (x0, y0, x1, y1, start, end), color, alpha, width); return self

    def wedge(self, x0, y0, x1, y1, start, end, color, alpha=1.0):
        self._shape("wedge", (x0, y0, x1, y1, start, end), color, alpha); return self

    def grid(self, step=80, color="#ffffff", alpha=0.08, width=1, offset=0):
        """Сетка одной маской (быстро, в отличие от поэтапных линий)."""
        def draw(d):
            for x in range(offset, self.w, step):
                d.line([(x, 0), (x, self.h)], fill=255, width=max(1, width))
            for y in range(offset, self.h, step):
                d.line([(0, y), (self.w, y)], fill=255, width=max(1, width))
        self._paint(self.col(color), self._mask(draw) * float(alpha))
        return self

    def scatter(self, count=400, color="#ffffff", r=(1, 4), alpha=0.7,
                region=None, seed=None, glow=0.0, spread=None):
        """Случайные точки; glow>0 размывает их — получается «звёздная пыль»."""
        rng = self._rng(seed)
        x0, y0, x1, y1 = region or (0, 0, self.w, self.h)
        n = int(count)
        xs = rng.uniform(x0, x1, n)
        ys = rng.uniform(y0, y1, n)
        rs = rng.uniform(r[0], r[1], n)
        if spread is not None:                      # разброс яркости/размера
            rs = rs * rng.uniform(spread[0], spread[1], n)

        def draw(d):
            for x, y, rr in zip(xs, ys, rs):
                d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=255)
        mask = self._mask(draw)
        if glow:
            mask = _blur2d(mask, glow)
        self._paint(self.col(color), mask * float(alpha))
        return self

    # --- текст ------------------------------------------------------------
    def text(self, x, y, text, family="sans", size=48, color="#ffffff",
             alpha=1.0, anchor="la", align="left", spacing=6, stroke=0,
             stroke_color="#000000", stroke_alpha=None):
        """Текст. stroke>0 рисует обводку цветом stroke_color ПОД заливкой."""
        f = font(resolve_family(family, text), int(size))

        def render(width: int) -> np.ndarray:
            m = Image.new("L", (self.w, self.h), 0)
            d = ImageDraw.Draw(m)
            kw = dict(stroke_width=width, stroke_fill=255) if width else {}
            if "\n" in text:
                d.multiline_text((x, y), text, font=f, fill=255, anchor=anchor,
                                 align=align, spacing=spacing, **kw)
            else:
                d.text((x, y), text, font=f, fill=255, anchor=anchor, **kw)
            return np.asarray(m, np.float32) / 255.0

        if stroke:
            sa = float(alpha) if stroke_alpha is None else float(stroke_alpha)
            self._paint(self.col(stroke_color), render(int(stroke)) * sa)
        self._paint(self.col(color), render(0) * float(alpha))
        return self

    def measure(self, text, family="sans", size=48, spacing=6) -> tuple[int, int]:
        """Ширина и высота текста в пикселях."""
        f = font(resolve_family(family, text), int(size))
        d = ImageDraw.Draw(Image.new("L", (8, 8)))
        box = (d.multiline_textbbox((0, 0), text, font=f, spacing=spacing)
               if "\n" in text else d.textbbox((0, 0), text, font=f))
        return int(box[2] - box[0]), int(box[3] - box[1])

    def fit_size(self, text, max_width, family="sans", start=400, floor=6) -> int:
        """Максимальный размер шрифта, при котором текст влезает в max_width."""
        lo, hi, best = int(floor), int(start), int(floor)
        while lo <= hi:
            mid = (lo + hi) // 2
            if self.measure(text, family, mid)[0] <= max_width:
                best, lo = mid, mid + 1
            else:
                hi = mid - 1
        return best

    def text_center(self, text, y=None, family="sans", size=48, color="#ffffff",
                    alpha=1.0, stroke=0, stroke_color="#000000", spacing=6):
        tw, th = self.measure(text, family, size, spacing)
        x = (self.w - tw) // 2
        yy = (self.h - th) // 2 if y is None else int(y)
        return self.text(x, yy, text, family, size, color, alpha, "la", "left",
                         spacing, stroke, stroke_color)

    def text_fit(self, text, max_width=0.9, y=None, family="sans", size=400,
                 color="#ffffff", alpha=1.0, stroke=0, stroke_color="#000000"):
        """Заголовок, автоматически вписанный в ширину (доля холста или пиксели)."""
        mw = int(max_width * self.w) if max_width <= 1.0 else int(max_width)
        return self.text_center(text, y, family, self.fit_size(text, mw, family, size),
                                color, alpha, stroke, stroke_color)

    # --- поля -------------------------------------------------------------
    def paint_field(self, colors, cov=1.0):
        """Закрасить поле: colors — (H,W,3) или один цвет; cov — число или (H,W)."""
        col = hex2rgb(colors) if isinstance(colors, (str, tuple, np.ndarray)) else np.asarray(colors, np.float32)
        cov_arr = (np.full((self.h, self.w), float(cov), np.float32)
                   if np.isscalar(cov) else cov.astype(np.float32))
        self._paint(col, cov_arr)
        return self

    def fill(self, color, alpha=1.0):
        return self.paint_field(color, alpha)

    def _uv(self) -> tuple[np.ndarray, np.ndarray]:
        ys, xs = np.mgrid[0:self.h, 0:self.w]
        return xs.astype(np.float32), ys.astype(np.float32)

    def gradient(self, colors, angle=90.0, cov=1.0, stops=None):
        """Линейный градиент по палитре под углом (0 = слева направо)."""
        cols = [colors, "#000000"] if isinstance(colors, (str, tuple, np.ndarray)) else list(colors)
        xs, ys = self._uv()
        u, v = xs / max(self.w - 1, 1), ys / max(self.h - 1, 1)
        rad = math.radians(float(angle))
        t = u * math.cos(rad) + v * math.sin(rad)
        t = (t - t.min()) / max(t.max() - t.min(), 1e-6)
        if stops is not None:
            t = np.interp(t, np.linspace(0, 1, len(stops)), np.asarray(stops, np.float32))
        self._paint(lerp_colors(cols, t),
                    np.full((self.h, self.w), float(cov), np.float32))
        return self

    def radial(self, colors, center=(0.5, 0.5), radius=None, falloff=1.0, cov=1.0):
        """Радиальный градиент: colors[0] в центре -> colors[-1] на краю."""
        cols = [colors, "#000000"] if isinstance(colors, (str, tuple, np.ndarray)) else list(colors)
        xs, ys = self._uv()
        cx, cy = center[0] * self.w, center[1] * self.h
        r = float(radius) if radius else math.hypot(self.w, self.h) * 0.6
        d = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2) / max(r, 1e-6)
        t = np.clip(d, 0.0, 1.0) ** max(float(falloff), 1e-3)
        self._paint(lerp_colors(cols, t),
                    np.full((self.h, self.w), float(cov), np.float32))
        return self

    def blobs(self, count=6, colors=("#4cc9f0", "#f72585"), r=(180, 480),
              alpha=0.35, seed=None, additive=True, falloff=1.6, softness=0.0):
        """Мягкие цветные пятна — самый надёжный способ получить «красиво»."""
        rng = self._rng(seed)
        if isinstance(colors, str):
            colors = [colors]
        xs, ys = self._uv()
        for i in range(int(count)):
            cx = float(rng.uniform(0.05, 0.95)) * self.w
            cy = float(rng.uniform(0.05, 0.95)) * self.h
            rr = max(1e-6, float(rng.uniform(r[0], r[1])))
            m = np.clip(1.0 - np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2) / rr, 0.0, 1.0) ** falloff
            if softness:
                m = _blur2d(m, softness)
            col = self.col(colors[i % len(colors)])
            if additive and self.a is None:
                self.px = np.clip(self.px + col * (m * alpha)[..., None], 0.0, None)
            else:
                self._paint(col, m * alpha)
        return self

    def light(self, cx, cy, radius, color="#ffffff", intensity=0.5,
              falloff=2.0, additive=True):
        """Мягкий источник света в заданной точке — луна, лампа, свечение.

        В отличие от radial() не заливает весь холст, а подсвечивает вокруг
        точки. Главный приём для «светящихся» картин.
        """
        xs, ys = self._uv()
        m = np.clip(1.0 - np.sqrt((xs - float(cx)) ** 2 + (ys - float(cy)) ** 2)
                    / max(1e-6, float(radius)), 0.0, 1.0) ** max(1e-3, float(falloff))
        col = self.col(color)
        if additive and self.a is None:
            self.px = np.clip(self.px + col * (m * intensity)[..., None], 0.0, None)
        else:
            self._paint(col, m * intensity)
        return self

    def noise(self, amount=0.35, scale=3, octaves=5, seed=None, colorize=None,
              softness=0.0, cov=1.0):
        """Фрактальный шум: как текстура (яркость) или как цвет из палитры."""
        f = fbm(self.w, self.h, scale, octaves, seed=seed)
        if softness:
            f = _blur2d(f, softness)
        if colorize:
            self._paint(lerp_colors(colorize, f), np.clip(f * amount, 0.0, 1.0) * cov)
        else:
            self._paint(np.ones(3, np.float32), np.clip(f * amount, 0.0, 1.0) * cov)
        return self

    def noise_field(self, scale=3, octaves=5, seed=None, softness=0.0) -> np.ndarray:
        """Сырое поле шума (H, W) — для собственной логики художника."""
        f = fbm(self.w, self.h, scale, octaves, seed=seed)
        return _blur2d(f, softness) if softness else f

    def flow(self, colors=("#4cc9f0", "#f72585"), lines=180, steps=140, scale=3,
             width=2, alpha=0.55, seed=None, angle_offset=0.0, margin=0.0,
             curl=2.2, additive=True, both_dirs=False):
        """Линии вдоль поля шума (flow field) — генеративная классика."""
        rng = self._rng(seed)
        field = _blur2d(fbm(self.w, self.h, scale, 4, seed=int(rng.integers(0, 2 ** 31 - 1))),
                        max(self.w, self.h) * 0.02)
        ang = field * math.pi * curl + math.radians(angle_offset)
        dx, dy = np.cos(ang), np.sin(ang)
        if isinstance(colors, str):
            colors = [colors]
        pad = margin * min(self.w, self.h)
        pts_all: list[list[tuple[float, float]]] = []
        for _ in range(int(lines)):
            x0 = float(rng.uniform(pad, self.w - 1 - pad))
            y0 = float(rng.uniform(pad, self.h - 1 - pad))
            for direction in ((1,) if not both_dirs else (1, -1)):
                x, y = x0, y0
                pts = []
                for _ in range(int(steps)):
                    xi = int(np.clip(x, 0, self.w - 1))
                    yi = int(np.clip(y, 0, self.h - 1))
                    pts.append((x, y))
                    x += direction * dx[yi, xi] * 2.4
                    y += direction * dy[yi, xi] * 2.4
                    if not (0 <= x < self.w and 0 <= y < self.h):
                        break
                if len(pts) > 1:
                    pts_all.append(pts)

        def draw(d):
            for pts in pts_all:
                d.line(pts, fill=255, width=max(1, int(width)))
        mask = self._mask(draw)
        col = (lerp_colors(list(colors), rng.random()) if len(colors) > 1
               else self.col(colors[0]))
        if additive and self.a is None:
            self.px = np.clip(self.px + col * (mask * alpha)[..., None], 0.0, None)
        else:
            self._paint(col, mask * alpha)
        return self

    def scanlines(self, spacing=4, strength=0.14, angle=0.0, color="#000000"):
        xs, ys = self._uv()
        rad = math.radians(angle)
        coord = xs * math.cos(rad) + ys * math.sin(rad)
        band = 0.5 + 0.5 * np.cos(coord * (2 * math.pi / max(1, spacing)))
        self._paint(self.col(color), (band ** 1.5) * strength)
        return self

    def quantize_to_palette(self, colors=None):
        """Ограничить картинку палитрой — даёт «плакатный» вид."""
        cols = np.stack([hex2rgb(c) for c in (colors or self.palette)])
        flat = self.px.reshape(-1, 3)
        d = ((flat[:, None, :] - cols[None, :, :]) ** 2).sum(-1)
        self.px = cols[d.argmin(1)].reshape(self.h, self.w, 3)
        return self

    # --- эффекты (работают и на холсте, и на слое) ------------------------
    def blur(self, radius=4.0):
        self.px = _blur_rgb(self.px, radius)
        if self.a is not None:
            self.a = _blur2d(self.a, radius)
        return self

    def glow(self, radius=24.0, intensity=0.6):
        """Добавить свечение из собственных пикселей."""
        b = _blur_rgb(self.px, radius)
        self.px = np.clip(self.px + b * intensity, 0.0, None)
        if self.a is not None:
            self.a = np.clip(self.a + _blur2d(self.a, radius) * intensity * 0.5, 0.0, 1.0)
        return self

    def bloom(self, threshold=0.72, radius=26.0, intensity=0.55):
        """Мягкое свечение из ярких участков — «дорогой» вид."""
        lum = self.px.mean(axis=2)
        hi = np.clip((lum - threshold) / max(1e-6, 1.0 - threshold), 0, 1)[..., None]
        self.px = np.clip(self.px + _blur_rgb(self.px * hi, radius) * intensity, 0.0, 1.0)
        return self

    def vignette(self, strength=0.45, power=1.8):
        xs, ys = self._uv()
        cx, cy = self.w / 2.0, self.h / 2.0
        d = np.sqrt(((xs - cx) / cx) ** 2 + ((ys - cy) / cy) ** 2) / math.sqrt(2)
        self.px = np.clip(self.px * (1.0 - np.clip(d, 0, 1) ** power * strength)[..., None],
                          0.0, 1.0)
        return self

    def grain(self, amount=0.05, mono=True, seed=None, softness=0.0):
        rng = self._rng(seed)
        if mono:
            n = rng.normal(0.0, 1.0, (self.h, self.w)).astype(np.float32)
            if softness:
                n = _blur2d(n, softness)
            self.px = np.clip(self.px + n[..., None] * amount, 0.0, 1.0)
        else:
            n = rng.normal(0.0, 1.0, (self.h, self.w, 3)).astype(np.float32)
            if softness:
                n = _blur_rgb(n, softness)
            self.px = np.clip(self.px + n * amount, 0.0, 1.0)
        return self

    def posterize(self, levels=6):
        q = 255.0 / max(1, int(levels) - 1)
        self.px = np.clip(np.round(self.px * 255.0 / q) * q / 255.0, 0.0, 1.0)
        return self

    def contrast(self, amount=1.2):
        self.px = np.clip((self.px - 0.5) * float(amount) + 0.5, 0.0, 1.0)
        return self

    def brightness(self, amount=0.05):
        self.px = np.clip(self.px + float(amount), 0.0, 1.0)
        return self

    def saturate(self, amount=1.2):
        lum = self.px.mean(axis=2, keepdims=True)
        self.px = np.clip(lum + (self.px - lum) * float(amount), 0.0, 1.0)
        return self

    def duotone(self, dark="#0b0b1a", light="#ffd166", amount=1.0):
        """Перекрасить по яркости в два цвета."""
        lum = self.px.mean(axis=2)
        self.px = np.clip(self.px * (1 - amount) + lerp_colors([dark, light], lum) * amount,
                          0.0, 1.0)
        return self

    def invert(self):
        self.px = 1.0 - self.px
        return self

    def chromatic(self, shift=4):
        """Хроматическая аберрация — сдвиг красного и синего каналов."""
        s = int(shift)
        if s == 0:
            return self
        self.px = np.stack([np.roll(self.px[..., 0], s, axis=1),
                            self.px[..., 1],
                            np.roll(self.px[..., 2], -s, axis=1)], -1)
        return self

    def pixelate(self, block=8):
        """Пиксель-арт: уменьшить и вернуть без сглаживания."""
        b = max(1, int(block))
        sw, sh = max(1, self.w // b), max(1, self.h // b)
        img = Image.fromarray((np.clip(self.px, 0, 1) * 255).astype(np.uint8))
        self.px = np.asarray(img.resize((sw, sh), Image.BILINEAR)
                             .resize((self.w, self.h), Image.NEAREST), np.float32) / 255.0
        if self.a is not None:
            am = Image.fromarray((np.clip(self.a, 0, 1) * 255).astype(np.uint8), "L")
            self.a = np.asarray(am.resize((sw, sh), Image.BILINEAR)
                                .resize((self.w, self.h), Image.NEAREST), np.float32) / 255.0
        return self


# --------------------------------------------------------------------------
# Слой
# --------------------------------------------------------------------------

class Layer(_Painter):
    """Слой с premultiplied alpha. Рисуем в него, потом холст накладывает его."""

    def __init__(self, width: int, height: int, canvas: "ArtCanvas", name: str = "layer"):
        self.w, self.h = width, height
        self.canvas = canvas
        self.palette = canvas.palette
        self.px = np.zeros((height, width, 3), dtype=np.float32)   # premultiplied
        self.a = np.zeros((height, width), dtype=np.float32)       # покрытие
        self.name = name

    def _paint(self, color: np.ndarray, cov: np.ndarray) -> None:
        cov = np.clip(cov, 0.0, 1.0).astype(np.float32)
        c = cov[..., None]
        self.px = color.astype(np.float32) * c + self.px * (1.0 - c)
        self.a = cov + self.a * (1.0 - c[..., 0])

    def __repr__(self) -> str:
        return f"<Layer {self.name} {self.w}x{self.h}>"


# --------------------------------------------------------------------------
# Холст
# --------------------------------------------------------------------------

class ArtCanvas(_Painter):
    """Холст для рисования кодом.

    Пример:
        c = ArtCanvas(1400, 1000, bg="#0a0a12", palette="neon")
        c.gradient(["#3a0ca3", "#f72585"], angle=60)
        c.blobs(6, ["#4cc9f0", "#f72585"], r=(200, 520), alpha=0.3)
        c.text_fit("DIPSEEK", family="display", color="#fff")
        c.vignette().grain(0.04)
        c.save("art/works/demo/art.png")
    """

    def __init__(self, width: int = 1200, height: int = 1200,
                 bg="#0b0b0f", palette=None, scale: int = 1):
        self.w = int(width) * int(scale)
        self.h = int(height) * int(scale)
        self.scale = int(scale)
        self.px = np.zeros((self.h, self.w, 3), dtype=np.float32)
        self.px[:] = hex2rgb(bg)
        self.a = None                                    # холст непрозрачный
        if palette is None:
            self.palette = list(DEFAULT_PALETTE)
        elif isinstance(palette, str):
            self.palette = list(PALETTES.get(palette, DEFAULT_PALETTE))
        else:
            self.palette = list(palette)
        self.layers: list[Layer] = []
        self.meta: dict = {}

    # --- служебное --------------------------------------------------------
    @property
    def size(self) -> tuple[int, int]:
        return self.w, self.h

    def new_layer(self, name: str = "layer") -> Layer:
        L = Layer(self.w, self.h, self, name)
        self.layers.append(L)
        return L

    def flatten(self) -> "ArtCanvas":
        """Наложить все слои на холст и очистить список."""
        for L in self.layers:
            la = L.a[..., None]
            self.px = np.clip(L.px + self.px * (1.0 - la), 0.0, None)
        self.layers = []
        return self

    def _paint(self, color: np.ndarray, cov: np.ndarray) -> None:
        cov = np.clip(cov, 0.0, 1.0).astype(np.float32)
        self.px = self.px * (1.0 - cov[..., None]) + color.astype(np.float32) * cov[..., None]

    def crop_fraction(self, left=0.0, top=0.0, right=1.0, bottom=1.0):
        x0, y0 = int(left * self.w), int(top * self.h)
        x1, y1 = int(right * self.w), int(bottom * self.h)
        self.px = self.px[y0:y1, x0:x1]
        self.h, self.w = self.px.shape[:2]
        return self

    def resize(self, width: int, height: int, resample: str = "lanczos"):
        """Изменить размер готовой картинки. resample: 'lanczos' | 'nearest'."""
        img = Image.fromarray((np.clip(self.px, 0, 1) * 255).astype(np.uint8))
        flt = Image.NEAREST if resample == "nearest" else Image.LANCZOS
        img = img.resize((int(width), int(height)), flt)
        self.px = np.asarray(img, np.float32) / 255.0
        self.w, self.h = int(width), int(height)
        return self

    def upscale(self, factor: int = 8, resample: str = "nearest"):
        """Увеличить картинку (для пиксель-арта: factor=8, resample='nearest')."""
        return self.resize(self.w * int(factor), self.h * int(factor), resample)


    def __repr__(self) -> str:
        return f"<ArtCanvas {self.w}x{self.h} layers={len(self.layers)}>"

    # --- вывод ------------------------------------------------------------
    def to_image(self) -> Image.Image:
        if self.layers:
            self.flatten()
        return Image.fromarray((np.clip(self.px, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8))

    def save(self, path: str, meta: dict | None = None, thumb: int | None = 512) -> str:
        """Сохранить PNG + миниатюру + sidecar .json с метаданными."""
        if self.layers:
            self.flatten()
        path = os.path.abspath(path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        img = self.to_image()
        img.save(path)
        info = {"width": self.w, "height": self.h, "file": os.path.basename(path)}
        info.update(self.meta)
        info.update(meta or {})
        try:
            with open(os.path.splitext(path)[0] + ".json", "w", encoding="utf-8") as fh:
                json.dump(info, fh, ensure_ascii=False, indent=2)
        except Exception:
            pass
        if thumb:
            t = img.copy()
            t.thumbnail((thumb, thumb), Image.LANCZOS)
            t.save(os.path.splitext(path)[0] + ".thumb.png")
        return path

    def show(self):
        self.to_image().show()
