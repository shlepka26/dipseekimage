#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dip — командный интерфейс проекта «ДИПСИК ХУДОЖНИК».

Примеры:
    .\\dip.cmd styles
    .\\dip.cmd styles neon-glow
    .\\dip.cmd new "закат над морем, минимализм" --style gradient-poster
    .\\dip.cmd new "плакат про осень" --style risograph --code my_code.py
    .\\dip.cmd render art\\works\\2025-01-01-120000-zakat\\work.py
    .\\dip.cmd ls
    .\\dip.cmd gallery
    .\\dip.cmd doctor
"""

from __future__ import annotations

import argparse
import os
import random
import subprocess
import sys
import textwrap
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))
PYTHON_DIR = os.path.join(ROOT, "python")
sys.path.insert(0, PYTHON_DIR)

from dipkit import __version__  # noqa: E402
from dipkit import brain, gallery, runner  # noqa: E402
from dipkit.paths import data_root, platform_name, python_dir, works_dir  # noqa: E402
from dipkit.styles import SIZE_PRESETS, STYLES, recipe_text  # noqa: E402

BAR = "=" * 68


def parse_size(value: str | None, style: str | None) -> tuple[int, int]:
    """'1600x900' | 'wide' | None -> (w, h)."""
    if not value:
        pal = STYLES.get(style or "", {}).get("size")
        return tuple(pal) if pal else (1200, 1600)
    v = value.lower().strip()
    if v in SIZE_PRESETS:
        return SIZE_PRESETS[v]
    if "x" in v:
        a, b = v.split("x", 1)
        try:
            return max(64, int(a)), max(64, int(b))
        except ValueError:
            pass
    raise SystemExit(f"не понимаю размер {value!r}. Примеры: 1200x1600, wide, square, poster")


def read_code(source: str) -> str:
    """Код из файла или из stdin ('-')."""
    if source == "-":
        return sys.stdin.read()
    with open(source, encoding="utf-8") as fh:
        return fh.read()


def report(rep: dict, show_stdout: bool = True) -> None:
    """Напечатать отчёт о запуске работы."""
    status = "ГОТОВО" if rep["ok"] else ("ТАЙМАУТ" if rep.get("timed_out") else "ОШИБКА")
    print(f"\n[{status}] {rep['seconds']} с, код возврата {rep['returncode']}")
    if show_stdout and rep["stdout"].strip():
        print("--- вывод работы ---")
        print(rep["stdout"].strip()[:1500])
    if not rep["ok"]:
        print("--- ошибка ---")
        print((rep["stderr"] or "").strip()[-2500:])
        print("\nПодсказка: посмотри traceback выше и поправь work.py "
              "(или попроси художника исправить: dip revise <работа> \"что не так\")")
    for a in rep["artifacts"]:
        print(f"  файл: {a}")


# --------------------------------------------------------------------------
# Команды
# --------------------------------------------------------------------------

def cmd_new(args) -> int:
    style = args.style or "gradient-poster"
    if style not in STYLES:
        print(f"нет стиля {style!r}. Доступные: {', '.join(STYLES)}")
        return 2
    size = parse_size(args.size, style)
    seed = args.seed if args.seed is not None else random.randint(1, 10 ** 6)
    work_dir = runner.new_work_dir(prompt=args.prompt, slug=args.name)
    work_py = os.path.join(work_dir, "work.py")
    print(BAR)
    print(f"Работа:  {os.path.basename(work_dir)}")
    print(f"Стиль:   {style} — {STYLES[style]['title']}")
    print(f"Размер:  {size[0]}x{size[1]}   seed={seed}")

    source = None
    if args.code:
        source = "файл " + args.code
        code = read_code(args.code)
    elif brain.has_key() and not args.scaffold:
        source = f"DeepSeek API ({args.model})"
        print("Художник: DeepSeek думает... (ключ найден)")
        try:
            code = brain.plan_work(args.prompt, style, size, seed, model=args.model,
                                   extra=args.extra or "")
        except RuntimeError as exc:
            print(f"DeepSeek не смог: {exc}")
            return 3
    else:
        source = "каркас (ключа DeepSeek нет)"
        code = runner.work_scaffold(args.prompt, style, size, seed)

    with open(work_py, "w", encoding="utf-8") as fh:
        fh.write(code)
    print(f"Источник: {source}")
    print(f"Код:     {work_py}   ({len(code.splitlines())} строк)")

    if args.no_render:
        print("\n--no-render: код создан, отрисовка пропущена.")
        return 0
    rep = runner.render_and_record(work_py, prompt=args.prompt, style=style,
                                   timeout=args.timeout, seed=seed)
    report(rep)
    return 0 if rep["ok"] else 1


def cmd_init(args) -> int:
    """Создать папку работы и напечатать её путь (код пишет художник сам)."""
    work_dir = runner.new_work_dir(prompt=args.prompt, slug=args.name)
    runner.write_meta(work_dir, {
        "prompt": args.prompt, "style": args.style, "seed": args.seed,
        "created": datetime.now().isoformat(timespec="seconds"),
        "ok": False, "stage": "created",
    })
    print(work_dir)
    return 0


def cmd_render(args) -> int:
    target = args.target
    if not os.path.exists(target):
        found = gallery.open_work(target)
        if not found:
            print(f"не найдено: {target}")
            return 2
        target = os.path.join(os.path.dirname(found), "work.py")
    rep = runner.render_and_record(target, prompt=args.prompt, style=args.style,
                                   timeout=args.timeout, seed=args.seed)
    report(rep)
    return 0 if rep["ok"] else 1


def cmd_revise(args) -> int:
    work = runner.list_works()
    match = next((w for w in work if args.target in w["name"]), None)
    if not match:
        print(f"работа не найдена: {args.target}")
        return 2
    work_py = os.path.join(match["dir"], "work.py")
    if not os.path.exists(work_py):
        print(f"в работе нет work.py: {match['dir']}")
        return 2
    if not brain.has_key():
        print("Для правки через DeepSeek нужен ключ (DEEPSEEK_API_KEY).\n"
              "Без ключа просто открой work.py и поправь вручную.")
        return 3
    code = open(work_py, encoding="utf-8").read()
    style = (match["meta"] or {}).get("style")
    print(f"Правка: {args.feedback}")
    new_code = brain.revise_work(code, args.feedback, style, model=args.model)
    if args.backup:
        with open(work_py + ".bak", "w", encoding="utf-8") as fh:
            fh.write(code)
    with open(work_py, "w", encoding="utf-8") as fh:
        fh.write(new_code)
    rep = runner.render_and_record(work_py, style=style, timeout=args.timeout)
    report(rep)
    return 0 if rep["ok"] else 1


def cmd_styles(args) -> int:
    if args.name:
        print(recipe_text(args.name))
        return 0
    print(BAR)
    print(f"Стилей: {len(STYLES)}   (подробнее: dip styles <имя>)")
    print(BAR)
    for name, s in STYLES.items():
        w, h = s["size"]
        print(f"\n  {name}  —  {s['title']}   [{w}x{h}]")
        print(textwrap.fill(s["summary"], 66, initial_indent="      ",
                            subsequent_indent="      "))
    print("\nРазмеры-пресеты:", ", ".join(SIZE_PRESETS))
    return 0


def cmd_ls(args) -> int:
    print(gallery.text_index(limit=args.limit))
    return 0


def cmd_gallery(args) -> int:
    out = gallery.contact_sheet(cols=args.cols, cell=args.cell, out=args.out)
    if not out:
        print("Работ пока нет — сначала создай первую: "
              'dip new "описание" --style neon-glow')
        return 1
    print(f"Контактный лист: {out}")
    print()
    print(gallery.text_index(limit=args.limit))
    return 0


def cmd_api(args) -> int:
    """Напечатать справочник по движку — его читает художник перед работой."""
    print(brain.API_REFERENCE)
    if args.full:
        print("\n" + BAR)
        print("РЕЦЕПТЫ ВСЕХ СТИЛЕЙ")
        print(BAR)
        from dipkit.styles import all_recipes
        print(all_recipes())
    return 0


def cmd_show(args) -> int:
    """Показать путь к готовой работе (для вставки в ответ картинкой)."""
    works = runner.list_works()
    if not works:
        print("работ нет")
        return 1
    if args.target:
        match = next((w for w in works if args.target in w["name"]), None)
    else:
        match = next((w for w in works if w["png"]), None)
    if not match or not match["png"]:
        print(f"не найдено: {args.target or '(последняя)'}")
        return 1
    print(match["png"])
    if args.meta:
        meta = match["meta"] or {}
        for k in ("prompt", "style", "seed", "created", "seconds", "ok"):
            if k in meta:
                print(f"  {k}: {meta[k]}")
    return 0


def cmd_doctor(args) -> int:
    import numpy
    import PIL

    print(BAR)
    print(f"dipkit {__version__} — проверка окружения")
    print(BAR)
    print(f"  корень проекта : {ROOT}")
    print(f"  платформа      : {platform_name()}")
    print(f"  python         : {sys.version.split()[0]}")
    print(f"  интерпретатор  : {sys.executable}")
    print(f"  папка движка   : {python_dir()}")
    print(f"  данные         : {data_root()}")
    print(f"  Pillow         : {PIL.__version__}")
    print(f"  numpy          : {numpy.__version__}")
    from dipkit.canvas import available_families
    fams = available_families()
    good = [k for k, v in fams.items() if v]
    print(f"  шрифты         : найдено {len(good)}/{len(fams)} семейств")
    for k, v in fams.items():
        if not v:
            print(f"      нет: {k}")
    print(f"  ключ DeepSeek  : {'есть' if brain.has_key() else 'НЕТ (это нормально)'}")
    if not brain.has_key():
        print("      без ключа рисует агент в чате или ты сам (--code)")
    works = runner.list_works()
    print(f"  работ в art/   : {len(works)}")
    print(f"  папка работ    : {works_dir()}")
    out = os.path.join(data_root(), "art", "_doctor")
    try:
        from dipkit import ArtCanvas
        p = ArtCanvas(320, 200, palette="neon").gradient(["#3a0ca3", "#f72585"], 45)
        p.blobs(3, ["#4cc9f0"], r=(40, 120), alpha=0.4, seed=1)
        p.circle(160, 100, 40, "#e0fbfc", alpha=0.8).save(os.path.join(out, "smoke.png"))
        print(f"  тест отрисовки : OK ({os.path.join(out, 'smoke.png')})")
    except Exception as exc:  # noqa: BLE001
        print(f"  тест отрисовки : ПРОВАЛ — {type(exc).__name__}: {exc}")
        return 1
    print("\nВсё готово к рисованию.")
    return 0


def cmd_selftest(args) -> int:
    return subprocess.call([sys.executable, os.path.join(ROOT, "tools", "selftest.py")])


def cmd_mobiletest(args) -> int:
    """Проверить JSON-мост, через который с приложением говорит Android."""
    return subprocess.call([sys.executable, os.path.join(ROOT, "tools", "test_mobile.py")])


def cmd_icons(args) -> int:
    """Нарисовать иконку Android-приложения движком dipkit."""
    return subprocess.call([sys.executable, os.path.join(ROOT, "tools", "make_icons.py")])


def cmd_checkandroid(args) -> int:
    """Статическая проверка Android-проекта (сборку не заменяет)."""
    return subprocess.call([sys.executable, os.path.join(ROOT, "tools", "check_android.py")])


def cmd_simandroid(args) -> int:
    """Прогнать движок в режиме Android: подменённый HOME и запуск через exec."""
    return subprocess.call([sys.executable, os.path.join(ROOT, "tools", "test_android_sim.py")])


def cmd_clean(args) -> int:
    """Убрать кэш Python и служебные папки — обязательно перед сборкой APK."""
    import shutil as _shutil

    removed: list[str] = []
    for base in (os.path.join(ROOT, "python"), os.path.join(ROOT, "tools")):
        for dirpath, dirs, _files in os.walk(base):
            for d in list(dirs):
                if d == "__pycache__":
                    p = os.path.join(dirpath, d)
                    _shutil.rmtree(p, ignore_errors=True)
                    dirs.remove(d)
                    removed.append(os.path.relpath(p, ROOT))
    for junk in ("_selftest", "_doctor", "_icons", "exec", "_android-sim", "_check-logs"):
        p = os.path.join(data_root(), "art", junk)
        if os.path.isdir(p):
            _shutil.rmtree(p, ignore_errors=True)
            removed.append(os.path.relpath(p, ROOT))
    if removed:
        print(f"удалено: {len(removed)}")
        for r in removed:
            print("  -", r)
    else:
        print("нечего удалять")
    return 0


# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dip", description="ДИПСИК ХУДОЖНИК — рисование кодом",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            примеры:
              dip styles neon-glow
              dip new "закат над морем" --style gradient-poster
              dip new "плакат" --style risograph --code code.py
              dip render art/works/<работа>/work.py
              dip ls
              dip gallery
        """))
    p.add_argument("--version", action="version", version=f"dipkit {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    n = sub.add_parser("new", help="создать и отрисовать новую работу")
    n.add_argument("prompt", help="что нарисовать")
    n.add_argument("--style", "-s", help=f"стиль: {', '.join(STYLES)}")
    n.add_argument("--size", help="размер: 1200x1600 или пресет (wide, square, poster, story, card, avatar, wallpaper)")
    n.add_argument("--seed", type=int, help="зерно случайности (для повторяемости)")
    n.add_argument("--name", help="имя папки (по умолчанию — из описания)")
    n.add_argument("--code", help="взять код из файла ('-' = stdin) вместо DeepSeek")
    n.add_argument("--scaffold", action="store_true", help="не звать DeepSeek, сделать каркас")
    n.add_argument("--extra", help="дополнительное указание художнику")
    n.add_argument("--model", default=brain.DEFAULT_MODEL, help="модель DeepSeek")
    n.add_argument("--timeout", type=float, default=180.0, help="таймаут отрисовки, с")
    n.add_argument("--no-render", action="store_true", help="только создать код")
    n.set_defaults(func=cmd_new)

    r = sub.add_parser("render", help="перерисовать существующую работу или файл")
    r.add_argument("target", help="путь к work.py, папке работы или часть имени работы")
    r.add_argument("--timeout", type=float, default=180.0)
    r.add_argument("--seed", type=int)
    r.add_argument("--prompt", help="записать в метаданные, что было заказано")
    r.add_argument("--style", help="записать в метаданные имя стиля")
    r.set_defaults(func=cmd_render)

    i = sub.add_parser("init", help="создать папку работы (код пишет художник)")
    i.add_argument("prompt", help="что нарисовать")
    i.add_argument("--style", "-s")
    i.add_argument("--seed", type=int)
    i.add_argument("--name", help="имя папки")
    i.set_defaults(func=cmd_init)

    v = sub.add_parser("revise", help="попросить DeepSeek исправить работу")
    v.add_argument("target", help="часть имени работы")
    v.add_argument("feedback", help="что поправить")
    v.add_argument("--model", default=brain.DEFAULT_MODEL)
    v.add_argument("--timeout", type=float, default=180.0)
    v.add_argument("--no-backup", dest="backup", action="store_false", default=True)
    v.set_defaults(func=cmd_revise)

    s = sub.add_parser("styles", help="список стилей или рецепт одного")
    s.add_argument("name", nargs="?")
    s.set_defaults(func=cmd_styles)

    l = sub.add_parser("ls", help="список работ")
    l.add_argument("--limit", type=int, default=40)
    l.set_defaults(func=cmd_ls)

    g = sub.add_parser("gallery", help="контактный лист всех работ")
    g.add_argument("--cols", type=int, default=4)
    g.add_argument("--cell", type=int, default=440)
    g.add_argument("--out", default=None, help="куда сохранить лист (по умолчанию art/index.png)")
    g.add_argument("--limit", type=int, default=40)
    g.set_defaults(func=cmd_gallery)

    sub.add_parser("doctor", help="проверить окружение").set_defaults(func=cmd_doctor)
    sub.add_parser("selftest", help="полная самопроверка движка").set_defaults(func=cmd_selftest)
    sub.add_parser("mobiletest", help="проверить мост для Android").set_defaults(func=cmd_mobiletest)
    sub.add_parser("icons", help="нарисовать иконку Android-приложения").set_defaults(func=cmd_icons)
    sub.add_parser("checkandroid", help="проверить Android-проект без сборки").set_defaults(func=cmd_checkandroid)
    sub.add_parser("simandroid", help="прогнать движок в режиме Android").set_defaults(func=cmd_simandroid)
    sub.add_parser("clean", help="убрать кэш и служебные папки").set_defaults(func=cmd_clean)

    a = sub.add_parser("api", help="справочник API движка (читает художник)")
    a.add_argument("--full", action="store_true", help="добавить рецепты всех стилей")
    a.set_defaults(func=cmd_api)

    sh = sub.add_parser("show", help="путь к готовой работе")
    sh.add_argument("target", nargs="?", help="часть имени работы (по умолчанию — последняя)")
    sh.add_argument("--meta", action="store_true", help="показать метаданные")
    sh.set_defaults(func=cmd_show)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nпрервано")
        return 130
    except Exception as exc:  # noqa: BLE001
        print(f"ошибка: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
