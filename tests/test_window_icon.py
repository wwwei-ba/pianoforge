import ctypes, os, sys
from ctypes import wintypes
sys.path.insert(0, r"D:\deepfile\pianoforge\src")
import pianoforge.gui as gui

app = gui.App()
app.update()

user32 = ctypes.windll.user32
user32.GetParent.restype = wintypes.HWND
user32.GetParent.argtypes = [wintypes.HWND]
hwnd = app.winfo_id()
top = user32.GetParent(hwnd)
WM_GETICON = 0x007F
ICON_BIG, ICON_SMALL, ICON_SMALL2 = 1, 0, 2
big = user32.SendMessageW(top, WM_GETICON, ICON_BIG, 0)
small = user32.SendMessageW(top, WM_GETICON, ICON_SMALL, 0)
small2 = user32.SendMessageW(top, WM_GETICON, ICON_SMALL2, 0)
GCLP_HICON = -14
cls_icon = user32.GetClassLongPtrW(top, GCLP_HICON)
print("hwnd", top)
print("WM_GETICON big=", big, "small=", small, "small2=", small2)
print("class icon=", cls_icon)
app.destroy()
