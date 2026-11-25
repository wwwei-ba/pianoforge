@echo off
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "PYTHONPATH=%ROOT%\src"
set "PYTHONIOENCODING=utf-8"
set "MPLCONFIGDIR=%ROOT%\cache\mpl"
set "TMP=%ROOT%\tmp"
set "TEMP=%ROOT%\tmp"
set "HF_ENDPOINT=https://hf-mirror.com"
set "TORCH_HOME=%ROOT%\cache\torch"
start "" "%ROOT%\.venv\Scripts\pythonw.exe" -m pianoforge.gui
