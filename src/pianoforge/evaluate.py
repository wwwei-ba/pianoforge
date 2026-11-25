"""Objective comparison between the original track and the rendered piano track.

Both files share the same timeline (the score is written onto the detected beat
grid), so frames are compared directly after estimating one small global offset.
"""
from __future__ import annotations

import numpy as np
import librosa

from . import analysis, melody

FPS = 10.0


def _melody_track(y, sr):
    harm, _ = analysis.hpss(y, sr)
    res = melody.extract_melody(harm, sr, hop=256)
    return res["times"], res["midi"], res["conf"]


def _resample_1d(times, values, grid):
    if len(times) < 2:
        return np.zeros(len(grid), dtype=np.float32)
    return np.interp(grid, times, values).astype(np.float32)


def compare(y_orig, sr, y_piano, sr_p, melody_ref_notes=None, melody_score_notes=None,
            y_ref_melody=None, max_shift: float = 1.5) -> dict:
    n = min(len(y_orig), len(y_piano))
    y_orig, y_piano = y_orig[:n].astype(np.float32), y_piano[:n].astype(np.float32)
    ref_signal = (y_ref_melody[:n] if y_ref_melody is not None else y_orig)

    # ---- melody tracks -------------------------------------------------------
    ta, ma, _ = _melody_track(ref_signal, sr)
    tb, mb, _ = _melody_track(y_piano, sr_p)

    grid = np.arange(0, min(ta[-1], tb[-1]) if len(ta) and len(tb) else 0, 1.0 / FPS)
    ga = _resample_1d(ta, ma, grid)
    gb = _resample_1d(tb, mb, grid)

    # ---- best global offset (render shifted relative to the reference) ------
    def agreement(shift_frames: int):
        a = ga
        b = np.roll(gb, shift_frames)
        v = (a > 0) & (b > 0)
        if v.sum() < 30:
            return -1.0, 0
        d = np.abs(a[v] - b[v])
        pc = np.minimum(d % 12, 12 - (d % 12))
        return float(np.mean(pc < 0.5)), int(v.sum())

    candidates = range(-int(max_shift * FPS), int(max_shift * FPS) + 1)
    scored = [(agreement(s)[0], s) for s in candidates]
    best_score, best_shift = max(scored, key=lambda x: (x[0], -abs(x[1])))

    a = ga
    b = np.roll(gb, best_shift)
    v = (a > 0) & (b > 0)
    if v.sum() > 30:
        d = np.abs(a[v] - b[v])
        pc = np.minimum(d % 12, 12 - (d % 12))
        exact = float(np.mean(pc < 0.5))
        within1 = float(np.mean(pc <= 1.0))
        octave_err = float(np.mean((d >= 11) & (d <= 13)))
        mean_abs = float(np.mean(d))
        cc = float(np.corrcoef(a[v], b[v])[0, 1]) if v.sum() > 50 else 0.0
    else:
        exact = within1 = octave_err = 0.0
        mean_abs = 99.0
        cc = 0.0

    # ---- chroma similarity on the aligned timeline --------------------------
    hop = 512
    c1 = librosa.feature.chroma_cqt(y=ref_signal, sr=sr, hop_length=hop)
    c2 = librosa.feature.chroma_cqt(y=y_piano, sr=sr_p, hop_length=hop)
    t1 = librosa.frames_to_time(np.arange(c1.shape[1]), sr=sr, hop_length=hop)
    t2 = librosa.frames_to_time(np.arange(c2.shape[1]), sr=sr_p, hop_length=hop)
    cg = np.arange(0, min(t1[-1], t2[-1]) if len(t1) and len(t2) else 0, 1.0 / FPS)
    c1r = np.stack([np.interp(cg, t1, c1[i]) for i in range(12)])
    c2r = np.stack([np.interp(cg, t2, c2[i]) for i in range(12)])
    c2s = np.roll(c2r, best_shift, axis=1)
    cos = (c1r * c2s).sum(axis=0) / (
        np.linalg.norm(c1r, axis=0) * np.linalg.norm(c2s, axis=0) + 1e-9)
    chroma_sim = float(np.nanmean(cos))

    # ---- note level: written score vs the re-detected reference melody ------
    note_prec = note_rec = None
    if melody_ref_notes and melody_score_notes:
        shift_s = best_shift / FPS
        matched = 0
        used = set()
        for r in melody_ref_notes:
            for j, s in enumerate(melody_score_notes):
                if j in used:
                    continue
                if abs(r["start"] - (s["start"] + shift_s)) < 0.2 and r["pitch"] == s["pitch"]:
                    used.add(j)
                    matched += 1
                    break
        note_prec = matched / max(1, len(melody_score_notes))
        note_rec = matched / max(1, len(melody_ref_notes))

    return {
        "chroma_similarity": round(chroma_sim, 4),
        "melody_pitch_exact_pct": round(100 * exact, 2),
        "melody_pitch_within_semitone_pct": round(100 * within1, 2),
        "melody_octave_error_pct": round(100 * octave_err, 2),
        "melody_mean_abs_semitone_error": round(mean_abs, 2),
        "melody_contour_corr": round(cc, 4),
        "best_time_shift_sec": round(best_shift / FPS, 2),
        "score_note_precision_pct": None if note_prec is None else round(100 * note_prec, 2),
        "score_note_recall_pct": None if note_rec is None else round(100 * note_rec, 2),
        "voiced_frames_compared": int(v.sum()),
    }
