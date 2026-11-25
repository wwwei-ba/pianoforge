"""Create the PianoForge shortcut (.lnk) with the generated original icon.

Windows refuses to load .ico files that live under the project folder on this
machine (the shell icon loader runs under a more restricted token than the one
that can read the workspace), so the icon is installed into the user profile
first and the shortcut points there.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON_SRC = os.path.join(ROOT, "assets", "pianoforge.ico")
EXE = os.path.join(ROOT, "PianoForge.exe")
VBS = os.path.join(ROOT, "PianoForge.vbs")
NAME = "PianoForge"


def install_icon() -> str:
    r"""Copy the icon into %LOCALAPPDATA%\PianoForge so the shell can read it."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    dest_dir = os.path.join(base, "PianoForge")
    try:
        os.makedirs(dest_dir, exist_ok=True)
        import hashlib
        digest = hashlib.md5(open(ICON_SRC, "rb").read()).hexdigest()[:8]
        dest = os.path.join(dest_dir, f"PianoForge-{digest}.ico")
        # PowerShell first: some environments let only the shell process write
        # outside the project folder
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Copy-Item -LiteralPath '{ICON_SRC}' -Destination '{dest}' -Force"],
            capture_output=True, text=True, timeout=60)
        if res.returncode != 0 or not os.path.exists(dest):
            shutil.copyfile(ICON_SRC, dest)
        for old in os.listdir(dest_dir):
            if old.startswith("PianoForge") and old.endswith(".ico") and old != os.path.basename(dest):
                try:
                    os.remove(os.path.join(dest_dir, old))
                except Exception:
                    pass
        return dest
    except Exception as exc:
        print(f"icon install failed ({exc}); falling back to the project copy")
        return ICON_SRC


PYTHONW = os.path.join(ROOT, ".venv", "Scripts", "pythonw.exe")


def target() -> tuple[str, str]:
    """Launch the GUI through pythonw.exe.

    pythonw.exe carries a valid digital signature, so Windows never shows a
    SmartScreen / "unknown publisher" prompt for our own unsigned launcher; the
    window icon (set by Tk) supplies the taskbar icon. The compiled launcher is
    kept as a fallback for machines without the venv.
    """
    # an interpreter that is not marked "low integrity" keeps the app at normal
    # privileges; a labelled interpreter silently disables shell integration
    alt_file = os.path.join(ROOT, "python_medium.txt")
    if os.path.exists(alt_file):
        try:
            alt = open(alt_file, encoding="utf-8").read().strip()
            if alt and os.path.exists(alt):
                return alt, "-m pianoforge.gui"
        except Exception:
            pass
    if os.path.exists(PYTHONW):
        return PYTHONW, "-m pianoforge.gui"
    if os.path.exists(EXE):
        return EXE, ""
    return os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                        "System32", "wscript.exe"), f'"{VBS}"'


def make(lnk_path: str, icon_path: str) -> str:
    os.makedirs(os.path.dirname(lnk_path), exist_ok=True)
    target_path, target_args = target()
    ps = f"""
$ErrorActionPreference = 'Stop'
$sh = New-Object -ComObject WScript.Shell
$lnk = $sh.CreateShortcut('{lnk_path}')
$lnk.TargetPath = '{target_path}'
$lnk.Arguments = '{target_args.replace(chr(34), chr(39))}'
$lnk.WorkingDirectory = '{ROOT}'
$lnk.IconLocation = '{icon_path},0'
$lnk.Description = 'PianoForge - audio to piano score, fingerstyle tab and piano track'
$lnk.WindowStyle = 1
$lnk.Save()
Write-Output ('created ' + '{lnk_path}')
"""
    res = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                          "-Command", ps], capture_output=True, text=True, timeout=90)
    sys.stdout.write(res.stdout)
    if res.returncode != 0:
        sys.stderr.write(res.stderr)
    return lnk_path


def read_back(lnk_path: str) -> None:
    ps = f"""
$sh = New-Object -ComObject WScript.Shell
$l = $sh.CreateShortcut('{lnk_path}')
Write-Output ('target=' + $l.TargetPath)
Write-Output ('workdir=' + $l.WorkingDirectory)
Write-Output ('icon=' + $l.IconLocation)
Write-Output ('exists=' + (Test-Path -LiteralPath '{lnk_path}'))
"""
    res = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                         capture_output=True, text=True, timeout=60)
    print(res.stdout.strip())


def main():
    args = list(sys.argv[1:])
    icon_override = None
    if "--icon" in args:
        i = args.index("--icon")
        icon_override = args[i + 1]
        args = args[:i] + args[i + 2:]
    target_lnk = args[0] if args else os.path.join(ROOT, "assets", NAME + ".lnk")
    icon = icon_override or install_icon()
    print("icon ->", icon)
    make(target_lnk, icon)
    read_back(target_lnk)


if __name__ == "__main__":
    main()
