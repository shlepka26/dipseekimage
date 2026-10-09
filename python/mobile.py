# -*- coding: utf-8 -*-
"""mobile — мост между Android-приложением и движком dipkit.

Правила этого модуля (почему он выглядит именно так):

* **JSON-строка на входе и на выходе.** Мост через Chaquopy тогда не зависит
  от преобразования типов Kotlin <-> Python: пришла строка, ушла строка.
* **Ни одна функция не бросает исключение наружу.** Любая ошибка возвращается
  как `{"ok": false, "error": "..."}`, иначе приложение упадёт без объяснений.
* **Только то, что нужно интерфейсу.** Стили, рисование, галерея, код работы,
  диагностика.

Тот же код работает и на ПК (для тестов), потому что dipkit портируемый.
"""

from __future__ import annotations

import functools
import json
import os
import shutil
import traceback

from dipkit import brain, runner
from dipkit.paths import IS_ANDROID, data_root, platform_name, python_dir, works_dir
from dipkit.styles import SIZE_PRESETS, STYLES

__all__ = [
    "version", "styles", "doctor", "draw", "render", "works",
    "work_code", "delete_work",
]


# --------------------------------------------------------------------------
# Обвязка: одинаковые ответы и перехват любых исключений
# --------------------------------------------------------------------------

def _ok(**fields) -> str:
    return json.dumps({"ok": True, **fields}, ensure_ascii=False)


def _err(message: str, **fields) -> str:
    return json.dumps({"ok": False, "error": message, **fields}, ensure_ascii=False)


def _guard(fn):
    """Функция моста не имеет права уронить приложение."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:                              # noqa: BLE001
            return _err(f"{type(exc).__name__}: {exc}",
                        traceback=traceback.format_exc()[-2000:])
    return wrapper


def _load(request_json: str | None) -> dict:
    if not request_json or not request_json.strip():
        return {}
    data = json.loads(request_json)
    if not isinstance(data, dict):
        raise ValueError("запрос должен быть JSON-объектом")
    return data


def _size_from(data: dict, style: str) -> tuple[int, int]:
    """Размер: явные size_w/size_h > size ('1600x900' или пресет) > размер стиля."""
    if data.get("size_w") and data.get("size_h"):
        return max(64, int(data["size_w"])), max(64, int(data["size_h"]))
    raw = str(data.get("size") or "").strip().lower()
    if raw in SIZE_PRESETS:
        return SIZE_PRESETS[raw]
    if "x" in raw:
        a, b = raw.split("x", 1)
        return max(64, int(a)), max(64, int(b))
    return tuple(STYLES.get(style, {}).get("size", (1200, 1600)))


# --------------------------------------------------------------------------
# Справочная информация
# --------------------------------------------------------------------------

@_guard
def version() -> str:
    """Версия движка и платформа — приложение показывает в «О программе»."""
    from dipkit import __version__
    return _ok(version=__version__, platform=platform_name(), android=IS_ANDROID)


@_guard
def styles() -> str:
    """Список стилей для выпадающего списка в интерфейсе."""
    items = []
    for key, s in STYLES.items():
        w, h = s["size"]
        items.append({
            "id": key,
            "title": s["title"],
            "summary": s["summary"],
            "avoid": s["avoid"],
            "size_w": w,
            "size_h": h,
        })
    return _ok(styles=items, sizes=list(SIZE_PRESETS))


@_guard
def doctor() -> str:
    """Диагностика: версии, шрифты, пути, наличие ключа."""
    import numpy
    import PIL

    from dipkit.canvas import available_families

    fams = available_families()
    works = runner.list_works()
    return _ok(
        platform=platform_name(),
        android=IS_ANDROID,
        python_packages={
            "pillow": getattr(PIL, "__version__", "?"),
            "numpy": getattr(numpy, "__version__", "?"),
        },
        paths={"data": data_root(), "works": works_dir(), "engine": python_dir()},
        fonts={k: (os.path.basename(v) if v else None) for k, v in fams.items()},
        fonts_missing=[k for k, v in fams.items() if not v],
        has_key=brain.has_key(),
        works_count=len(works),
    )


# --------------------------------------------------------------------------
# Главное: нарисовать
# --------------------------------------------------------------------------

@_guard
def draw(request_json: str) -> str:
    """Нарисовать картину по текстовому запросу.

    Запрос (JSON)::
        {
          "prompt":   "закат над морем, минимализм",   // обязательно
          "style":    "gradient-poster",               // необязательно
          "size_w":   1200, "size_h": 1600,            // необязательно
          "seed":     42,                              // необязательно
          "api_key":  "sk-...",                        // ключ пользователя
          "model":    "deepseek-chat",                 // необязательно
          "timeout":  180,                             // необязательно
          "repair":   true                             // чинить код при падении
        }

    Ответ: `png`, `code`, `log`, `seconds`, `width`, `height`, `work_dir`,
    `self_repair` (была ли починка), `attempts`.
    """
    data = _load(request_json)
    prompt = str(data.get("prompt") or "").strip()
    if not prompt:
        return _err("пустой запрос: напиши, что нарисовать")

    api_key = (data.get("api_key") or "").strip() or None
    if not api_key and not brain.has_key():
        return _err("нет ключа DeepSeek: введи его в настройках приложения",
                    need_key=True)

    style = str(data.get("style") or "gradient-poster").strip()
    if style not in STYLES:
        style = "gradient-poster"
    size = _size_from(data, style)
    seed = data.get("seed")
    seed = int(seed) if seed not in (None, "") else None
    model = str(data.get("model") or brain.DEFAULT_MODEL)
    timeout = float(data.get("timeout") or 180)
    allow_repair = bool(data.get("repair", True))

    # 1. Просим художника написать код
    try:
        code = brain.plan_work(prompt, style, size, seed, model=model,
                               api_key=api_key)
    except RuntimeError as exc:
        return _err(str(exc), stage="plan")
    if not code.strip():
        return _err("модель вернула пустой код", stage="plan")

    work_dir = runner.new_work_dir(prompt=prompt, root=data.get("work_root") or None)
    work_py = os.path.join(work_dir, "work.py")

    # 2. Рисуем, при падении — одна попытка починки по traceback
    attempts, self_repair = 0, False
    rep: dict = {}
    log_parts: list[str] = []
    while True:
        attempts += 1
        with open(work_py, "w", encoding="utf-8") as fh:
            fh.write(code)
        rep = runner.render_and_record(work_py, prompt=prompt, style=style,
                                       timeout=timeout, seed=seed)
        if rep["stdout"].strip():
            log_parts.append(rep["stdout"].strip())
        if rep["ok"] or not allow_repair or attempts > 1:
            break
        log_parts.append("--- код упал, пробую починить ---\n" + rep["stderr"][-1500:])
        try:
            fixed = brain.revise_work(
                code,
                "Код упал при запуске. Вот traceback:\n" + rep["stderr"][-2500:] +
                "\nИсправь ошибку, сохранив замысел.",
                style, model=model, api_key=api_key)
        except RuntimeError as exc:
            log_parts.append(f"починка не удалась: {exc}")
            break
        if not fixed.strip():
            log_parts.append("починка вернула пустой код")
            break
        code, self_repair = fixed, True

    result = {
        "prompt": prompt, "style": style, "seed": seed,
        "width": size[0], "height": size[1],
        "work_dir": work_dir, "work_py": work_py,
        "code": code, "log": "\n".join(log_parts)[-4000:],
        "seconds": rep.get("seconds"), "attempts": attempts,
        "self_repair": self_repair, "engine": rep.get("engine"),
    }
    if rep["ok"]:
        return _ok(png=rep["artifacts"][0],
                   thumb=os.path.splitext(rep["artifacts"][0])[0] + ".thumb.png",
                   **result)
    return _err("картина не отрисовалась", stderr=(rep.get("stderr") or "")[-2500:],
                **result)


@_guard
def render(request_json: str) -> str:
    """Отрисовать готовый код (например, после правки в редакторе приложения).

    Запрос: `{"code": "...", "prompt": "...", "style": "...", "seed": 42,
    "work_dir": "<существующая папка, иначе создастся новая>", "timeout": 180}`
    """
    data = _load(request_json)
    code = str(data.get("code") or "")
    if not code.strip():
        return _err("пустой код")
    work_dir = str(data.get("work_dir") or "").strip()
    if not work_dir or not os.path.isdir(work_dir):
        work_dir = runner.new_work_dir(prompt=data.get("prompt") or "правка")
    work_py = os.path.join(work_dir, "work.py")
    with open(work_py, "w", encoding="utf-8") as fh:
        fh.write(code)

    rep = runner.render_and_record(
        work_py, prompt=data.get("prompt"), style=data.get("style"),
        timeout=float(data.get("timeout") or 180),
        seed=int(data["seed"]) if data.get("seed") not in (None, "") else None)
    common = {"work_dir": work_dir, "work_py": work_py, "code": code,
              "seconds": rep.get("seconds"), "engine": rep.get("engine"),
              "log": (rep.get("stdout") or "").strip()}
    if rep["ok"]:
        return _ok(png=rep["artifacts"][0],
                   thumb=os.path.splitext(rep["artifacts"][0])[0] + ".thumb.png",
                   **common)
    return _err("код не отрисовался", stderr=(rep.get("stderr") or "")[-2500:],
                **common)


# --------------------------------------------------------------------------
# Галерея
# --------------------------------------------------------------------------

@_guard
def works(request_json: str | None = None) -> str:
    """Список работ для истории: имя, PNG, миниатюра, описание, стиль, дата."""
    data = _load(request_json)
    limit = int(data.get("limit") or 100)
    items = []
    for w in runner.list_works()[:limit]:
        meta = w.get("meta") or {}
        png = w.get("png")
        thumb = os.path.splitext(png)[0] + ".thumb.png" if png else None
        items.append({
            "name": w["name"],
            "dir": w["dir"],                 # нужен Kotlin для work_code/render
            "png": png,
            "thumb": thumb if thumb and os.path.exists(thumb) else None,
            "prompt": meta.get("prompt"),
            "style": meta.get("style"),
            "created": meta.get("created"),
            "seconds": meta.get("seconds"),
            "ok": bool(meta.get("ok")),
            "has_code": bool(w.get("work_py")),
        })
    return _ok(works=items, total=len(runner.list_works()))


@_guard
def work_code(request_json: str) -> str:
    """Исходный код работы — для экрана «Код»."""
    data = _load(request_json)
    target = str(data.get("dir") or data.get("name") or "")
    for w in runner.list_works():
        if target and (target in w["name"] or target == w["dir"]):
            if not w.get("work_py"):
                return _err("у этой работы нет сохранённого кода")
            with open(w["work_py"], encoding="utf-8") as fh:
                return _ok(code=fh.read(), work_dir=w["dir"], name=w["name"])
    return _err(f"работа не найдена: {target}")


@_guard
def delete_work(request_json: str) -> str:
    """Удалить работу вместе с её папкой."""
    data = _load(request_json)
    target = str(data.get("dir") or data.get("name") or "")
    if not target:
        return _err("не указана работа")
    root = os.path.realpath(works_dir())
    for w in runner.list_works():
        if target in w["name"] or target == w["dir"]:
            real = os.path.realpath(w["dir"])
            # страховка: удаляем только внутри art/works
            if os.path.dirname(real) != root:
                return _err("отказ: путь вне папки работ")
            shutil.rmtree(real, ignore_errors=True)
            return _ok(deleted=w["name"])
    return _err(f"работа не найдена: {target}")
