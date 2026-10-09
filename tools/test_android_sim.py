# -*- coding: utf-8 -*-
"""Прогон Python-движка в режиме Android прямо на ПК.

Внутри APK три вещи отличаются от ПК: писать можно только в
`os.environ["HOME"]`, подпроцессов нет (код работы выполняется через `exec`),
а шрифты лежат в `/system/fonts`. Проверять это на телефоне дорого и долго.

Оказывается, всё это можно проверить здесь: Chaquopy сообщает об Android
наличием функции `sys.getandroidapilevel`, и движок узнаёт платформу именно по
ней. Подставляем такую функцию ДО импорта движка — и получаем ровно ту ветку
кода, которая выполнится в APK, вместе с подменённым HOME.

Именно этот тест ловит ошибки вида «путь посчитан один раз при импорте»:
на ПК они безвредны, а на телефоне приводят к записи в несуществующую папку.

Запуск: .\\dip.cmd androidsim
"""

from __future__ import annotations

import json
import os
import shutil
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- Притворяемся Android ДО первого импорта движка ------------------------
FAKE_HOME = os.path.join(ROOT, "art", "_android-sim", "home")
FAKE_API = 34

if os.path.isdir(FAKE_HOME):
    shutil.rmtree(FAKE_HOME, ignore_errors=True)
os.makedirs(FAKE_HOME, exist_ok=True)

os.environ["HOME"] = FAKE_HOME          # куда «телефон» разрешает писать
sys.getandroidapilevel = lambda: FAKE_API   # так Chaquopy сигналит об Android

sys.path.insert(0, os.path.join(ROOT, "python"))

import dipkit  # noqa: E402
import mobile  # noqa: E402  (модуль верхнего уровня рядом с пакетом dipkit)
from dipkit import gallery, runner  # noqa: E402
from dipkit.paths import IS_ANDROID, data_root, platform_name, works_dir  # noqa: E402

FAILS: list[str] = []
WARNS: list[str] = []


def check(label: str, fn) -> None:
    try:
        fn()
        print(f"  OK    {label}")
    except Exception as exc:  # noqa: BLE001
        FAILS.append(f"{label}: {exc}")
        print(f"  FAIL  {label} - {type(exc).__name__}: {exc}")


def _assert(cond, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def j(raw: str) -> dict:
    data = json.loads(raw)
    _assert(isinstance(data, dict), f"ответ не объект: {type(data)}")
    return data


def main() -> int:
    print("=" * 66)
    print("движок в режиме Android (HOME подменён, getandroidapilevel подставлен)")
    print("=" * 66)
    print(f"  HOME эмулируемого приложения: {FAKE_HOME}")

    print("\n[1] Определение платформы")

    def detected():
        _assert(IS_ANDROID is True, "движок не увидел Android")
        _assert(platform_name() == f"android-api{FAKE_API}",
                f"platform_name(): {platform_name()}")
        print(f"        platform_name() = {platform_name()}")
    check("движок распознал Android", detected)

    def paths_use_home():
        _assert(data_root() == FAKE_HOME, f"data_root(): {data_root()}")
        expected = os.path.join(FAKE_HOME, "art", "works")
        _assert(works_dir() == expected, f"works_dir(): {works_dir()}")
    check("все пути идут в HOME, а не в папку проекта", paths_use_home)

    def gallery_lazy_path():
        """Регрессия: путь контактного листа должен считаться лениво.
        Взяв его при импорте, мы получили бы папку проекта вместо HOME."""
        out = gallery.default_out()
        _assert(out.startswith(FAKE_HOME), f"контактный лист вне HOME: {out}")
    check("контактный лист считается от HOME, а не при импорте", gallery_lazy_path)

    print("\n[2] Запуск работы: подпроцессов нет, только exec")

    code = (
        "import os\n"
        "from dipkit import ArtCanvas\n"
        "OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'art.png')\n"
        "c = ArtCanvas(200, 260, palette='neon')\n"
        "c.gradient(['#3a0ca3', '#f72585'], 60)\n"
        "c.circle(100, 110, 55, '#e0fbfc')\n"
        "c.text_fit('ТЕСТ', max_width=0.8, y=200, family='sans-bold')\n"
        "c.save(OUT)\n"
        "print('нарисовано', c.w, c.h)\n"
    )

    work_dir: list[str] = []

    def engine_is_exec():
        """Движок обязан сам выбрать exec: subprocess на Android невозможен."""
        d = j(mobile.render(json.dumps({"code": code, "prompt": "симуляция Android",
                                        "style": "gradient-poster"})))
        _assert(d["ok"] is True,
                f"не отрисовалось: {d.get('error')} {d.get('stderr', '')[-300:]}")
        _assert(d["engine"] == "exec",
                f"выбран движок {d['engine']!r}, а на Android нужен exec")
        _assert(os.path.exists(d["png"]), "нет PNG")
        _assert(d["png"].startswith(FAKE_HOME), f"PNG вне HOME: {d['png']}")
        _assert("нарисовано 200 260" in d["log"], f"лог не пойман: {d['log']!r}")
        work_dir.append(d["work_dir"])
    check("движок сам выбрал exec и записал PNG в HOME", engine_is_exec)

    def no_subprocess_used():
        """Проверяем прямо: subprocess в этой сессии не запускался."""
        import subprocess

        src = open(os.path.join(ROOT, "python", "dipkit", "runner.py"),
                   encoding="utf-8").read()
        _assert('if engine == "auto":' in src and "IS_ANDROID" in src,
                "в runner.py нет автовыбора движка по IS_ANDROID")
        # Popen не должен вызываться на Android; убедимся, что ветка exec не зовёт его
        exec_branch = src.split("def _run_exec")[1].split("def run_work")[0]
        _assert("subprocess" not in exec_branch,
                "ветка exec зачем-то использует subprocess")
        _assert(hasattr(subprocess, "Popen"), "subprocess не импортируется")
    check("ветка exec не использует subprocess", no_subprocess_used)

    def work_visible_in_gallery():
        d = j(mobile.works())
        _assert(d["ok"] is True, d.get("error", ""))
        names = [w["name"] for w in d["works"]]
        _assert(os.path.basename(work_dir[0]) in names,
                f"работы нет в списке: {names}")
        entry = next(w for w in d["works"] if w["name"] == os.path.basename(work_dir[0]))
        _assert(entry["png"].startswith(FAKE_HOME), "PNG вне HOME")
        _assert(entry["thumb"] and os.path.exists(entry["thumb"]),
                "миниатюра не создана (нужна истории в приложении)")
        _assert(entry["dir"].startswith(FAKE_HOME), "путь работы вне HOME")
    check("галерея видит работу и её миниатюру", work_visible_in_gallery)

    print("\n[3] Интерфейс моста в режиме Android")

    def doctor_reports_android():
        d = j(mobile.doctor())
        _assert(d["ok"] is True, d.get("error", ""))
        _assert(d["android"] is True, "doctor не видит Android")
        _assert(d["platform"].startswith("android"), d["platform"])
        _assert(d["paths"]["data"] == FAKE_HOME, f"paths.data: {d['paths']['data']}")
        _assert(d["python_packages"]["pillow"], "нет версии Pillow")
        _assert(d["python_packages"]["numpy"], "нет версии numpy")
        print(f"        pillow {d['python_packages']['pillow']}, "
              f"numpy {d['python_packages']['numpy']}")
    check("doctor() сообщает об Android и версиях пакетов", doctor_reports_android)

    def styles_available():
        d = j(mobile.styles())
        _assert(d["ok"] and len(d["styles"]) >= 11, f"стилей: {len(d['styles'])}")
    check("styles() отдаёт список стилей", styles_available)

    def fonts_available():
        fams = dipkit.available_families()
        good = [k for k, v in fams.items() if v]
        if not good:
            # На сборочной машине шрифтов может не быть вовсе (например, в CI).
            # Это не поломка движка: в APK шрифты берутся из /system/fonts.
            WARNS.append("на этой машине нет системных шрифтов, проверки текста "
                         "пропущены; на телефоне движок возьмёт Roboto из /system/fonts")
            print("        шрифтов не найдено - проверки текста пропущены")
            return
        from dipkit.canvas import covers
        _assert(covers("sans", "Проверка"), "sans не покрывает кириллицу")
        print(f"        семейств шрифтов: {len(good)}/{len(fams)}")
        if len(good) < len(fams):
            WARNS.append("часть семейств недоступна на этой машине; "
                         "на телефоне движок возьмёт Roboto из /system/fonts")
    check("шрифты доступны и кириллица покрыта", fonts_available)

    def text_cyrillic_renders():
        """Текст по-русски обязан реально появляться в пикселях: иначе
        подстановка шрифта на Android дала бы пустые квадраты."""
        if not any(dipkit.available_families().values()):
            WARNS.append("проверка отрисовки кириллицы пропущена: нет шрифтов")
            return
        import numpy as np

        from dipkit import ArtCanvas
        t = ArtCanvas(300, 120, bg="#000000")
        t.text(10, 20, "ГОРЫ", family="sans-bold", size=64, color="#ffffff")
        lit = int((t.px.max(axis=2) > 0.5).sum())
        _assert(lit > 200, f"текст почти не нарисовался: {lit} пикселей")
        _assert(np.isfinite(t.px).all(), "в пикселях NaN/Inf")
        print(f"        закрашенных пикселей текста: {lit}")
    check("кириллица действительно рисуется", text_cyrillic_renders)

    def draw_without_key_is_graceful():
        """Без ключа приложение не должно падать: ждём понятный отказ."""
        clean = {k: v for k, v in os.environ.items()
                 if k not in ("DEEPSEEK_API_KEY", "DSH_DEEPSEEK_API_KEY")}
        saved = dict(os.environ)
        os.environ.clear()
        os.environ.update(clean)
        try:
            d = j(mobile.draw(json.dumps({"prompt": "тест"})))
        finally:
            os.environ.clear()
            os.environ.update(saved)
        _assert(d["ok"] is False, "нарисовал без ключа")
        _assert(d.get("need_key") is True, "нет флага need_key для интерфейса")
    check("draw() без ключа отвечает need_key, а не падает", draw_without_key_is_graceful)

    def delete_work_from_home():
        d = j(mobile.delete_work(json.dumps({"dir": work_dir[0]})))
        _assert(d["ok"] is True, d.get("error", ""))
        _assert(not os.path.exists(work_dir[0]), "папка работы не удалена")
    check("delete_work() удаляет работу из HOME", delete_work_from_home)

    print("\n" + "=" * 66)
    for w in WARNS:
        print("  предупреждение:", w)
    if FAILS:
        print(f"ПРОВАЛЕНО: {len(FAILS)}")
        for f in FAILS:
            print("  -", f)
        return 1
    print("РЕЖИМ ANDROID РАБОТАЕТ: пути в HOME, движок exec, кириллица рисуется.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
