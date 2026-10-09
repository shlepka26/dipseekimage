# -*- coding: utf-8 -*-
"""Проверка JSON-моста (python/mobile.py) — того контракта, который зовёт Kotlin.

Эти же проверки прогоняются на ПК: мост не зависит от Android, поэтому
ошибку в контракте видно задолго до сборки APK.

Запуск:
    .\\dip.cmd mobiletest
"""

from __future__ import annotations

import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "python"))

import mobile  # noqa: E402

FAILS: list[str] = []


def check(label: str, fn) -> None:
    try:
        fn()
        print(f"  OK    {label}")
    except Exception as exc:  # noqa: BLE001
        FAILS.append(f"{label}: {exc}")
        print(f"  FAIL  {label} — {type(exc).__name__}: {exc}")


def j(raw: str) -> dict:
    """Мост обязан возвращать валидный JSON-объект — проверяем это везде."""
    data = json.loads(raw)
    assert isinstance(data, dict), f"ответ не объект: {type(data)}"
    assert "ok" in data, "в ответе нет поля ok"
    return data


def main() -> int:
    print("=" * 66)
    print("проверка моста mobile.py")
    print("=" * 66)

    print("\n[1] Справочные вызовы")

    def version():
        d = j(mobile.version())
        assert d["ok"] is True
        assert d["platform"] == "desktop", f"платформа: {d['platform']}"
        assert d["android"] is False
        assert d["version"]
    check("version()", version)

    def styles():
        d = j(mobile.styles())
        assert d["ok"] and len(d["styles"]) >= 11, f"стилей: {len(d.get('styles', []))}"
        first = d["styles"][0]
        for key in ("id", "title", "summary", "size_w", "size_h"):
            assert key in first, f"в стиле нет поля {key}"
        assert "poster" in d["sizes"]
    check("styles() — все поля для списка в UI", styles)

    def doctor():
        d = j(mobile.doctor())
        assert d["ok"] is True
        assert d["python_packages"]["pillow"], "нет версии Pillow"
        assert d["python_packages"]["numpy"], "нет версии numpy"
        assert "data" in d["paths"] and "works" in d["paths"]
        assert isinstance(d["fonts"], dict) and d["fonts"]
    check("doctor() — диагностика", doctor)

    print("\n[2] Ошибки не роняют приложение")

    def empty_prompt():
        d = j(mobile.draw(json.dumps({"prompt": "   ", "api_key": "sk-test"})))
        assert d["ok"] is False, "пустой запрос принят"
        assert "пустой" in d["error"]
    check("draw(): пустой запрос -> ok=false", empty_prompt)

    def no_key():
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
        assert d["ok"] is False, "нарисовал без ключа"
        assert d.get("need_key") is True, "нет флага need_key для интерфейса"
    check("draw(): без ключа -> need_key", no_key)

    def broken_code():
        d = j(mobile.render(json.dumps({"code": "raise RuntimeError('нарочно')"})))
        assert d["ok"] is False, "битый код прошёл как успех"
        assert "RuntimeError" in (d.get("stderr") or ""), "нет traceback для показа"
    check("render(): битый код -> traceback в ответе", broken_code)

    def bad_json():
        d = j(mobile.draw("{это не json"))
        assert d["ok"] is False
    check("draw(): мусор вместо JSON -> ok=false", bad_json)

    print("\n[3] Рисование готовым кодом (без сети)")

    work_dir = [None]
    code = (
        "import os, sys\n"
        f"sys.path.insert(0, {os.path.join(ROOT, 'python')!r})\n"
        "from dipkit import ArtCanvas\n"
        "OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'art.png')\n"
        "c = ArtCanvas(240, 320, palette='paper')\n"
        "c.gradient(['#f7f3ec', '#e3dccd'], 90)\n"
        "c.circle(120, 140, 70, '#b4553a')\n"
        "c.text_fit('ТЕСТ', max_width=0.8, y=250, family='display', color='#2f2a25')\n"
        "c.save(OUT)\n"
        "print('готово', c.w, c.h)\n"
    )

    def render_ok():
        d = j(mobile.render(json.dumps({"code": code, "prompt": "тест моста",
                                        "style": "minimal-geometry"})))
        assert d["ok"] is True, f"не отрисовалось: {d.get('error')} {d.get('stderr')}"
        assert os.path.exists(d["png"]), "нет PNG"
        assert os.path.getsize(d["png"]) > 2000, "PNG подозрительно мал"
        assert d["engine"] == "subprocess", f"движок: {d['engine']}"
        assert "готово 240 320" in d["log"], f"лог не пойман: {d['log']!r}"
        work_dir[0] = d["work_dir"]
    check("render(): код -> PNG + лог", render_ok)

    def thumb_exists():
        assert work_dir[0], "нет папки работы из прошлой проверки"
        thumb = os.path.join(work_dir[0], "art.thumb.png")
        assert os.path.exists(thumb), "миниатюра не создана"
    check("миниатюра создана (нужна истории)", thumb_exists)

    print("\n[4] Галерея")

    def works():
        d = j(mobile.works())
        assert d["ok"] is True
        assert isinstance(d["works"], list) and d["works"], "список работ пуст"
        names = [w["name"] for w in d["works"]]
        assert os.path.basename(work_dir[0]) in names, "новой работы нет в списке"
        entry = next(w for w in d["works"] if w["name"] == os.path.basename(work_dir[0]))
        assert entry["png"] and entry["prompt"] == "тест моста"
        assert entry["has_code"] is True
    check("works(): работа видна с описанием", works)

    def work_code():
        d = j(mobile.work_code(json.dumps({"dir": work_dir[0]})))
        assert d["ok"] is True
        assert "ArtCanvas" in d["code"], "код не тот"
    check("work_code(): отдаёт исходник", work_code)

    def delete():
        d = j(mobile.delete_work(json.dumps({"dir": work_dir[0]})))
        assert d["ok"] is True, d.get("error")
        assert not os.path.exists(work_dir[0]), "папка не удалена"
    check("delete_work(): удаляет работу", delete)

    def delete_refuses_outside():
        d = j(mobile.delete_work(json.dumps({"dir": ROOT})))
        assert d["ok"] is False, "разрешил удалить папку вне art/works!"
    check("delete_work(): не трогает путь вне art/works", delete_refuses_outside)

    print("\n" + "=" * 66)
    if FAILS:
        print(f"ПРОВАЛЕНО: {len(FAILS)}")
        for f in FAILS:
            print("  -", f)
        return 1
    print("МОСТ ИСПРАВЕН — Kotlin может на него опираться.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
