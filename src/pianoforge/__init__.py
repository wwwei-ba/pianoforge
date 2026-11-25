"""pianoforge: audio -> piano score, fingerstyle tab and rendered piano track."""
import os as _os

__version__ = "0.1.0"

# Keep every cache and temporary file inside the project. Without this the app
# depends on the user profile being writable, and demucs silently falls back to
# whole-track analysis (or matplotlib fails to start) when it is not.
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_CACHE = _os.path.join(_ROOT, "cache")
_TMP = _os.path.join(_ROOT, "tmp")
for _d in (_CACHE, _TMP, _os.path.join(_CACHE, "torch"), _os.path.join(_CACHE, "mpl")):
    try:
        _os.makedirs(_d, exist_ok=True)
    except Exception:
        pass

_os.environ.setdefault("TORCH_HOME", _os.path.join(_CACHE, "torch"))
_os.environ.setdefault("XDG_CACHE_HOME", _CACHE)
_os.environ.setdefault("MPLCONFIGDIR", _os.path.join(_CACHE, "mpl"))
_os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
_os.environ.setdefault("TMP", _TMP)
_os.environ.setdefault("TEMP", _TMP)
_os.environ.setdefault("PYTHONIOENCODING", "utf-8")
