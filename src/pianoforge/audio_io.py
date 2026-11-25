"""Audio decoding, resampling and writing that works on this host."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

import numpy as np

try:
    import soundfile as sf
except Exception:  # pragma: no cover
    sf = None

from scipy.signal import resample_poly

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _find_ffmpeg() -> str:
    env = os.environ.get("PIANOFORGE_FFMPEG")
    if env and os.path.exists(env):
        return env
    for cand in (os.path.join(ROOT, "bin", "ffmpeg.exe"), shutil.which("ffmpeg") or ""):
        if cand and os.path.exists(cand):
            return cand
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return ""


FFMPEG = _find_ffmpeg()


def _decode_ffmpeg(path: str, sr: int | None, mono: bool) -> tuple[np.ndarray, int]:
    if not os.path.exists(FFMPEG):
        raise RuntimeError(f"ffmpeg not found at {FFMPEG}")
    channels = "1" if mono else "2"
    tmp = tempfile.mktemp(suffix=".wav")
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", path,
           "-ac", channels, "-f", "wav"]
    if sr:
        cmd += ["-ar", str(sr)]
    cmd += [tmp]
    subprocess.run(cmd, check=True, timeout=600)
    with sf.SoundFile(tmp) as f:
        data = f.read(dtype="float32")
        fs = f.samplerate
    os.unlink(tmp)
    return data, fs


def load_audio(path: str, sr: int = 22050, mono: bool = True, offset: float = 0.0,
               duration: float | None = None) -> tuple[np.ndarray, int]:
    """Return (samples, sample_rate). Samples are float32; shape (n,) or (n, 2)."""
    data = None
    fs = sr
    try:
        with sf.SoundFile(path) as f:
            fs = f.samplerate
            if offset:
                f.seek(int(offset * fs))
            frames = -1 if duration is None else int(duration * fs)
            data = f.read(frames=frames, dtype="float32", always_2d=True)
    except Exception:
        data, fs = None, sr

    if data is None or data.size == 0:
        data, fs = _decode_ffmpeg(path, None, mono)
        if data.ndim == 1:
            data = data[:, None]

    if mono and data.shape[1] > 1:
        data = data.mean(axis=1, keepdims=True)
    if fs != sr:
        from math import gcd
        g = gcd(int(fs), int(sr))
        data = resample_poly(data, sr // g, int(fs) // g, axis=0)
        fs = sr
    data = np.ascontiguousarray(data.astype(np.float32))
    return (data[:, 0] if mono else data), fs


def write_wav(path: str, y: np.ndarray, sr: int) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    y = np.asarray(y, dtype=np.float32)
    if y.ndim == 1:
        y = y[:, None]
    sf.write(path, y, sr, subtype="PCM_16")
    return path


def encode_audio(wav_path: str, out_path: str, bitrate: str = "192k") -> str:
    """Convert wav to ogg/mp3 with ffmpeg when available, else keep wav."""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    if os.path.exists(FFMPEG):
        subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
                        "-i", wav_path, "-b:a", bitrate, out_path],
                       check=True, timeout=300)
        return out_path
    # fallback: soundfile can write ogg/vorbis and flac
    data, fs = sf.read(wav_path, always_2d=True)
    sf.write(out_path, data, fs)
    return out_path


def normalize_peak(y: np.ndarray, peak: float = 0.95) -> np.ndarray:
    m = float(np.max(np.abs(y))) if y.size else 0.0
    if m < 1e-9:
        return y
    return (y * (peak / m)).astype(np.float32)
