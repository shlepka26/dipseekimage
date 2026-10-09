# -*- coding: utf-8 -*-
"""Самопроверка движка dipkit: прогоняет все примитивы и эффекты.

Запуск:
    .\\dip.cmd selftest
или
    <bundled-python> tools/selftest.py
"""

from __future__ import annotations

import os
import sys
import time
import traceback

try:  # чтобы кириллица в консоли Windows не превращалась в мусор
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "python"))

import numpy as np  # noqa: E402

from dipkit import ArtCanvas, PALETTES, available_families, fbm  # noqa: E402

OUT = os.path.join(ROOT, "art", "_selftest")
FAILS: list[str] = []


def _assert(cond, msg: str = "условие не выполнено"):
    """Проверка внутри check(): бросает AssertionError с понятным текстом."""
    if not cond:
        raise AssertionError(msg)


def check(label, fn):
    t0 = time.perf_counter()
    try:
        fn()
        dt = (time.perf_counter() - t0) * 1000
        print(f"  OK    {label:<34} {dt:8.0f} ms")
    except Exception as exc:  # noqa: BLE001
        FAILS.append(f"{label}: {exc}")
        print(f"  FAIL  {label:<34} {type(exc).__name__}: {exc}")
        traceback.print_exc(limit=2)


def main() -> int:
    print("=" * 66)
    print("dipkit selftest")
    print("=" * 66)

    print("\n[1] Шрифты")
    fams = available_families()
    for k, v in fams.items():
        mark = "OK  " if v else "--  "
        print(f"  {mark} {k:<12} {os.path.basename(v) if v else 'не найден'}")

    print("\n[2] Основные примитивы (900x700)")
    c = ArtCanvas(900, 700, bg="#0a0a12", palette="neon")
    c.meta = {"kind": "selftest", "style": "primitives"}

    check("gradient", lambda: c.gradient(["#3a0ca3", "#f72585", "#4cc9f0"], angle=65))
    check("radial", lambda: c.radial(["#4cc9f0", "#000000"], center=(0.3, 0.4), radius=420, falloff=1.8))
    check("blobs (additive)", lambda: c.blobs(7, ["#4cc9f0", "#f72585"], r=(90, 260), alpha=0.28, seed=7))
    check("blobs (over)", lambda: c.blobs(3, ["#f72585"], r=(60, 160), alpha=0.25, seed=3, additive=False))
    check("noise цветной", lambda: c.noise(amount=0.4, scale=4, octaves=4, seed=11, colorize=["#0a0a12", "#4cc9f0"]))
    check("noise_field", lambda: fbm(c.w, c.h, 5, 4, seed=2))
    check("grid", lambda: c.grid(step=70, color="#ffffff", alpha=0.07))
    check("scatter", lambda: c.scatter(500, "#e0fbfc", r=(1, 3), alpha=0.6, seed=5, glow=1.2))
    check("rect", lambda: c.rect(60, 60, 380, 240, "#f72585", alpha=0.85))
    check("rect outline", lambda: c.rect(80, 80, 360, 220, "#e0fbfc", width=4, alpha=0.9))
    check("ellipse", lambda: c.ellipse(520, 80, 780, 300, "#4cc9f0", alpha=0.8))
    check("circle", lambda: c.circle(200, 480, 90, "#ffd166", alpha=0.9))
    check("ring", lambda: c.ring(200, 480, 120, "#e0fbfc", width=6, alpha=0.7))
    check("polygon", lambda: c.polygon([(520, 560), (700, 430), (820, 620), (560, 660)], "#3a0ca3", alpha=0.85))
    check("line", lambda: c.line([(60, 640), (300, 560), (540, 660)], "#e0fbfc", width=5, alpha=0.8))
    check("arc", lambda: c.arc(430, 320, 700, 590, 200, 340, "#ffd166", width=8))
    check("wedge", lambda: c.wedge(760, 380, 880, 500, 0, 120, "#f72585", alpha=0.7))
    check("flow", lambda: c.flow(["#4cc9f0", "#f72585"], lines=90, steps=110, scale=3, width=2, alpha=0.4, seed=9))
    check("text", lambda: c.text(60, 620, "dipkit", family="display", size=54, color="#ffffff"))
    check("measure", lambda: c.measure("Проверка", "sans", 40))
    check("text_fit", lambda: c.text_fit("ХУДОЖНИК", max_width=0.85, y=26, family="sans-bold", color="#ffffff", stroke=2))

    print("\n[3] Слои (полный паритет примитивов)")
    lay = [None]

    def layers():
        L = c.new_layer("accent")
        L.gradient(["#f72585", "#4cc9f0"], angle=0, cov=0.55)
        L.blobs(4, ["#ffd166"], r=(40, 140), alpha=0.5, seed=21)   # на слое идёт через _paint
        L.circle(700, 180, 70, "#ffffff", alpha=0.9)
        L.ring(700, 180, 95, "#e0fbfc", width=5, alpha=0.8)
        L.wedge(120, 120, 300, 300, 30, 210, "#e0fbfc", alpha=0.6)
        L.polygon([(400, 400), (520, 330), (600, 470)], "#ffffff", alpha=0.7)
        L.line([(60, 380), (330, 300)], "#ffd166", width=6, alpha=0.9)
        L.arc(430, 320, 700, 590, 200, 340, "#ffd166", width=6)
        L.flow(["#ffffff"], lines=25, steps=60, scale=3, width=1, alpha=0.35, seed=4)
        L.grid(step=120, color="#ffffff", alpha=0.15)
        L.noise(amount=0.3, scale=4, octaves=3, seed=8)
        L.text(120, 300, "слой", family="mono", size=40, color="#ffffff")
        L.scanlines(6, 0.12)
        L.blur(4)
        L.glow(radius=16, intensity=0.6)
        c.flatten()
        lay[0] = L
    check("layer: фигуры+поля+эффекты", layers)

    def layer_effects():
        L = c.new_layer("fx")
        L.gradient(["#4cc9f0", "#f72585"], 45)
        L.posterize(8)
        L.duotone("#05010f", "#4cc9f0", 0.5)
        L.contrast(1.1)
        L.saturate(1.2)
        L.brightness(0.03)
        L.chromatic(4)
        L.invert().invert()
        L.vignette(0.3)
        L.grain(0.03, seed=31)
        L.pixelate(4)
        L.quantize_to_palette()
        L.bloom(0.7, 18, 0.4)
        c.flatten()
    check("layer: все эффекты", layer_effects)

    print("\n[4] Эффекты")
    check("bloom", lambda: c.bloom(0.7, 22, 0.5))
    check("blur", lambda: c.blur(1.5))
    check("vignette", lambda: c.vignette(0.4))
    check("grain", lambda: c.grain(0.045, seed=13))
    check("scanlines", lambda: c.scanlines(5, 0.10, angle=8))
    check("chromatic", lambda: c.chromatic(3))
    check("contrast", lambda: c.contrast(1.12))
    check("saturate", lambda: c.saturate(1.18))
    check("brightness", lambda: c.brightness(0.02))
    check("posterize", lambda: c.posterize(12))
    check("duotone", lambda: c.duotone("#0a0a12", "#ffd166", amount=0.35))

    print("\n[5] Сохранение")
    p1 = os.path.join(OUT, "primitives.png")
    check("save + thumb + json", lambda: c.save(p1))
    for ext in (".png", ".thumb.png", ".json"):
        f = os.path.join(OUT, "primitives" + ext)
        print(f"  {'OK  ' if os.path.exists(f) else 'MISS'} {os.path.basename(f):<22} "
              f"{os.path.getsize(f) if os.path.exists(f) else 0} байт")

    print("\n[6] Изоляция: палитры и режимы")
    check("все палитры", lambda: [ArtCanvas(120, 120, palette=k).gradient(PALETTES[k], angle=45).pixelate(4)
                                  for k in PALETTES])
    check("pixelate + quantize", lambda: ArtCanvas(300, 300, palette="risograph")
          .blobs(5, PALETTES["risograph"], r=(40, 120), alpha=0.5, seed=1)
          .pixelate(6).quantize_to_palette())
    check("crop_fraction", lambda: ArtCanvas(400, 400).gradient(["#000", "#fff"], 0).crop_fraction(0.25, 0.25, 0.75, 0.75))

    print("\n[7] aRGB-корректность холста")
    check("нет NaN/Inf", lambda: (_ for _ in ()).throw(AssertionError("NaN в пикселях"))
          if not np.isfinite(c.px).all() else None)
    check("диапазон 0..1", lambda: (_ for _ in ()).throw(AssertionError("выход за диапазон"))
          if (c.px.min() < -1e-6 or c.px.max() > 1.0 + 1e-6) else None)

    print("\n[8] Текст: выравнивание и обводка (регрессия)")
    state = {}

    def anchor_mm():
        t = ArtCanvas(400, 200, bg="#000000")
        t.text(200, 100, "MM", family="sans-bold", size=80, color="#ffffff", anchor="mm")
        m = t.px.mean(axis=2)
        ys, xs = np.nonzero(m > 0.5)
        assert len(xs) > 50, "текст не нарисован"
        cx, cy = float(xs.mean()), float(ys.mean())
        assert abs(cx - 200) < 14, f"anchor='mm' по X: центр {cx:.0f}, ожидалось ~200"
        assert abs(cy - 100) < 14, f"anchor='mm' по Y: центр {cy:.0f}, ожидалось ~100"
        state["cx"] = cx
    check("anchor='mm' центрирует", anchor_mm)

    def anchor_lm():
        t = ArtCanvas(400, 200, bg="#000000")
        t.text(0, 100, "LLLL", family="sans-bold", size=60, color="#ffffff", anchor="lm")
        m = t.px.mean(axis=2)
        ys, xs = np.nonzero(m > 0.5)
        assert len(xs) > 50, "текст не нарисован"
        assert xs.min() < 12, f"anchor='lm' по X: левый край {xs.min()}, ожидалось ~0"
        assert abs(ys.mean() - 100) < 14, f"anchor='lm' по Y: центр {ys.mean():.0f}, ожидалось ~100"
    check("anchor='lm' прижимает влево", anchor_lm)

    def stroke_paint():
        t = ArtCanvas(420, 200, bg="#000000")
        t.text(10, 40, "OO", family="sans-bold", size=110, color="#ffffff",
               stroke=6, stroke_color="#ff0000")
        red = int(((t.px[..., 0] > 0.6) & (t.px[..., 1] < 0.35) & (t.px[..., 2] < 0.35)).sum())
        white = int((t.px.min(axis=2) > 0.8).sum())
        assert red > 150, f"обводка не нарисована (красных пикселей {red})"
        assert white > 150, f"заливка не нарисована (белых пикселей {white})"
    check("stroke рисует обводку цветом", stroke_paint)

    def light_primitive():
        t = ArtCanvas(300, 300, bg="#000000")
        before = float(t.px.mean())
        t.light(150, 150, 120, "#ffffff", intensity=0.8, falloff=2.0)
        mid, corner = float(t.px[150, 150].mean()), float(t.px[5, 5].mean())
        assert mid > corner + 0.3, f"light() не даёт градиент: центр {mid:.2f}, угол {corner:.2f}"
        assert before == 0.0
    check("light() подсвечивает точку", light_primitive)

    print("\n[9] Шрифты: покрытие глифов (важно для Android)")
    from dipkit.canvas import covers, resolve_family

    check("covers: латиница в sans", lambda: _assert(covers("sans", "Hello")))
    check("covers: кириллица в sans", lambda: _assert(covers("sans", "Привет, мир")))
    check("resolve_family: моно+кириллица", lambda: _assert(
        covers(resolve_family("mono", "Привет"), "Привет"),
        "запасное семейство тоже не покрывает кириллицу"))
    check("resolve_family: display+кириллица", lambda: _assert(
        covers(resolve_family("display", "ГОРЫ"), "ГОРЫ")))

    print("\n[10] Движок выполнения: exec (путь Android) на ПК")
    import shutil

    from dipkit import runner as _runner

    def _exec_case(name, body, timeout=60, **kw):
        """Тестовая папка — внутри проекта: системный %TEMP% закрыт песочницей."""
        d = os.path.join(OUT, "exec", name)
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d, exist_ok=True)
        script = os.path.join(d, "work.py")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write(body)
        kw.setdefault("engine", "exec")      # проверяем именно путь Android
        return _runner.run_work(script, timeout=timeout, **kw)

    def exec_engine():
        rep = _exec_case("render",
            "import os, sys\n"
            f"sys.path.insert(0, {os.path.join(ROOT, 'python')!r})\n"
            "from dipkit import ArtCanvas\n"
            "OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'art.png')\n"
            "c = ArtCanvas(160, 160, palette='neon')\n"
            "c.gradient(['#3a0ca3', '#f72585'], 45)\n"
            "c.circle(80, 80, 40, '#e0fbfc')\n"
            "c.save(OUT)\n"
            "print('ok', c.w, c.h)\n", seed=1)
        _assert(rep["ok"], f"exec-движок не отработал: {rep['stderr'][-400:]}")
        _assert(rep["engine"] == "exec")
        _assert("ok 160 160" in rep["stdout"], f"вывод не перехвачен: {rep['stdout']!r}")
        _assert(rep["artifacts"], "PNG не создан")
        _assert(os.path.getsize(rep["artifacts"][0]) > 1000, "PNG подозрительно мал")
    check("exec: рендер + перехват вывода", exec_engine)

    def exec_timeout():
        real_out = sys.stdout
        rep = _exec_case("timeout", "import time\nwhile True:\n    time.sleep(0.2)\n",
                         timeout=1.5)
        _assert(rep["timed_out"], "таймаут не сработал")
        _assert(not rep["ok"])
        # регрессия: зависший поток не должен оставить sys.stdout подменённым
        _assert(sys.stdout is real_out,
                "sys.stdout остался подменённым после таймаута")
    check("exec: таймаут срабатывает", exec_timeout)

    def exec_error():
        rep = _exec_case("error", "raise ValueError('нарочно')\n", timeout=20)
        _assert(not rep["ok"], "ошибка не поймана")
        _assert("ValueError" in rep["stderr"], f"нет traceback: {rep['stderr']!r}")
    check("exec: ошибка ловится, не роняя процесс", exec_error)

    print("\n[11] Устойчивость к Android: работа без режима 'F'")
    from dipkit import canvas as _canvas

    def upscale_fallback():
        """На Android режим 'F' может быть недоступен. Притворяемся, что его
        нет, и проверяем, что фрактальный шум всё равно считается: на нём
        держатся эффекты noise() и flow()."""
        real = _canvas.Image.fromarray

        def fake(obj, mode=None):
            if mode == "F":
                raise ValueError("нарочно: на Android режим 'F' недоступен")
            return real(obj) if mode is None else real(obj, mode)

        _canvas.Image.fromarray = fake
        try:
            f = _canvas.value_noise(64, 48, 4, seed=3)
            _assert(f.shape == (48, 64), f"форма поля: {f.shape}")
            _assert(float(f.min()) >= 0.0 and float(f.max()) <= 1.0, "поле вне 0..1")
            _assert(float(f.std()) > 0.01, "запасной путь даёт плоское поле")
            fb = _canvas.fbm(64, 48, 3, 4, seed=5)
            _assert(fb.shape == (48, 64), "fbm не отработал на запасном пути")
        finally:
            _canvas.Image.fromarray = real
    check("апскейл без режима 'F' не падает", upscale_fallback)

    def noise_and_flow_survive():
        """Те же эффекты целиком — так проверка ближе к реальной картине."""
        real = _canvas.Image.fromarray

        def fake(obj, mode=None):
            if mode == "F":
                raise ValueError("нарочно")
            return real(obj) if mode is None else real(obj, mode)

        _canvas.Image.fromarray = fake
        try:
            t = ArtCanvas(120, 120, palette="neon")
            t.noise(amount=0.4, scale=3, octaves=3, seed=7)
            t.flow(["#4cc9f0"], lines=8, steps=10, seed=9)
            _assert(np.isfinite(t.px).all(), "в пикселях NaN/Inf")
        finally:
            _canvas.Image.fromarray = real
    check("noise() и flow() работают без режима 'F'", noise_and_flow_survive)

    print("\n" + "=" * 66)
    if FAILS:
        print(f"ПРОВАЛЕНО: {len(FAILS)}")
        for f in FAILS:
            print("  -", f)
        return 1
    print("ВСЁ ХОРОШО — движок работает.")
    print(f"Пример: {p1}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
