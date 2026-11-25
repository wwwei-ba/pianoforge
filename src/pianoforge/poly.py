"""Polyphonic transcription by greedy harmonic matching pursuit.

Instead of factorising the whole spectrum (which smears energy over every
plausible pitch), each frame is explained note by note: pick the pitch whose
harmonic template explains the most energy, subtract it, repeat. That keeps the
octave/fifth phantom problem under control and yields a playable note list.
"""
from __future__ import annotations

import numpy as np
import librosa
from scipy.ndimage import median_filter, uniform_filter1d

# partial offsets (semitones) and weights
PARTIALS = [(0, 1.00), (12, 0.50), (19, 0.30), (24, 0.18), (28, 0.12), (31, 0.08)]


def cqt_mag(y: np.ndarray, sr: int, hop: int = 256, n_bins: int = 84,
            fmin_midi: int = 24, background: float = 0.0,
            background_frames: int = 63) -> np.ndarray:
    fmin = float(librosa.midi_to_hz(fmin_midi))
    C = np.abs(librosa.cqt(y, sr=sr, hop_length=hop, fmin=fmin, n_bins=n_bins,
                           bins_per_octave=12, filter_scale=1.4))
    if background > 0:
        # optional: subtract a slow background estimate (helps percussive material,
        # hurts sustained pads, so it is off by default)
        C = np.maximum(C - median_filter(C, size=(1, background_frames),
                                         mode="nearest") * background, 0)
    return C.astype(np.float32)


def templates(n_bins: int = 84) -> np.ndarray:
    """(n_bins x n_bins) unit-norm harmonic templates, one per pitch."""
    T = np.zeros((n_bins, n_bins), dtype=np.float32)
    for p in range(n_bins):
        for off, w in PARTIALS:
            b = p + off
            if b < n_bins:
                T[b, p] += w
        if p + 1 < n_bins:
            T[p + 1, p] += 0.10
        if p - 1 >= 0:
            T[p - 1, p] += 0.10
    T /= (np.linalg.norm(T, axis=0, keepdims=True) + 1e-9)
    return T


def activations(y: np.ndarray, sr: int, hop: int = 256, n_bins: int = 84,
                fmin_midi: int = 24, max_poly: int = 6, min_share: float = 0.055,
                compress: float = 0.65, background: float = 0.0,
                background_frames: int = 63) -> tuple[np.ndarray, np.ndarray]:
    """Greedy per-frame decomposition. Returns (activations pitches x frames, times)."""
    C = cqt_mag(y, sr, hop=hop, n_bins=n_bins, fmin_midi=fmin_midi,
                background=background, background_frames=background_frames)
    C = C ** compress
    T = templates(n_bins)
    n_frames = C.shape[1]
    A = np.zeros((n_bins, n_frames), dtype=np.float32)

    frame_energy = C.sum(axis=0) + 1e-9
    for t in range(n_frames):
        R = C[:, t].copy()
        e0 = frame_energy[t]
        for _ in range(max_poly):
            if R.sum() < min_share * e0:
                break
            scores = T.T @ R                      # correlation with every pitch
            p = int(np.argmax(scores))
            gain = float(scores[p])
            if gain <= 0:
                break
            A[p, t] = gain
            R = np.maximum(R - gain * T[:, p], 0)
        A[:, t] /= (A[:, t].max() + 1e-9)
    times = librosa.frames_to_time(np.arange(n_frames), sr=sr, hop_length=hop)
    return A, times


def track_notes(A: np.ndarray, times: np.ndarray, fmin_midi: int = 24,
                on_thresh: float = 0.35, off_thresh: float = 0.18,
                min_dur: float = 0.07, max_poly: int = 6) -> list[dict]:
    n_bins, n_frames = A.shape
    hop_s = float(times[1] - times[0]) if n_frames > 1 else 0.01
    min_frames = max(2, int(round(min_dur / hop_s)))

    order = np.argsort(-A, axis=0)
    keep = np.zeros_like(A, dtype=bool)
    for k in range(min(max_poly, n_bins)):
        keep[order[k], np.arange(n_frames)] = True
    A = A * keep

    notes: list[dict] = []
    for p in range(n_bins):
        env = uniform_filter1d(A[p], size=3, mode="nearest")
        if env.max() < on_thresh:
            continue
        active = False
        start = 0
        weak = 0
        for i, v in enumerate(env):
            if not active and v >= on_thresh:
                active, start, weak = True, i, 0
            elif active:
                if v < off_thresh:
                    weak += 1
                    if weak >= 3:
                        end = i - weak + 1
                        if end - start >= min_frames:
                            notes.append({"pitch": int(p + fmin_midi),
                                          "start": float(times[start]),
                                          "end": float(times[min(end, n_frames - 1)]),
                                          "strength": float(env[start:end].mean())})
                        active = False
                else:
                    weak = 0
        if active:
            end = n_frames - 1
            if end - start >= min_frames:
                notes.append({"pitch": int(p + fmin_midi),
                              "start": float(times[start]),
                              "end": float(times[end]),
                              "strength": float(env[start:end].mean())})
    notes.sort(key=lambda n: (n["start"], n["pitch"]))
    return notes


def cleanup_notes(notes: list[dict], merge_gap: float = 0.04,
                  octave_ratio: float = 0.55) -> list[dict]:
    """Merge stutter fragments and drop octave phantoms of a stronger note."""
    if not notes:
        return []
    notes = sorted(notes, key=lambda n: (n["pitch"], n["start"]))
    merged: list[dict] = []
    for n in notes:
        if merged and merged[-1]["pitch"] == n["pitch"] and n["start"] - merged[-1]["end"] <= merge_gap:
            merged[-1]["end"] = max(merged[-1]["end"], n["end"])
            merged[-1]["strength"] = max(merged[-1]["strength"], n["strength"])
        else:
            merged.append(dict(n))

    by_pitch: dict[int, list[dict]] = {}
    for n in merged:
        by_pitch.setdefault(n["pitch"], []).append(n)
    keep: list[dict] = []
    for n in merged:
        phantom = False
        for delta in (-12, 12):
            for other in by_pitch.get(n["pitch"] + delta, []):
                overlap = min(n["end"], other["end"]) - max(n["start"], other["start"])
                if overlap > 0.6 * (n["end"] - n["start"]):
                    if delta == -12 and other["strength"] >= octave_ratio * n["strength"]:
                        phantom = True          # a lower note explains this one
                    elif delta == 12 and other["strength"] >= 1.6 * n["strength"]:
                        phantom = True          # this one is just the partial of the octave above
        if not phantom:
            keep.append(n)
    keep.sort(key=lambda n: (n["start"], n["pitch"]))
    return keep


# tuned on a 26-song synthetic corpus (note F1 0.72 on piano+drums mixes)
DEFAULTS = dict(max_poly=4, min_share=0.09, compress=0.65, background=0.5,
                on_thresh=0.45, off_thresh=0.18, min_dur=0.13)


def transcribe(y: np.ndarray, sr: int, hop: int = 256, **kw) -> list[dict]:
    params = dict(DEFAULTS)
    params.update({k: v for k, v in kw.items() if k in params})
    act_kw = {k: params[k] for k in ("max_poly", "min_share", "compress",
                                     "background")}
    act_kw.update({k: v for k, v in kw.items()
                   if k in ("n_bins", "fmin_midi", "background_frames")})
    track_kw = {"max_poly": params["max_poly"], "on_thresh": params["on_thresh"],
                "off_thresh": params["off_thresh"], "min_dur": params["min_dur"]}
    track_kw.update({k: v for k, v in kw.items() if k in ("fmin_midi",)})
    A, times = activations(y, sr, hop=hop, **act_kw)
    notes = track_notes(A, times, **track_kw)
    return cleanup_notes(notes, octave_ratio=float(kw.get("octave_ratio", 0.55)))
