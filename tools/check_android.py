# -*- coding: utf-8 -*-
"""Статическая проверка Android-проекта.

Собрать APK без Android SDK нельзя, но большую часть ошибок можно поймать
заранее: битый XML, ссылки на несуществующие ресурсы, рассинхрон имён функций
между Kotlin и Python, несбалансированные скобки в Kotlin/Gradle.

Запуск: .\\dip.cmd checkandroid
"""

from __future__ import annotations

import os
import re
import sys
import xml.etree.ElementTree as ET

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANDROID = os.path.join(ROOT, "android")
APP = os.path.join(ANDROID, "app")
RES = os.path.join(APP, "src", "main", "res")
SRC = os.path.join(APP, "src", "main", "java", "com", "dipseek", "artist")
PYTHON = os.path.join(ROOT, "python")

FAILS: list[str] = []
WARNS: list[str] = []


def check(label: str, fn) -> None:
    try:
        fn()
        print(f"  OK    {label}")
    except Exception as exc:  # noqa: BLE001
        FAILS.append(f"{label}: {exc}")
        print(f"  FAIL  {label} — {exc}")


def _assert(cond, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def all_files(ext: str, base: str | None = None) -> list[str]:
    out = []
    for dirpath, _dirs, files in os.walk(base or ANDROID):
        for f in files:
            if f.endswith(ext):
                out.append(os.path.join(dirpath, f))
    return sorted(out)


# --------------------------------------------------------------------------

def main() -> int:
    print("=" * 66)
    print("проверка Android-проекта (без сборки)")
    print("=" * 66)

    print("\n[1] Структура")

    def structure():
        required = [
            os.path.join(ANDROID, "settings.gradle.kts"),
            os.path.join(ANDROID, "build.gradle.kts"),
            os.path.join(ANDROID, "gradle.properties"),
            os.path.join(APP, "build.gradle.kts"),
            os.path.join(APP, "src", "main", "AndroidManifest.xml"),
            os.path.join(PYTHON, "mobile.py"),
            os.path.join(PYTHON, "dipkit", "__init__.py"),
            os.path.join(ROOT, ".github", "workflows", "android-apk.yml"),
        ]
        missing = [p for p in required if not os.path.exists(p)]
        _assert(not missing, "нет файлов: " + ", ".join(
            p.replace(ROOT + os.sep, "") for p in missing))
        _assert(os.path.isdir(SRC), f"нет папки исходников Kotlin: {SRC}")
    check("все ключевые файлы на месте", structure)

    print("\n[2] XML: синтаксис и ссылки")

    def xml_wellformed():
        files = all_files(".xml", RES) + [
            os.path.join(APP, "src", "main", "AndroidManifest.xml")]
        bad = []
        for f in files:
            try:
                ET.parse(f)
            except ET.ParseError as exc:
                bad.append(f"{os.path.basename(f)}: {exc}")
        _assert(not bad, "; ".join(bad))
        print(f"        разобрано XML-файлов: {len(files)}")
    check("XML разбирается", xml_wellformed)

    def manifest_refs():
        manifest = read(os.path.join(APP, "src", "main", "AndroidManifest.xml"))
        refs = re.findall(r'@(mipmap|string|style|xml|color)/([A-Za-z0-9_.]+)', manifest)
        _assert(refs, "в манифесте нет ссылок на ресурсы")
        for kind, name in refs:
            if kind == "mipmap":
                # либо файл mipmap-<density>/<name>.png, либо mipmap-anydpi-v26/<name>.xml
                found = any(
                    os.path.exists(os.path.join(RES, d, f"{name}.png"))
                    for d in os.listdir(RES) if d.startswith("mipmap-"))
                found = found or os.path.exists(
                    os.path.join(RES, "mipmap-anydpi-v26", f"{name}.xml"))
                _assert(found, f"нет mipmap-ресурса {name}")
            elif kind == "string":
                _assert(f'name="{name}"' in read(os.path.join(RES, "values", "strings.xml")),
                        f"нет строки {name}")
            elif kind == "color":
                _assert(f'name="{name}"' in read(os.path.join(RES, "values", "colors.xml")),
                        f"нет цвета {name}")
            elif kind == "style":
                _assert(f'name="{name}"' in read(os.path.join(RES, "values", "themes.xml")),
                        f"нет стиля {name}")
            elif kind == "xml":
                _assert(os.path.exists(os.path.join(RES, "xml", f"{name}.xml")),
                        f"нет xml/{name}.xml")
    check("манифест ссылается на существующие ресурсы", manifest_refs)

    def icons_complete():
        densities = {"mdpi": (48, 108), "hdpi": (72, 162), "xhdpi": (96, 216),
                     "xxhdpi": (144, 324), "xxxhdpi": (192, 432)}
        for d, (legacy, fg) in densities.items():
            folder = os.path.join(RES, f"mipmap-{d}")
            for name in ("ic_launcher.png", "ic_launcher_round.png",
                         "ic_launcher_foreground.png"):
                p = os.path.join(folder, name)
                _assert(os.path.exists(p), f"нет {d}/{name}")
            # проверим реальный размер обычной иконки
            try:
                from PIL import Image
                with Image.open(os.path.join(folder, "ic_launcher.png")) as im:
                    _assert(im.size == (legacy, legacy),
                            f"{d}: размер {im.size}, ожидался {(legacy, legacy)}")
                with Image.open(os.path.join(folder, "ic_launcher_foreground.png")) as im:
                    _assert(im.size == (fg, fg),
                            f"{d}: foreground {im.size}, ожидался {(fg, fg)}")
            except ImportError:
                pass
    check("иконки есть во всех плотностях и верного размера", icons_complete)

    print("\n[3] Gradle")

    def gradle_balance():
        for f in all_files(".kts"):
            src = read(f)
            stripped = re.sub(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"', "", src, flags=re.S)
            for open_c, close_c in (("{", "}"), ("(", ")"), ("[", "]")):
                a, b = stripped.count(open_c), stripped.count(close_c)
                _assert(a == b, f"{os.path.basename(f)}: {open_c}={a} {close_c}={b}")
    check("скобки в gradle-файлах сбалансированы", gradle_balance)

    def gradle_versions():
        root_gradle = read(os.path.join(ANDROID, "build.gradle.kts"))
        app_gradle = read(os.path.join(APP, "build.gradle.kts"))
        for needle in ('id("com.android.application") version "8.9.3"',
                       'id("com.chaquo.python") version "17.0.0"',
                       'id("org.jetbrains.kotlin.android") version "2.0.21"'):
            _assert(needle in root_gradle, f"нет строки: {needle}")
        # AGP 8.7.x валит сборку с Chaquopy ошибкой "does not hold the state lock"
        _assert('version "8.7.' not in root_gradle,
                "AGP 8.7.x несовместим с Chaquopy: chaquo/chaquopy#1339")
        _assert('version = "3.12"' in app_gradle, "не задана версия Python 3.12")
        _assert('install("numpy==1.26.2")' in app_gradle, "не прибит numpy")
        _assert('install("pillow==11.0.0")' in app_gradle, "не прибит pillow")
        _assert("arm64-v8a" in app_gradle, "не задан ABI")
        # На Windows команды "python3" не существует, поэтому жёстко прописывать
        # её нельзя: путь должен приходить свойством, иначе Chaquopy ищет сам.
        _assert('buildPython("python3")' not in app_gradle,
                'жёсткий buildPython("python3") сломает сборку на Windows')
    check("версии и зависимости зафиксированы", gradle_versions)

    def minsdk_rule():
        app_gradle = read(os.path.join(APP, "build.gradle.kts"))
        m = re.search(r"minSdk\s*=\s*(\d+)", app_gradle)
        _assert(m, "не найден minSdk")
        value = int(m.group(1))
        # pillow-11.0.0 собран как android_24: на меньшем API pip не найдёт wheel
        _assert(value >= 24, f"minSdk={value}, а wheel pillow помечен android_24")
        print(f"        minSdk = {value} (нужно >= 24 из-за pillow android_24)")
    check("minSdk совместим с wheel pillow", minsdk_rule)

    def chaquopy_src():
        app_gradle = read(os.path.join(APP, "build.gradle.kts"))
        m = re.search(r'srcDir\("([^"]+)"\)', app_gradle)
        _assert(m, "не найден srcDir для Chaquopy")
        resolved = os.path.abspath(os.path.join(APP, m.group(1)))
        _assert(os.path.isdir(resolved), f"srcDir не существует: {resolved}")
        _assert(os.path.isdir(os.path.join(resolved, "dipkit")),
                f"в {resolved} нет пакета dipkit")
        _assert(os.path.isfile(os.path.join(resolved, "mobile.py")),
                f"в {resolved} нет mobile.py")
        print(f"        Chaquopy возьмёт движок из {resolved}")
    check("srcDir Chaquopy указывает на общий python/", chaquopy_src)

    def no_parallel_builds():
        """Параллельная сборка вместе с Chaquopy валит :app:compileDebugKotlin
        ошибкой "Current thread does not hold the state lock for root project"
        (chaquo/chaquopy#1339, gradle/gradle#15730). Модуль в проекте один,
        так что параллельность и не ускоряет ничего."""
        props = read(os.path.join(ANDROID, "gradle.properties"))
        enabled = [ln.strip() for ln in props.splitlines()
                   if ln.strip().startswith("org.gradle.parallel")
                   and "true" in ln.lower()]
        _assert(not enabled,
                "включён org.gradle.parallel - это известная причина падения сборки")
        print("        org.gradle.parallel не включён")
    check("параллельная сборка отключена (chaquopy#1339)", no_parallel_builds)

    def wrapper_matches_gradle():
        """Обе зафиксированные версии Gradle должны совпадать: та, что ставит
        CI, и та, что прописана в wrapper для Android Studio."""
        wrapper = read(os.path.join(ANDROID, "gradle", "wrapper",
                                    "gradle-wrapper.properties"))
        _assert("gradle-8.11.1-bin.zip" in wrapper,
                "wrapper указывает не на Gradle 8.11.1")
        print("        wrapper и CI на одной версии Gradle")
    check("версия Gradle в wrapper и в CI совпадает", wrapper_matches_gradle)

    def no_pycache_in_apk():
        """Кэш в python/ попадёт в APK как данные. CI его чистит сам,
        а для локальной сборки это предупреждение."""
        junk = all_files(".pyc", PYTHON) or [
            os.path.join(dp, d) for dp, dirs, _f in os.walk(PYTHON)
            for d in dirs if d == "__pycache__"]
        if junk:
            WARNS.append(
                f"в python/ есть кэш ({len(junk)} шт.) — почисти перед локальной "
                f"сборкой: .\\dip.cmd clean (в GitHub Actions это делается автоматически)")
            print(f"        кэш найден: {len(junk)} шт. (в APK не нужен)")
        else:
            print("        кэша нет")
    check("кэш python/ не попадёт в APK", no_pycache_in_apk)

    print("\n[4] Kotlin")

    def kotlin_balance():
        for f in all_files(".kt", SRC):
            src = read(f)
            stripped = re.sub(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"', "", src, flags=re.S)
            for open_c, close_c in (("{", "}"), ("(", ")")):
                a, b = stripped.count(open_c), stripped.count(close_c)
                _assert(a == b, f"{os.path.basename(f)}: {open_c}={a} {close_c}={b}")
    check("скобки в Kotlin сбалансированы", kotlin_balance)

    def kotlin_package():
        for f in all_files(".kt", SRC):
            src = read(f)
            _assert("package com.dipseek.artist" in src,
                    f"{os.path.basename(f)}: неверный package")
    check("package совпадает с путём и namespace", kotlin_package)

    def bridge_matches_python():
        """Каждая функция, которую зовёт Kotlin, обязана быть в python/mobile.py."""
        bridge = read(os.path.join(SRC, "ArtistBridge.kt"))
        called = set(re.findall(r'call\("([a-z_]+)"', bridge))
        _assert(called, "в ArtistBridge.kt не найдено вызовов")
        mobile = read(os.path.join(PYTHON, "mobile.py"))
        defined = set(re.findall(r"^def ([a-z_]+)\(", mobile, flags=re.M))
        missing = sorted(called - defined)
        _assert(not missing,
                f"Kotlin зовёт функции, которых нет в mobile.py: {missing}")
        print(f"        сверено функций моста: {len(called)} -> {sorted(called)}")
    check("ArtistBridge.kt и mobile.py не разошлись", bridge_matches_python)

    def manifest_activity_exists():
        _assert(os.path.exists(os.path.join(SRC, "MainActivity.kt")),
                "манифест объявляет .MainActivity, а файла нет")
        src = read(os.path.join(SRC, "MainActivity.kt"))
        _assert("class MainActivity" in src, "в MainActivity.kt нет класса MainActivity")
        _assert("PyApplication" in read(os.path.join(APP, "src", "main",
                                                     "AndroidManifest.xml")),
                "в манифесте не подключён PyApplication (Python не запустится)")
    check("Activity и запуск Python объявлены", manifest_activity_exists)

    def prefs_crypto_api():
        """Ключ DeepSeek лежит в EncryptedSharedPreferences. Вид вызова у этой
        библиотеки менялся между версиями, поэтому проверяем, что используется
        актуальная форма: MasterKey.Builder + create(context, fileName, masterKey, ...).
        """
        app_gradle = read(os.path.join(APP, "build.gradle.kts"))
        _assert("androidx.security:security-crypto" in app_gradle,
                "нет зависимости security-crypto")
        prefs = read(os.path.join(SRC, "Prefs.kt"))
        _assert("MasterKey.Builder(" in prefs, "не используется MasterKey.Builder")
        _assert("MasterKey.KeyScheme.AES256_GCM" in prefs, "не задана схема ключа")
        _assert("EncryptedSharedPreferences.create(" in prefs, "нет создания хранилища")
        _assert("PrefKeyEncryptionScheme.AES256_SIV" in prefs, "нет схемы шифрования ключей")
        _assert("PrefValueEncryptionScheme.AES256_GCM" in prefs, "нет схемы шифрования значений")
        # старый API MasterKeys.getOrCreate удалён в 1.1.x
        _assert("MasterKeys.getOrCreate" not in prefs,
                "используется устаревший MasterKeys.getOrCreate")
        # на случай, если шифрованное хранилище недоступно, должен быть запасной путь
        _assert("catch" in prefs, "нет запасного пути, если Keystore недоступен")
        print("        Prefs.kt: актуальный API, есть запасной путь")
    check("шифрованное хранилище ключа на актуальном API", prefs_crypto_api)

    def fileprovider_paths():
        paths = read(os.path.join(RES, "xml", "file_paths.xml"))
        _assert("files-path" in paths, "file_paths.xml не описывает files-path")
        # Python пишет в os.environ["HOME"]/art/works — это files/art/works
        _assert("art/works" in paths.replace("\\", "/"),
                "file_paths.xml не покрывает art/works")
        manifest = read(os.path.join(APP, "src", "main", "AndroidManifest.xml"))
        _assert("FileProvider" in manifest, "в манифесте нет FileProvider")
        _assert("${applicationId}.fileprovider" in manifest,
                "authority FileProvider не совпадает с тем, что использует ImageSaver")
        saver = read(os.path.join(SRC, "ImageSaver.kt"))
        _assert('"${context.packageName}.fileprovider"' in saver,
                "ImageSaver использует другой authority")
    check("FileProvider настроен согласованно", fileprovider_paths)

    print("\n[5] Workflow сборки")

    def workflow():
        path = os.path.join(ROOT, ".github", "workflows", "android-apk.yml")
        src = read(path)
        for needle in ("actions/checkout@v4", "actions/setup-java@v4",
                       "actions/setup-python@v5", "android-actions/setup-android@v4",
                       "gradle/actions/setup-gradle@v6", "actions/upload-artifact@v4"):
            _assert(needle in src, f"нет шага {needle}")
        _assert("python-version: '3.12'" in src, "в CI не зафиксирован Python 3.12")
        _assert("gradle-version: '8.11.1'" in src, "в CI не зафиксирован Gradle 8.11.1")
        _assert("platforms;android-35" in src, "в CI не ставится платформа android-35")
        _assert("working-directory: android" in src, "сборка идёт не из папки android")
        _assert("assembleDebug" in src, "не собирается debug APK")
        _assert("android/app/build/outputs/apk/debug/*.apk" in src,
                "неверный путь к APK для выгрузки")
        # Проверки движка должны идти до установки SDK: незачем ждать
        # скачивания SDK, если сломан Python-код.
        _assert("pillow numpy" in src, "в CI не ставятся зависимости движка (pillow, numpy)")
        for suite in ("tools/selftest.py", "tools/test_mobile.py",
                      "tools/test_android_sim.py"):
            _assert(suite in src, f"в CI не запускается {suite}")
        _assert(src.index("tools/selftest.py") < src.index("android-actions/setup-android"),
                "проверки движка должны стоять до установки Android SDK")
        print("        все шаги и версии на месте; проверки идут до установки SDK")
    check("workflow собирает APK и выкладывает артефакт", workflow)

    def workflow_yaml():
        try:
            import yaml  # type: ignore
        except ImportError:
            WARNS.append("pyyaml не установлен — YAML проверен только по строкам")
            print("        pyyaml недоступен, разбор пропущен")
            return
        data = yaml.safe_load(read(os.path.join(
            ROOT, ".github", "workflows", "android-apk.yml")))
        _assert(isinstance(data, dict) and "jobs" in data, "нет секции jobs")
        _assert("apk" in data["jobs"], "нет job apk")
        steps = data["jobs"]["apk"]["steps"]
        _assert(len(steps) >= 12, f"шагов всего {len(steps)}")
        print(f"        YAML разобран, шагов: {len(steps)}")
    check("YAML корректен", workflow_yaml)

    print("\n[6] Скрипт локальной сборки")

    PS = os.path.join(ROOT, "build-apk.ps1")
    IS_WINDOWS = os.name == "nt"

    def ps_bootstrap():
        """Скрипт «собрать одной командой» обязан запускаться в Windows
        PowerShell 5.1, а тот без BOM читает .ps1 как CP1251: типографские
        тире и кавычки-ёлочки превращаются в кавычки и рвут строки."""
        _assert(os.path.exists(PS), "нет build-apk.ps1")
        raw = open(PS, "rb").read()
        text = raw.decode("utf-8-sig")
        has_bom = raw.startswith(b"\xef\xbb\xbf")
        typographic = [c for c in ("\u2014", "\u2013", "\u00ab", "\u00bb") if c in text]
        if has_bom and not typographic:
            print("        UTF-8 BOM на месте, типографских знаков нет")
            return
        fixed = (text.replace("\u2014", "-").replace("\u2013", "-")
                     .replace("\u00ab", '"').replace("\u00bb", '"'))
        with open(PS, "wb") as fh:
            fh.write(b"\xef\xbb\xbf" + fixed.encode("utf-8"))
        WARNS.append("build-apk.ps1 перезаписан с UTF-8 BOM"
                     + (f" и без знаков {typographic}" if typographic else "")
                     + ": иначе Windows PowerShell 5.1 его не разберёт")
        print("        починено: BOM добавлен, знаки заменены")
    check("build-apk.ps1 в правильной кодировке", ps_bootstrap)

    def ps_parses():
        """Настоящий разбор файла парсером PowerShell: ловит опечатки, которые
        иначе всплывут только при запуске у пользователя.

        На Windows это Windows PowerShell 5.1 (именно он читает .ps1 без BOM
        как CP1251), в CI на Linux - PowerShell Core, если он есть.
        """
        import shutil as _shutil
        import subprocess

        exe = "powershell.exe" if IS_WINDOWS else _shutil.which("pwsh")
        if not exe:
            print("        пропущено: PowerShell недоступен")
            return
        cmd = [
            exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
            "$t=$null;$e=$null;"
            f"$null=[System.Management.Automation.Language.Parser]::ParseFile('{PS}',[ref]$t,[ref]$e);"
            "if($e -and $e.Count -gt 0){$e|ForEach-Object{'ERR: '+$_.Message};exit 1};exit 0",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=180)
        _assert(proc.returncode == 0,
                "PowerShell не разбирает скрипт:\n" + (proc.stdout or "")[:800])
        print(f"        парсер {os.path.basename(exe)}: ошибок нет")
    check("build-apk.ps1 разбирается парсером", ps_parses)

    def ps_dry_run():
        """Самая честная проверка без сборки: прогон -DryRun.
        Ничего не скачивает, работает офлайн."""
        if not IS_WINDOWS:
            print("        пропущено: не Windows")
            return
        import subprocess

        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", PS, "-DryRun"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=600)
        _assert(proc.returncode == 0,
                f"-DryRun вернул {proc.returncode}:\n" + (proc.stdout or "")[-1200:])
        out = proc.stdout or ""
        for needle in ("Java 17", "Python 3.12", "Android SDK", "Gradle", "ABI"):
            _assert(needle in out, f"в плане нет пункта {needle!r}")
        print("        -DryRun: план построен, код возврата 0")
    check("build-apk.ps1 -DryRun проходит", ps_dry_run)

    def ps_matches_gradle():
        """Скрипт должен передавать в Gradle ровно те свойства, что Gradle читает."""
        app_gradle = read(os.path.join(APP, "build.gradle.kts"))
        for prop in ("dip.python", "dip.abis"):
            _assert(f'findProperty("{prop}")' in app_gradle,
                    f"app/build.gradle.kts не читает свойство {prop}")
        ps = open(PS, "rb").read().decode("utf-8-sig")
        _assert("-Pdip.python=" in ps, "скрипт не передаёт -Pdip.python")
        _assert("-Pdip.abis=" in ps, "скрипт не передаёт -Pdip.abis")
        _assert("assembleDebug" in ps, "скрипт не собирает debug APK")
        _assert("__pycache__" in ps, "скрипт не чистит кэш Python перед сборкой")
        print("        свойства Gradle и скрипт согласованы")
    check("build-apk.ps1 и Gradle не разошлись", ps_matches_gradle)

    def log_analysis():
        """Если сборка упадёт, скрипт должен сам объяснить причину. Проверяем
        это на синтетических логах реальных ошибок Gradle."""
        if not IS_WINDOWS:
            print("        пропущено: не Windows")
            return
        import subprocess

        cases = [
            ("Could not find a version that satisfies the requirement pillow==11.0.0",
             "pip_wheel"),
            ("Plugin [id: 'com.chaquo.python', version: '17.0.0'] was not found in any sources",
             "chaquopy_repo"),
            ("Minimum supported Gradle version is 8.9. Current version is 7.5.",
             "gradle_version"),
            ("SDK location not found. Define a valid SDK location.",
             "android_sdk"),
            ("e: file:///app/src/main/java/com/dipseek/artist/MainActivity.kt:120:5 "
             "Unresolved reference: Foo",
             "kotlin_compile"),
            ("Unsupported class file major version 61",
             "java_version"),
            ("Execution failed for task ':app:compileDebugKotlin'.\n"
             "   > Current thread does not hold the state lock for root project 'DipseekArtist'",
             "state_lock"),
            ("No space left on device",
             "disk_space"),
        ]
        logs_dir = os.path.join(ROOT, "art", "_check-logs")
        os.makedirs(logs_dir, exist_ok=True)
        for i, (line, expected_id) in enumerate(cases):
            path = os.path.join(logs_dir, f"case{i}.txt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("* What went wrong:\n" + line + "\n")
            proc = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", PS, "-ExplainLog", path],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=240)
            _assert(proc.returncode == 0,
                    f"-ExplainLog вернул {proc.returncode}")
            out = proc.stdout or ""
            # Сверяем по ASCII-идентификатору, а не по русскому тексту:
            # кодировка консоли не должна влиять на результат проверки.
            _assert(f"[{expected_id}]" in out,
                    f"для {line[:44]!r} ожидалось правило [{expected_id}], "
                    f"получено: {out.strip()[:200]!r}")

        # чистый лог не должен давать ложных срабатываний
        clean = os.path.join(logs_dir, "clean.txt")
        with open(clean, "w", encoding="utf-8") as fh:
            fh.write("BUILD SUCCESSFUL in 3m 12s\n42 actionable tasks: 42 executed\n")
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", PS, "-ExplainLog", clean],
            capture_output=True, text=True, timeout=240)
        _assert("[none]" in (proc.stdout or ""),
                "на успешном логе сработала ложная тревога: "
                + (proc.stdout or "")[:200])
        print(f"        разобрано логов: {len(cases) + 1}, все опознаны верно")
    check("разбор ошибок сборки опознаёт известные сбои", log_analysis)

    print("\n" + "=" * 66)
    for w in WARNS:
        print("  предупреждение:", w)
    if FAILS:
        print(f"ПРОВАЛЕНО: {len(FAILS)}")
        for f in FAILS:
            print("  -", f)
        return 1
    print("СТАТИЧЕСКИХ ОШИБОК НЕТ.")
    print("Осталось собрать APK — в GitHub Actions или в Android Studio.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
