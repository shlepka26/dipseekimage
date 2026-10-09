# -*- coding: utf-8 -*-
"""dipkit.runner — запуск работы художника (work.py) и сбор метаданных.

Работа — это папка `art/works/<дата>-<слаг>/` с файлом `work.py`.

Два движка выполнения:

* **subprocess** — на ПК. Изоляция, жёсткий таймаут, упавшая работа не роняет CLI.
* **exec** — на Android. Подпроцессов там нет (`sys.executable` бесполезен),
  поэтому код выполняется в демон-потоке с перехватом вывода и таймаутом.

Движок выбирается автоматически по `dipkit.paths.IS_ANDROID`, но его можно
задать явно (`engine="exec"`) — это позволяет тестировать Android-путь на ПК.
"""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime

from .paths import IS_ANDROID, data_root, ensure_dir, python_dir, works_dir

#: Куда складывать работы по умолчанию.
WORKS_DIR = works_dir()

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def translit(text: str) -> str:
    """Кириллица -> латиница (для имён папок и файлов)."""
    out = []
    for ch in text.lower():
        if ch in _TRANSLIT:
            out.append(_TRANSLIT[ch])
        elif ch.isalnum() and ch.isascii():
            out.append(ch)
        else:
            out.append("-")
    return "".join(out)


def slugify(text: str, max_len: int = 42) -> str:
    """Человекочитаемый слаг: 'Закат над морем' -> 'zakat-nad-morem'."""
    s = re.sub(r"-{2,}", "-", translit(text or "")).strip("-")
    return (s[:max_len].rstrip("-")) or "work"


def new_work_dir(prompt: str | None = None, slug: str | None = None,
                 root: str | None = None) -> str:
    """Создать папку новой работы и вернуть её путь."""
    base = root or works_dir()
    name = slug or slugify(prompt or "work")
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    path = os.path.join(base, f"{stamp}-{name}")
    original, n = path, 2
    while os.path.exists(path):          # быстрые повторы не должны затирать друг друга
        path = f"{original}-{n}"
        n += 1
    return ensure_dir(path)


#: Импорт движка из работы: art/works/<dir>/work.py -> <root>/python
PATH_BOOTSTRAP = ('import os, sys\n'
                  'sys.path.insert(0, os.path.abspath(os.path.join(\n'
                  '    os.path.dirname(__file__), "..", "..", "..", "python")))\n')


def work_scaffold(prompt: str = "", style: str = "gradient-poster",
                  size: tuple[int, int] | None = None, seed: int | None = None) -> str:
    """Каркас work.py — художник заполняет тело и стиль по вкусу."""
    from .styles import STYLES
    w, h = size or STYLES.get(style, {}).get("size", (1200, 1600))
    pal = STYLES.get(style, {}).get("palette", "midnight")
    pal_src = f'"{pal}"' if isinstance(pal, str) else repr(pal)
    seed_line = f"SEED = {seed}" if seed is not None else "SEED = 20240501"
    prompt_repr = prompt.replace('"', "'")
    headline = (prompt or "заголовок").strip().upper()[:28].replace('"', "'")
    return f'''# -*- coding: utf-8 -*-
"""Работа: {prompt_repr or "без описания"}

Стиль: {style}
Запуск:  .\\dip.cmd run <папка-работы>
"""
{PATH_BOOTSTRAP}
from dipkit import ArtCanvas

{seed_line}
W, H = {w}, {h}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "art.png")

c = ArtCanvas(W, H, bg="#0b0b0f", palette={pal_src})
c.meta = {{"prompt": {prompt_repr!r}, "style": {style!r}, "seed": SEED}}

# ---------------------------------------------------------------- рисунок --
c.gradient(["#070b1a", "#1b2a5b", "#4f7cff"], angle=90)
c.blobs(6, ["#4f7cff", "#9fd0ff"], r=(0.25 * min(W, H), 0.55 * min(W, H)),
        alpha=0.30, seed=SEED)
c.text_fit("{headline}", max_width=0.82, y=int(0.10 * H),
           family="sans-bold", color="#f4f7ff", stroke=2)
c.vignette(0.4).grain(0.04, seed=SEED)
# --------------------------------------------------------------------------

path = c.save(OUT)
print(f"готово: {{path}} ({{c.w}}x{{c.h}})")
'''


# --------------------------------------------------------------------------
# Движок 1: подпроцесс (ПК)
# --------------------------------------------------------------------------

def _run_subprocess(script: str, work_dir: str, timeout: float,
                    seed: int | None, extra_env: dict | None) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = python_dir() + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["DIP_WORK"] = os.path.basename(work_dir)
    env["DIP_ROOT"] = data_root()
    if seed is not None:
        env["DIP_SEED"] = str(seed)
    env.update({k: str(v) for k, v in (extra_env or {}).items()})

    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, script],
            cwd=work_dir, env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        rc, out, err, timed_out = proc.returncode, proc.stdout, proc.stderr, False
    except subprocess.TimeoutExpired as exc:
        rc, timed_out = None, True
        out = exc.stdout if isinstance(exc.stdout, str) else ""
        err = f"таймаут {timeout:g} с — работа прервана"
    return {"returncode": rc, "timed_out": timed_out, "stdout": out or "",
            "stderr": err or "", "seconds": round(time.perf_counter() - t0, 2)}


# --------------------------------------------------------------------------
# Движок 2: exec в потоке (Android)
# --------------------------------------------------------------------------

def _run_exec(script: str, work_dir: str, timeout: float,
              seed: int | None, extra_env: dict | None) -> dict:
    """Выполнить work.py в этом же процессе, но в отдельном демон-потоке.

    Поток нельзя убить по таймауту, поэтому мы просто перестаём его ждать и
    сообщаем о таймауте; поток — демон, процесс он не удержит.
    Побочный эффект: `sys.stdout` подменяется на время работы.
    """
    with open(script, encoding="utf-8") as fh:
        source = fh.read()
    code = compile(source, script, "exec")

    out_buf, err_buf = io.StringIO(), io.StringIO()
    state: dict = {"failed": False}
    ns = {"__name__": "__main__", "__file__": script, "__builtins__": __builtins__}

    env_backup: dict[str, str | None] = {}
    for k, v in (extra_env or {}).items():
        env_backup[k] = os.environ.get(k)
        os.environ[k] = str(v)
    env_backup["DIP_WORK"] = os.environ.get("DIP_WORK")
    os.environ["DIP_WORK"] = os.path.basename(work_dir)
    if seed is not None:
        env_backup["DIP_SEED"] = os.environ.get("DIP_SEED")
        os.environ["DIP_SEED"] = str(seed)

    def target() -> None:
        try:
            exec(code, ns)
        except SystemExit:
            pass
        except BaseException as exc:      # noqa: BLE001
            state["failed"] = True
            err_buf.write("".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)))

    t = threading.Thread(target=target, name="dip-work", daemon=True)
    # Подмену и восстановление делает ИМЕННО вызывающий поток. Если бы это делал
    # рабочий поток в finally, то при таймауте он остался бы жив, finally не
    # выполнился бы никогда, и sys.stdout навсегда остался бы подменённым —
    # на Android это убило бы все последующие логи приложения.
    old_out, old_err = sys.stdout, sys.stderr
    t0 = time.perf_counter()
    sys.stdout, sys.stderr = out_buf, err_buf
    try:
        t.start()
        t.join(timeout)
        timed_out = t.is_alive()
    finally:
        sys.stdout, sys.stderr = old_out, old_err
    seconds = round(time.perf_counter() - t0, 2)

    for k, v in env_backup.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

    err = err_buf.getvalue()
    if timed_out:
        err += f"\nтаймаут {timeout:g} с — работа прервана (поток остался висеть)"
    rc = None if timed_out else (1 if state["failed"] else 0)
    return {"returncode": rc, "timed_out": timed_out,
            "stdout": out_buf.getvalue(), "stderr": err, "seconds": seconds}


# --------------------------------------------------------------------------

def run_work(path: str, timeout: float = 180.0, seed: int | None = None,
             extra_env: dict | None = None, engine: str = "auto") -> dict:
    """Запустить work.py. Возвращает отчёт о запуске."""
    script = os.path.abspath(path)
    if os.path.isdir(script):
        script = os.path.join(script, "work.py")
    work_dir = os.path.dirname(script)

    if not os.path.exists(script):
        return {"ok": False, "error": f"нет файла: {script}", "script": script,
                "returncode": None, "timed_out": False, "stdout": "", "stderr": "",
                "seconds": 0.0, "artifacts": [], "new_files": [],
                "work_dir": work_dir, "engine": engine}

    if engine == "auto":
        engine = "exec" if IS_ANDROID else "subprocess"
    if engine not in ("exec", "subprocess"):
        raise ValueError(f"неизвестный движок: {engine!r}")

    before = set(os.listdir(work_dir)) if os.path.isdir(work_dir) else set()
    raw = (_run_exec if engine == "exec" else _run_subprocess)(
        script, work_dir, timeout, seed, extra_env)

    artifacts = sorted(
        os.path.join(work_dir, f) for f in os.listdir(work_dir)
        if f.lower().endswith((".png", ".jpg", ".svg", ".gif"))
        and not f.endswith(".thumb.png")
    )
    ok = (raw["returncode"] == 0) and bool(artifacts) and not raw["timed_out"]
    return {"ok": ok, "script": script, "work_dir": work_dir, "engine": engine,
            "artifacts": artifacts,
            "new_files": sorted(set(os.listdir(work_dir)) - before), **raw}


def write_meta(work_dir: str, data: dict) -> str:
    """Записать/дополнить meta.json работы."""
    path = os.path.join(work_dir, "meta.json")
    old: dict = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                old = json.load(fh)
        except Exception:
            old = {}
    old.update(data)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(old, fh, ensure_ascii=False, indent=2)
    return path


def render_and_record(work_py: str, prompt: str | None = None,
                      style: str | None = None, timeout: float = 180.0,
                      seed: int | None = None, engine: str = "auto") -> dict:
    """Запустить работу и записать метаданные (даже если она упала)."""
    rep = run_work(work_py, timeout=timeout, seed=seed, engine=engine)
    write_meta(rep["work_dir"], {
        "prompt": prompt,
        "style": style,
        "seed": seed,
        "created": datetime.now().isoformat(timespec="seconds"),
        "ok": rep["ok"],
        "seconds": rep["seconds"],
        "returncode": rep["returncode"],
        "timed_out": rep.get("timed_out", False),
        "engine": rep.get("engine"),
        "artifacts": [os.path.basename(a) for a in rep["artifacts"]],
        "stderr_tail": (rep["stderr"] or "")[-1200:],
        "stdout_tail": (rep["stdout"] or "")[-600:],
    })
    return rep


def list_works(base: str | None = None) -> list[dict]:
    """Все работы, новые сверху."""
    root = base or works_dir()
    if not os.path.isdir(root):
        return []
    items: list[dict] = []
    for name in sorted(os.listdir(root)):
        d = os.path.join(root, name)
        if not os.path.isdir(d):
            continue
        png = os.path.join(d, "art.png")
        meta: dict = {}
        mpath = os.path.join(d, "meta.json")
        if os.path.exists(mpath):
            try:
                with open(mpath, encoding="utf-8") as fh:
                    meta = json.load(fh)
            except Exception:
                meta = {}
        work_py = os.path.join(d, "work.py")
        items.append({
            "name": name, "dir": d,
            "png": png if os.path.exists(png) else None,
            "work_py": work_py if os.path.exists(work_py) else None,
            "has_code": os.path.exists(work_py),
            "meta": meta,
            "mtime": os.path.getmtime(d),
        })
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items
