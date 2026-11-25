"""Sample-based piano rendering using the FluidR3_GM piano set (MIDI.js layout).

Samples live in bin/samples/piano_mp3 as <note>.mp3. They are decoded once with
ffmpeg and cached as .npy, then pitch-shifted to the requested notes.
"""
from __future__ import annotations

import os
import subprocess

import numpy as np

from . import audio_io

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SAMPLE_DIR = os.path.join(ROOT, "bin", "samples", "piano_mp3")
CACHE_DIR = os.path.join(ROOT, "cache", "piano_npy")

NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
_CACHE: dict[int, np.ndarray] = {}
_RATE: int | None = None
_TUNING: dict[int, float] | None = None


def load_tuning() -> dict[int, float]:
    """Per-sample pitch deviation in cents, measured by tools/calibrate_samples.py."""
    global _TUNING
    if _TUNING is not None:
        return _TUNING
    import json
    path = os.path.join(ROOT, "cache", "piano_tuning.json")
    try:
        raw = json.load(open(path, encoding="utf-8"))
        _TUNING = {int(k): float(v) for k, v in raw.items()}
    except Exception:
        _TUNING = {}
    return _TUNING


def name_to_midi(name: str) -> int:
    import re
    m = re.match(r"([A-G][b#]?)(-?\d+)", name)
    if not m:
        raise ValueError(name)
    base = NAMES.index(m.group(1).replace("#", "b")) if m.group(1) in NAMES else 0
    return 12 * (int(m.group(2)) + 1) + base


def _decode(mp3: str) -> tuple[np.ndarray, int]:
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = os.path.join(CACHE_DIR, os.path.basename(mp3).replace(".mp3", ".npy"))
    meta = cache + ".rate"
    if os.path.exists(cache) and os.path.exists(meta):
        return np.load(cache), int(open(meta).read())
    y, sr = audio_io.load_audio(mp3, sr=0, mono=True) if False else (None, None)
    tmp = mp3 + ".tmp.wav"
    subprocess.run([audio_io.FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
                    "-i", mp3, "-ac", "1", "-ar", "44100", tmp], check=True)
    data, fs = audio_io.load_audio(tmp, sr=44100)
    os.unlink(tmp)
    data = data.astype(np.float32)
    np.save(cache, data)
    with open(meta, "w") as f:
        f.write(str(fs))
    return data, fs


def available() -> dict[int, str]:
    out = {}
    if not os.path.isdir(SAMPLE_DIR):
        return out
    for f in os.listdir(SAMPLE_DIR):
        if f.endswith(".mp3"):
            try:
                out[name_to_midi(f[:-4])] = os.path.join(SAMPLE_DIR, f)
            except ValueError:
                continue
    return out


def load_bank() -> dict[int, np.ndarray]:
    global _CACHE, _RATE
    if _CACHE:
        return _CACHE
    files = available()
    for midi, path in files.items():
        try:
            data, sr = _decode(path)
            _CACHE[midi] = data
            _RATE = sr
        except Exception:
            continue
    return _CACHE


def render_note(pitch: int, dur: float, velocity: float = 0.8, sr: int = 44100) -> np.ndarray:
    bank = load_bank()
    if not bank:
        return np.zeros(0, dtype=np.float32)
    keys = sorted(bank)
    # nearest sample, preferring one at or below the target pitch
    below = [k for k in keys if k <= pitch]
    src = max(below) if below else min(keys)
    shift = pitch - src
    if abs(shift) > 7:
        src = min(keys, key=lambda k: abs(k - pitch))
        shift = pitch - src
    sample = bank[src]
    rate = _RATE or 44100
    cents = load_tuning().get(src, 0.0)
    # resample from the sample's own rate *and* pitch-shift; forgetting the rate
    # factor transposes everything by the sample-rate ratio (a whole octave at 22 kHz)
    ratio = (rate / float(sr)) * 2.0 ** ((shift - cents / 100.0) / 12.0)
    n_out = int(len(sample) / ratio)
    idx = np.arange(n_out) * ratio
    idx = np.clip(idx, 0, len(sample) - 1.001)
    i0 = idx.astype(np.int32)
    frac = idx - i0
    out = sample[i0] * (1 - frac) + sample[i0 + 1] * frac
    out = out.astype(np.float32)
    # gentle attack shaping
    attack = int(0.003 * sr)
    if attack < len(out):
        out[:attack] *= np.linspace(0, 1, attack, dtype=np.float32) ** 0.7
    # release after the key is lifted; with the sustain pedal down the string keeps
    # ringing instead of being cut short
    pedal = os.environ.get("PF_PEDAL", "1") != "0"
    end = int(dur * sr)
    if end < len(out):
        if pedal:
            rel = int(0.45 * sr)
            tail_start = end + rel
            if tail_start < len(out):
                tail = np.exp(-np.arange(len(out) - tail_start) / (0.35 * sr)).astype(np.float32)
                out[tail_start:] *= tail
                out = out[: tail_start + int(0.9 * sr)]
        else:
            rel = int(0.25 * sr)
            tail = np.exp(-np.arange(len(out) - end) / (0.08 * sr)).astype(np.float32)
            out[end:] *= tail
            out = out[: end + rel * 3] if end + rel * 3 < len(out) else out
    return out * (0.35 + 0.65 * velocity)


def render_notes(notes: list[dict], total_sec: float, sr: int = 44100,
                 gain: float = 0.7) -> np.ndarray:
    n = int(np.ceil(total_sec * sr)) + sr
    out = np.zeros(n, dtype=np.float32)
    for note in notes:
        sig = render_note(int(note["pitch"]), max(0.05, float(note["end"] - note["start"])),
                          float(note.get("velocity", 0.8)), sr=sr)
        if sig.size == 0:
            continue
        start = int(note["start"] * sr)
        if start < 0:
            sig = sig[-start:]
            start = 0
        if start >= n:
            continue
        end = min(n, start + len(sig))
        if end <= start:
            continue
        out[start:end] += sig[: end - start]
    return out * gain
