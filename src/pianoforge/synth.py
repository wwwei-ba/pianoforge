"""A dependency-free piano synthesiser (additive, inharmonic, two-stage decay).

Used to render the transcribed notes to audio. It is not a sampled piano, but it
keeps exact pitch and a recognisable piano timbre, and it works offline.
"""
from __future__ import annotations

import numpy as np

SR = 44100


def _voice(f0: float, dur: float, sr: int, velocity: float = 0.8,
           detune_cents: float = 0.0) -> np.ndarray:
    """Synthesise one piano note of the given frequency and duration (seconds)."""
    n = int(sr * (dur + 0.6))
    t = np.arange(n, dtype=np.float32) / sr
    f0 = f0 * 2 ** (detune_cents / 1200.0)
    B = 0.0004 * (f0 / 261.63) ** 0.5
    out = np.zeros(n, dtype=np.float32)
    max_partial = int(min(16, max(1, (sr / 2.2) / max(f0, 1.0))))
    for k in range(1, max_partial + 1):
        fk = k * f0 * np.sqrt(1 + B * k * k)
        if fk >= sr / 2.2:
            break
        amp = (1.0 / (k ** 1.25)) * np.exp(-0.08 * (k - 1))
        tau = (2.2 / (1 + 0.55 * (k - 1))) * (0.6 + 0.4 * velocity)
        env = np.exp(-t / tau)
        # short attack to avoid clicks
        attack = int(0.004 * sr)
        if attack > 0:
            env[:attack] *= np.linspace(0, 1, attack, dtype=np.float32)
        out += (amp * env * np.sin(2 * np.pi * fk * t + 0.3 * k)).astype(np.float32)

    # hammer transient
    nz = np.random.default_rng(1234).normal(0, 1, n).astype(np.float32)
    attack_len = int(0.012 * sr)
    if attack_len > 0:
        ham = np.exp(-np.arange(attack_len) / (0.0035 * sr)).astype(np.float32)
        out[:attack_len] += 0.05 * velocity * nz[:attack_len] * ham

    # damper: cut the tail shortly after the key is released
    rel_start = int(dur * sr)
    if rel_start < n:
        rel = np.exp(-(np.arange(n - rel_start) / (0.12 * sr))).astype(np.float32)
        out[rel_start:] *= rel
    return out * (0.22 * velocity)


def render_notes(notes: list[dict], total_sec: float, sr: int = SR,
                 gain: float = 1.0) -> np.ndarray:
    """notes: dicts with start, end, pitch (midi), velocity (0-1)."""
    n = int(np.ceil(total_sec * sr)) + sr
    out = np.zeros(n, dtype=np.float32)
    for note in notes:
        f0 = 440.0 * 2 ** ((note["pitch"] - 69) / 12.0)
        dur = max(0.05, float(note["end"] - note["start"]))
        vel = float(note.get("velocity", 0.8))
        sig = _voice(f0, dur, sr, velocity=vel)
        start = int(note["start"] * sr)
        if start < 0:
            sig = sig[-start:]
            start = 0
        if start >= n or sig.size == 0:
            continue
        end = min(n, start + len(sig))
        if end <= start:
            continue
        out[start:end] += sig[: end - start]
    return out * gain


def add_reverb(x: np.ndarray, sr: int = SR, wet: float = 0.18, decay: float = 0.35) -> np.ndarray:
    """Small Schroeder-ish reverb so the piano does not sound dry."""
    if x.size == 0:
        return x
    rng = np.random.default_rng(7)
    ir_len = int(sr * 1.2)
    ir = rng.normal(0, 1, ir_len).astype(np.float32) * np.exp(-np.arange(ir_len) / (decay * sr))
    ir[0] = 1.0
    ir /= np.abs(ir).sum() ** 0.5
    from scipy.signal import fftconvolve
    wet_sig = fftconvolve(x, ir, mode="full")[: len(x)]
    return ((1 - wet) * x + wet * wet_sig).astype(np.float32)


def normalize(x: np.ndarray, peak: float = 0.92) -> np.ndarray:
    m = float(np.max(np.abs(x))) if x.size else 0.0
    return x if m < 1e-9 else (x * (peak / m)).astype(np.float32)
