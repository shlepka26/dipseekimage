# -*- coding: utf-8 -*-
"""dipkit.brain — DeepSeek как художник: генерация кода картины.

Ключ НЕ обязателен для работы проекта: движок, CLI и skill работают
и без него (картину пишет агент или человек). Этот модуль нужен, чтобы
автономный CLI мог рисовать сам.

Ключ берётся из переменной окружения DEEPSEEK_API_KEY или из файла
.env в корне проекта (строка вида DEEPSEEK_API_KEY=sk-...).
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

from .paths import env_file
from .styles import STYLES, recipe_text

API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-chat"

# --------------------------------------------------------------------------
# Справочник по движку — то, что видит модель
# --------------------------------------------------------------------------

API_REFERENCE = '''\
Модуль: from dipkit import ArtCanvas, PALETTES, fbm   (импорт уже доступен, PYTHONPATH настроен)

ArtCanvas(width, height, bg="#0b0b0f", palette="neon"|["#hex",...], scale=1)
    поля: c.w, c.h, c.meta (dict для метаданных)
    c.new_layer(name) -> Layer     # слой; ЛЮБОЙ примитив и эффект доступны и на слое
    c.flatten()                    # наложить слои
Готовые палитры PALETTES: ink midnight sunset risograph forest neon paper pastel
                          desert ocean ember blueprint mono

ПОЛЯ И ФОН
    .fill(color, alpha=1)
    .gradient([c1,c2,...], angle=90, cov=1)            # 0=слева направо, 90=сверху вниз
    .radial([c1,c2], center=(0.5,0.5), radius=px|None, falloff=1, cov=1)
    .blobs(count, [colors], r=(min,max)_px, alpha=0.3, seed=None, additive=True, falloff=1.6, softness=0)
    .light(cx, cy, radius_px, color, intensity=0.5, falloff=2.0)   # мягкий источник света в точке:
                                                # луна, лампа, свечение. НЕ заливает весь холст
    .noise(amount=0.35, scale=3, octaves=5, seed=None, colorize=[c1,c2], softness=0)
    .noise_field(scale=3, octaves=5, seed=None) -> np.ndarray (H,W) в 0..1
    .flow([colors], lines=180, steps=140, scale=3, width=2, alpha=0.55, seed=None, curl=2.2,
          both_dirs=False, margin=0, angle_offset=0)
    .scanlines(spacing=4, strength=0.14, angle=0, color="#000000")

ФИГУРЫ (color = '#hex' | индекс палитры int | '@2')
    .rect(x0,y0,x1,y1,color,alpha=1,width=0)      # width>0 -> только контур
    .ellipse(x0,y0,x1,y1,color,alpha=1,width=0)
    .circle(cx,cy,r,color,alpha=1,width=0)        .ring(cx,cy,r,color,width=8)
    .polygon([(x,y),...],color,alpha=1)           .line([(x,y),...],color,width=4,alpha=1)
    .arc(x0,y0,x1,y1,start_deg,end_deg,color,width=6)
    .wedge(x0,y0,x1,y1,start_deg,end_deg,color,alpha=1)   # сектор
    .grid(step=80,color="#ffffff",alpha=0.08,width=1,offset=0)
    .scatter(count=400,color="#ffffff",r=(1,4),alpha=0.7,region=(x0,y0,x1,y1),seed=None,glow=0)

ТЕКСТ
    .text(x,y,s,family="sans",size=48,color="#fff",alpha=1,anchor="la",align="left",spacing=6,
          stroke=0, stroke_color="#000")
          # anchor: "la"=левый верх, "mm"=центр, "ms"=низ-центр, "lm"=левый центр и др.
          # stroke>0 рисует обводку stroke_color ПОД заливкой
    .text_center(s,y=None,...)                     .text_fit(s,max_width=0.9,y=None,...)  # сам подберёт размер
    .measure(s,family,size) -> (w,h)               .fit_size(s,max_width,family,start=400) -> int
    family: sans sans-bold sans-light serif serif-bold mono mono-bold display script hand narrow

ЭФФЕКТЫ (цепочкой, возвращают self)
    .bloom(threshold=0.72, radius=26, intensity=0.55)   .glow(radius=24, intensity=0.6)
    .blur(radius=4)          .vignette(strength=0.45, power=1.8)
    .grain(amount=0.05, mono=True, seed=None)           .posterize(levels=6)
    .contrast(1.2) .brightness(0.05) .saturate(1.2)
    .duotone(dark, light, amount=1)     .invert()       .chromatic(shift=4)
    .pixelate(block=8)                  .quantize_to_palette([colors])

ВЫВОД
    .save(path, meta=None) -> абсолютный путь     # пишет PNG + .thumb.png + .json
    .resize(w,h,resample="lanczos"|"nearest")     .upscale(factor=8, resample="nearest")
    .crop_fraction(left,top,right,bottom)
'''

RULES = '''\
Ты — художник, который рисует ТОЛЬКО кодом на Python через библиотеку dipkit.
Ты не можешь генерировать растровые картинки напрямую — ты пишешь программу,
которая их рисует. Твоя сила: композиция, цвет, типографика, геометрия, шум.

Жёсткие правила:
1. Ответ — РОВНО ОДИН блок ```python с полным работающим скриптом. Без пояснений вне блока.
2. Скрипт должен быть самодостаточным: импорты, sys.path, рисование, сохранение.
3. Никаких внешних файлов, сети, matplotlib, PIL напрямую — только API dipkit
   (numpy импортировать можно).
4. Размер холста — ровно тот, что задан в задании.
5. Сохранять строго так (путь передаётся в задании как OUT).
6. Используй SEED для воспроизводимости: все случайные вызовы получают seed=SEED.
7. Не больше 70 строк. Композиция важнее количества объектов.
8. Никаких комментариев-заглушек «тут добавь» — только готовый рисунок.
9. Цвета — из выбранной палитры, не более 4 основных.
10. Помни: тёмный фон + мягкие пятна + свечение + крупная типографика = надёжно красиво.

Типичные ошибки, которых избегай:
- координаты за пределами холста (всё должно быть в 0..w и 0..h);
- градиент цвета одной строкой вместо списка;
- текст без text_fit и потому вылезает за край;
- 10 равнозначных объектов без иерархии — получится шум;
- забытый .save() в конце.
'''


def load_env(path: str | None = None) -> None:
    """Подхватить DEEPSEEK_API_KEY из .env в корне проекта (если есть)."""
    env_path = path or env_file()
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"\''))
    except Exception:
        pass


def _env_key() -> str | None:
    """Ключ из окружения или .env (когда пользователь не передал свой)."""
    load_env()
    key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("DSH_DEEPSEEK_API_KEY")
    return key.strip() if key and key.strip() else None


def api_key() -> str | None:
    """Публичный доступ к ключу окружения."""
    return _env_key()


def has_key() -> bool:
    return _env_key() is not None


def chat(messages: list[dict], model: str = DEFAULT_MODEL,
         temperature: float = 1.25, max_tokens: int = 4000,
         timeout: float = 180.0, api_key: str | None = None) -> str:
    """Один запрос к DeepSeek. Бросает RuntimeError с понятным текстом.

    `api_key` — ключ, который передало приложение (пользователь ввёл его сам).
    Если не передан, берём из окружения или .env — как в CLI.
    """
    key = (api_key or "").strip() or _env_key()
    if not key:
        raise RuntimeError(
            "нет ключа DeepSeek. Задай переменную окружения DEEPSEEK_API_KEY "
            "или создай файл .env в корне проекта со строкой:\n"
            "    DEEPSEEK_API_KEY=sk-...\n"
            "Ключ выдают на https://platform.deepseek.com"
        )
    payload = json.dumps({
        "model": model, "messages": messages,
        "temperature": temperature, "max_tokens": max_tokens, "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        API_URL, data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"DeepSeek API вернул {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"не удалось связаться с DeepSeek API: {exc.reason}") from exc
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"неожиданный ответ API: {str(data)[:300]}") from exc


def extract_code(text: str) -> str:
    """Достать python-код из ответа модели (```python ... ```)."""
    m = re.search(r"```(?:python|py)?\s*\n(.*?)```", text, re.S)
    code = m.group(1) if m else text
    return code.strip() + "\n"


def system_prompt(style: str | None = None) -> str:
    """Системный промпт художника: правила + справочник + рецепт стиля."""
    parts = [RULES, "СПРАВОЧНИК API:\n" + API_REFERENCE]
    if style and style in STYLES:
        parts.append("РЕЦЕПТ ВЫБРАННОГО СТИЛЯ (следуй ему):\n" + recipe_text(style))
    else:
        parts.append("ДОСТУПНЫЕ СТИЛИ: " + ", ".join(STYLES) +
                     "\nВыбери подходящий и следуй его духу.")
    return "\n\n".join(parts)


def brief(prompt: str, style: str | None = None,
          size: tuple[int, int] = (1200, 1600), seed: int | None = None,
          extra: str = "") -> str:
    """Задание художнику."""
    lines = [
        f"Нарисуй: {prompt}",
        f"Размер холста: {size[0]}x{size[1]} (ровно такой)",
    ]
    if style:
        lines.append(f"Стиль: {style}")
    if seed is not None:
        lines.append(f"SEED = {seed}")
    lines += [
        "Файл сохранить по пути, который лежит в переменной OUT "
        "(создай её: OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'art.png')).",
        "Начни скрипт с:",
        "import os, sys",
        "sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'python')))",
        "from dipkit import ArtCanvas",
        "В конце обязательно c.save(OUT) и print пути.",
    ]
    if extra:
        lines.append("Дополнительно: " + extra)
    return "\n".join(lines)


def plan_work(prompt: str, style: str | None = None,
              size: tuple[int, int] = (1200, 1600), seed: int | None = None,
              model: str = DEFAULT_MODEL, extra: str = "",
              api_key: str | None = None) -> str:
    """Попросить DeepSeek написать код картины. Возвращает python-код."""
    messages = [
        {"role": "system", "content": system_prompt(style)},
        {"role": "user", "content": brief(prompt, style, size, seed, extra)},
    ]
    return extract_code(chat(messages, model=model, api_key=api_key))


def revise_work(code: str, feedback: str, style: str | None = None,
                model: str = DEFAULT_MODEL, api_key: str | None = None) -> str:
    """Попросить поправить готовый код по замечанию (например, «текст вылез»)."""
    messages = [
        {"role": "system", "content": system_prompt(style)},
        {"role": "user", "content":
            "Вот текущий код картины:\n```python\n" + code + "\n```\n\n"
            "Внеси правку: " + feedback + "\n"
            "Верни РОВНО ОДИН блок ```python с полным исправленным скриптом."},
    ]
    return extract_code(chat(messages, model=model, api_key=api_key))
