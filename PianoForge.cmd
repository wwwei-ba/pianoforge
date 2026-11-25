@echo off
rem Launch PianoForge with an interpreter that is not marked with a low
rem integrity label. Sandboxes and some installers label files "Low"; Windows
rem then starts the whole app restricted, which blocks shell integration.
setlocal
set "ROOT=%~dp0"
set "PY=%ROOT%.venv\Scripts\pythonw.exe"
set "ALT="
if exist "%ROOT%python_medium.txt" set /p ALT=<"%ROOT%python_medium.txt"
if defined ALT if exist "%ALT%" set "PY=%ALT%"
if not "%PY%"=="%ROOT%.venv\Scripts\pythonw.exe" (
  set "PYTHONPATH=%ROOT%src;%ROOT%.venv\Lib\site-packages"
) else (
  set "PYTHONPATH=%ROOT%src"
)
set "TMP=%ROOT%tmp"
set "TEMP=%ROOT%tmp"
set "PYTHONIOENCODING=utf-8"
start "" "%PY%" -m pianoforge.gui
endlocal
