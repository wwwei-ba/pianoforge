"""Turn analysed material (melody + chords + bass) into piano and guitar arrangements."""
from __future__ import annotations

import numpy as np

from . import chords as chordlib
from .musicxml import DIVISIONS, Event, Part

STANDARD_TUNING = [40, 45, 50, 55, 59, 64]  # E2 A2 D3 G3 B3 E4, index 0 = string 6


class TimeMap:
    def __init__(self, bpm: float, t0: float = 0.0):
        self.bpm = float(bpm)
        self.t0 = float(t0)

    def tick(self, t: float) -> int:
        return int(round((t - self.t0) * self.bpm / 60.0 * DIVISIONS))

    def sec(self, tick: int) -> float:
        return self.t0 + tick * 60.0 / self.bpm / DIVISIONS


def chord_at(chord_segments: list[dict], t: float) -> dict | None:
    for seg in chord_segments:
        if seg["start"] <= t < seg["end"]:
            return seg
    return chord_segments[-1] if chord_segments else None


def nearest_chord(chord_segments, t):
    best = None
    for seg in chord_segments:
        d = 0 if seg["start"] <= t < seg["end"] else min(abs(t - seg["start"]), abs(t - seg["end"]))
        if best is None or d < best[0]:
            best = (d, seg)
    return best[1] if best else None


def _bass_note(root: int, lo: int = 36, hi: int = 50) -> int:
    if root < 0:
        return 43
    n = root
    while n < lo:
        n += 12
    while n > hi:
        n -= 12
    return n


def _chord_tones(root: int, quality: str) -> list[int]:
    return chordlib.chord_pitch_classes(root, quality)


def harmonise_note(pitch: int, root: int, quality: str, prev_top: int | None) -> list[int]:
    """Pick 1-2 chord tones just below a melody note, close and voice-led."""
    if root < 0:
        return []
    tones = _chord_tones(root, quality)
    if not tones:
        return []
    candidates = []
    for pc in tones:
        for octv in (3, 4, 5):
            n = 12 * (octv + 1) + pc
            if pitch - 10 <= n <= pitch - 2:
                candidates.append(n)
    if not candidates:
        return []
    candidates = sorted(set(candidates))
    if prev_top is not None:
        candidates.sort(key=lambda n: abs(n - prev_top))
    picked = candidates[:1]
    for n in candidates[1:]:
        if 2 <= abs(n - picked[-1]) <= 5:
            picked.append(n)
            break
    return sorted(picked)


def build_piano(melody: list[dict], chord_segments: list[dict], bass_notes: list[dict],
                tm: TimeMap, bpm: float, total_sec: float, style: str = "pop",
                harmonize: bool = False, broken_bass: bool = True) -> Part:
    """Grand-staff piano, one voice per staff.

    Right hand: melody with optional chord tones stacked underneath.
    Left hand: broken-chord accompaniment built from the recognised harmony.
    """
    part = Part(part_id="P1", name="Piano", staves=2, clefs=[("G", 2), ("F", 4)])
    events: list[Event] = []
    beat = 60.0 / bpm

    prev_top = None
    for n in melody:
        s = max(tm.tick(n["start"]), 0)
        e = max(tm.tick(n["end"]), s + DIVISIONS // 2)
        pitches = [int(n["pitch"])]
        dur_sec = n["end"] - n["start"]
        if harmonize and dur_sec >= 0.28:
            seg = chord_at(chord_segments, n["start"])
            if seg is not None:
                tones = harmonise_note(int(n["pitch"]), seg["root"], seg["quality"], prev_top)
                if tones:
                    prev_top = tones[-1]
                    pitches = tones + pitches
        events.append(Event(start=s, dur=e - s, pitches=pitches, staff=1, voice=1))

    n_beats = max(1, int(np.ceil((total_sec - tm.t0) / beat)))
    for k in range(n_beats):
        tick = k * DIVISIONS
        t = tm.t0 + k * beat
        seg = chord_at(chord_segments, t)
        root = seg["root"] if seg else -1
        qual = seg["quality"] if seg else "maj"
        if root < 0:
            continue
        bass = _bass_note(root)
        pos = k % 4
        if broken_bass:
            intervals = chordlib.CHORD_TEMPLATES.get(qual, [0, 4, 7])
            colour = intervals[3] if len(intervals) >= 4 else 12      # 7th if the chord has one
            third = intervals[1] % 12
            pattern = [bass, bass + 7, bass + colour, _bass_note(root + third, 48, 62)]
            pitch = pattern[pos]
            events.append(Event(start=tick, dur=DIVISIONS, pitches=[pitch],
                                staff=2, voice=1))
        else:
            if pos == 0:
                events.append(Event(start=tick, dur=2 * DIVISIONS, pitches=[bass],
                                    staff=2, voice=1))
            elif pos == 2:
                voicing = chordlib.voice_chord(root, qual, low=52, high=67, prev=prev_voicing)
                if voicing:
                    prev_voicing = voicing
                    events.append(Event(start=tick, dur=DIVISIONS, pitches=voicing,
                                        staff=2, voice=1))

    part.events = _dedupe([e for e in events if e.dur > 0])
    return part


def _dedupe(events: list[Event]) -> list[Event]:
    """Drop repeated identical notes and trim overlaps inside a voice."""
    events.sort(key=lambda e: (e.staff, e.voice, e.start, e.pitches[0]))
    out: list[Event] = []
    for ev in events:
        if out and out[-1].staff == ev.staff and out[-1].voice == ev.voice:
            last = out[-1]
            if last.start == ev.start and tuple(last.pitches) == tuple(ev.pitches):
                continue
            if ev.start < last.end:
                last.dur = max(1, ev.start - last.start)
        out.append(ev)
    return out


def assign_fingering(pitches: list[int], prev_center: float = 5.0,
                     max_fret: int = 14) -> list[tuple[int, int]] | None:
    """Map sorted pitches to (string, fret) pairs on a standard-tuned guitar.

    Returns a list aligned with the input pitches (ascending order), or None.
    """
    order = sorted(range(len(pitches)), key=lambda i: pitches[i])
    sorted_pitches = [pitches[i] for i in order]
    result = [None] * len(pitches)
    prev_string = 0
    frets: list[float] = []
    for idx, p in enumerate(sorted_pitches):
        best = None
        for si in range(prev_string, 6):
            fret = p - STANDARD_TUNING[si]
            if 0 <= fret <= max_fret:
                cost = abs(fret - prev_center) + 0.35 * (si - prev_string)
                if fret == 0:
                    cost -= 0.6
                if best is None or cost < best[0]:
                    best = (cost, si, fret)
        if best is None:
            return None
        _, si, fret = best
        result[order[idx]] = (6 - si, fret)
        prev_string = si + 1
        frets.append(fret)
    fretted = [f for f in frets if f > 0]
    if len(fretted) >= 2 and max(fretted) - min(fretted) > 4:
        return None
    return result


def _melody_position(pitch: int, max_fret: int = 7) -> tuple[int, int, int] | None:
    """Best (string, fret, sounding pitch) for a melody note on the top strings.

    The written octave is kept when it is playable; transposition is a last resort.
    """
    for pitch_oct in (0, 12, -12):
        p = pitch + pitch_oct
        best = None
        for si in (5, 4, 3):  # high E, B, G
            fret = p - STANDARD_TUNING[si]
            if 0 <= fret <= max_fret:
                cost = abs(fret - 3) + 0.5 * si
                if best is None or cost < best[0]:
                    best = (cost, 6 - si, fret, p)
        if best is not None:
            return best[1], best[2], best[3]
    return None


def _bass_position(pitch: int, lo_fret: int, hi_fret: int) -> tuple[int, int, int] | None:
    """Bass note on strings 6-4 inside the hand position (open strings allowed)."""
    for pitch_oct in (0, -12, 12):
        p = pitch + pitch_oct
        best = None
        for si in (2, 1, 0):  # D, A, low E
            fret = p - STANDARD_TUNING[si]
            if 0 <= fret <= 12:
                inside = lo_fret <= fret <= hi_fret or fret == 0
                cost = (0 if inside else 3.0) + abs(fret - max(lo_fret, 1)) * 0.3 + 0.3 * (5 - si)
                if best is None or cost < best[0]:
                    best = (cost, 6 - si, fret, p)
        if best is not None and best[0] < 3.0:
            return best[1], best[2], best[3]
        if best is not None and pitch_oct == 0:
            fallback = best
    try:
        return fallback[1], fallback[2], fallback[3]
    except Exception:
        return None


def build_guitar(melody: list[dict], chord_segments: list[dict], tm: TimeMap, bpm: float,
                 total_sec: float, max_fret: int = 7) -> Part:
    """Fingerstyle tab: melody on the top strings, alternating bass, inner chord tones.

    All notes of a beat share a hand position so the shapes stay playable.
    """
    part = Part(part_id="P2", name="Fingerstyle Guitar", staves=1, clefs=[("TAB", 5)], tab=True)
    events: list[Event] = []
    beat = 60.0 / bpm
    beat_sec = beat

    # melody notes indexed by beat
    mel_by_beat: dict[int, list[dict]] = {}
    for n in melody:
        b = int(round((n["start"] - tm.t0) / beat_sec))
        mel_by_beat.setdefault(max(0, b), []).append(n)

    n_beats = max(1, int(np.ceil((total_sec - tm.t0) / beat_sec)))
    for k in range(n_beats):
        tick = k * DIVISIONS
        t = tm.t0 + k * beat_sec
        seg = chord_at(chord_segments, t)
        root = seg["root"] if seg else -1
        qual = seg["quality"] if seg else "maj"
        pos = k % 4

        mel_notes = sorted(mel_by_beat.get(k, []), key=lambda n: n["start"])
        placed_mel = []
        positions = []
        for n in mel_notes:
            got = _melody_position(int(n["pitch"]), max_fret=max_fret)
            if got:
                placed_mel.append((n, got))
                positions.append(got[1])

        if positions:
            lo = min(positions)
            hi = max(positions)
            if hi - lo > 3:
                hi = lo + 3
                placed_mel = [pm for pm in placed_mel if lo <= pm[1][1] <= hi]
        else:
            lo, hi = 1, 4

        grid16 = DIVISIONS // 4
        seen_ticks = set()
        for n, (string, fret, pitch) in placed_mel:
            s = max(int(round(tm.tick(n["start"]) / grid16)) * grid16, tick)
            if s in seen_ticks:
                continue
            seen_ticks.add(s)
            e = int(round(tm.tick(n["end"]) / grid16)) * grid16
            e = max(e, s + grid16)
            events.append(Event(start=s, dur=e - s, pitches=[pitch], staff=1, voice=1,
                                string_frets=[(string, fret)]))

        if root >= 0:
            if pos in (0, 2):
                bass = _bass_note(root, 40, 52)
                got = _bass_position(bass, lo, hi)
                if got:
                    string, fret, pitch = got
                    events.append(Event(start=tick, dur=DIVISIONS, pitches=[pitch],
                                        staff=1, voice=2, string_frets=[(string, fret)]))
            else:
                voicing = chordlib.voice_chord(root, qual, low=55, high=71, prev=None)
                if voicing:
                    sel = []
                    for p in sorted(voicing)[:2]:
                        cand = None
                        for si in (4, 3, 2):
                            fret = p - STANDARD_TUNING[si]
                            if lo <= fret <= hi or fret == 0:
                                cand = (6 - si, fret, p)
                                break
                        if cand:
                            sel.append(cand)
                    if sel:
                        events.append(Event(start=tick, dur=DIVISIONS // 2,
                                            pitches=[c[2] for c in sel], staff=1, voice=2,
                                            string_frets=[(c[0], c[1]) for c in sel]))

    part.events = _enforce_monophonic([e for e in events if e.dur > 0])
    part.events.sort(key=lambda e: (e.start, e.pitches[0]))
    return part


def _snap_ticks(t: float, tm: TimeMap, step_ticks: int) -> int:
    return int(round(tm.tick(t) / step_ticks)) * step_ticks


def _assign_voices(notes: list[dict], n_voices: int, min_len_ticks: int,
                   step_ticks: int) -> list[tuple[int, dict]]:
    """Greedy interval scheduling: each voice stays monophonic in time."""
    out: list[tuple[int, dict]] = []
    last_end = [-(10 ** 9)] * n_voices
    for n in sorted(notes, key=lambda x: (x["start_t"], -x["pitch"])):
        s, e = n["start_t"], n["end_t"]
        if e - s < min_len_ticks:
            e = s + min_len_ticks
        for v in range(n_voices):
            if s >= last_end[v]:
                last_end[v] = e
                out.append((v, dict(n, start_t=s, end_t=e)))
                break
        else:
            v = int(np.argmin(last_end))
            if s < last_end[v]:
                s = last_end[v]
            if e - s < min_len_ticks:
                e = s + min_len_ticks
            last_end[v] = e
            out.append((v, dict(n, start_t=s, end_t=e)))
    return out


def build_piano_poly(melody: list[dict], poly_notes: list[dict], tm: TimeMap,
                     bpm: float, total_sec: float, step_ticks: int = DIVISIONS // 4,
                     max_upper_voices: int = 2, max_bass_voices: int = 2,
                     min_strength: float = 0.30) -> Part:
    """Piano part built from real transcribed notes, not from a chord pattern.

    Right hand: the melody on top, transcribed upper notes filling the harmony.
    Left hand: the transcribed bass, plus low chord tones when they exist.
    """
    part = Part(part_id="P1", name="Piano", staves=2, clefs=[("G", 2), ("F", 4)])
    min_len = step_ticks

    # ---- melody ----------------------------------------------------------
    mel_events = []
    for n in melody:
        s = max(_snap_ticks(n["start"], tm, step_ticks), 0)
        e = max(_snap_ticks(n["end"], tm, step_ticks), s + min_len)
        mel_events.append({"pitch": int(n["pitch"]), "start_t": s, "end_t": e, "role": "melody"})
    mel_events = _assign_voices(mel_events, 1, min_len, step_ticks)

    # ---- transcribed notes ----------------------------------------------
    upper, lower = [], []
    strengths = [float(n.get("strength", 0.5)) for n in poly_notes] or [1.0]
    floor = min_strength * float(np.median(strengths))
    for n in poly_notes:
        if float(n.get("strength", 0.5)) < floor:
            continue
        s = max(_snap_ticks(n["start"], tm, step_ticks), 0)
        e = max(_snap_ticks(n["end"], tm, step_ticks), s + min_len)
        if s / DIVISIONS > total_sec / (60.0 / bpm):
            continue
        item = {"pitch": int(n["pitch"]), "start_t": s, "end_t": e,
                "strength": float(n.get("strength", 0.5))}
        (upper if item["pitch"] >= 59 else lower).append(item)

    # drop transcribed notes that merely double the melody at the same moment
    melody_spans = [(e["start_t"], e["end_t"], e["pitch"]) for _, e in mel_events]
    filtered = []
    for n in upper:
        dup = any(abs(n["pitch"] - mp) <= 0 and n["start_t"] < me and n["end_t"] > ms
                  for ms, me, mp in melody_spans)
        if not dup:
            filtered.append(n)
    upper = filtered

    events: list[Event] = []
    for v, e in mel_events:
        events.append(Event(start=e["start_t"], dur=e["end_t"] - e["start_t"],
                            pitches=[e["pitch"]], staff=1, voice=1))

    for v, e in _assign_voices(upper, max_upper_voices, min_len, step_ticks):
        events.append(Event(start=e["start_t"], dur=e["end_t"] - e["start_t"],
                            pitches=[e["pitch"]], staff=1, voice=2 + v))

    for v, e in _assign_voices(lower, max_bass_voices, min_len, step_ticks):
        events.append(Event(start=e["start_t"], dur=e["end_t"] - e["start_t"],
                            pitches=[e["pitch"]], staff=2, voice=1 + v))

    part.events = _enforce_register(_dedupe_global(_remove_melody_clashes(
        _enforce_monophonic([ev for ev in events if ev.dur > 0])), tm), tm)
    part.events.sort(key=lambda e: (e.staff, e.voice, e.start))
    return part


def build_piano_reduced(melody: list[dict], poly_notes: list[dict],
                        chord_segments: list[dict], tm: TimeMap, bpm: float,
                        total_sec: float, step_ticks: int = DIVISIONS // 2,
                        max_harmony: int = 3, melody_lo: int = 48,
                        melody_hi: int = 88, bass_notes: list[dict] | None = None) -> Part:
    """Readable piano reduction of the transcription.

    Melody on top; the harmony is taken from the notes *below* the melody (never
    a copy of it), and the left hand carries the lowest sounding line.
    """
    part = Part(part_id="P1", name="Piano", staves=2, clefs=[("G", 2), ("F", 4)])
    beat = 60.0 / bpm
    step_sec = beat * step_ticks / DIVISIONS
    n_steps = max(1, int(np.ceil((total_sec - tm.t0) / step_sec)))

    events: list[Event] = []
    for n in melody:
        s = max(tm.tick(n["start"]), 0)
        e = max(tm.tick(n["end"]), s + DIVISIONS // 4)
        events.append(Event(start=s, dur=e - s, pitches=[int(n["pitch"])], staff=1, voice=1))

    poly = sorted(poly_notes, key=lambda n: n["start"])
    strengths = [float(n.get("strength", 0.5)) for n in poly] or [1.0]
    floor = 0.25 * float(np.median(strengths))
    poly = [n for n in poly if float(n.get("strength", 0.5)) >= floor]

    prev_voicing: list[int] = []
    harmony_runs: list[tuple[int, int, list[int]]] = []
    bass_runs: list[tuple[int, int, int]] = []
    # register reference for bars where the melody is silent: without it the
    # harmony would grab the highest notes and flatten the whole texture
    _mel_pitches = [int(n["pitch"]) for n in melody]
    fallback_top = int(np.median(_mel_pitches)) if _mel_pitches else None

    for k in range(n_steps):
        t = tm.t0 + k * step_sec
        t_end = t + step_sec
        active = [n for n in poly if n["start"] < t_end - 1e-6 and n["end"] > t + 1e-6]
        seg = chord_at(chord_segments, t)
        root = seg["root"] if seg else -1
        qual = seg["quality"] if seg else "maj"
        pcs = set(chordlib.chord_pitch_classes(root, qual)) if root >= 0 else set()

        # melody register at this step (top voice) - harmony must sit below it
        mel_here = [n["pitch"] for n in melody if n["start"] < t_end and n["end"] > t]
        mel_top = max(mel_here) if mel_here else fallback_top

        pool = [n["pitch"] for n in active if 45 <= n["pitch"] <= 88]
        if mel_top is not None:
            # stay below the melody and never a semitone away from it: a minor
            # second against the melody is the single most audible "wrong note"
            pool = [p for p in pool if p < mel_top - 1
                    and abs(p - mel_top) not in (1, 11)]
        if not pool:
            pool = [n["pitch"] for n in active if 45 <= n["pitch"] <= 88
                    and (mel_top is None or n["pitch"] < mel_top - 1)]

        # prefer notes that just started (the harmony actually changing) and
        # that belong to the recognised chord, then the ones closest to the melody
        def consonance(p):
            """How well a pitch sits against the melody (Helmholtz-style ranking)."""
            if mel_top is None:
                return 3
            d = abs(p - mel_top) % 12
            return {0: 2, 3: 4, 4: 4, 5: 3, 7: 3, 8: 4, 9: 4,
                    2: 2, 10: 1, 6: 0, 1: 0, 11: 0}.get(d, 1)

        def rank(p):
            fresh, strength = 0, 0.0
            for n in active:
                if n["pitch"] == p:
                    if abs(n["start"] - t) <= step_sec * 1.2:
                        fresh = 1
                    strength = max(strength, float(n.get("strength", 0.5)))
            in_chord = 1 if (pcs and (p % 12) in pcs) else 0
            # transcription first, then sonority against the melody
            return (-fresh, -consonance(p), -round(strength, 2), -in_chord, -p)

        # the reference scores alternate a fuller chord on the beat with a thinner
        # one off the beat - but only when there is something to spare, otherwise
        # thinning just loses harmony
        cap = max_harmony
        if k % 2 == 1 and len(set(pool)) > 3:
            cap = max(1, max_harmony - 1)
        chosen: list[int] = []
        for p in sorted(set(pool), key=rank):
            if len(chosen) >= cap:
                break
            # a minor second against a note that is still sounding is heard as a
            # wrong pitch; keep the freshly struck note and drop the old one
            if any(abs(p - q) in (1, 11) for q in chosen):
                continue
            if any(p % 12 == q % 12 for q in chosen):
                continue
            chosen.append(int(p))
        if chosen and prev_voicing:
            chosen.sort(key=lambda x: abs(x - int(np.mean(prev_voicing))))
            chosen = sorted(chosen[:max_harmony])
        if chosen:
            prev_voicing = chosen

        tick = k * step_ticks

        def clashes(pitches):
            return mel_top is not None and any(abs(q - mel_top) in (1, 11) for q in pitches)

        if chosen:
            extend = (harmony_runs and harmony_runs[-1][1] == tick
                      and harmony_runs[-1][2] == chosen and not clashes(chosen))
            if extend:
                s0, _, pitches = harmony_runs[-1]
                harmony_runs[-1] = (s0, tick + step_ticks, pitches)
            else:
                harmony_runs.append((tick, tick + step_ticks, chosen))

        # the left hand follows the bass stem only; inventing low notes from the
        # harmonic pool writes notes that are not in the original
        if bass_notes is not None:
            live = [b for b in bass_notes if b["start"] < t_end and b["end"] > t]
            low = [int(b["pitch"]) for b in live]
        else:
            low = [n["pitch"] for n in active if n["pitch"] < 52]
        if low:
            b = int(min(low))
            if b > 60:          # a "bass" note this high is an octave artefact
                b -= 12
            if b < 33:
                b += 12
            # never double a harmony pitch in the left hand
            while chosen and (b in chosen or (b + 12) in chosen):
                b -= 12
            if b < 28:
                b += 12
            if bass_runs and bass_runs[-1][1] == tick and bass_runs[-1][2] == b:
                s0, _, pitch = bass_runs[-1]
                bass_runs[-1] = (s0, tick + step_ticks, pitch)
            else:
                bass_runs.append((tick, tick + step_ticks, b))

    for s0, e0, pitches in harmony_runs:
        events.append(Event(start=s0, dur=max(step_ticks, e0 - s0), pitches=pitches,
                            staff=1, voice=2))
    for s0, e0, pitch in bass_runs:
        events.append(Event(start=s0, dur=max(step_ticks, e0 - s0), pitches=[pitch],
                            staff=2, voice=1))

    events = _enforce_monophonic([e for e in events if e.dur > 0])
    events = _enforce_register(_dedupe_global(_remove_melody_clashes(events), tm), tm)
    part.events = sorted(events, key=lambda e: (e.staff, e.voice, e.start))
    return part


def _enforce_monophonic(events: list[Event]) -> list[Event]:
    """Trim overlaps inside every (staff, voice) pair so the voice stays monophonic."""
    out: list[Event] = []
    by_voice: dict[tuple[int, int], list[Event]] = {}
    for ev in events:
        by_voice.setdefault((ev.staff, ev.voice), []).append(ev)
    for (_, _), evs in by_voice.items():
        evs.sort(key=lambda e: (e.start, e.pitches[0]))
        for i in range(len(evs) - 1):
            nxt = evs[i + 1].start
            if evs[i].start + evs[i].dur > nxt:
                evs[i].dur = nxt - evs[i].start
        out.extend([e for e in evs if e.dur > 0])
    return out

def _remove_melody_clashes(events: list[Event]) -> list[Event]:
    """Drop accompaniment notes that sit a semitone (or a major seventh) from the
    melody sounding at the same moment, and any exact doubling of it.

    This is the single most audible defect: a minor second against the melody
    reads as a wrong note even when every individual pitch was transcribed.
    """
    melody = [e for e in events if e.staff == 1 and e.voice == 1]
    if not melody:
        return events
    out = []
    for ev in events:
        if ev.staff == 1 and ev.voice == 1:
            out.append(ev)
            continue
        keep = []
        for p in ev.pitches:
            bad = False
            voice_ok = True
            for m in melody:
                if m.start - 0.15 < ev.start + ev.dur and m.start + m.dur + 0.15 > ev.start:
                    for mp in m.pitches:
                        if abs(p - mp) in (1, 11) or p == mp:
                            bad = True
                            break
                        if p > mp:
                            voice_ok = False
                if bad:
                    break
            if bad:
                continue
            if not voice_ok:
                # never let the accompaniment sit above the melody
                p -= 12
                if p < 33 or any(abs(p - q) in (1, 11) for q in keep):
                    continue
            keep.append(p)
        if keep:
            ev.pitches = keep
            out.append(ev)
    return out

def _dedupe_global(events: list[Event], tm, step: float = 0.02) -> list[Event]:
    """Remove pitches that another voice is already sounding at the same time.

    Doubling the same pitch in two voices does not make the note louder in a
    musical sense, it makes it honky: the two samples are not phase aligned.
    """
    if not events:
        return events
    t_end = max(tm.sec(e.start + e.dur) for e in events)
    n = int(t_end / step) + 1
    occupied = [set() for _ in range(n)]
    priority = sorted(events, key=lambda e: (0 if (e.staff == 1 and e.voice == 1) else 1,
                                             e.staff, e.voice, e.start))
    keep: dict[int, list[int]] = {}
    for e in priority:
        t0 = tm.sec(e.start)
        t1 = tm.sec(e.start + e.dur)
        i0 = max(0, int(t0 / step))
        i1 = min(n, max(i0 + 1, int(t1 / step)))
        kept = []
        for p in e.pitches:
            clash = sum(1 for i in range(i0, i1) if p in occupied[i])
            if clash > 0.5 * (i1 - i0):
                continue
            for i in range(i0, i1):
                occupied[i].add(p)
            kept.append(p)
        if kept:
            keep[id(e)] = kept
    out = []
    for e in events:
        if id(e) in keep:
            e.pitches = keep[id(e)]
            out.append(e)
    return out

def _enforce_register(events: list[Event], tm, step: float = 0.02) -> list[Event]:
    """Keep the accompaniment below the melody at every moment.

    A sustained chord can end up above a melody note that moves below it later;
    this checks frame by frame and drops the offending pitch (or moves it down an
    octave when that stays in range).
    """
    melody = [e for e in events if e.staff == 1 and e.voice == 1]
    if not melody:
        return events
    t_end = max(tm.sec(e.start + e.dur) for e in events)
    n = int(t_end / step) + 1
    top = [None] * n
    for e in melody:
        i0 = max(0, int(tm.sec(e.start) / step))
        i1 = min(n, max(i0 + 1, int(tm.sec(e.start + e.dur) / step)))
        hi = max(e.pitches)
        for i in range(i0, i1):
            if top[i] is None or hi > top[i]:
                top[i] = hi
    out = []
    for e in events:
        if e.staff == 1 and e.voice == 1:
            out.append(e)
            continue
        i0 = max(0, int(tm.sec(e.start) / step))
        i1 = min(n, max(i0 + 1, int(tm.sec(e.start + e.dur) / step)))
        keep = []
        for p in e.pitches:
            above = sum(1 for i in range(i0, i1) if top[i] is not None and p >= top[i])
            if above > 0.4 * (i1 - i0):
                p -= 12
                if p < 33:
                    continue
                above2 = sum(1 for i in range(i0, i1) if top[i] is not None and p >= top[i])
                if above2 > 0.2 * (i1 - i0):
                    continue
            keep.append(p)
        if keep:
            e.pitches = keep
            out.append(e)
    return out
