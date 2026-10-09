# -*- coding: utf-8 -*-
"""dipkit — набор инструментов для рисования кодом (проект «ДИПСИК ХУДОЖНИК»).

Один и тот же код работает и на ПК, и внутри Android-приложения (Chaquopy):

    canvas   — ArtCanvas/Layer: градиенты, шум, фигуры, текст, эффекты
    styles   — 11 стилей с рецептами для художника
    runner   — запуск работы (work.py): subprocess на ПК, exec на Android
    gallery  — индекс работ и контактный лист
    brain    — клиент DeepSeek API (нужен ключ; опционально)
    paths    — где что лежит на ПК и на Android

Быстрый старт:
    from dipkit import ArtCanvas
    c = ArtCanvas(1200, 1600, palette="neon")
    c.gradient(["#3a0ca3", "#f72585"], angle=70)
    c.blobs(8, ["#4cc9f0", "#f72585"], alpha=0.3)
    c.bloom().vignette().grain(0.04)
    c.save("art/works/demo/art.png")
"""

from .canvas import (  # noqa: F401
    ArtCanvas,
    Layer,
    PALETTES,
    available_families,
    covers,
    fbm,
    find_font,
    font,
    hex2rgb,
    lerp_colors,
    resolve_family,
    value_noise,
)
from .paths import (  # noqa: F401
    IS_ANDROID,
    data_root,
    platform_name,
    project_root,
    python_dir,
    works_dir,
)

__version__ = "0.2.0"
__all__ = [
    "ArtCanvas", "Layer", "PALETTES", "hex2rgb", "lerp_colors",
    "fbm", "value_noise", "font", "find_font", "available_families",
    "covers", "resolve_family",
    "IS_ANDROID", "data_root", "project_root", "python_dir", "works_dir",
    "platform_name",
    "__version__",
]
