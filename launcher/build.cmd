@echo off
setlocal
set "ROOT=%~dp0.."
pushd "%ROOT%" >nul
if not exist "assets\pianoforge.ico" (
  echo [build] icon missing, run "python tools\make_icon.py"
  popd & exit /b 1
)
set "CSC=C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if not exist "%CSC%" set "CSC=C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"
if not exist "%CSC%" (
  echo [build] csc.exe not found
  popd & exit /b 1
)
"%CSC%" /nologo /target:winexe /platform:anycpu /win32icon:"%ROOT%\assets\pianoforge.ico" /out:"%ROOT%\PianoForge.exe" "%ROOT%\launcher\PianoForgeLauncher.cs"
if errorlevel 1 (
  echo [build] FAILED
  popd & exit /b 1
)
echo [build] OK: PianoForge.exe
popd >nul
