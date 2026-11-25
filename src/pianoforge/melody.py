"""Predominant-melody extraction.

Pipeline: harmonic-summed CQT salience -> register-prioritised Viterbi with a rest
state -> note segmentation on a semitone grid (onsets may split repeated notes).
"""
from __future__ import annotations

import numpy as np
import librosa
from scipy.ndimage import median_filter

# partial offsets in semitones and weights for a piano-like tone
HARMONIC_OFFSETS = [(0, 1.0), (12, 0.85), (19, 0.55), (24, 0.42), (28, 0.30), (31, 0.22)]
REST_PENALTY = 1.2


def midi_to_hz(m):
    return 440.0 * 2.0 ** ((np.asarray(m, dtype=float) - 69.0) / 12.0)


def hz_to_midi(f):
    return 69.0 + 12.0 * np.log2(np.maximum(np.asarray(f, dtype=float), 1e-6) / 440.0)


def salience_cqt(y: np.ndarray, sr: int, hop: int = 256, fmin_midi: int = 24,
                 n_bins: int = 96) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Harmonic-summed semitone salience plus a per-frame level (dB, max = 0)."""
    fmin = float(midi_to_hz(fmin_midi))
    cqt = np.abs(librosa.cqt(y, sr=sr, hop_length=hop, fmin=fmin,
                             n_bins=n_bins, bins_per_octave=12, filter_scale=1.0))
    db = librosa.amplitude_to_db(cqt + 1e-9, ref=np.max)
    level = db.max(axis=0)

    sal = np.zeros_like(db)
    for off, w in HARMONIC_OFFSETS:
        if off == 0:
            sal += w * db
        else:
            shifted = np.full_like(db, -80.0)
            shifted[:-off] = db[off:]
            sal += w * shifted
    floor = median_filter(sal, size=(25, 1), mode="nearest")
    sal = np.clip(sal - floor, 0, None)
    sal = sal / (sal.max(axis=0, keepdims=True) + 1e-6)
    times = librosa.frames_to_time(np.arange(sal.shape[1]), sr=sr, hop_length=hop)
    return sal.astype(np.float32), times, level.astype(np.float32)


def prior_curve(sal: np.ndarray, lo: int = 48, hi: int = 96,
                smooth_frames: int = 1290, clip_lo: float = 55.0,
                clip_hi: float = 92.0) -> np.ndarray:
    """Time-varying register prior: follows the top melodic voice over the piece."""
    peak = sal.max(axis=0, keepdims=True) + 1e-6
    strong = (sal > (0.55 * peak)) & (sal > 0.08)
    bins = np.arange(sal.shape[0])[:, None] * np.ones((1, sal.shape[1]), dtype=bool)
    top = np.where(strong, bins, -1).max(axis=0) + 24.0
    valid = (top >= lo) & (top <= hi)
    idx = np.arange(len(top))
    if not valid.any():
        return np.full(len(top), 76.0, dtype=np.float32)
    curve = np.interp(idx, idx[valid], top[valid])
    from scipy.ndimage import median_filter, uniform_filter1d
    curve = median_filter(curve, size=max(5, smooth_frames), mode="nearest")
    curve = uniform_filter1d(curve, size=max(5, smooth_frames // 2), mode="nearest")
    return np.clip(curve, clip_lo, clip_hi).astype(np.float32)


def viterbi_path(sal: np.ndarray, lo: int = 55, hi: int = 96,
                 step_penalty: float = 0.22, jump_penalty: float = 2.5,
                 octave_penalty: float = 1.2, prior_center: float = 76.0,
                 prior_sigma: float = 12.0, onset: np.ndarray | None = None,
                 onset_relax: float = 0.65, level: np.ndarray | None = None,
                 level_thresh: float = -45.0, rest_bias: float = 0.0,
                 prior_curve_values: np.ndarray | None = None):
    """Track a smooth pitch path, optionally with a rest state.

    Returns (midi path with -1 for rests, per-frame confidence).
    """
    n_bins, n_frames = sal.shape
    a, b = max(lo - 24, 0), min(hi - 24, n_bins - 1)
    sub = sal[a:b + 1]
    m = sub.shape[0]
    use_rest = level is not None
    if not use_rest:
        midi, conf = _viterbi_pitch_only(sub, a, n_frames, prior_center, prior_sigma,
                                         step_penalty, jump_penalty, octave_penalty,
                                         onset, onset_relax, prior_curve_values)
        return midi, conf
    n_states = m + 1  # last state = rest

    lw = np.log(sub + 1e-3)
    idx = (np.arange(m) + a + 24).astype(np.float32)[:, None]
    lw += -0.5 * ((idx - prior_center) / prior_sigma) ** 2

    if level is not None and len(level) >= n_frames:
        lv = np.clip((level_thresh - level[:n_frames]) / 12.0, 0, 1)
        rest_score = -3.5 + 6.0 * lv + rest_bias   # rising only when the frame is quiet
    else:
        rest_score = np.full(n_frames, -1.0)

    dp = np.full((n_states, n_frames), -1e9, dtype=np.float32)
    back = np.zeros((n_states, n_frames), dtype=np.int16)

    dst = np.abs(np.arange(m)[:, None] - np.arange(m)[None, :]).astype(np.float32)
    base_cost = (step_penalty * dst + jump_penalty * (dst >= 7)
                 + octave_penalty * (dst >= 12) + 0.35 * (dst > 4))

    on = np.ones(n_frames, dtype=np.float32)
    if onset is not None and len(onset) >= n_frames:
        o = np.clip(onset[:n_frames] / (np.percentile(onset, 90) + 1e-6), 0, 1)
        on = 1.0 - onset_relax * o

    dp[:m, 0] = lw[:, 0]
    dp[m, 0] = rest_score[0]
    for t in range(1, n_frames):
        cost = base_cost * on[t]
        prev_pitch = dp[:m, t - 1][:, None] - cost          # (m, m)
        best_prev = np.argmax(prev_pitch, axis=0)
        best_val = prev_pitch[best_prev, np.arange(m)]

        from_rest = dp[m, t - 1] - REST_PENALTY
        take_rest = best_val < from_rest
        best_val = np.where(take_rest, from_rest, best_val)
        best_prev = np.where(take_rest, m, best_prev)

        dp[:m, t] = best_val + lw[:, t]
        back[:m, t] = best_prev

        to_rest = dp[:m, t - 1].max() - REST_PENALTY
        stay_rest = dp[m, t - 1]
        if to_rest > stay_rest:
            dp[m, t] = to_rest + rest_score[t]
            back[m, t] = int(np.argmax(dp[:m, t - 1]))
        else:
            dp[m, t] = stay_rest + rest_score[t]
            back[m, t] = m

    path = np.zeros(n_frames, dtype=np.int16)
    path[-1] = int(np.argmax(dp[:, -1]))
    for t in range(n_frames - 1, 0, -1):
        path[t - 1] = back[path[t], t]
    midi = np.where(path == m, -1, path + a + 24).astype(np.float32)

    conf = np.zeros(n_frames, dtype=np.float32)
    voiced = path != m
    conf[voiced] = sub[path[voiced] - a, np.arange(n_frames)[voiced]]
    midi = despeckle(midi, min_rest=4, min_note=3)
    return midi, conf


def despeckle(midi: np.ndarray, min_rest: int = 4, min_note: int = 3) -> np.ndarray:
    """Remove one-frame rest flicker and very short pitch excursions."""
    out = midi.astype(np.float32).copy()
    n = len(out)
    i = 0
    last_pitch = -1
    while i < n:
        j = i
        while j + 1 < n and out[j + 1] == out[i]:
            j += 1
        run = j - i + 1
        if out[i] < 0 and 0 < i and j < n - 1 and run < min_rest:
            out[i:j + 1] = last_pitch if last_pitch >= 0 else out[i - 1]
        elif out[i] >= 0:
            last_pitch = out[i]
        i = j + 1
    return out


def _viterbi_pitch_only(sub, a, n_frames, prior_center, prior_sigma, step_penalty,
                        jump_penalty, octave_penalty, onset, onset_relax,
                        curve: np.ndarray | None = None):
    m = sub.shape[0]
    lw = np.log(sub + 1e-3)
    idx = (np.arange(m) + a + 24).astype(np.float32)[:, None]
    if curve is not None and len(curve) >= n_frames:
        center = curve[:n_frames][None, :]
        lw += -0.5 * ((idx - center) / prior_sigma) ** 2
    else:
        lw += -0.5 * ((idx - prior_center) / prior_sigma) ** 2

    dst = np.abs(np.arange(m)[:, None] - np.arange(m)[None, :]).astype(np.float32)
    base_cost = (step_penalty * dst + jump_penalty * (dst >= 7)
                 + octave_penalty * (dst >= 12) + 0.35 * (dst > 4))
    on = np.ones(n_frames, dtype=np.float32)
    if onset is not None and len(onset) >= n_frames:
        o = np.clip(onset[:n_frames] / (np.percentile(onset, 90) + 1e-6), 0, 1)
        on = 1.0 - onset_relax * o

    dp = np.full((m, n_frames), -1e9, dtype=np.float32)
    back = np.zeros((m, n_frames), dtype=np.int16)
    dp[:, 0] = lw[:, 0]
    for t in range(1, n_frames):
        cost = base_cost * on[t]
        prev = dp[:, t - 1][:, None] - cost
        best = np.argmax(prev, axis=0)
        dp[:, t] = prev[best, np.arange(m)] + lw[:, t]
        back[:, t] = best
    path = np.zeros(n_frames, dtype=np.int16)
    path[-1] = int(np.argmax(dp[:, -1]))
    for t in range(n_frames - 1, 0, -1):
        path[t - 1] = back[path[t], t]
    midi = (path + a + 24).astype(np.float32)
    conf = sub[path, np.arange(n_frames)]
    return midi, conf


def estimate_prior_center(sal: np.ndarray, lo: int = 48, hi: int = 96,
                          clip_lo: float = 60.0, clip_hi: float = 92.0) -> float:
    """Register prior from the top melodic voice rather than the loudest pitch.

    For every frame the highest pitch that is still reasonably salient is taken;
    the median of that contour approximates where the lead line sits.
    """
    peak = sal.max(axis=0, keepdims=True) + 1e-6
    strong = sal > (0.55 * peak)
    strong &= (sal > 0.08)
    n_bins = sal.shape[0]
    bins = np.arange(n_bins)[:, None] * np.ones((1, sal.shape[1]), dtype=bool)
    top = np.where(strong, bins, -1).max(axis=0) + 24
    top = top[(top >= lo) & (top <= hi)]
    if len(top) < 10:
        return 76.0
    return float(np.clip(np.median(top), clip_lo, clip_hi))


def onset_peaks(onset: np.ndarray, frac: float = 0.55) -> set[int]:
    if onset is None or len(onset) == 0:
        return set()
    thr = np.percentile(onset, 95) * frac
    out = set()
    for i in range(1, len(onset) - 1):
        if onset[i] >= thr and onset[i] >= onset[i - 1] and onset[i] >= onset[i + 1]:
            out.add(i)
    return out


def f0_to_notes(times: np.ndarray, midi: np.ndarray, conf: np.ndarray | None = None,
                min_dur: float = 0.07, merge_gap: float = 0.05,
                max_step: float = 0.75, conf_thresh: float = 0.10,
                onset: np.ndarray | None = None, split_at_onsets: bool = True,
                onset_frac: float = 0.55, split_rise: float = 0.0) -> list[dict]:
    """Segment a semitone path into notes. Rest frames (pitch < 0) end a note."""
    if len(midi) == 0:
        return []
    voiced = midi >= 0
    if conf is not None:
        voiced &= conf > conf_thresh
    peaks = onset_peaks(onset, onset_frac) if (split_at_onsets and onset is not None) else set()
    rise_ok = np.ones(len(midi), dtype=bool)
    if split_rise > 0 and conf is not None and len(conf) == len(midi):
        from scipy.ndimage import median_filter as _mf
        c = _mf(conf.astype(np.float32), size=3, mode="nearest")
        rise = np.zeros_like(c)
        rise[2:] = c[2:] - np.minimum(c[1:-1], c[:-2])
        rise_ok = rise > split_rise

    notes: list[dict] = []
    cur_start = None
    cur_pitch = None
    buf: list[float] = []
    cbuf: list[float] = []
    split_flag = False

    def flush(end_t):
        nonlocal cur_start, cur_pitch, buf, cbuf
        if cur_start is None or not buf:
            cur_pitch, cur_start, buf, cbuf = None, None, [], []
            return
        dur = end_t - cur_start
        if dur >= min_dur:
            notes.append({"pitch": int(round(float(np.median(buf)))),
                          "start": float(cur_start), "end": float(end_t),
                          "confidence": float(np.mean(cbuf)) if cbuf else 1.0,
                          "_split": split_flag})
        cur_pitch, cur_start, buf, cbuf = None, None, [], []

    prev_t = float(times[0])
    for i in range(len(midi)):
        t = float(times[i])
        if cur_start is not None and i in peaks and rise_ok[i] and (t - cur_start) >= min_dur:
            flush(t)
            split_flag = True
        if not voiced[i]:
            if cur_start is not None and t - prev_t > merge_gap:
                flush(prev_t)
        else:
            p = float(midi[i])
            c = float(conf[i]) if conf is not None else 1.0
            if cur_pitch is None:
                cur_start, cur_pitch, buf, cbuf = t, p, [p], [c]
            elif abs(p - cur_pitch) <= max_step:
                cur_pitch = 0.85 * cur_pitch + 0.15 * p
                buf.append(cur_pitch)
                cbuf.append(c)
            else:
                flush(t)
                cur_start, cur_pitch, buf, cbuf = t, p, [p], [c]
        prev_t = t
    if cur_start is not None:
        flush(float(times[-1]))

    merged: list[dict] = []
    for n in notes:
        if (merged and merged[-1]["pitch"] == n["pitch"]
                and n["start"] - merged[-1]["end"] <= merge_gap * 2
                and not n.get("_split")):
            merged[-1]["end"] = n["end"]
        else:
            merged.append(n)
    for n in merged:
        n.pop("_split", None)
    return merged


def filter_weak_notes(notes: list[dict], rel: float = 0.35) -> list[dict]:
    """Drop notes whose pitch salience is far below the piece's typical confidence."""
    if len(notes) < 4:
        return notes
    confs = np.array([n.get("confidence", 1.0) for n in notes])
    thr = max(0.05, float(np.percentile(confs, 60)) * rel)
    return [n for n in notes if n.get("confidence", 1.0) >= thr]


def extract_melody_cached(sal: np.ndarray, times: np.ndarray, onset: np.ndarray,
                          level: np.ndarray | None = None,
                          prior_center: float | None = 76.0, prior_sigma: float = 12.0,
                          step_penalty: float = 0.22, jump_penalty: float = 2.5,
                          onset_relax: float = 0.65, adaptive_prior: bool = True,
                          lo: int = 55, hi: int = 96, min_dur: float = 0.07,
                          split_at_onsets: bool = True,
                          level_thresh: float = -45.0,
                          onset_frac: float = 0.9, split_rise: float = 0.05,
                          use_rest: bool = False, local_prior: bool = False) -> dict:
    if adaptive_prior and prior_center is None:
        prior_center = estimate_prior_center(sal, lo, hi)
    if adaptive_prior and prior_center == 76.0:
        prior_center = estimate_prior_center(sal, lo, hi)
    if prior_center is None:
        prior_center = 76.0
    curve = None
    if local_prior:
        curve = prior_curve(sal, lo=max(48, lo - 7), hi=hi)
    midi, conf = viterbi_path(sal, lo=lo, hi=hi, prior_center=prior_center,
                              prior_sigma=prior_sigma, step_penalty=step_penalty,
                              jump_penalty=jump_penalty, onset=onset,
                              onset_relax=onset_relax,
                              level=level if use_rest else None,
                              level_thresh=level_thresh,
                              prior_curve_values=curve)
    notes = f0_to_notes(times, midi, conf, min_dur=min_dur, onset=onset,
                        split_at_onsets=split_at_onsets, onset_frac=onset_frac,
                        split_rise=split_rise)
    notes = filter_weak_notes(notes)
    return {"times": times, "midi": midi.astype(np.float32), "conf": conf,
            "salience": sal, "notes": notes, "prior_center": prior_center}


def extract_melody(y: np.ndarray, sr: int, hop: int = 256, lo: int = 55, hi: int = 96,
                   min_dur: float = 0.07, **params) -> dict:
    sal, times, level = salience_cqt(y, sr, hop=hop)
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    return extract_melody_cached(sal, times, onset, level=level, lo=lo, hi=hi,
                                 min_dur=min_dur, **params)

def from_poly_onsets(y: np.ndarray, sr: int, poly_notes: list[dict],
                     hop: int = 256, lo: int = 60, hi: int = 92,
                     min_dur: float = 0.10) -> list[dict]:
    """Melody whose *timing* comes from the transcription and whose *pitch* is
    chosen by CQT salience inside the transcribed candidates for that segment."""
    import librosa

    onsets = sorted({round(n["start"], 3) for n in poly_notes if n["pitch"] >= lo})
    if not onsets:
        return []
    C = np.abs(librosa.cqt(y.astype(np.float32), sr=sr, hop_length=hop,
                           fmin=float(librosa.midi_to_hz(lo)),
                           n_bins=(hi - lo + 1), bins_per_octave=12, filter_scale=1.4))
    times = librosa.frames_to_time(np.arange(C.shape[1]), sr=sr, hop_length=hop)
    end_time = times[-1] if len(times) else 0.0
    out = []
    for i, t0 in enumerate(onsets):
        t1 = onsets[i + 1] if i + 1 < len(onsets) else min(end_time, t0 + 1.0)
        if t1 - t0 < min_dur:
            t1 = t0 + min_dur
        idx = np.where((times >= t0) & (times < t1))[0]
        if len(idx) == 0:
            continue
        energy = C[:, idx].mean(axis=1)
        # candidates: pitches transcribed in this segment (+/- 1 semitone)
        cands = [n["pitch"] for n in poly_notes
                 if t0 - 0.06 <= n["start"] < t1 and lo <= n["pitch"] <= hi]
        allowed = set()
        for p_ in cands:
            for d in (-1, 0, 1):
                q = p_ + d
                if lo <= q <= hi:
                    allowed.add(q)
        if allowed:
            best = max(allowed, key=lambda q: energy[q - lo])
        else:
            best = lo + int(np.argmax(energy))
        if out and best == out[-1]["pitch"] and t0 - out[-1]["end"] < 0.02:
            out[-1]["end"] = t1
            continue
        out.append({"start": float(t0), "end": float(t1), "pitch": int(best),
                    "strength": float(energy[best - lo])})
    return out

def snap_octaves(melody: list[dict], poly: list[dict], win: float = 0.09) -> list[dict]:
    """Fix octave jumps: if the transcription has the same pitch class an octave
    away and nothing at the tracked octave, move the melody note to it."""
    if not melody or not poly:
        return melody
    out = []
    for m in melody:
        near = [n for n in poly if abs(n["start"] - m["start"]) <= win]
        if not near:
            out.append(m)
            continue
        if any(abs(n["pitch"] - m["pitch"]) <= 1 for n in near):
            out.append(m)
            continue
        octs = [n for n in near if abs(abs(n["pitch"] - m["pitch"]) - 12) <= 1]
        if octs:
            best = max(octs, key=lambda n: n.get("strength", 0))
            x = dict(m)
            x["pitch"] = int(best["pitch"])
            out.append(x)
        else:
            out.append(m)
    return out

def top_voice_from_notes(poly: list[dict], min_dur: float = 0.07,
                         lo: int = 55, frame: float = 0.02) -> list[dict]:
    """Melody as the highest sounding line, measured frame by frame.

    For solo piano the melody really is the top voice; a note counts as melody
    when it stays on top for at least min_dur seconds.
    """
    if not poly:
        return []
    notes = sorted([n for n in poly if n["pitch"] >= lo], key=lambda n: n["start"])
    if not notes:
        return []
    t_start = notes[0]["start"]
    t_end = max(n["end"] for n in notes)
    n_frames = int(np.ceil((t_end - t_start) / frame)) + 1
    top_count = {}
    for i in range(n_frames):
        t = t_start + i * frame
        best = None
        for n in notes:
            if n["start"] <= t < n["end"]:
                if best is None or n["pitch"] > best["pitch"]:
                    best = n
        if best is not None:
            k = (round(best["start"], 3), best["pitch"])
            top_count[k] = top_count.get(k, 0) + 1
    out = []
    for (st, pitch), cnt in sorted(top_count.items()):
        if cnt * frame < min_dur:
            continue
        n = next((x for x in notes if round(x["start"], 3) == st and x["pitch"] == pitch), None)
        if n is None:
            continue
        if out and out[-1]["pitch"] == pitch and st - out[-1]["end"] < 0.05:
            out[-1]["end"] = max(out[-1]["end"], n["end"])
            continue
        out.append({"start": float(st), "end": float(n["end"]), "pitch": int(pitch),
                    "strength": float(n.get("strength", 0.2))})
    return out
def from_poly_viterbi(poly: list[dict], lo: int = 55, hi: int = 96,
                     leap_penalty: float = 0.10, height_bonus: float = 0.35,
                     strength_w: float = 1.0, gap_penalty: float = 0.25) -> list[dict]:
    """Pick the most plausible melodic line out of a polyphonic transcription.

    Every transcribed note is a state; the path is scored by how strong and how
    high the note is, minus the size of the leap and any silence before it.
    This keeps the melody on one continuous line instead of jumping to whatever
    happens to be loudest in each frame.
    """
    notes = [n for n in poly if lo <= n["pitch"] <= hi and n["end"] > n["start"]]
    if not notes:
        return []
    notes.sort(key=lambda n: (n["start"], n["pitch"]))
    n = len(notes)
    best = [0.0] * n
    prev = [-1] * n
    span = max(1, hi - lo)
    for i, ni in enumerate(notes):
        score = strength_w * float(ni.get("strength", 0.2)) + height_bonus * (ni["pitch"] - lo) / span
        best[i] = score
        for j in range(i - 1, -1, -1):
            nj = notes[j]
            if nj["start"] > ni["start"]:
                continue
            gap = ni["start"] - nj["end"]
            if gap > 1.2:
                break
            leap = abs(ni["pitch"] - nj["pitch"])
            # prefer stepwise motion; allow leaps but charge for them
            cost = best[j] + score - leap_penalty * min(leap, 12) - gap_penalty * max(0.0, gap)
            if cost > best[i]:
                best[i] = cost
                prev[i] = j
    end = max(range(n), key=lambda i: best[i])
    path = []
    while end >= 0:
        path.append(notes[end])
        end = prev[end]
    path.reverse()
    out = []
    for x in path:
        if out and abs(x["start"] - out[-1]["start"]) < 0.05:
            continue
        out.append({"start": float(x["start"]), "end": float(x["end"]),
                    "pitch": int(x["pitch"]), "strength": float(x.get("strength", 0.2))})
    return out
def smooth_octaves(notes: list[dict], max_jump: int = 13,
                   return_tol: int = 2) -> list[dict]:
    """Remove one-note octave blips in a melody line.

    The tracker occasionally jumps an octave for a single note (a strong
    harmonic wins) and comes straight back; a pianist would never phrase it
    that way, so shift such notes back into the surrounding register.
    """
    out = [dict(n) for n in notes]
    for i in range(1, len(out) - 1):
        prev, cur, nxt = out[i - 1], out[i], out[i + 1]
        jump = cur["pitch"] - prev["pitch"]
        if max_jump - 2 <= abs(jump) <= max_jump and abs(nxt["pitch"] - prev["pitch"]) <= return_tol:
            cur["pitch"] = int(prev["pitch"]) + (jump % 12 if jump > 0 else -((-jump) % 12))
    return out

def remove_outliers(notes: list[dict], soft: int = 7, hard: int = 14,
                    short: float = 0.35) -> list[dict]:
    """Drop melody notes that pop far outside the song's register for a moment.

    Cymbal and synth overtones show up as an isolated top note (e.g. a single
    high D# that appears and vanishes); a singer never phrases that way, and in
    the score it reads as a sudden wrong pitch.
    """
    if len(notes) < 12:
        return notes
    times = np.array([n["start"] for n in notes], dtype=float)
    pitches = np.array([n["pitch"] for n in notes], dtype=float)
    out = []
    for i, n in enumerate(notes):
        win = np.abs(times - n["start"]) <= 2.0
        local = float(np.median(pitches[win])) if win.any() else float(np.median(pitches))
        p = n["pitch"]
        dur = n["end"] - n["start"]
        if dur <= short and (p > local + soft + 2 or p < local - soft - 2):
            continue
        out.append(n)
    return out if len(out) >= max(8, len(notes) // 2) else notes
