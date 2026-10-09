@echo off
rem dip.cmd - launcher for "DIPSEEK ARTIST".
rem Picks the Python interpreter in this order:
rem   1) %DIP_PYTHON% if set
rem   2) bundled DSH runtime (has Pillow + numpy)
rem   3) "python" from PATH
setlocal
set "PY=%DIP_PYTHON%"
if not defined PY set "PY=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" "%~dp0dip.py" %*
exit /b %ERRORLEVEL%
