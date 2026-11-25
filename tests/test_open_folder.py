"""open_out must hand the exact folder path to the shell."""
import ctypes
import os
import sys

sys.path.insert(0, r"D:\deepfile\pianoforge\src")
import pianoforge.gui as gui

app = gui.App()
app.update()
folder = os.path.join(r"D:\deepfile\pianoforge\out", "fukashigi_lofi")
app.last_run = {"out": folder}

calls = []
real = ctypes.windll.shell32.ShellExecuteW


class Fake:
    def __call__(self, hwnd, op, path, params, cwd, show):
        calls.append((op, path))
        return 42


ctypes.windll.shell32.ShellExecuteW = Fake()
try:
    ok, err = gui.open_folder_shell(folder)
    print("open_folder_shell:", ok, err)
    app.open_out()
finally:
    ctypes.windll.shell32.ShellExecuteW = real

print("calls:", calls)
print("status:", app.play_status.cget("text"))
passed = ok and calls and calls[0][1] == os.path.normpath(folder)
print("OK" if passed else "FAIL")
app.destroy()
