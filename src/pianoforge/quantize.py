"""Grid quantization: map free-time notes onto a musical metrical grid."""
from __future__ import annotations

import numpy as np


def make_grid(beat_times: np.ndarray, subdivisions: int = 4, start: float = 0.0,
              end: float | None = None) -> np.ndarray:
    """Grid points at chosen subdivisions between detected beats (beat times are seconds)."""
    bt = np.asarray(beat_times, dtype=float)
    if len(bt) < 2:
        step = 0.5 / subdivisions
        if end is None:
            end = start + 4.0
        return np.arange(start, end + step, step)
    # extend the beat grid to cover the whole piece with constant tempo
    intervals = np.diff(bt)
    med = float(np.median(intervals)) if len(intervals) else 0.5
    grid = []
    for i in range(len(bt) - 1):
        for k in range(subdivisions):
            grid.append(bt[i] + (bt[i + 1] - bt[i]) * k / subdivisions)
    grid.append(bt[-1])
    if end is not None and grid[-1] < end:
        step = med / subdivisions
        while grid[-1] < end:
            grid.append(grid[-1] + step)
    return np.array(grid, dtype=float)


def snap(values: np.ndarray, grid: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if len(grid) == 0:
        return values
    idx = np.searchsorted(grid, values)
    idx = np.clip(idx, 1, len(grid) - 1)
    left = grid[idx - 1]
    right = grid[idx]
    return np.where(np.abs(values - left) <= np.abs(values - right), left, right)


def quantize_notes(notes: list[dict], grid: np.ndarray, tempo: float,
                   min_len: float = 0.06) -> list[dict]:
    """Snap notes to the grid and enforce a monophonic, non-overlapping line."""
    if not notes or len(grid) < 2:
        return []
    step = float(np.min(np.diff(grid)))
    starts = snap(np.array([n["start"] for n in notes]), grid)
    ends = snap(np.array([n["end"] for n in notes]), grid)
    out = []
    for n, s, e in zip(notes, starts, ends):
        if e <= s:
            e = s + step
        if e - s < min_len:
            continue
        out.append({**n, "start": float(s), "end": float(e)})
    out.sort(key=lambda n: (n["start"], -n.get("confidence", 1.0), n["pitch"]))

    # one start per event: keep the most confident, longest note
    dedup = []
    for n in out:
        if dedup and abs(dedup[-1]["start"] - n["start"]) < 1e-9:
            if (n.get("confidence", 0), n["end"] - n["start"]) > (
                    dedup[-1].get("confidence", 0), dedup[-1]["end"] - dedup[-1]["start"]):
                dedup[-1] = n
        else:
            dedup.append(n)

    # truncate overlaps so the line stays monophonic
    for i in range(len(dedup) - 1):
        dedup[i]["end"] = min(dedup[i]["end"], dedup[i + 1]["start"])
    result = [n for n in dedup if n["end"] - n["start"] >= min_len - 1e-9]
    for n in result:
        n["start"] = round(n["start"], 4)
        n["end"] = round(n["end"], 4)
    return result


def beats_per_bar(tempo: float, beat_times: np.ndarray) -> int:
    return 4