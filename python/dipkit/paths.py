# -*- coding: utf-8 -*-
"""dipkit.paths — где что лежит на ПК и на Android.

На Android код движка упакован внутрь APK, поэтому `__file__` не указывает на
настоящую папку. Единственное место, куда приложению разрешено писать, — это
`os.environ["HOME"]` (внутреннее хранилище приложения). Так требует Chaquopy,
и весь код проекта обязан ходить за путями только сюда.
"""

from __future__ import annotations

import os
import sys

#: True, если код исполняется внутри Android-приложения (Chaquopy).
IS_ANDROID = hasattr(sys, "getandroidapilevel")


def platform_name() -> str:
    """'android' или 'desktop' — для логов и диагностики."""
    if IS_ANDROID:
        try:
            return f"android-api{int(sys.getandroidapilevel())}"
        except Exception:
            return "android"
    return "desktop"


def data_root() -> str:
    """Папка, в которую можно писать: HOME на Android, корень проекта на ПК."""
    if IS_ANDROID:
        return os.environ.get("HOME") or os.getcwd()
    return project_root()


def python_dir() -> str:
    """Папка, содержащая пакет `dipkit` (на Android пути не существует)."""
    if IS_ANDROID:
        return data_root()
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def project_root() -> str:
    """Корень проекта на ПК — родитель папки `python/`."""
    if IS_ANDROID:
        return data_root()
    return os.path.dirname(python_dir())


def works_dir() -> str:
    """Где лежат работы: <data_root>/art/works."""
    return os.path.join(data_root(), "art", "works")


def ensure_dir(path: str) -> str:
    """Создать папку (и родителей), вернуть её путь."""
    os.makedirs(path, exist_ok=True)
    return path


def env_file() -> str:
    """Путь к .env с ключом DeepSeek (только ПК)."""
    return os.path.join(project_root(), ".env")
