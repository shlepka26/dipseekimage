<#
.SYNOPSIS
    Собрать APK "ДИПСИК ХУДОЖНИК" одной командой.

.DESCRIPTION
    Скрипт сам находит всё, что нужно для сборки, и докачивает недостающее:

      * Java 17            - из JAVA_HOME, Program Files или PATH
      * Python 3.12        - из DIP_PYTHON, bundled-рантайма DSH или PATH
                             (нужен Chaquopy для сборки байткода и колёс)
      * Android SDK        - из ANDROID_SDK_ROOT/ANDROID_HOME, иначе скачает
                             command-line tools и поставит platform + build-tools
      * Gradle 8.11.1      - из PATH, иначе скачает дистрибутив в .tools

    Ничего не нужно настраивать вручную и не нужно править файлы проекта:
    путь к Python и список ABI передаются в Gradle свойствами.

.PARAMETER DryRun
    Ничего не скачивать и не собирать: только показать, что найдено и что
    будет сделано. Работает полностью офлайн - удобно для проверки.

.PARAMETER X86_64
    Добавить архитектуру x86_64 (для эмулятора). APK станет примерно вдвое больше.

.PARAMETER SkipSdk
    Не скачивать Android SDK (если он уже стоит в нестандартном месте,
    укажи -SdkRoot).

.EXAMPLE
    .\build-apk.ps1 -DryRun
    Проверить, всё ли найдено, ничего не делая.

.EXAMPLE
    .\build-apk.ps1
    Собрать debug-APK для телефона (arm64-v8a).

.EXAMPLE
    .\build-apk.ps1 -X86_64
    Собрать с поддержкой эмулятора.
#>
[CmdletBinding()]
param(
    [string]$ApiLevel = '35',
    [string]$BuildTools = '35.0.0',
    [string]$GradleVersion = '8.11.1',
    [string]$SdkRoot = '',
    [string]$Python = '',
    [switch]$X86_64,
    [switch]$SkipSdk,
    [switch]$SkipGradleDownload,
    [switch]$DryRun,
    [string]$ExplainLog = ''
)

$ErrorActionPreference = 'Continue'
# Именно 'Continue', а не 'Stop': скрипт постоянно зовёт внешние программы
# (java, python, sdkmanager, gradle), а PowerShell 5.1 считает их вывод в stderr
# терминальной ошибкой. Свои ошибки ловим сами: по $LASTEXITCODE и в try/catch.

# Gradle и sdkmanager пишут в UTF-8, а PowerShell разбирает их вывод по кодировке
# консоли. Здесь мы просим UTF-8; если консольного дескриптора нет (вывод в
# трубу), настройка может не примениться - поэтому разбор ошибок ниже опирается
# на ASCII-метки, а не на русский текст.
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch { }

$Root       = $PSScriptRoot
$AndroidDir = Join-Path $Root 'android'
$ToolsDir   = Join-Path $Root '.tools'
$CmdToolsVersion = '11076708'   # command-line tools 12.0

function Step($text)  { Write-Host "`n=== $text" -ForegroundColor Cyan }
function Ok($text)    { Write-Host "  OK    $text" -ForegroundColor Green }
function Note($text)  { Write-Host "  ..    $text" -ForegroundColor Gray }
function Warn($text)  { Write-Host "  !     $text" -ForegroundColor Yellow }
function Fail($text)  { Write-Host "  СТОП  $text" -ForegroundColor Red; exit 1 }

function Get-RemoteFile {
    param([string]$Url, [string]$Dest)
    $dir = Split-Path -Parent $Dest
    if ($dir -and -not (Test-Path $dir)) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }
    Note "скачиваю $Url"
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($curl) {
        & $curl.Source -L --fail --silent --show-error -o $Dest $Url
        if ($LASTEXITCODE -ne 0) { throw "не удалось скачать $Url" }
    } else {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $Url -OutFile $Dest -UseBasicParsing
    }
    Ok ("скачано: {0:N1} МБ" -f ((Get-Item $Dest).Length / 1MB))
}

function Invoke-Capture {
    <# Безопасно снять вывод внешней программы.

       Две ловушки PowerShell 5.1, из-за которых обычный `& $exe args` врёт:
         1) java и python печатают версию в stderr, и при ErrorActionPreference
            ='Stop' это выглядит как терминальная ошибка;
         2) при слиянии 2>&1 каждая строка stderr становится ErrorRecord и
            печатается с префиксом "python.exe :", ломая разбор. Поэтому
            приводим элементы к строке сами. #>
    param([string]$Exe, [string[]]$Arguments = @())
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $parts = @(& $Exe @Arguments 2>&1 | ForEach-Object { $_.ToString() })
        return (($parts -join "`n").Trim())
    } catch {
        return ''
    } finally {
        $ErrorActionPreference = $prev
    }
}

function Get-PythonVersion {
    <# Вернуть '3.12' или $null.

       Одна строка Python намеренно БЕЗ кавычек: PowerShell 5.1 съедает
       двойные кавычки в аргументах внешних программ, и print("%d.%d"%...) 
       превращался бы в print(%d.%d%...) -> SyntaxError. #>
    param([string]$Exe, [string[]]$Pre = @())
    $all = @()
    $all += $Pre
    $all += @('-c', 'import sys;print(sys.version_info[0],sys.version_info[1])')
    $out = Invoke-Capture -Exe $Exe -Arguments $all
    if ($out -match '^\s*(\d+)\s+(\d+)') { return "$($Matches[1]).$($Matches[2])" }
    return $null
}

#: Известные ошибки сборки и что они означают.
#:
#: У каждого правила есть ASCII-идентификатор `id`. Он печатается рядом с
#: подсказкой и нужен тестам: сверять русский текст в консоли нельзя - Windows
#: PowerShell отдаёт его в кодировке консоли, и проверка ломалась бы на ровном
#: месте. Идентификатор от кодировки не зависит.
$GradleHintRules = @(
    @{ id = 'pip_wheel'
       re = 'Could not find a version that satisfies the requirement|No matching distributions'
       hint = 'pip не нашёл колесо под Android. Почти всегда дело в версии Python: Chaquopy собирает колёса строго под неё. Нужен Python 3.12 (запусти с -Python "путь\python.exe").' }
    @{ id = 'chaquopy_repo'
       re = 'Could not resolve com\.chaquo\.python|Plugin \[id: .com\.chaquo\.python'
       hint = 'Плагин Chaquopy не найден в репозиториях. Он публикуется на Maven Central, а не на Google Maven: в android/settings.gradle.kts должен быть mavenCentral().' }
    @{ id = 'state_lock'
       re = 'does not hold the state lock for root project|friendPathsSet'
       hint = 'Известный баг связки Gradle + Chaquopy (chaquo/chaquopy#1339). Лечится так: убрать org.gradle.parallel=true из android/gradle.properties и обновить AGP до 8.9.x с Gradle 8.11.1. В проекте это уже сделано - значит, настройку вернули обратно.' }
    @{ id = 'java_version'
       re = 'Unsupported class file major version|requires Java 17|Unsupported Java'
       hint = 'Не та версия Java. Нужна ровно 17: Android Gradle Plugin 8.7 другие не поддерживает.' }
    @{ id = 'gradle_version'
       re = 'Minimum supported Gradle version|requires Gradle'
       hint = 'Слишком старый Gradle. Нужен 8.9 или новее (в скрипте это -GradleVersion).' }
    @{ id = 'build_python'
       re = 'buildPython|Python .* not found|Failed to find Python'
       hint = 'Chaquopy не нашёл Python 3.12 на сборочной машине. Укажи путь явно: .\build-apk.ps1 -Python "C:\Python312\python.exe"' }
    @{ id = 'android_sdk'
       re = 'SDK location not found|ANDROID_SDK_ROOT|ANDROID_HOME'
       hint = 'Не найден Android SDK. Задай -SdkRoot "D:\Android\Sdk" либо убери -SkipSdk, чтобы скрипт скачал SDK сам.' }
    @{ id = 'sdk_platform'
       re = 'Failed to find target with hash string|platforms;android'
       hint = 'Нет нужной платформы Android SDK. Поставь: sdkmanager "platforms;android-35" "build-tools;35.0.0"' }
    @{ id = 'kotlin_compile'
       re = 'Unresolved reference|Compilation error|e: file:///'
       hint = 'Ошибка компиляции Kotlin. Это уже не про окружение: пришли лог, поправим код.' }
    @{ id = 'gradle_dsl'
       re = 'Could not find method .* for arguments|Could not set unknown property|Cannot run program'
       hint = 'Похоже на несовместимость Gradle-скрипта с версиями плагинов: сверься с таблицей версий в android/README.md.' }
    @{ id = 'disk_space'
       re = 'No space left|insufficient disk space'
       hint = 'Мало места на диске. Chaquopy требует несколько гигабайт под SDK, Gradle и колёса.' }
)

function Get-GradleHint {
    <# Вернуть список сработавших правил (каждое - хеш с id и hint). #>
    param([string[]]$Lines)
    $joined = ($Lines -join "`n")
    $found = @()
    foreach ($rule in $GradleHintRules) {
        if ($joined -match $rule.re) { $found += $rule }
    }
    return $found
}

function Show-LogAnalysis {
    param([string[]]$Lines)
    $hints = Get-GradleHint -Lines $Lines
    if (-not $hints) { return $false }
    Write-Host ""
    Write-Host "  Похоже на известную проблему:" -ForegroundColor Yellow
    foreach ($h in $hints) {
        Write-Host "   * [$($h.id)] $($h.hint)" -ForegroundColor Yellow
    }
    return $true
}

# --- Разбор готового лога (так эту логику проверяют тесты) -----------------
if ($ExplainLog) {
    if (-not (Test-Path $ExplainLog)) {
        Write-Host "нет файла: $ExplainLog" -ForegroundColor Red
        exit 2
    }
    $lines = Get-Content -Path $ExplainLog -Encoding UTF8
    if (-not (Show-LogAnalysis -Lines $lines)) {
        # [none] - ASCII-метка для тестов: сверять русский текст в перехваченном
        # выводе нельзя, кодировка консоли это ломает.
        Write-Host "  [none] известных проблем не найдено"
    }
    exit 0
}

# --- Java ------------------------------------------------------------------
Step "Java 17"

$javaHome = $null
$javaCandidates = @()
if ($env:JAVA_HOME) { $javaCandidates += $env:JAVA_HOME }
foreach ($base in @('C:\Program Files\Eclipse Adoptium',
                    'C:\Program Files\Java',
                    'C:\Program Files\Microsoft',
                    'C:\Program Files\Amazon Corretto')) {
    if (Test-Path $base) {
        Get-ChildItem $base -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match 'jdk-?17|jdk17|17\.' } |
            ForEach-Object { $javaCandidates += $_.FullName }
    }
}
foreach ($c in $javaCandidates) {
    if (Test-Path (Join-Path $c 'bin\java.exe')) { $javaHome = $c; break }
}
if (-not $javaHome) {
    $j = Get-Command java.exe -ErrorAction SilentlyContinue
    if ($j) { $javaHome = Split-Path -Parent (Split-Path -Parent $j.Source) }
}
if (-not $javaHome) {
    Fail @"
Java 17 не найдена. Поставь JDK 17 и повтори:
    winget install EclipseAdoptium.Temurin.17.JDK
или скачай с https://adoptium.net
"@
}

$env:JAVA_HOME = $javaHome
$javaExe = Join-Path $javaHome 'bin\java.exe'
$javaOut = ((Invoke-Capture -Exe $javaExe -Arguments @('-version')) -split "`n")[0]
if ("$javaOut" -notmatch '"17\.') {
    Warn "найдена не 17-я версия: $javaOut"
    Warn "Android Gradle Plugin 8.7 требует Java 17 - сборка может упасть"
} else {
    Ok "$javaOut"
    Note "JAVA_HOME = $javaHome"
}

# --- Python ----------------------------------------------------------------
Step "Python 3.12 (для Chaquopy)"

$pyPath = $null
$pyMode = $null      # 'explicit' - передать путь в Gradle, 'auto' - найдёт сам Chaquopy

foreach ($c in @($Python, $env:DIP_PYTHON)) {
    if ($c -and (Test-Path $c)) {
        $v = Get-PythonVersion -Exe $c
        if ($v -eq '3.12') { $pyPath = $c; $pyMode = 'explicit'; break }
        elseif ($v) { Warn "пропускаю $c - версия $v, нужна 3.12" }
    }
}

if (-not $pyPath) {
    # bundled-рантайм DSH: там ровно 3.12 и уже стоят numpy с Pillow
    $bundled = Join-Path $env:USERPROFILE `
        '.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
    if (Test-Path $bundled) {
        $v = Get-PythonVersion -Exe $bundled
        if ($v -eq '3.12') { $pyPath = $bundled; $pyMode = 'explicit' }
    }
}

if (-not $pyPath) {
    # Chaquopy по умолчанию пробует на Windows 'py -3.12', затем 'py -3'
    $pyLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($pyLauncher -and (Get-PythonVersion -Exe $pyLauncher.Source -Pre @('-3.12')) -eq '3.12') {
        $pyMode = 'auto'
    }
}

if (-not $pyPath -and $pyMode -ne 'auto') {
    $plain = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($plain -and (Get-PythonVersion -Exe $plain.Source) -eq '3.12') { $pyMode = 'auto' }
}

if ($pyMode -eq 'explicit') {
    Ok "$pyPath"
    Note "передам в Gradle: -Pdip.python"
} elseif ($pyMode -eq 'auto') {
    Ok "Python 3.12 доступен через PATH - Chaquopy найдёт его сам"
} else {
    Fail @"
Python 3.12 не найден, а Chaquopy без него не соберёт колёса.
Варианты:
    winget install Python.Python.3.12
    .\build-apk.ps1 -Python "C:\Python312\python.exe"
"@
}

# --- Android SDK -----------------------------------------------------------
Step "Android SDK"

function Test-Sdk {
    param([string]$Path, [string]$Api)
    if (-not $Path) { return $false }
    return (Test-Path (Join-Path $Path "platforms\android-$Api"))
}

$sdk = $null
foreach ($c in @($SdkRoot, $env:ANDROID_SDK_ROOT, $env:ANDROID_HOME,
                 (Join-Path $env:LOCALAPPDATA 'Android\Sdk'))) {
    if (Test-Sdk -Path $c -Api $ApiLevel) { $sdk = $c; break }
}

if ($sdk) {
    Ok "$sdk"
} else {
    if (-not $SdkRoot) { $SdkRoot = Join-Path $env:LOCALAPPDATA 'Android\Sdk' }
    if ($SkipSdk) {
        Fail "Android SDK с platforms\android-$ApiLevel не найден, а -SkipSdk запрещает скачивать"
    }
    Warn "SDK с platforms\android-$ApiLevel не найден - будет скачан в $SdkRoot"
}

if ($sdk) { $env:ANDROID_SDK_ROOT = $sdk; $env:ANDROID_HOME = $sdk }

# --- Gradle ----------------------------------------------------------------
Step "Gradle $GradleVersion"

$gradleExe = $null
$localGradle = Join-Path $ToolsDir "gradle-$GradleVersion\bin\gradle.bat"
if (Test-Path $localGradle) {
    $gradleExe = $localGradle
    Ok "$localGradle (уже скачан)"
} elseif (-not $SkipGradleDownload) {
    Warn "будет скачан в .tools\gradle-$GradleVersion"
} else {
    $g = Get-Command gradle.bat -ErrorAction SilentlyContinue
    if (-not $g) { $g = Get-Command gradle -ErrorAction SilentlyContinue }
    if ($g) { $gradleExe = $g.Source; Ok "$($g.Source)" }
    else { Fail "Gradle не найден, а -SkipGradleDownload запрещает скачивать" }
}

# --- План ------------------------------------------------------------------
Step "План"

$abis = 'arm64-v8a'
if ($X86_64) { $abis = 'arm64-v8a,x86_64' }

Write-Host "  Java 17      : $javaHome"
if ($pyMode -eq 'explicit') { Write-Host "  Python 3.12  : $pyPath" }
else                        { Write-Host "  Python 3.12  : из PATH (определит Chaquopy)" }
if ($sdk) { Write-Host "  Android SDK  : $sdk" }
else      { Write-Host "  Android SDK  : скачать в $SdkRoot (+ platforms;android-$ApiLevel, build-tools;$BuildTools)" }
if ($gradleExe) { Write-Host "  Gradle       : $gradleExe" }
else            { Write-Host "  Gradle       : скачать $GradleVersion в .tools" }
Write-Host "  ABI          : $abis"
Write-Host "  Команда      : gradle :app:assembleDebug  (в папке android)"

if ($DryRun) {
    Write-Host "`n-DryRun: ничего не скачиваю и не собираю." -ForegroundColor Cyan
    exit 0
}

# --- Скачивание SDK --------------------------------------------------------
if (-not $sdk) {
    Step "Ставлю Android SDK"
    New-Item -ItemType Directory -Force -Path $SdkRoot | Out-Null

    $zip = Join-Path $ToolsDir 'cmdline-tools.zip'
    $url = "https://dl.google.com/android/repository/commandlinetools-win-${CmdToolsVersion}_latest.zip"
    Get-RemoteFile -Url $url -Dest $zip

    $unzip = Join-Path $ToolsDir 'cmdline-unzip'
    if (Test-Path $unzip) { Remove-Item -Recurse -Force $unzip }
    Expand-Archive -Path $zip -DestinationPath $unzip -Force

    $dst = Join-Path $SdkRoot 'cmdline-tools\latest'
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dst) | Out-Null
    if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
    Move-Item -Path (Join-Path $unzip 'cmdline-tools') -Destination $dst

    $sdkmanager = Join-Path $dst 'bin\sdkmanager.bat'
    if (-not (Test-Path $sdkmanager)) { Fail "в архиве нет sdkmanager: $sdkmanager" }

    Note "принимаю лицензии"
    $answers = ("y`n" * 40)
    $answers | & $sdkmanager "--sdk_root=$SdkRoot" '--licenses' | Out-Null

    Note "ставлю платформу и build-tools (это несколько минут)"
    & $sdkmanager "--sdk_root=$SdkRoot" "platforms;android-$ApiLevel" `
        "build-tools;$BuildTools" 'platform-tools'
    if ($LASTEXITCODE -ne 0) { Fail "sdkmanager вернул код $LASTEXITCODE" }

    $sdk = $SdkRoot
    $env:ANDROID_SDK_ROOT = $sdk
    $env:ANDROID_HOME = $sdk
    Ok "SDK готов: $sdk"
}

# --- Скачивание Gradle -----------------------------------------------------
if (-not $gradleExe) {
    Step "Скачиваю Gradle $GradleVersion"
    New-Item -ItemType Directory -Force -Path $ToolsDir | Out-Null
    $zip = Join-Path $ToolsDir "gradle-$GradleVersion-bin.zip"
    Get-RemoteFile -Url "https://services.gradle.org/distributions/gradle-$GradleVersion-bin.zip" -Dest $zip
    Expand-Archive -Path $zip -DestinationPath $ToolsDir -Force
    if (-not (Test-Path $localGradle)) { Fail "после распаковки нет $localGradle" }
    $gradleExe = $localGradle
    Ok "$gradleExe"
}

# --- Сборка ----------------------------------------------------------------
Step "Сборка APK"

if (-not (Test-Path $AndroidDir)) { Fail "нет папки $AndroidDir" }

# Кэш байткода Python не должен попасть в APK: Chaquopy забирает python/ целиком.
Get-ChildItem -Path (Join-Path $Root 'python') -Recurse -Directory -Filter '__pycache__' `
    -ErrorAction SilentlyContinue | ForEach-Object { Remove-Item -Recurse -Force $_.FullName }

$gradleArgs = @('--no-daemon', '--stacktrace')
if ($pyMode -eq 'explicit') { $gradleArgs += "-Pdip.python=$pyPath" }
if ($X86_64) { $gradleArgs += '-Pdip.abis=arm64-v8a,x86_64' }
$gradleArgs += ':app:assembleDebug'

$gradleLog = @()
Push-Location $AndroidDir
try {
    Note "$gradleExe $($gradleArgs -join ' ')"
    # Вывод собираем в память: он нужен и на экране, и для разбора ошибки.
    & $gradleExe @gradleArgs 2>&1 | ForEach-Object {
        $line = $_.ToString()
        $gradleLog += $line
        Write-Host $line
    }
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}

$logPath = Join-Path $ToolsDir 'build-log.txt'
New-Item -ItemType Directory -Force -Path $ToolsDir | Out-Null
($gradleLog -join "`n") | Set-Content -Path $logPath -Encoding UTF8

if ($code -ne 0) {
    Show-LogAnalysis -Lines $gradleLog | Out-Null
    Fail @"
Gradle вернул код $code.

Полный лог сохранён: $logPath
Пришли его - по нему видно причину. Если в выводе есть 'What went wrong',
начинать смотреть надо оттуда.
"@
}

# --- Результат -------------------------------------------------------------
Step "Готово"

$apkDir = Join-Path $AndroidDir 'app\build\outputs\apk\debug'
$apks = Get-ChildItem $apkDir -Filter '*.apk' -ErrorAction SilentlyContinue
if (-not $apks) { Fail "Gradle отработал, но APK не найден в $apkDir" }

foreach ($a in $apks) {
    Write-Host ("  {0}  ({1:N1} МБ)" -f $a.FullName, ($a.Length / 1MB)) -ForegroundColor Green
}
Write-Host @"

Как поставить на телефон:
  1. Перекинь APK на телефон (кабель, облако, Telegram - как удобно).
  2. Открой файл и разреши установку из неизвестных источников.
  3. В приложении нажми "Ключ" и вставь свой ключ с platform.deepseek.com.

APK подписан отладочным ключом: для Google Play нужен release со своим keystore.
"@
