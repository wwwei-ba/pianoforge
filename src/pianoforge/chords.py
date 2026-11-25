"""Chord recognition (template + Viterbi) and voicing helpers."""
from __future__ import annotations

import numpy as np
import librosa

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# intervals (semitones from root) for each quality
CHORD_TEMPLATES = {
    "maj": [0, 4, 7],
    "min": [0, 3, 7],
    "7": [0, 4, 7, 10],
    "m7": [0, 3, 7, 10],
    "maj7": [0, 4, 7, 11],
    "dim": [0, 3, 6],
    "m7b5": [0, 3, 6, 10],
    "aug": [0, 4, 8],
    "sus4": [0, 5, 7],
    "sus2": [0, 2, 7],
    "6": [0, 4, 7, 9],
    "m6": [0, 3, 7, 9],
    "9": [0, 4, 7, 10, 14],
    "m9": [0, 3, 7, 10, 14],
    "add9": [0, 4, 7, 14],
}
QUALITY_ORDER = list(CHORD_TEMPLATES.keys())


def chord_label(root: int, quality: str) -> str:
    if root < 0 or quality == "N":
        return "N.C."
    return f"{NOTE_NAMES[root % 12]}{'' if quality == 'maj' else quality}"


def build_template_matrix() -> tuple[np.ndarray, list[tuple[int, str]]]:
    rows, labels = [], []
    for q in QUALITY_ORDER:
        for r in range(12):
            v = np.zeros(12, dtype=np.float32)
            for iv in CHORD_TEMPLATES[q]:
                v[(r + iv) % 12] = 1.0
            # bass emphasis
            v[r] = 1.4
            rows.append(v / np.linalg.norm(v))
            labels.append((r, q))
    rows.append(np.full(12, 1 / np.sqrt(12), dtype=np.float32))
    labels.append((-1, "N"))
    return np.vstack(rows), labels


TEMPLATES, TEMPLATE_LABELS = build_template_matrix()


def beat_chroma(chroma: np.ndarray, beat_frames: np.ndarray) -> np.ndarray:
    if len(beat_frames) < 2:
        return chroma
    return librosa.util.sync(chroma, beat_frames, aggregate=np.median)


def recognize_chords(chroma: np.ndarray, beat_frames: np.ndarray,
                     switch_penalty: float = 0.22, bass_chroma: np.ndarray | None = None,
                     bass_weight: float = 0.25) -> list[tuple[int, str]]:
    """Viterbi over beat-synchronous chroma. Returns (root, quality) per beat."""
    b = beat_chroma(chroma, beat_frames).T  # (beats, 12)
    b = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-6)
    sim = b @ TEMPLATES.T  # (beats, templates)

    if bass_chroma is not None:
        bb = beat_chroma(bass_chroma, beat_frames).T
        bb = bb / (np.linalg.norm(bb, axis=1, keepdims=True) + 1e-6)
        bass_sim = bb @ TEMPLATES.T
        sim = (1 - bass_weight) * sim + bass_weight * bass_sim

    n_states = sim.shape[1]
    dp = np.zeros((len(sim), n_states), dtype=np.float32)
    back = np.zeros((len(sim), n_states), dtype=np.int16)
    dp[0] = sim[0]
    for t in range(1, len(sim)):
        prev = dp[t - 1][None, :] - switch_penalty * (1.0 - np.eye(n_states, dtype=np.float32))
        back[t] = np.argmax(prev, axis=1)
        dp[t] = np.max(prev, axis=1) + sim[t]
    path = np.zeros(len(sim), dtype=np.int16)
    path[-1] = int(np.argmax(dp[-1]))
    for t in range(len(sim) - 1, 0, -1):
        path[t - 1] = back[t, path[t]]
    return [TEMPLATE_LABELS[i] for i in path]


def segments_from_chords(chords, beat_times: np.ndarray) -> list[dict]:
    segs = []
    cur = chords[0] if chords else (-1, "N")
    start = float(beat_times[0]) if len(beat_times) else 0.0
    for i in range(1, len(chords)):
        if chords[i] != cur:
            end = float(beat_times[min(i, len(beat_times) - 1)])
            segs.append({"root": cur[0], "quality": cur[1], "start": start, "end": end})
            cur, start = chords[i], end
    end = float(beat_times[-1]) if len(beat_times) else start + 1.0
    segs.append({"root": cur[0], "quality": cur[1], "start": start, "end": end})
    return segs


def chord_pitch_classes(root: int, quality: str) -> list[int]:
    if root < 0:
        return []
    return sorted({(root + iv) % 12 for iv in CHORD_TEMPLATES.get(quality, [0, 4, 7])})


def voice_chord(root: int, quality: str, low: int = 48, high: int = 64,
                prev: list[int] | None = None) -> list[int]:
    """Pick a compact voicing (MIDI notes) inside [low, high], biased to voice leading."""
    pcs = chord_pitch_classes(root, quality)
    if not pcs:
        return []
    candidates: list[list[int]] = []
    for base in range(low, high - 11):
        scale = [base + iv for iv in CHORD_TEMPLATES.get(quality, [0, 4, 7])]
        notes = sorted(set(n for n in scale if low <= n <= high))
        if not notes:
            continue
        if prev:
            # prefer the inversion whose top note is closest to the previous top
            cost = abs(notes[-1] - prev[-1]) + 0.15 * abs(np.mean(notes) - np.mean(prev))
        else:
            cost = abs(np.mean(notes) - (low + high) / 2) * 0.3
        cost += 0.25 * abs(notes[-1] - (high - 4))
        candidates.append((cost, notes))
    if not candidates:
        return []
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]
