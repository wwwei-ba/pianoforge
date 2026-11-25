"""Render the app to PNG files for a visual check."""
import os, sys, time
sys.path.insert(0, r"D:\deepfile\pianoforge\src")
import ctypes
import pianoforge.gui as gui
from PIL import ImageGrab

ROOT = r"D:\deepfile\pianoforge"
OUT = os.path.join(ROOT, "cache")

app = gui.App()
app.geometry("1180x700+20+20")
app.attributes("-topmost", True)
app.update()
app.lift()
app.update()
time.sleep(0.6)
app.update()


def grab(name):
    user32 = ctypes.windll.user32
    hwnd = user32.GetParent(app.winfo_id()) or app.winfo_id()
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    box = (rect.left, rect.top, rect.right, rect.bottom)
    img = ImageGrab.grab(bbox=box, all_screens=True)
    p = os.path.join(OUT, name)
    img.save(p)
    print("saved", p, img.size)


import ctypes.wintypes  # noqa: E402

app.nb.select(app.tab_r)
app.update()
time.sleep(0.4)
folder = os.path.join(ROOT, "out", "fukashigi_lofi")
if os.path.isdir(folder):
    app._activate_song(folder)
    app.update()
    time.sleep(0.5)
    app.update()
grab("ui_results.png")


def grab_widget(widget, name, pad=6):
    widget.update_idletasks()
    x = widget.winfo_rootx() - pad
    y = widget.winfo_rooty() - pad
    w = widget.winfo_width() + 2 * pad
    h = widget.winfo_height() + 2 * pad
    img = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
    p = os.path.join(OUT, name)
    img.save(p)
    print("saved", p, img.size)


grab_widget(app.player.row, "ui_player_seek.png")
grab_widget(app.player.meta, "ui_player_meta.png")
grab_widget(app.pbar.master, "ui_progress_row.png")
grab("ui_results.png")
app.nb.select(app.tab_t)
app.update()
time.sleep(0.3)
grab("ui_transcribe.png")
grab_widget(app.pbar, "ui_progress.png")
app.destroy()
