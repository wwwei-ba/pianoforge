@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title PianoForge 安装

echo ============================================================
echo   PianoForge 安装程序 / installer
echo   首次安装约需 5-10 分钟，请保持网络畅通
echo ============================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [!] 没有找到 Python。
  echo     请先安装 Python 3.11 或更高版本：
  echo     https://www.python.org/downloads/
  echo     安装时务必勾选 "Add python.exe to PATH"。
  echo.
  pause
  exit /b 1
)
for /f "tokens=2" %%v in ('python -V 2^>^&1') do set PYVER=%%v
echo [0/5] 检测到 Python %PYVER%

if not exist ".venv\Scripts\python.exe" (
  echo [1/5] 创建虚拟环境 .venv ...
  python -m venv .venv
  if errorlevel 1 ( echo [!] 创建虚拟环境失败 & pause & exit /b 1 )
) else (
  echo [1/5] 虚拟环境已存在，跳过
)

echo [2/5] 升级 pip ...
".venv\Scripts\python.exe" -m pip install --upgrade pip -q

echo [3/5] 安装 PyTorch(CPU) ...
".venv\Scripts\python.exe" -m pip install torch --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 echo     （torch 预装失败，稍后随依赖一起装）

echo [4/5] 安装其余依赖（较慢）...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo     换用清华镜像重试 ...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
)
if errorlevel 1 (
  echo.
  echo [!] 依赖安装失败。请检查网络后重新运行本脚本。
  pause
  exit /b 1
)

echo [5/5] 准备钢琴采样 ...
".venv\Scripts\python.exe" tools\fetch_assets.py

echo.
echo ============================================================
echo   安装完成！以后双击 PianoForge.cmd 或 PianoForge.exe 启动
echo ============================================================
pause
