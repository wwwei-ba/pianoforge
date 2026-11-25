"""PianoForge desktop app.

Tabs: transcribe / results (tree of songs) / score library.
Scores are previewed in-app (PDF rendered with PyMuPDF) and the piano track can
be played back for a direct A/B against the original.
"""
from __future__ import annotations

import datetime
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import pipeline
from .i18n import (LANGUAGES, get_language, get_setting, language_name, set_language,
                   set_setting, tr)

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    _BASE = TkinterDnD.Tk
    DND = True
except Exception:  # pragma: no cover
    _BASE = tk.Tk
    DND = False

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
AUMID = "PianoForge.Desktop.App"


def _register_aumid_icon() -> None:
    """Tell the shell which icon belongs to our AppUserModelID.

    Without this the taskbar falls back to pythonw.exe's icon when the window
    is pinned; the registration lives in HKCU, so no administrator is needed.
    """
    try:
        import winreg
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        ico = os.path.join(base, "PianoForge", "pianoforge-ui.ico")
        if not os.path.exists(ico):
            src = os.path.join(ROOT, "assets", "pianoforge.ico")
            if os.path.exists(src):
                try:
                    os.makedirs(os.path.dirname(ico), exist_ok=True)
                    import shutil
                    shutil.copyfile(src, ico)
                except Exception:
                    ico = src
        key = "Software\\Classes\\AppUserModelId\\" + AUMID
        k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key)
        winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, "PianoForge")
        winreg.SetValueEx(k, "IconUri", 0, winreg.REG_SZ, ico)
        winreg.SetValueEx(k, "IconBackgroundColor", 0, winreg.REG_SZ, "0")
        k.Close()
    except Exception:
        pass
OUT_ROOT = os.path.join(ROOT, "out")
BG = "#14171c"
PANEL = "#1b1f26"
ELEV = "#232935"
BORDER = "#2e3542"
FG = "#e6e9ef"
MUTED = "#98a1b0"
ACCENT = "#6aa1ff"
AUDIO_EXT = {".ogg", ".mp3", ".wav", ".flac", ".m4a", ".aiff", ".aac", ".opus", ".wma"}

# the four things a song folder exposes; older folders keep working
ARTIFACTS = (
    ("audio", "res.art_audio", ("audio.wav", "piano.wav", "piano.ogg")),
    ("original", "res.art_original", ("original.ogg", "original.mp3", "original.wav",
                                      "original.flac", "original.m4a")),
    ("piano", "res.art_piano", ("piano.pdf", "score_piano.pdf")),
    ("guitar", "res.art_guitar", ("guitar.pdf", "score_guitar_tab.pdf")),
)


def find_artifact(folder: str, key: str) -> str | None:
    """Path of one deliverable inside a song folder (new layout or legacy)."""
    for akey, _label, names in ARTIFACTS:
        if akey != key:
            continue
        for name in names:
            p = os.path.join(folder, name)
            if os.path.exists(p):
                return p
        if key == "original":
            try:
                for f in sorted(os.listdir(folder)):
                    if f.lower().startswith("original."):
                        return os.path.join(folder, f)
            except Exception:
                pass
    return None


def integrity_level() -> str:
    """Mandatory integrity level of this process ("Low", "Medium", ...)."""
    try:
        import ctypes
        from ctypes import wintypes

        class SID_AND_ATTRIBUTES(ctypes.Structure):
            _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]

        class TOKEN_MANDATORY_LABEL(ctypes.Structure):
            _fields_ = [("Label", SID_AND_ATTRIBUTES)]

        adv = ctypes.windll.advapi32
        k32 = ctypes.windll.kernel32
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        adv.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                         ctypes.POINTER(wintypes.HANDLE)]
        tok = wintypes.HANDLE()
        if not adv.OpenProcessToken(k32.GetCurrentProcess(), 0x0008, ctypes.byref(tok)):
            return "?"
        size = wintypes.DWORD()
        adv.GetTokenInformation(tok, 25, None, 0, ctypes.byref(size))
        buf = ctypes.create_string_buffer(size.value)
        if not adv.GetTokenInformation(tok, 25, buf, size, ctypes.byref(size)):
            return "?"
        label = ctypes.cast(buf, ctypes.POINTER(TOKEN_MANDATORY_LABEL)).contents
        adv.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
        adv.GetSidSubAuthorityCount.argtypes = [ctypes.c_void_p]
        cnt = adv.GetSidSubAuthorityCount(ctypes.c_void_p(label.Label.Sid)).contents.value
        adv.GetSidSubAuthority.restype = ctypes.POINTER(wintypes.DWORD)
        adv.GetSidSubAuthority.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        rva = adv.GetSidSubAuthority(ctypes.c_void_p(label.Label.Sid), cnt - 1).contents.value
        return {0x1000: "Low", 0x2000: "Medium", 0x3000: "High",
                0x4000: "System"}.get(rva, hex(rva))
    except Exception:
        return "?"


def open_folder_shell(path: str) -> tuple[bool, str]:
    """Open a folder in Explorer from any integrity level.

    A low-integrity process (sandboxed launcher, some installers) cannot talk to
    the shell directly and cannot start explorer.exe - spawning it produces a
    "0xc0000142" dialog. The fallbacks below go from cheapest to most robust:
    ShellExecute, then the shell's folder API, then a one-shot scheduled task
    that runs explorer with the user's normal token.
    """
    try:
        import ctypes
        rc = ctypes.windll.shell32.ShellExecuteW(None, "open", path, None, None, 1)
        if rc > 32:
            return True, ""
    except Exception:
        pass

    try:
        import ctypes
        ole32 = ctypes.windll.ole32
        shell32 = ctypes.windll.shell32
        ole32.CoInitializeEx(None, 2)
        oidl = ctypes.c_void_p()
        if shell32.SHParseDisplayName(path, None, ctypes.byref(oidl), 0, None) == 0:
            sidl = (ctypes.c_void_p * 1)(oidl.value)
            if shell32.SHOpenFolderAndSelectItems(sidl, 0, None, 0) == 0:
                return True, ""
    except Exception:
        pass

    try:
        import os as _os
        _os.startfile(path)
        return True, ""
    except Exception:
        pass
    if integrity_level() == "Low":
        return False, tr("res.open_low_il")
    return False, tr("res.open_denied")


def has_score(folder: str) -> bool:
    return find_artifact(folder, "piano") is not None or os.path.exists(
        os.path.join(folder, "score_piano.pdf"))


def media_paths(data: str) -> list[str]:
    if not data:
        return []
    parts = re.findall(r"{([^}]*)}|(S+)", data)
    return [b or p for b, p in parts if (b or p)]


def song_key(path: str) -> str:
    """Folder name used for a given audio file (matches pipeline.run)."""
    name = os.path.splitext(os.path.basename(path))[0]
    return "".join(c for c in name if c.isalnum() or c in " -_")[:60].strip() or "track"


class ScoreViewer(ttk.Frame):
    """Continuous vertical score view: the wheel scrolls, pages stack in a column."""

    GAP = 18

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.doc = None
        self.path = None
        self.zoom_factor = 1.15
        self._photos: dict[int, tk.PhotoImage] = {}
        self._offsets: list[tuple[int, int]] = []   # (y, height) per page
        self._width = 0
        self._total_h = 0

        head = ttk.Frame(self)
        head.pack(fill="x")
        self.title = ttk.Label(head, text="", style="Sub.TLabel")
        self.title.pack(side="left")
        self.page_lbl = ttk.Label(head, text="", style="Sub.TLabel")
        self.page_lbl.pack(side="right", padx=(6, 2))
        ttk.Button(head, text="+", width=3, command=lambda: self.zoom(0.15)).pack(
            side="right", padx=(4, 0))
        ttk.Button(head, text="−", width=3, command=lambda: self.zoom(-0.15)).pack(side="right")
        ttk.Button(head, text="⟳", width=3, command=self.fit_width).pack(
            side="right", padx=(0, 4))

        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True, pady=(4, 0))
        self.canvas = tk.Canvas(wrap, bg="#22262e", highlightthickness=0, bd=0)
        self.bar = ttk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self._on_scroll_pos)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.bar.pack(side="right", fill="y")

        self.canvas.bind("<Configure>", lambda e: self._on_resize())
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", lambda e: self._scroll(-3))
        self.canvas.bind("<Button-5>", lambda e: self._scroll(3))
        self.canvas.bind("<ButtonPress-1>", self._drag_start)
        self.canvas.bind("<B1-Motion>", self._drag_move)

    # -- interaction ----------------------------------------------------
    def _on_wheel(self, event):
        delta = -1 if event.delta > 0 else 1
        self._scroll(delta * 3)

    def _scroll(self, steps: int):
        """Scroll by a fixed number of pixels per wheel notch (Tk has no pixel mode)."""
        if not self._total_h:
            return
        view = self.canvas.yview()
        span = max(0.0, view[1] - view[0])
        frac = (steps * 88.0) / float(self._total_h)
        target = max(0.0, min(max(0.0, 1.0 - span), view[0] + frac))
        self.canvas.yview_moveto(target)
        self._render_visible()

    def _drag_start(self, event):
        self.canvas.scan_mark(event.x, event.y)

    def _drag_move(self, event):
        self.canvas.scan_dragto(event.x, event.y, gain=1)
        self._render_visible()

    def _on_scroll_pos(self, first, last):
        self.bar.set(first, last)
        self.page_lbl.configure(text=tr("res.zoom", pct=int(round(self.zoom_factor * 100))))

    def _on_resize(self):
        self._layout()

    def fit_width(self):
        if self.doc is None or self.doc.page_count == 0:
            return
        try:
            w = self.canvas.winfo_width() - 28
            page_w = self.doc[0].rect.width
            if w > 80 and page_w > 0:
                self.zoom_factor = max(0.5, min(3.0, w / float(page_w)))
                self._photos.clear()
                self._layout()
        except Exception:
            pass

    def show(self, pdf_path: str):
        try:
            import pymupdf
            if self.doc is not None:
                try:
                    self.doc.close()
                except Exception:
                    pass
            self.doc = pymupdf.open(pdf_path)
            self.path = pdf_path
            self._photos.clear()
            self.title.configure(text=os.path.basename(os.path.dirname(pdf_path)) + " · " +
                                      os.path.basename(pdf_path))
            self.canvas.yview_moveto(0)
            self._layout()
            self.after(60, self.fit_width)
        except Exception as exc:
            self.canvas.delete("all")
            self.canvas.create_text(12, 12, anchor="nw", fill="#c9d1d9", text=str(exc))

    def close(self):
        """Release the PDF handle (Windows keeps a lock on the file)."""
        try:
            if self.doc is not None:
                self.doc.close()
        except Exception:
            pass
        self.doc = None
        self.path = None
        self._photos.clear()
        try:
            self.canvas.delete("all")
            self.title.configure(text="")
        except Exception:
            pass

    def zoom(self, delta: float):
        if self.doc is None:
            return
        keep = self.canvas.yview()[0]
        self.zoom_factor = max(0.5, min(3.0, self.zoom_factor + delta))
        self._photos.clear()
        self._layout()
        self.canvas.yview_moveto(keep)

    # -- layout ---------------------------------------------------------
    def _layout(self):
        if self.doc is None:
            return
        try:
            self.canvas.delete("all")
            self._photos.clear()
            self._offsets = []
            y = 10
            for i in range(self.doc.page_count):
                rect = self.doc[i].rect
                h = int(rect.height * self.zoom_factor)
                self._offsets.append((y, h))
                y += h + self.GAP
            self._total_h = y
            self._width = int(max(self.doc[i].rect.width for i in range(self.doc.page_count))
                              * self.zoom_factor)
            self.canvas.configure(scrollregion=(0, 0, self._width + 24, self._total_h))
            self._render_visible()
        except Exception:
            pass

    def _render_visible(self):
        if self.doc is None or not self._offsets:
            return
        try:
            top = self.canvas.canvasy(0)
            bottom = top + self.canvas.winfo_height()
            for i, (y, h) in enumerate(self._offsets):
                if y > bottom + 400 or y + h < top - 400:
                    if i in self._photos:
                        self.canvas.delete(f"pg{i}")
                        self._photos.pop(i, None)
                    continue
                if i in self._photos:
                    continue
                self._draw_page(i)
        except Exception:
            pass

    def _draw_page(self, i: int):
        import pymupdf
        page = self.doc[i]
        pix = page.get_pixmap(matrix=pymupdf.Matrix(self.zoom_factor, self.zoom_factor))
        photo = tk.PhotoImage(data=pix.tobytes("png"))
        self._photos[i] = photo
        y, h = self._offsets[i]
        x = max(12, (self.canvas.winfo_width() - pix.width) // 2)
        self.canvas.create_rectangle(x - 1, y - 1, x + pix.width + 1, y + pix.height + 1,
                                     fill="#0f1216", outline="#313743", tags=f"pg{i}")
        self.canvas.create_image(x, y, anchor="nw", image=photo, tags=f"pg{i}")



class CircleButton(tk.Canvas):
    """Round transport button (play / pause / stop) that matches the palette."""

    def __init__(self, parent, glyph: str = "▶", command=None, size: int = 34,
                 accent: str = ACCENT, filled: bool = True):
        try:
            bg = parent.cget("background")
        except Exception:
            bg = BG
        super().__init__(parent, width=size, height=size, bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self._glyph = glyph
        self._size = size
        self._accent = accent
        self._filled = filled
        self._hover = False
        self._command = command
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self._draw()

    def configure(self, cnf=None, **kw):
        if "text" in kw:
            self._glyph = kw.pop("text")
            self._draw()
        if "command" in kw:
            self._command = kw.pop("command")
        if kw or cnf:
            super().configure(cnf, **kw)

    config = configure

    def _click(self, _event):
        if self._command:
            self._command()

    def _enter(self, _event):
        self._hover = True
        self._draw()

    def _leave(self, _event):
        self._hover = False
        self._draw()

    def _draw(self):
        self.delete("all")
        s = self._size
        pad = 2
        fill = self._accent if self._filled else (ELEV if self._hover else BG)
        if self._filled and self._hover:
            fill = "#7cb0ff"
        if not self._filled and not self._hover:
            fill = BG
        self.create_oval(pad, pad, s - pad, s - pad, fill=fill, outline="")
        fg = "#0d1117" if self._filled else (FG if self._hover else MUTED)
        self.create_text(s / 2, s / 2, text=self._glyph, fill=fg,
                         font=("Segoe UI Symbol", 11))


class ProgressBar(tk.Canvas):
    """Thin rounded step indicator that matches the sliders."""

    def __init__(self, parent, maximum: int = 9, width: int = 240, height: int = 8,
                 accent: str = ACCENT):
        try:
            bg = parent.cget("background")
        except Exception:
            bg = BG
        super().__init__(parent, width=width, height=height, bg=bg,
                         highlightthickness=0, bd=0)
        self._max = max(1, int(maximum))
        self._value = 0.0
        self._accent = accent
        self.bind("<Configure>", lambda e: self._draw())
        self._draw()

    def __setitem__(self, key, value):
        if key == "value":
            self._value = max(0.0, min(float(self._max), float(value)))
            self._draw()

    def __getitem__(self, key):
        if key == "value":
            return self._value
        raise KeyError(key)

    def configure(self, cnf=None, **kw):
        if "maximum" in kw:
            self._max = max(1, int(kw.pop("maximum")))
        if "value" in kw:
            self._value = float(kw.pop("value"))
        super().configure(cnf, **kw)
        self._draw()

    def _draw(self):
        self.delete("all")
        w = max(2, self.winfo_width())
        h = max(2, self.winfo_height())
        r = h / 2.0
        y = h / 2.0
        self.create_line(r, y, w - r, y, fill=ELEV, width=h, capstyle="round")
        if self._value > 0:
            frac = min(1.0, self._value / self._max)
            end = r + (w - 2 * r) * frac
            if end > r + 0.5:
                self.create_line(r, y, end, y, fill=self._accent, width=h,
                                 capstyle="round")


class Slider(tk.Canvas):
    """Flat, rounded slider: thin track, filled part, round handle.

    Drawn on a canvas so it looks the same on every Windows theme and stays
    crisp at any DPI; ttk.Scale always brings the native chrome along.
    """

    TRACK = "#2b313c"
    KNOB = "#e9edf5"
    KNOB_HOVER = "#ffffff"

    def __init__(self, parent, value: float = 0.0, command=None, on_release=None,
                 accent: str = "#5b9dff", height: int = 24, width: int = 0,
                 thickness: int = 4, knob: int = 6):
        try:
            bg = parent.cget("background")
        except Exception:
            bg = BG
        super().__init__(parent, height=height, bg=bg, highlightthickness=0, bd=0,
                         cursor="hand2")
        if width:
            self.configure(width=width)
        self._value = max(0.0, min(1.0, float(value)))
        self._command = command
        self._on_release = on_release
        self._accent = accent
        self._thickness = thickness
        self._knob = knob
        self._hover = False
        self._dragging = False
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)

    # -- public ---------------------------------------------------------
    def get(self) -> float:
        return self._value

    def set(self, value: float) -> None:
        self._value = max(0.0, min(1.0, float(value)))
        self._draw()

    # -- drawing --------------------------------------------------------
    def _geom(self):
        w = max(1, self.winfo_width())
        h = max(1, self.winfo_height())
        pad = self._knob + 2
        return pad, w - pad, h // 2

    def _draw(self):
        self.delete("all")
        x0, x1, cy = self._geom()
        if x1 <= x0:
            return
        r = self._thickness / 2.0
        self.create_line(x0, cy, x1, cy, fill=self.TRACK, width=self._thickness,
                         capstyle="round")
        kx = x0 + (x1 - x0) * self._value
        if kx > x0 + 0.5:
            self.create_line(x0, cy, kx, cy, fill=self._accent, width=self._thickness,
                             capstyle="round")
        radius = self._knob + (1 if (self._hover or self._dragging) else 0)
        self.create_oval(kx - radius, cy - radius, kx + radius, cy + radius,
                         fill=self.KNOB_HOVER if (self._hover or self._dragging) else self.KNOB,
                         outline="")

    # -- interaction ----------------------------------------------------
    def _value_at(self, x: int) -> float:
        x0, x1, _ = self._geom()
        if x1 <= x0:
            return 0.0
        return max(0.0, min(1.0, (x - x0) / float(x1 - x0)))

    def _apply(self, x: int):
        self._value = self._value_at(x)
        self._draw()
        if self._command:
            try:
                self._command(self._value)
            except Exception:
                pass

    def _press(self, event):
        self._dragging = True
        self._apply(event.x)

    def _drag(self, event):
        if self._dragging:
            self._apply(event.x)

    def _release(self, _event):
        self._dragging = False
        self._draw()
        if self._on_release:
            try:
                self._on_release()
            except Exception:
                pass

    def _enter(self, _event):
        self._hover = True
        self._draw()

    def _leave(self, _event):
        self._hover = False
        self._draw()


class AudioPlayer:
    """Small WAV player: play/pause, seek, volume, A/B between two sources."""

    def __init__(self, app, parent, on_status):
        self.app = app
        self.parent = parent
        self.on_status = on_status
        self.data = None
        self.sr = 44100
        self.duration = 0.0
        self.path = None
        try:
            self.volume = max(0.0, min(1.0, float(get_setting("volume", 0.8))))
        except Exception:
            self.volume = 0.8
        self.playing = False
        self.anchor = 0.0
        self.wall0 = 0.0
        self._flip = 0
        self._after = None
        self.cache_dir = os.path.join(ROOT, "cache", "playback")
        os.makedirs(self.cache_dir, exist_ok=True)
        self._seeking = False
        self._guard = False
        self.loaded_mtime = 0.0
        self.loaded_size = 0

        # transport row: play / stop / time / seek
        self.row = ttk.Frame(parent)
        self.row.pack(fill="x", pady=(6, 0))
        self.play_btn = CircleButton(self.row, glyph="▶", command=self.toggle, size=34)
        self.play_btn.pack(side="left")
        self.stop_btn = CircleButton(self.row, glyph="■", command=self.stop, size=34,
                                     filled=False)
        self.stop_btn.pack(side="left", padx=(6, 12))
        self.time_lbl = ttk.Label(self.row, text="00:00 / 00:00", style="Mono.TLabel")
        self.time_lbl.pack(side="left", padx=(0, 10))
        self.scale = Slider(self.row, value=0.0, command=self.on_seek_drag,
                            on_release=self.on_seek_release, accent="#5b9dff",
                            height=26, thickness=4, knob=6)
        self.scale.pack(side="left", fill="x", expand=True, padx=(2, 6))

        # meta row: which file is loaded, volume with a numeric readout
        self.meta = ttk.Frame(parent)
        self.meta.pack(fill="x", pady=(2, 2))
        self.info_lbl = ttk.Label(self.meta, text="", style="Sub.TLabel")
        self.info_lbl.pack(side="left")
        self.mute_btn = ttk.Button(self.meta, text="", width=8, command=self.toggle_mute)
        self.mute_btn.pack(side="right")
        self.vol_pct = ttk.Label(self.meta, text="", style="Mono.TLabel", width=5,
                                 anchor="e")
        self.vol_pct.pack(side="right")
        self.vol = Slider(self.meta, value=self.volume, command=self.on_volume,
                          on_release=self._remember_volume, accent="#7aa2f7",
                          height=22, width=132, thickness=4, knob=5)
        self._guard = True
        self.vol.set(self.volume)
        self._guard = False
        self.vol.pack(side="right", padx=(4, 6))
        self.vol_lbl = ttk.Label(self.meta, text="", style="Sub.TLabel")
        self.vol_lbl.pack(side="right")
        self._last_volume = self.volume
        self.vol.bind("<MouseWheel>", self._wheel_volume)
        self._update_volume_label()

    # -- state ---------------------------------------------------------
    def set_time_label(self, pos=None):
        pos = self.position() if pos is None else pos
        self.time_lbl.configure(text=f"{fmt_time(pos)} / {fmt_time(self.duration)}")

    def load(self, path: str) -> bool:
        if not path or not os.path.exists(path):
            return False
        from . import audio_io
        try:
            y, sr = audio_io.load_audio(path, sr=44100, mono=False)
        except Exception as exc:
            self.on_status(str(exc))
            return False
        if y.ndim == 1:
            y = y[:, None]
        self.data = y.astype("float32")
        self.sr = sr
        self.duration = len(self.data) / float(sr)
        self.path = path
        try:
            st = os.stat(path)
            self.loaded_mtime = st.st_mtime
            self.loaded_size = st.st_size
        except Exception:
            self.loaded_mtime = 0.0
            self.loaded_size = 0
        self.anchor = 0.0
        self.set_time_label(0.0)
        self._guard = True
        try:
            self.scale.set(0.0)
        finally:
            self._guard = False
        try:
            song = os.path.basename(os.path.dirname(path)) or os.path.basename(path)
            self.info_lbl.configure(text=f"{song} · {fmt_time(self.duration)}")
        except Exception:
            self.info_lbl.configure(text=os.path.basename(path))
        return True

    def position(self) -> float:
        if self.playing:
            import time
            return min(self.duration, self.anchor + (time.time() - self.wall0))
        return self.anchor

    # -- playback ------------------------------------------------------
    def stale(self) -> bool:
        """True when the file on disk changed since it was loaded."""
        if not self.path:
            return False
        try:
            st = os.stat(self.path)
        except Exception:
            return False
        return abs(st.st_mtime - self.loaded_mtime) > 1e-6 or st.st_size != self.loaded_size

    def reload_if_stale(self) -> bool:
        if self.data is None or not self.stale():
            return False
        pos = self.anchor
        if self.load(self.path):
            self.anchor = min(pos, max(0.0, self.duration - 0.1))
            self.on_status(tr("res.reloaded", name=os.path.basename(self.path)))
            return True
        return False

    def play_from(self, t: float):
        if self.data is None:
            self.on_status(tr("res.no_audio"))
            return
        if self.stale():
            self.reload_if_stale()
        t = max(0.0, min(self.duration - 0.02, float(t)))
        self.stop(silent=True)
        start = int(t * self.sr)
        chunk = self.data[start:]
        if self.volume < 0.999:
            chunk = chunk * float(self.volume)
        self._flip ^= 1
        tmp = os.path.join(self.cache_dir, f"_play{self._flip}.wav")
        try:
            import soundfile as sf
            sf.write(tmp, chunk, self.sr, subtype="PCM_16")
        except Exception as exc:
            self.on_status(str(exc))
            return
        try:
            import winsound
            winsound.PlaySound(os.path.normpath(tmp),
                               winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception as exc:
            # last resort: hand the file to the system player so the user still hears it
            try:
                os.startfile(os.path.normpath(tmp))
                self.on_status(tr("res.fallback_player"))
            except Exception:
                self.on_status(str(exc))
            return
        self.playing = True
        self.anchor = t
        import time
        self.wall0 = time.time()
        self.play_btn.configure(text="❚❚")
        self.on_status(tr("res.playing", name=os.path.basename(self.path or "")))
        self._tick()

    def toggle(self):
        if self.playing:
            self.pause()
            return
        if self.data is not None and self.stale():
            self.reload_if_stale()
        if self.data is None:
            # nothing loaded yet: ask the app for the current source and start there
            self.app.on_source()
            return
        self.play_from(self.anchor)

    def pause(self):
        if not self.playing:
            return
        self.anchor = self.position()
        self.playing = False
        try:
            import winsound
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass
        self.play_btn.configure(text="▶")
        self.set_time_label(self.anchor)

    def stop(self, silent: bool = False):
        was = self.playing
        self.playing = False
        try:
            import winsound
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass
        self.anchor = 0.0 if not silent else self.anchor
        self.play_btn.configure(text="▶")
        if not silent:
            self.set_time_label(0.0)
            self._guard = True
            try:
                self.scale.set(0.0)
            finally:
                self._guard = False
            self.on_status(tr("res.stopped"))

    # -- widgets -------------------------------------------------------
    def on_seek_drag(self, value):
        """Only move the label while dragging; seeking happens on release."""
        if self._guard or self.data is None:
            return
        self._seeking = True
        self.set_time_label(float(value) * self.duration)

    def on_seek_release(self, _event=None):
        if self.data is None:
            return
        self._seeking = False
        pos = float(self.scale.get()) * self.duration
        if self.playing:
            self.play_from(pos)
        else:
            self.anchor = pos
            self.set_time_label(pos)

    def _remember_volume(self, apply: bool = True):
        """Persist the in-app volume and apply it to the running track."""
        try:
            set_setting("volume", round(float(self.volume), 3))
        except Exception:
            pass
        if apply and self.playing:
            # winsound has no volume control: restart with the scaled chunk once,
            # on release, instead of rewriting the whole track on every drag step
            self.play_from(self.position())

    def _update_volume_label(self):
        pct = int(round(self.volume * 100))
        self.vol_pct.configure(text=f"{pct}%")
        self.mute_btn.configure(
            text=tr("res.unmute") if self.volume <= 0.001 else tr("res.mute"))

    def _wheel_volume(self, event):
        step = 0.05 if event.delta > 0 else -0.05
        self.volume = max(0.0, min(1.0, self.volume + step))
        self._guard = True
        self.vol.set(self.volume)
        self._guard = False
        self._update_volume_label()
        self._remember_volume()
        return "break"

    def toggle_mute(self):
        if self.volume > 0.001:
            self._last_volume = self.volume
            self._guard = True
            self.vol.set(0.0)
            self._guard = False
            self.volume = 0.0
        else:
            self.volume = self._last_volume or 0.8
            self._guard = True
            self.vol.set(self.volume)
            self._guard = False
        self._update_volume_label()
        self._remember_volume()

    def on_volume(self, value):
        """Drag feedback only; the new level is applied on release."""
        if self._guard:
            return
        self.volume = float(value)
        self._update_volume_label()

    def _tick(self):
        if not self.playing:
            return
        pos = self.position()
        self.set_time_label(pos)
        if self.duration > 0:
            self._guard = True
            try:
                self.scale.set(min(1.0, pos / self.duration))
            finally:
                self._guard = False
        if pos >= self.duration - 0.05:
            self.stop()
            return
        self._after = self.app.after(250, self._tick)


def fmt_time(t: float) -> str:
    t = max(0, int(round(t)))
    return f"{t // 60:02d}:{t % 60:02d}"


def _enable_dpi_awareness() -> None:
    """Crisp text on scaled displays, and Tk and Win32 agree on pixel sizes."""
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


class App(_BASE):
    def __init__(self):
        _enable_dpi_awareness()
        super().__init__()
        self.geometry("1120x760")
        self.minsize(980, 640)
        self.configure(bg=BG)
        # the window belongs to pythonw.exe: give it our icon and a stable
        # AppUserModelID so the taskbar shows PianoForge, not Python
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(AUMID)
        except Exception:
            pass
        _register_aumid_icon()
        try:
            _ico = os.path.join(ROOT, "assets", "pianoforge.ico")
            if os.path.exists(_ico):
                self.iconbitmap(default=_ico)
                self.iconbitmap(_ico)
        except Exception:
            pass
        try:
            # dark title bar to match the app (Windows 10 1809+ / Windows 11)
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            on = ctypes.c_int(1)
            for attr in (20, 19):
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr,
                                                           ctypes.byref(on), ctypes.sizeof(on))
        except Exception:
            pass
        self.q: queue.Queue = queue.Queue()
        self.out_dir = None
        self.last_run: dict | None = None
        self._texts: list[tuple[tk.Widget, str, str]] = []
        self._status_key = "app.ready"
        self._overwrite_ok = False
        self.play_target: str | None = None

        style = ttk.Style(self)
        style.theme_use("clam")
        # one flat dark palette, no native chrome anywhere
        style.configure(".", background=BG, foreground=FG, font=("Segoe UI", 10),
                        borderwidth=0, focuscolor=BG)
        style.configure("TLabel", background=BG, foreground=FG, font=("Segoe UI", 10))
        style.configure("Sub.TLabel", foreground=MUTED)
        style.configure("Mono.TLabel", foreground="#c9d1d9", font=("Consolas", 10))
        style.configure("Header.TLabel", font=("Segoe UI Semibold", 17), foreground="#ffffff")
        style.configure("Drop.TLabel", foreground=MUTED, font=("Segoe UI", 10, "italic"))
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=PANEL)
        style.configure("TButton", background=ELEV, foreground=FG, padding=(14, 8),
                        borderwidth=0, relief="flat", font=("Segoe UI", 10))
        style.map("TButton",
                  background=[("pressed", "#333d4d"), ("active", "#2b3340")],
                  foreground=[("disabled", MUTED)])
        style.configure("Accent.TButton", background=ACCENT, foreground="#0d1117",
                        padding=(18, 9), font=("Segoe UI Semibold", 10))
        style.map("Accent.TButton",
                  background=[("pressed", "#4b86e6"), ("active", "#7cb0ff")])
        style.configure("Compact.TButton", background=ELEV, foreground=FG,
                        padding=(11, 7), font=("Segoe UI", 9))
        style.map("Compact.TButton",
                  background=[("pressed", "#333d4d"), ("active", "#2b3340")])
        style.configure("Ghost.TButton", background=BG, foreground=MUTED, padding=(11, 7),
                        font=("Segoe UI", 9))
        style.map("Ghost.TButton", background=[("active", ELEV)], foreground=[("active", FG)])
        style.configure("Src.TRadiobutton", background=BG, foreground=MUTED,
                        font=("Segoe UI", 9), padding=(2, 2))
        style.map("Src.TRadiobutton", background=[("active", BG)],
                  foreground=[("selected", FG), ("active", FG)],
                  indicatorcolor=[("selected", ACCENT), ("!selected", ELEV)])
        style.map("Ghost.TButton", background=[("active", ELEV)], foreground=[("active", FG)])
        style.configure("TCheckbutton", background=BG, foreground=FG, focuscolor=BG,
                        padding=(2, 4), indicatorcolor=ELEV, indicatorrelief="flat",
                        indicatorbackground=ELEV, indicatorforeground=ACCENT,
                        indicatormargin=(0, 0, 8, 0), upperbordercolor=ELEV,
                        lowerbordercolor=ELEV, bordercolor=ELEV,
                        lightcolor=ELEV, darkcolor=ELEV)
        style.map("TCheckbutton", background=[("active", BG)],
                  indicatorcolor=[("selected", ACCENT), ("!selected", ELEV)],
                  indicatorbackground=[("selected", ACCENT), ("!selected", ELEV)],
                  foreground=[("active", FG)])
        try:
            style.layout("TNotebook", [("Notebook.client", {"sticky": "nswe"})])
        except Exception:
            pass
        style.configure("TEntry", fieldbackground=ELEV, foreground=FG, insertcolor=FG,
                        bordercolor=BORDER, lightcolor=ELEV, darkcolor=ELEV, padding=6)
        style.configure("TCombobox", fieldbackground=ELEV, background=ELEV, foreground=FG,
                        arrowcolor=MUTED, bordercolor=ELEV, lightcolor=ELEV,
                        darkcolor=ELEV, arrowsize=12, padding=5)
        style.map("TCombobox", fieldbackground=[("readonly", ELEV)],
                  foreground=[("readonly", FG)])
        self.option_add("*TCombobox*Listbox.background", ELEV)
        self.option_add("*TCombobox*Listbox.foreground", FG)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.option_add("*TCombobox*Listbox.selectForeground", "#0d1117")
        style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(6, 6, 6, 0),
                        bordercolor=BG, lightcolor=BG, darkcolor=BG)
        style.configure("TNotebook.Tab", background=BG, foreground=MUTED,
                        padding=(18, 9), borderwidth=0, font=("Segoe UI", 10),
                        bordercolor=BG, lightcolor=BG, darkcolor=BG)
        style.map("TNotebook.Tab",
                  background=[("selected", PANEL), ("active", BG)],
                  foreground=[("selected", FG), ("active", FG)],
                  bordercolor=[("selected", BG), ("active", BG)],
                  lightcolor=[("selected", BG), ("active", BG)],
                  darkcolor=[("selected", BG), ("active", BG)],
                  expand=[("selected", (0, 0, 0, 0))])
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL,
                        foreground=FG, rowheight=27, borderwidth=0, font=("Segoe UI", 10))
        style.map("Treeview", background=[("selected", "#2c3a55")],
                  foreground=[("selected", "#ffffff")])
        style.configure("Treeview.Heading", background=PANEL, foreground=MUTED,
                        borderwidth=0, font=("Segoe UI", 9))
        style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        for orient in ("Vertical", "Horizontal"):
            style.configure(f"{orient}.TScrollbar", background=ELEV, troughcolor=BG,
                            borderwidth=0, arrowcolor=MUTED, gripcount=0, relief="flat",
                            lightcolor=ELEV, darkcolor=ELEV, bordercolor=BG,
                            arrowsize=12)
            style.map(f"{orient}.TScrollbar",
                      background=[("active", "#3a4453"), ("pressed", ACCENT)],
                      lightcolor=[("active", ELEV)], darkcolor=[("active", ELEV)])
        style.configure("TSpinbox", fieldbackground=ELEV, background=ELEV, foreground=FG,
                        arrowcolor=MUTED, bordercolor=ELEV, lightcolor=ELEV,
                        darkcolor=ELEV, insertcolor=FG, padding=4)
        style.map("TSpinbox", fieldbackground=[("readonly", ELEV)],
                  foreground=[("readonly", FG)])

        head = ttk.Frame(self)
        head.pack(fill="x", padx=16, pady=(12, 0))
        self.title_lbl = ttk.Label(head, text="", style="Header.TLabel")
        self.title_lbl.pack(side="left")
        self.lang_lbl = ttk.Label(head, text="", style="Sub.TLabel")
        self.lang_lbl.pack(side="right", padx=(8, 6))
        self.lang_box = ttk.Combobox(head, values=[n for _, n in LANGUAGES],
                                     state="readonly", width=9, font=("Segoe UI", 9))
        self.lang_box.pack(side="right")
        self.lang_box.bind("<<ComboboxSelected>>", self.on_language)

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=14, pady=10)
        self.tab_t = ttk.Frame(self.nb)
        self.tab_r = ttk.Frame(self.nb)
        self.tab_s = ttk.Frame(self.nb)
        for t in (self.tab_t, self.tab_r, self.tab_s):
            self.nb.add(t, text="")
        self._tab_keys = ["tab.transcribe", "tab.results", "tab.scores"]

        self._build_transcribe(self.tab_t)
        self._build_results(self.tab_r)
        self._build_scores(self.tab_s)

        self._reg(self.title_lbl, "app.title")
        self._reg(self.lang_lbl, "app.language")
        self.apply_language(get_language(), announce=False)
        self.log.insert("end", tr("app.log_ready") + "\n")
        self._low_il = integrity_level() == "Low"
        if self._low_il:
            # sandboxed/limited launches cannot talk to the shell; say so once,
            # and mark the window so it is obvious which instance is running
            self.log.insert("end", tr("app.low_integrity") + "\n")
            self.apply_language(get_language(), announce=False)

        if DND:
            for w in (self, self.entry):
                try:
                    w.drop_target_register(DND_FILES)
                    w.dnd_bind("<<Drop>>", self.on_drop)
                    w.dnd_bind("<<DropEnter>>", lambda e: self._hover(True))
                    w.dnd_bind("<<DropLeave>>", lambda e: self._hover(False))
                except Exception:
                    pass
        self.report_callback_exception = self._on_tk_error
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._restore_last_run()
        self.after(200, self.poll)

    @staticmethod
    def engine_names():
        return [tr("app.engine_full"), tr("app.engine_neural"),
                tr("app.engine_piano"), tr("app.engine_classic")]

    def engine_key(self) -> str:
        names = self.engine_names()
        keys = ["full", "neural", "piano", "classic"]
        try:
            return keys[names.index(self.engine_var.get())]
        except ValueError:
            return "full"

    def _reg(self, widget, key, option="text"):
        self._texts.append((widget, key, option))

    # ------------------------------------------------------------- transcribe
    def _build_transcribe(self, parent):
        self.sub_lbl = ttk.Label(parent, text="", style="Sub.TLabel", wraplength=1000)
        self.sub_lbl.pack(anchor="w", padx=16, pady=(12, 8))
        row = ttk.Frame(parent)
        row.pack(fill="x", padx=16)
        self.path_var = tk.StringVar()
        self.entry_wrap = tk.Frame(row, bg=BORDER, padx=1, pady=1)
        self.entry_wrap.pack(side="left", fill="x", expand=True)
        self.entry = tk.Entry(self.entry_wrap, textvariable=self.path_var, bg=ELEV, fg=FG,
                              insertbackground=FG, relief="flat", font=("Segoe UI", 10),
                              highlightthickness=0)
        self.entry.pack(fill="x", expand=True, ipady=7, padx=8)
        self.browse_btn = ttk.Button(row, text="", command=self.browse)
        self.browse_btn.pack(side="left", padx=6)
        self.drop_lbl = ttk.Label(parent, text="", style="Drop.TLabel")
        self.drop_lbl.pack(anchor="w", padx=18, pady=(6, 0))

        opts = ttk.Frame(parent)
        opts.pack(fill="x", padx=16, pady=(8, 0))
        self.sep_var = tk.BooleanVar(value=True)
        self.sep_chk = ttk.Checkbutton(opts, text="", variable=self.sep_var)
        self.sep_chk.pack(side="left")
        self.engine_lbl = ttk.Label(opts, text="", style="Sub.TLabel")
        self.engine_lbl.pack(side="left", padx=(16, 4))
        self.engine_var = tk.StringVar(value=self.engine_names()[0])
        self.engine_box = ttk.Combobox(opts, textvariable=self.engine_var, width=14,
                                       state="readonly", values=self.engine_names())
        self.engine_box.pack(side="left")
        self.status = ttk.Label(opts, text="", style="Sub.TLabel")
        self.status.pack(side="right")

        btns = ttk.Frame(parent)
        btns.pack(fill="x", padx=16, pady=8)
        self.run_btn = ttk.Button(btns, text="", command=self.start)
        self.run_btn.pack(side="left")
        self.pbar = ProgressBar(btns, maximum=9, width=240, height=8)
        self.pbar.pack(side="left", padx=(12, 6), pady=(4, 0))
        self.pbar_lbl = ttk.Label(btns, text="", style="Sub.TLabel", width=14)
        self.pbar_lbl.pack(side="left")
        self.open_btn = ttk.Button(btns, text="", command=self.open_out)
        self.open_btn.pack(side="left", padx=8)

        self.log = tk.Text(parent, bg="#0d0f13", fg="#c9d1d9", relief="flat", height=18,
                           font=("Consolas", 9), wrap="word", insertbackground=FG)
        self.log.pack(fill="both", expand=True, padx=16, pady=(0, 14))

        self._reg(self.sub_lbl, "app.subtitle")
        self._reg(self.browse_btn, "app.browse")
        self._reg(self.sep_chk, "app.separate")
        self._reg(self.engine_lbl, "app.engine")
        self._reg(self.run_btn, "app.run")
        self._reg(self.open_btn, "app.open_out")
        self._reg(self.drop_lbl, "app.drop_hint")

    # ---------------------------------------------------------------- results
    def _build_results(self, parent):
        # the transport row and the action row are packed first (from the bottom)
        # so a small window never squeezes the player out of view
        actions = ttk.Frame(parent)
        actions.pack(side="bottom", fill="x", padx=12, pady=(2, 10))
        body = ttk.Frame(parent)
        body.pack(side="bottom", fill="x", padx=12, pady=(0, 2))
        top = ttk.Frame(parent)
        top.pack(fill="both", expand=True, padx=12, pady=(10, 4))
        left = ttk.Frame(top)
        left.pack(side="left", fill="both", expand=False)
        self.files_lbl = ttk.Label(left, text="", style="Sub.TLabel")
        self.files_lbl.pack(anchor="w", pady=(0, 4))
        self.tree = ttk.Treeview(left, show="tree", height=12, selectmode="browse")
        self.tree.column("#0", width=330)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_results_select)
        self.tree.bind("<Double-1>", self.on_results_double)

        right = ttk.Frame(top)
        right.pack(side="left", fill="both", expand=True, padx=(12, 0))
        self.viewer = ScoreViewer(right, self)
        self.viewer.pack(fill="both", expand=True)

        self.play_status = ttk.Label(body, text="", style="Sub.TLabel")
        self.player = AudioPlayer(self, body, lambda msg: self.play_status.configure(text=msg))

        # the A/B source switch belongs next to the transport controls
        self.src_var = tk.StringVar(value="piano")
        self.src_piano = ttk.Radiobutton(self.player.row, text="", value="piano",
                                         variable=self.src_var, command=self.on_source,
                                         style="Src.TRadiobutton")
        self.src_piano.pack(side="left", padx=(0, 4), before=self.player.scale)
        self.src_orig = ttk.Radiobutton(self.player.row, text="", value="original",
                                        variable=self.src_var, command=self.on_source,
                                        style="Src.TRadiobutton")
        self.src_orig.pack(side="left", padx=(0, 10), before=self.player.scale)

        self.mark_btn = ttk.Button(actions, text="", command=self.mark_time,
                                   style="Compact.TButton")
        self.mark_btn.pack(side="left", padx=(0, 3))
        self.refresh_btn = ttk.Button(actions, text="", command=self.refresh_results,
                                      style="Compact.TButton")
        self.refresh_btn.pack(side="left", padx=3)
        self.delete_btn = ttk.Button(actions, text="", command=self.delete_song,
                                     style="Ghost.TButton")
        self.delete_btn.pack(side="left", padx=3)
        self.copy_btn = ttk.Button(actions, text="", command=self.copy_path,
                                   style="Compact.TButton")
        self.copy_btn.pack(side="left", padx=3)
        self.open_folder_btn = ttk.Button(actions, text="", command=self.open_out,
                                          style="Compact.TButton")
        self.open_folder_btn.pack(side="left", padx=3)
        self.system_btn = ttk.Button(actions, text="", command=self.play_system,
                                     style="Compact.TButton")
        self.system_btn.pack(side="left", padx=3)
        self.play_status.pack(side="right", padx=(8, 2))

        self._reg(self.player.vol_lbl, "res.volume")
        self._reg(self.files_lbl, "res.files")
        self._reg(self.src_piano, "res.src_piano")
        self._reg(self.src_orig, "res.src_original")
        self._reg(self.mark_btn, "res.mark")
        self._reg(self.refresh_btn, "res.refresh")
        self._reg(self.delete_btn, "res.delete")
        self._reg(self.copy_btn, "res.copy_path")
        self._reg(self.open_folder_btn, "res.open_folder")
        self._reg(self.system_btn, "res.system_player")
        self._reg(self.player.time_lbl, "res.time_hint", "text") if False else None

    # ----------------------------------------------------------- score library
    def _build_scores(self, parent):
        top = ttk.Frame(parent)
        top.pack(fill="both", expand=True, padx=12, pady=(10, 4))
        left = ttk.Frame(top)
        left.pack(side="left", fill="both", expand=False)
        self.lib_lbl = ttk.Label(left, text="", style="Sub.TLabel")
        self.lib_lbl.pack(anchor="w", pady=(0, 4))
        self.search_var = tk.StringVar()
        search_wrap = tk.Frame(left, bg=BORDER, padx=1, pady=1)
        search_wrap.pack(fill="x", pady=(0, 8))
        search = tk.Entry(search_wrap, textvariable=self.search_var, bg=ELEV, fg=MUTED,
                          insertbackground=FG, relief="flat", font=("Segoe UI", 9),
                          highlightthickness=0)
        search.pack(fill="x", ipady=5, padx=8)
        self._search_hint = tr("lib.search")
        search.insert(0, self._search_hint)

        def _in(_e):
            if search.get() == self._search_hint:
                search.delete(0, "end")
                search.configure(fg=FG)

        def _out(_e):
            if not search.get().strip():
                search.insert(0, self._search_hint)
                search.configure(fg=MUTED)

        search.bind("<FocusIn>", _in)
        search.bind("<FocusOut>", _out)
        search.bind("<KeyRelease>", lambda e: self.refresh_library())
        self.lib_tree = ttk.Treeview(left, show="tree", height=14)
        self.lib_tree.column("#0", width=300)
        self.lib_tree.pack(fill="both", expand=True)
        self.lib_tree.bind("<<TreeviewSelect>>", self.on_library_select)
        self.lib_tree.bind("<Double-1>", lambda e: self.player.play_from(0.0))

        right = ttk.Frame(top)
        right.pack(side="left", fill="both", expand=True, padx=(12, 0))
        self.lib_viewer = ScoreViewer(right, self)
        self.lib_viewer.pack(fill="both", expand=True)

        self._reg(self.lib_lbl, "lib.title")

    # -------------------------------------------------------------- language
    def on_language(self, _event=None):
        name = self.lang_box.get()
        code = next((c for c, n in LANGUAGES if n == name), "zh")
        self.apply_language(code)

    def apply_language(self, code: str, announce: bool = True):
        set_language(code)
        _t = tr("app.title")
        if getattr(self, "_low_il", False):
            _t += tr("app.title_limited")
        self.title(_t)
        for widget, key, option in self._texts:
            try:
                widget.configure(**{option: tr(key)})
            except Exception:
                pass
        for i, key in enumerate(self._tab_keys):
            self.nb.tab(i, text=tr(key))
        try:
            key = self.engine_key()
            names = self.engine_names()
            self.engine_box["values"] = names
            self.engine_var.set(names[["full", "neural", "piano", "classic"].index(key)])
        except Exception:
            pass
        self.lang_box.set(language_name(code))
        try:
            self.player._update_volume_label()
        except Exception:
            pass
        self.status.configure(text=tr(self._status_key))
        # tree rows are data, not widgets: rebuild them so their labels switch too
        try:
            self.refresh_results()
            self.refresh_library()
        except Exception:
            pass
        if announce:
            self.log.insert("end", "— " + language_name(code) + " —\n")
            self.log.see("end")

    def set_status(self, key: str):
        self._status_key = key
        self.status.configure(text=tr(key))

    # ------------------------------------------------------------- transcribe
    def _hover(self, on: bool):
        self.drop_lbl.configure(text=tr("app.drop_hover" if on else "app.drop_hint"))

    def _existing_song(self, audio_path: str) -> str | None:
        d = os.path.join(OUT_ROOT, song_key(audio_path))
        if os.path.isdir(d) and has_score(d):
            return d
        return None

    def on_drop(self, event):
        self._hover(False)
        paths = media_paths(getattr(event, "data", "") or "")
        if not paths or os.path.isdir(paths[0]):
            return
        if os.path.splitext(paths[0])[1].lower() not in AUDIO_EXT:
            messagebox.showwarning(tr("app.warn_title"), tr("app.drop_bad"))
            return
        self._offer_overwrite(paths[0])
        self.write(tr("app.drop_ok", name=os.path.basename(paths[0])))
        self.nb.select(0)

    def _offer_overwrite(self, audio_path: str) -> bool:
        existing = self._existing_song(audio_path)
        self._overwrite_ok = False
        if not existing:
            self.path_var.set(audio_path)
            return True
        name = os.path.basename(existing)
        if messagebox.askyesno(tr("res.overwrite_title"),
                               tr("res.overwrite_body", name=name)):
            self._overwrite_ok = True
            self.path_var.set(audio_path)
            return True
        return False

    def browse(self):
        p = filedialog.askopenfilename(
            title=tr("app.browse"),
            filetypes=[("Audio", "*.ogg *.mp3 *.wav *.flac *.m4a *.aiff *.aac *.opus"),
                       ("All files", "*.*")])
        if p:
            self._offer_overwrite(p)

    def write(self, msg: str):
        self.q.put(msg)

    def start(self):
        path = self.path_var.get().strip()
        if not path or not os.path.exists(path):
            messagebox.showwarning(tr("app.warn_title"), tr("app.warn_body"))
            return
        existing = self._existing_song(path)
        if existing and not self._overwrite_ok:
            if not messagebox.askyesno(tr("res.overwrite_title"),
                                       tr("res.overwrite_body",
                                          name=os.path.basename(existing))):
                return
            self._overwrite_ok = True
        if existing and self._overwrite_ok:
            # close our own handles on the old output before deleting it
            try:
                self.player.stop(silent=True)
                self.player.data = None
                self.player.path = None
            except Exception:
                pass
            for viewer in (self.viewer, getattr(self, "lib_viewer", None)):
                try:
                    if viewer is not None and (viewer.path or "").startswith(existing):
                        viewer.close()
                except Exception:
                    pass
            try:
                shutil.rmtree(existing)
                self.write(tr("res.removed", name=os.path.basename(existing)))
            except Exception as exc:
                self.write(str(exc))
        self.run_btn.configure(state="disabled")
        self.pbar["value"] = 0
        self.log.delete("1.0", "end")
        self.set_status("app.working")
        self.nb.select(0)

        def work():
            try:
                rep = pipeline.run(path, use_separation=self.sep_var.get(),
                                   engine=self.engine_key(),
                                   progress=lambda i, n: self.q.put(("progress", (i, n))),
                                   log=lambda m: self.write(m))
                self.out_dir = os.path.dirname(rep["outputs"]["score_piano"])
                self.last_run = {"out": self.out_dir, "original": path,
                                 "report": rep, "piano_wav": rep["outputs"]["piano_wav"]}
                m = rep["metrics"]
                self.write("\n" + "---- " + tr("app.done") + " ----")
                self.write(tr("app.summary_tempo", bpm=rep["tempo_bpm"], key=rep["key"]))
                self.write(tr("app.summary_metrics", exact=m["melody_pitch_exact_pct"],
                              within=m["melody_pitch_within_semitone_pct"]))
                self.write(tr("app.summary_chroma", chroma=m["chroma_similarity"]))
                self.write(tr("app.summary_out", dir=self.out_dir))
                self.q.put(("refresh", None))
                self.q.put(("reload_player", None))
                self.q.put(("__done__", "app.done"))
            except Exception as exc:  # pragma: no cover
                self.write(tr("app.error", msg=exc))
                self.q.put(("__done__", "app.failed"))

        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                if isinstance(item, tuple):
                    if item[0] == "progress":
                        try:
                            stage, total = item[1]
                            self.pbar["value"] = stage
                            self.pbar_lbl.configure(
                                text=tr("app.stage", cur=stage, total=total))
                        except Exception:
                            pass
                    elif item[0] == "refresh":
                        self.refresh_results()
                        self.refresh_library()
                    elif item[0] == "reload_player":
                        try:
                            self.src_var.set("piano")
                            self.player.load(self.last_run["piano_wav"])
                        except Exception:
                            pass
                    else:
                        self.run_btn.configure(state="normal")
                        self.set_status(item[1])
                        if item[1] == "app.done":
                            self.nb.select(1)
                else:
                    self.log.insert("end", item + "\n")
                    self.log.see("end")
        except queue.Empty:
            pass
        self.after(200, self.poll)

    # --------------------------------------------------------------- results
    def _song_dirs(self) -> list[str]:
        if not os.path.isdir(OUT_ROOT):
            return []
        dirs = []
        for d in os.listdir(OUT_ROOT):
            full = os.path.join(OUT_ROOT, d)
            if os.path.isdir(full) and has_score(full):
                dirs.append(full)
        return sorted(dirs, key=os.path.getmtime, reverse=True)

    def refresh_results(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        dirs = self._song_dirs()
        if not dirs:
            return
        current = (self.last_run or {}).get("out") or self.out_dir
        target_iid = None
        for d in dirs:
            iid = self.tree.insert("", "end", text=os.path.basename(d), open=(d == current),
                                                              values=(), iid=d)
            if d == current:
                target_iid = iid
            for key, label_id, _names in ARTIFACTS:
                p = find_artifact(d, key)
                if p:
                    self.tree.insert(iid, "end", text=tr(label_id), iid=p)
        if target_iid:
            pdf = find_artifact(target_iid, "piano")
            if pdf:
                self.tree.selection_set(pdf)
                # keep the reader's place when the same score is already shown
                if getattr(self.viewer, "path", None) != pdf:
                    self.viewer.show(pdf)

    def _activate_song(self, folder: str, show_score: bool = True):
        """Make a song the active one: preview its score and load its audio."""
        pdf = find_artifact(folder, "piano")
        if pdf and show_score:
            self.viewer.show(pdf)
        wav = find_artifact(folder, "audio") or os.path.join(folder, "piano.wav")
        original = None
        try:
            rep_path = os.path.join(folder, "_analysis", "report.json")
            if os.path.exists(rep_path):
                cand = json.load(open(rep_path, encoding="utf-8")).get("input")
                if cand and os.path.exists(cand):
                    original = cand
        except Exception:
            original = None
        self.out_dir = folder
        self.last_run = {"out": folder, "original": original, "piano_wav": wav,
                         "report": None}
        self.play_target = None
        pos = self.player.position()
        self.src_var.set("piano")
        if os.path.exists(wav) and self.player.load(wav):
            self.player.anchor = min(pos, max(0.0, self.player.duration - 0.1))
        else:
            # no audio for this song: drop the previous track so nothing else plays
            self.player.stop(silent=True)
            self.player.data = None
            self.player.path = None
            self.player.duration = 0.0
            try:
                self.player.info_lbl.configure(text="")
                self.player.set_time_label(0.0)
            except Exception:
                pass
        self.refresh_library()

    def _activate_for(self, path: str):
        """Make the song that owns *path* the active one (keeps audio in sync)."""
        folder = path if os.path.isdir(path) else os.path.dirname(path)
        if (self.last_run or {}).get("out") != folder:
            self._activate_song(folder, show_score=False)
        return folder

    def on_results_select(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        path = sel[0]
        if os.path.isdir(path):
            self._activate_song(path)
            return
        self._activate_for(path)
        if path.lower().endswith(".pdf"):
            self.viewer.show(path)
        elif os.path.splitext(path)[1].lower() in AUDIO_EXT:
            self.play_target = path
            pos = self.player.position()
            self.src_var.set("piano")
            if self.player.load(path):
                self.player.anchor = min(pos, max(0.0, self.player.duration - 0.1))

    def delete_song(self):
        sel = self.tree.selection()
        if not sel:
            return
        target = sel[0]
        if not os.path.isdir(target):
            target = os.path.dirname(target)
        if not target.startswith(OUT_ROOT):
            return
        if not messagebox.askyesno(tr("res.delete_title"), tr("res.delete_body",
                                                             name=os.path.basename(target))):
            return
        # release any open handle first, otherwise Windows refuses to delete
        try:
            self.player.stop(silent=True)
        except Exception:
            pass
        for viewer in (self.viewer, getattr(self, "lib_viewer", None)):
            try:
                if viewer is not None and (viewer.path or "").startswith(target):
                    viewer.close()
            except Exception:
                pass
        self.player.data = None
        self.player.path = None
        try:
            shutil.rmtree(target)
        except Exception as exc:
            messagebox.showwarning(tr("res.delete_title"), str(exc))
            return
        if (self.last_run or {}).get("out") == target:
            self.player.stop(silent=True)
            self.player.data = None
            self.player.path = None
            self.last_run = None
            self.out_dir = None
        self.refresh_results()
        self.refresh_library()

    # ---------------------------------------------------------- score library
    def refresh_library(self):
        q = self.search_var.get().strip().lower()
        if q and q == getattr(self, "_search_hint", "").lower():
            q = ""
        for row in self.lib_tree.get_children():
            self.lib_tree.delete(row)
        for d in self._song_dirs():
            name = os.path.basename(d)
            if q and q not in name.lower():
                continue
            parent = self.lib_tree.insert("", "end", text=name, open=True, iid="lib:" + d)
            for key, label_id, _names in ARTIFACTS:
                p = find_artifact(d, key)
                if p:
                    self.lib_tree.insert(parent, "end", text=tr(label_id), iid=p)

    def on_results_double(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        path = sel[0]
        if os.path.isdir(path):
            self._activate_song(path)
            if self.player.data is not None:
                self.player.play_from(0.0)
            return
        self.on_results_select()
        # only audio plays; a score should never start some other song
        if os.path.splitext(path)[1].lower() in AUDIO_EXT and self.player.data is not None:
            self.player.play_from(0.0)

    def on_library_select(self, _event=None):
        sel = self.lib_tree.selection()
        if not sel:
            return
        path = sel[0]
        if path.startswith("lib:"):
            folder = path[4:]
            pdf = find_artifact(folder, "piano")
            if pdf:
                self.lib_viewer.show(pdf)
            self._activate_song(folder)
        elif os.path.splitext(path)[1].lower() in AUDIO_EXT:
            # an audio leaf: make its song active so the player and viewer agree
            self._activate_song(os.path.dirname(path))
        elif path.lower().endswith(".pdf"):
            self.lib_viewer.show(path)

    # ---------------------------------------------------------------- audio
    def _play_wav(self, path: str, label: str):
        if not path or not os.path.exists(path):
            self.play_status.configure(text=tr("res.audio_missing", path=path))
            return
        if not path.lower().endswith(".wav"):
            from . import audio_io
            cache = os.path.join(ROOT, "cache", "playback")
            os.makedirs(cache, exist_ok=True)
            converted = os.path.join(cache, "playing.wav")
            try:
                y, sr = audio_io.load_audio(path, sr=44100, mono=False)
                audio_io.write_wav(converted, y, sr)
                path = converted
            except Exception as exc:
                self.play_status.configure(text=str(exc))
                return
        try:
            import winsound
            winsound.PlaySound(None, winsound.SND_PURGE)
            winsound.PlaySound(os.path.normpath(path),
                               winsound.SND_FILENAME | winsound.SND_ASYNC)
            self.play_status.configure(text=tr("res.playing", name=os.path.basename(path)))
        except Exception as exc:
            self.play_status.configure(text=str(exc))

    def stop_audio(self):
        try:
            import winsound
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass
        self.play_status.configure(text=tr("res.stopped"))

    def _audio_for_source(self, kind):
        if kind == "original":
            return (self.last_run or {}).get("original")
        return (self.last_run or {}).get("piano_wav") or self.play_target

    def on_source(self):
        kind = self.src_var.get()
        path = self._audio_for_source(kind)
        if not path or not os.path.exists(path):
            msg = tr("res.no_original") if kind == "original" else tr("res.no_audio")
            self.play_status.configure(text=msg)
            messagebox.showinfo(tr("res.play_piano"), msg)
            return
        pos = self.player.position()
        if self.player.path != path:
            if not self.player.load(path):
                return
            self.player.anchor = min(pos, max(0.0, self.player.duration - 0.1))
        self.player.play_from(self.player.anchor)

    def play_system(self):
        """Fallback: hand the current file to the system player."""
        path = self._audio_for_source(self.src_var.get())
        if not path or not os.path.exists(path):
            messagebox.showinfo(tr("res.play_piano"), tr("res.no_audio"))
            return
        try:
            os.startfile(os.path.normpath(path))
        except Exception as exc:
            messagebox.showwarning(tr("res.play_piano"), str(exc))

    def mark_time(self):
        text_ = fmt_time(self.player.position())
        try:
            self.clipboard_clear()
            self.clipboard_append(text_)
        except Exception:
            pass
        self.play_status.configure(text=tr("res.marked", t=text_))

    def play_piano(self):
        self.src_var.set("piano")
        self.on_source()

    def play_original(self):
        self.src_var.set("original")
        self.on_source()

    def stop_audio(self):
        if hasattr(self, "player"):
            self.player.stop()

    # -------------------------------------------------------------- folders
    def open_out(self):
        target = (self.last_run or {}).get("out") or self.out_dir or OUT_ROOT
        if not os.path.isdir(target):
            try:
                os.makedirs(target, exist_ok=True)
            except Exception as exc:
                messagebox.showwarning(tr("res.open_folder"), tr("res.open_failed", msg=exc))
                return
        path = os.path.normpath(target)
        ok, err = open_folder_shell(path)
        if ok:
            self.play_status.configure(text=tr("res.opened", path=path))
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(path)
        except Exception:
            pass
        messagebox.showinfo(tr("res.open_folder"), err)

    def copy_path(self):
        target = (self.last_run or {}).get("out") or self.out_dir or OUT_ROOT
        try:
            self.clipboard_clear()
            self.clipboard_append(target)
            self.play_status.configure(text=tr("res.copied"))
        except Exception:
            pass

    # ------------------------------------------------------------ error guard
    def _on_close(self):
        try:
            self.player._remember_volume(apply=False)
        except Exception:
            pass
        try:
            self.stop_audio()
        except Exception:
            pass
        self.destroy()

    def _on_tk_error(self, exc, val, tb):
        import traceback
        text = "".join(traceback.format_exception(exc, val, tb))
        try:
            os.makedirs(os.path.join(ROOT, "cache"), exist_ok=True)
            with open(os.path.join(ROOT, "cache", "gui_error.log"), "a", encoding="utf-8") as f:
                f.write(datetime.datetime.now().isoformat() + "\n" + text + "\n")
        except Exception:
            pass
        try:
            messagebox.showerror("PianoForge", text[-800:])
        except Exception:
            pass

    def _restore_last_run(self):
        dirs = self._song_dirs()
        if not dirs:
            return
        newest = dirs[0]
        original = None
        try:
            rep_path = os.path.join(newest, "_analysis", "report.json")
            if os.path.exists(rep_path):
                cand = json.load(open(rep_path, encoding="utf-8")).get("input")
                if cand and os.path.exists(cand):
                    original = cand
        except Exception:
            original = None
        self.out_dir = newest
        self.last_run = {"out": newest, "original": original,
                         "piano_wav": find_artifact(newest, "audio") or os.path.join(newest, "piano.wav"),
            "report": None}
        self.src_var.set("piano")
        self.player.load(self.last_run["piano_wav"])
        self.refresh_results()
        self.refresh_library()



def main():
    App().mainloop()


if __name__ == "__main__":
    main()