"""End-to-end: audio file -> analysis -> arrangements -> scores -> audio -> report."""
from __future__ import annotations

import json
import os
import time

import numpy as np

from . import (analysis, arrange, audio_io, chords as chordlib, evaluate, melody,
               musicxml, neural, poly, quantize as quant, render)
from .i18n import tr
from .musicxml import DIVISIONS, KEY_FIFTHS

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def key_to_fifths(tonic: str, mode: str) -> int:
    tonic = tonic.replace("b", "b")
    if mode == "minor":
        idx = NOTE_NAMES.index(tonic)
        rel = NOTE_NAMES[(idx + 3) % 12]
        return KEY_FIFTHS.get(rel, 0)
    return KEY_FIFTHS.get(tonic, 0)



_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _separate_cached(audio_path: str, cache_dir: str,
                     model_name: str = "htdemucs") -> dict:
    """Separate into stems, reusing a previous run when the audio is unchanged."""
    import soundfile as sf
    from . import separate as sep

    stamp = os.path.join(cache_dir, "stamp.json")
    meta = {"source": os.path.abspath(audio_path),
            "mtime": os.path.getmtime(audio_path),
            "size": os.path.getsize(audio_path),
            "model": model_name}
    names = ("drums", "bass", "other", "vocals")
    if model_name == "htdemucs_6s":
        names = ("drums", "bass", "other", "vocals", "guitar", "piano")
    if os.path.exists(stamp):
        try:
            old = json.load(open(stamp, encoding="utf-8"))
            if old == meta and all(os.path.exists(os.path.join(cache_dir, n + ".wav")) for n in names):
                out = {}
                for n in names:
                    data, fs = sf.read(os.path.join(cache_dir, n + ".wav"), dtype="float32", always_2d=True)
                    out[n] = data.mean(axis=1)
                return out
        except Exception:
            pass
    stems = sep.separate_file(audio_path, sr=44100, model_name=model_name)
    os.makedirs(cache_dir, exist_ok=True)
    for n, y in stems.items():
        sf.write(os.path.join(cache_dir, n + ".wav"), y, 44100, subtype="PCM_16")
    json.dump(meta, open(stamp, "w", encoding="utf-8"))
    return stems


def _stem_agreement(stems: dict, sr: int) -> float:
    """How consistently the lead melody appears in the 'other' and 'vocals' stems."""
    import soundfile  # noqa: F401
    from . import analysis as an
    from . import melody as ml
    try:
        res_o = ml.extract_melody(stems["other"], sr, hop=256)
        res_v = ml.extract_melody(stems["vocals"], sr, hop=256)
    except Exception:
        return None
    a, b = res_o["notes"], res_v["notes"]
    if not a or not b:
        return None
    hit = 0
    for n in a:
        for m in b:
            if abs(n["start"] - m["start"]) < 0.12 and n["pitch"] == m["pitch"]:
                hit += 1
                break
    return round(hit / max(1, len(a)), 3)



def _bar_chroma(y: np.ndarray, sr: int, bpm: float, t0: float, n_bars: int) -> np.ndarray:
    """Average chroma per bar: returns (n_bars, 12), L2-normalised.

    chroma_stft is an order of magnitude faster than chroma_cqt and accurate
    enough for a per-bar similarity check.
    """
    import librosa
    C = librosa.feature.chroma_stft(y=y.astype(np.float32), sr=sr, hop_length=2048,
                                    n_fft=4096)
    times = librosa.frames_to_time(np.arange(C.shape[1]), sr=sr, hop_length=2048)
    bar_sec = 4.0 * 60.0 / bpm
    out = np.zeros((n_bars, 12), dtype=np.float32)
    for i in range(n_bars):
        a, b = t0 + i * bar_sec, t0 + (i + 1) * bar_sec
        idx = (times >= a) & (times < b)
        if idx.any():
            out[i] = C[:, idx].mean(axis=1)
        else:
            out[i] = C[:, min(C.shape[1] - 1, int(a / (1024 / sr)))] if C.size else 0
        out[i] /= (np.linalg.norm(out[i]) + 1e-9)
    return out


def _bar_similarity(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return (a * b).sum(axis=1)


def _compensate(piano, orig_chroma: np.ndarray, cur_chroma: np.ndarray, weak: list[int],
                tm, bpm: float) -> "musicxml.Part":
    """Add soft chord tones in bars where the rendered harmony is thinner than the original."""
    from .musicxml import DIVISIONS, Event, Part

    ticks_per_bar = 4 * DIVISIONS
    events = list(piano.events)
    for bar in weak:
        want = orig_chroma[bar]
        have = cur_chroma[bar]
        delta = want - have
        # pitch classes the original has but the render lacks
        order = np.argsort(-delta)
        pcs = [int(pc) for pc in order if delta[pc] > 0.02]
        if not pcs:
            continue
        existing = set()
        bar_start, bar_end = bar * ticks_per_bar, (bar + 1) * ticks_per_bar
        pitches = []
        melody_pitches = []
        for ev in events:
            if ev.start < bar_end and ev.start + ev.dur > bar_start:
                if ev.staff == 1 and ev.voice == 1:
                    melody_pitches.extend(ev.pitches)
                for p in ev.pitches:
                    existing.add(p % 12)
                    pitches.append(p)
        pcs = [pc for pc in pcs if pc not in existing][:2]
        if not pcs:
            continue
        centre = int(np.median(pitches)) if pitches else 64
        centre = max(57, min(76, centre))
        notes = []
        for pc in pcs:
            p = centre - (centre % 12) + pc
            while p < 57:
                p += 12
            while p > 79:
                p -= 12
            if p not in notes:
                notes.append(p)
        if melody_pitches:
            # never add a fill note a semitone away from the melody in that bar
            notes = [n for n in notes
                     if all(abs(n - m) not in (1, 11) for m in melody_pitches)]
        if notes:
            events.append(Event(start=bar_start, dur=ticks_per_bar, pitches=sorted(notes),
                                staff=2, voice=3))
    out = Part(part_id=piano.part_id, name=piano.name, staves=piano.staves,
               clefs=piano.clefs, tab=piano.tab)
    out.events = sorted(events, key=lambda e: (e.staff, e.voice, e.start))
    return out


def _refine_against_original(piano, harm: np.ndarray, sr: int, tm, bpm: float,
                             duration: float, render_fn, log,
                             max_iter: int = int(os.environ.get("PF_REFINE", "0")),
                             threshold: float = 0.62, render_sr: int = 44100,
                             ) -> tuple:
    """Repeatedly render, compare per-bar harmony with the original, thicken weak bars."""
    from .musicxml import DIVISIONS
    n_bars = max(1, int(np.ceil((duration - tm.t0) / (4.0 * 60.0 / bpm))))
    orig = _bar_chroma(harm, sr, bpm, tm.t0, n_bars)
    y = render_fn(piano)
    best = (piano, y, None)
    try:
        cur = _bar_chroma(y, render_sr, bpm, tm.t0, n_bars)
        sims = _bar_similarity(orig, cur)
        best_score = float(np.mean(sims))
    except Exception:
        return best
    threshold = max(threshold, best_score * 0.98)
    log(tr("pipe.refine_start", score=round(best_score, 3)))
    for it in range(max_iter):
        try:
            cur = _bar_chroma(y, render_sr, bpm, tm.t0, n_bars)
            sims = _bar_similarity(orig, cur)
        except Exception:
            break
        weak = [int(i) for i in np.where(sims < threshold)[0]]
        if not weak:
            break
        candidate = _compensate(piano, orig, cur, weak, tm, bpm)
        y2 = render_fn(candidate)
        cur2 = _bar_chroma(y2, render_sr, bpm, tm.t0, n_bars)
        score2 = float(np.mean(_bar_similarity(orig, cur2)))
        log(tr("pipe.refine_iter", i=it + 1, n=len(weak), before=round(best_score, 3),
               after=round(score2, 3)))
        if score2 > best_score + 1e-4:
            piano, y, best_score = candidate, y2, score2
            best = (piano, y, best_score)
        else:
            break
    return best



def _gate_by_energy(notes: list[dict], y: np.ndarray, sr: int, rel_db: float = -30.0) -> list[dict]:
    """Drop notes the model placed in near-silence (a generic hallucination guard)."""
    import librosa
    if not notes or y is None or len(y) == 0:
        return notes
    hop = 256
    rms = librosa.feature.rms(y=y.astype(np.float32), frame_length=1024, hop_length=hop)[0]
    total = float(np.sqrt(np.mean(y.astype(np.float32) ** 2))) + 1e-9
    floor = total * (10 ** (rel_db / 20.0))
    kept = []
    for n in notes:
        i0 = max(0, int(n["start"] * sr / hop))
        i1 = max(i0 + 1, int(n["end"] * sr / hop))
        seg = rms[i0:i1]
        if len(seg) and float(np.mean(seg)) < floor:
            continue
        kept.append(n)
    return kept


def _limit_density(part, tm, budget: int = 9) -> int:
    """Keep at most budget distinct pitches per bar.

    A human piano reduction of a band mix uses about 8-9 different pitches per
    bar; anything beyond that is transcription spill from other instruments.
    """
    from collections import defaultdict

    beat = 60.0 / float(tm.bpm)
    bars = defaultdict(list)
    for ev in part.events:
        t = tm.sec(ev.start)
        bars[int(t / (4 * beat))].append(ev)
    for bar, evs in bars.items():
        weight = defaultdict(float)
        for ev in evs:
            prio = 1000.0 if (ev.staff == 1 and ev.voice == 1) else ev.dur
            for p in ev.pitches:
                weight[int(p)] += prio
        if len(weight) <= budget:
            continue
        keep = set(sorted(weight, key=lambda k: -weight[k])[:budget])
        for ev in evs:
            ev.pitches = [p for p in ev.pitches if int(p) in keep]
    before = len(part.events)
    part.events = [ev for ev in part.events if ev.pitches and ev.dur > 0]
    return before - len(part.events)


def _smooth_melody_voice(part, tm, max_dur: float = 0.6, leap: int = 10) -> int:
    """An isolated note far from both neighbours is not part of the tune.

    Move it into the accompaniment so the melody line stops jumping registers.
    """
    from .musicxml import Event as _Ev
    mel = [e for e in part.events if e.staff == 1 and e.voice == 1]
    mel.sort(key=lambda e: e.start)
    moved = 0
    for i in range(1, len(mel) - 1):
        a, b, c = mel[i - 1], mel[i], mel[i + 1]
        pb = int(b.pitches[0])
        dur_sec = tm.sec(b.start + b.dur) - tm.sec(b.start)
        if (abs(pb - int(a.pitches[0])) >= leap and abs(pb - int(c.pitches[0])) >= leap
                and dur_sec <= max_dur):
            part.events.remove(b)
            part.events.append(_Ev(start=b.start, dur=b.dur, pitches=list(b.pitches),
                                   staff=1, voice=2))
            moved += 1
    if moved:
        part.events.sort(key=lambda e: (e.staff, e.voice, e.start))
    return moved


def _clamp_bass(part, lowest: int = 40) -> int:
    changed = 0
    for ev in part.events:
        if ev.staff != 2:
            continue
        fixed = []
        for p in ev.pitches:
            q = int(p)
            while q < lowest:
                q += 12
            fixed.append(q)
        if sorted(set(fixed)) != sorted(set(int(x) for x in ev.pitches)):
            changed += 1
        ev.pitches = sorted(set(fixed))
    return changed

def run(audio_path: str, out_dir: str | None = None, sr: int = 22050,
        use_separation: bool = True, title: str | None = None,
        melody_lo: int = 55, melody_hi: int = 96, hop: int = 256,
        min_note: float = 0.05, engine: str = "auto", progress=None, log=print) -> dict:
    t_start = time.time()

    # per-run defaults (a previous vocal-led song must not leak its balance)
    render.SETTINGS["melody_gain"] = 1.15
    render.SETTINGS["accomp_gain"] = 0.6

    _t_last = [t_start]
    _timings: list[tuple[int, float]] = []

    def _stage(i: int):
        now = time.time()
        if _timings or i > 1:
            _timings.append((i - 1, round(now - _t_last[0], 2)))
        _t_last[0] = now
        if progress is not None:
            try:
                progress(i, 9)
            except Exception:
                pass

    name = os.path.splitext(os.path.basename(audio_path))[0]
    name = "".join(c for c in name if c.isalnum() or c in " -_")[:60].strip() or "track"
    out_dir = out_dir or os.path.join(_ROOT, "out", name)
    os.makedirs(out_dir, exist_ok=True)
    # tidy leftovers from older versions (per-page folders, stray svg copies)
    for stale in os.listdir(out_dir):
        if stale.endswith("_pages") and os.path.isdir(os.path.join(out_dir, stale)):
            try:
                import shutil as _sh
                _sh.rmtree(os.path.join(out_dir, stale))
            except Exception:
                pass
        elif stale.endswith(".svg") or stale in ("report.json", "melody.json",
                                                 "chords.txt", "verification.png"):
            try:
                os.remove(os.path.join(out_dir, stale))
            except Exception:
                pass

    _stage(1)
    log(tr("pipe.decode", path=audio_path))
    y, sr = audio_io.load_audio(audio_path, sr=sr, mono=True)
    duration = len(y) / sr
    log(tr("pipe.duration", dur=duration, sr=sr))
    _rms_in = float(np.sqrt(np.mean(y ** 2))) if len(y) else 0.0
    if _rms_in < 1e-5:
        raise ValueError(tr("pipe.silent_input"))
    if duration < 1.0:
        raise ValueError(tr("pipe.too_short"))

    six_stem = engine in ("six", "sixfull")
    stems = {}
    if use_separation:
        _stage(2)
        log(tr("pipe.separation"))
        try:
            if six_stem:
                stems = _separate_cached(audio_path, os.path.join(_ROOT, "cache", "stems6", name),
                                         model_name="htdemucs_6s")
                log(tr("pipe.stems6", stems=[k for k in stems]))
            else:
                stems = _separate_cached(audio_path, os.path.join(_ROOT, "cache", "stems", name))
            import librosa
            stems = {k: librosa.resample(v, orig_sr=44100, target_sr=sr).astype("float32")
                     for k, v in stems.items()}
            log(tr("pipe.stems", stems=list(stems)))
        except Exception as exc:
            log(tr("pipe.separation_failed", err=exc))
            stems = {}
    else:
        log(tr("pipe.no_separation"))

    vocals_info = {"removed": False, "rms": 0.0}
    if stems:
        other = stems["other"]
        voc = stems.get("vocals")
        other_rms = float(np.sqrt(np.mean(other ** 2))) + 1e-9
        voc_rms = float(np.sqrt(np.mean(voc ** 2))) if voc is not None else 0.0
        # the user asked for instrumental-only scores: when the track has vocals,
        # leave them out of both the harmony and the melody source
        has_vocals = (voc is not None and voc_rms > max(0.05 * other_rms, 0.004)
                      and os.environ.get("PF_VOCALS_KEEP", "0") != "1")
        # a quiet vocal stem is backing vocals (karaoke tracks keep them): they
        # belong to the arrangement, not to the lead line
        backing_only = has_vocals and voc_rms < 0.55 * other_rms
        vocals_info = {"removed": bool(has_vocals), "rms": round(voc_rms, 4)}
        if backing_only:
            log(tr("pipe.vocals_backing", rms=round(voc_rms, 3)))
            mix_for_harmony = other + 0.5 * voc + 0.5 * stems.get("bass", 0)
            melody_src = other
            has_vocals = False
            vocals_info["removed"] = False
            vocals_info["backing"] = True
        elif has_vocals:
            log(tr("pipe.vocals_dropped", rms=round(voc_rms, 3)))
            try:
                from . import separate as _sep
                other_clean = _sep.suppress_vocals(other, voc, sr)
                if other_clean is not None and len(other_clean) > 1000:
                    other = other_clean
                    stems["other"] = other_clean
                    log(tr("pipe.vocals_cleaned"))
            except Exception as _exc:
                log(tr("pipe.vocals_clean_failed", err=_exc))
            mix_for_harmony = other + 0.5 * stems.get("bass", 0)
            melody_src = other
        else:
            mix_for_harmony = other + 0.6 * stems.get("vocals", 0) + 0.5 * stems.get("bass", 0)
            melody_src = other + 0.25 * stems.get("vocals", 0)
        if "piano" in stems:
            mix_for_harmony = mix_for_harmony + 0.8 * stems["piano"]
        perc = stems.get("drums", None)
    else:
        mix_for_harmony = y
        melody_src = None
        perc = None

    _stage(3)
    log(tr("pipe.harmonic"))
    harm, perc_hp = analysis.hpss(mix_for_harmony, sr)
    mel_sig = melody_src if melody_src is not None else harm

    _stage(4)
    log(tr("pipe.tempo"))
    beat_input = y
    if perc is not None:
        m = min(len(y), len(perc))
        beat_input = 0.55 * y[:m] + 0.45 * perc[:m]
    beats = analysis.estimate_tempo_and_beats(beat_input, sr)
    beat_times = beats["beat_times"]
    bpm = beats["tempo"]
    if len(beat_times) >= 4:
        bpm = float(60.0 / np.median(np.diff(beat_times)))
    if not np.isfinite(bpm) or bpm < 30.0 or bpm > 300.0:
        bpm = 120.0
    t0 = float(beat_times[0]) if len(beat_times) else 0.0
    tm = arrange.TimeMap(bpm, t0=t0)

    chroma = analysis.chroma_cqt(harm, sr, hop=512)
    tonic, mode, key_score = analysis.estimate_key(chroma)
    fifths = key_to_fifths(tonic, mode)
    log(tr("pipe.tempo_result", bpm=bpm, key=f"{tonic} {mode}", beats=len(beat_times)))

    _stage(5)
    log(tr("pipe.chords"))
    chord_seq = chordlib.recognize_chords(chroma, beats["beat_frames"])
    chord_segments = chordlib.segments_from_chords(chord_seq, beat_times)
    log(tr("pipe.chords_result", n=len(chord_segments)))

    _stage(6)
    log(tr("pipe.melody"))
    # solo piano: the melody is the top voice of the transcription, the CQT
    # tracker gets confused by the accompaniment and drops an octave
    # solo piano gets its own treatment: the melody is the top voice and the
    # arrangement keeps the real note rhythm instead of the eighth-note grid
    piano_input = (engine == "piano")
    if not piano_input and engine != "classic" and not stems:
        try:
            hm = float(np.sqrt(np.mean(harm ** 2))) + 1e-9
            pm = float(np.sqrt(np.mean(perc_hp ** 2))) + 1e-9
            piano_input = (pm / hm) < 0.12
        except Exception:
            piano_input = False
    mel = melody.extract_melody(mel_sig, sr, hop=hop, lo=melody_lo, hi=melody_hi)
    mel_notes = mel["notes"]

    _high_fill = []
    # with a singer, the tune is the vocal line: use it as the melody and keep the
    # instrumental melody only where the voice is silent (intros, solos)
    if stems and vocals_info.get("removed"):
        try:
            voc_h, _ = analysis.hpss(stems["vocals"], sr)
            mel_v = melody.extract_melody(voc_h, sr, hop=hop, lo=melody_lo, hi=melody_hi)["notes"]
            cover = sum(n["end"] - n["start"] for n in mel_v) / max(1e-6, duration)
            if mel_v and cover >= 0.15:
                inst = [n for n in mel_notes]
                merged = list(mel_v)
                for n in inst:
                    # only fill real silences (intro, interludes). A short gap
                    # between sung phrases must not let another instrument into
                    # the melody - it goes to the accompaniment instead.
                    if any(abs(n["start"] - m["start"]) < 0.25 for m in mel_v):
                        continue
                    if any(abs(n["start"] - m["start"]) < 0.12 and abs(n["pitch"] - m["pitch"]) <= 1
                           for m in merged):
                        continue
                    # a note far above the vocal line is a second instrumental layer,
                    # not part of the tune: keep it as harmony so the melody does not
                    # jump registers from one note to the next
                    near = [m for m in mel_v if abs(m["start"] - n["start"]) < 0.35]
                    if near and n["pitch"] - max(m["pitch"] for m in near) >= 7:
                        _high_fill.append(n)
                        continue
                    merged.append(n)
                merged.sort(key=lambda n: n["start"])
                mel_notes = merged
                # lift low vocal lines into the right hand's register so the
                # accompaniment still has room underneath
                mel_notes = [dict(n, pitch=int(n["pitch"]) + 12) if n["pitch"] < 64 else n
                             for n in mel_notes]
                # the tune comes from the singer: bring it forward in the mix
                render.SETTINGS["melody_gain"] = 1.4
                render.SETTINGS["accomp_gain"] = 0.5
                log(tr("pipe.vocal_melody", n=len(mel_v), cover=round(cover * 100)))
        except Exception as exc:
            log(tr("pipe.vocal_melody_failed", err=exc))
    try:
        _before = len(mel_notes)
        mel_notes = melody.remove_outliers(mel_notes)
        if len(mel_notes) != _before:
            log(tr("pipe.melody_outliers", n=_before - len(mel_notes)))
    except Exception:
        pass
    if os.environ.get("PF_SMOOTH", "1") != "0":
        try:
            mel_notes = melody.smooth_octaves(mel_notes)
        except Exception:
            pass
    log(tr("pipe.melody_raw", n=len(mel_notes)))

    beat_sec = 60.0 / bpm
    grid = t0 + np.arange(0, duration - t0 + beat_sec, beat_sec / 4.0)
    mel_q = quant.quantize_notes(mel_notes, grid, bpm, min_len=min_note)
    log(tr("pipe.melody_quant", n=len(mel_q)))

    _stage(7)
    log(tr("pipe.arrange"))
    _t_arr = time.time()
    total_ticks = max(tm.tick(duration), 4 * DIVISIONS)
    poly_notes = []
    if engine == "auto":
        engine = "full" if neural.available() else "classic"
    use_neural = engine in ("neural", "full", "piano", "six", "sixfull") and neural.available()
    if engine == "classic":
        use_neural = False
    try:
        if use_neural:
            # transcribing each separated stem separately gives better recall than
            # one pass over the mixture, and it is faster too
            sources = []
            _ref_rms = float(np.sqrt(np.mean(harm ** 2))) + 1e-9
            if stems:
                for key in ("piano", "other", "vocals", "bass"):
                    if key in stems:
                        rms = float(np.sqrt(np.mean(stems[key] ** 2)))
                        if rms < 0.02 * _ref_rms:      # silent stem: skip the pass
                            continue
                        h, _ = analysis.hpss(stems[key], sr)
                        sources.append(h)
                # a fourth pass over the whole harmonic mix catches notes the
                # per-stem runs miss (soft pads, layered parts)
                sources.append(harm)
            if not sources:
                sources = [harm]
            mixed_loose = None
            if engine in ("max", "maxfull"):
                mix_all = sum(s for s in sources[:1]) if sources else harm
                try:
                    pool = harm.copy()
                    for s in sources:
                        pool = pool[: min(len(pool), len(s))] + s[: min(len(pool), len(s))]
                    mixed_loose = neural.transcribe(pool / max(1, len(sources) + 1), sr,
                                                    onset_thresh=0.32, note_thresh=0.18,
                                                    min_len=0.05)
                except Exception:
                    mixed_loose = None
            merged = []
            # the per-stem passes are independent: run them concurrently unless
            # threading is disabled (onnxruntime is not always crash-safe in threads)
            _bp_kw = {"onset_thresh": float(os.environ.get("PF_ON_TH", "0.65")),
                      "note_thresh": float(os.environ.get("PF_NOTE_TH", "0.38"))}
            if os.environ.get("PF_THREADS", "1") != "0" and len(sources) > 1:
                try:
                    from concurrent.futures import ThreadPoolExecutor
                    with ThreadPoolExecutor(max_workers=min(4, len(sources))) as _ex:
                        _per_source = list(_ex.map(lambda s: neural.transcribe(s, sr, **_bp_kw), sources))
                except Exception:
                    _per_source = [neural.transcribe(s, sr, **_bp_kw) for s in sources]
            else:
                _per_source = [neural.transcribe(s, sr) for s in sources]
            for _notes in _per_source:
                for note in _notes:
                    if not any(abs(note["start"] - m["start"]) < 0.09
                               and note["pitch"] == m["pitch"] for m in merged):
                        merged.append(note)
            merged.sort(key=lambda n: (n["start"], n["pitch"]))
            if engine in ("full", "sixfull") and os.environ.get("PF_DENSE", "0") == "1":
                # denser variant: add the classical transcriber's extra notes where
                # the neural model found nothing (more notes, slightly less precise)
                extra = poly.transcribe(harm, sr)
                added = 0
                for n in extra:
                    if float(n.get("strength", 1.0)) < 0.30:
                        continue
                    if not any(abs(n["start"] - m["start"]) < 0.10 and abs(n["pitch"] - m["pitch"]) <= 0
                               for m in merged):
                        merged.append(n)
                        added += 1
                merged.sort(key=lambda n: (n["start"], n["pitch"]))
                log(tr("pipe.full", extra=added))
            if engine in ("max", "maxfull"):
                # maximum-recall variant: add the six-stem piano/other passes and a
                # loose-threshold pass, then let the arranger choose what to keep
                extra_src = []
                s6 = os.environ.get("PF_STEMS6", "")
                if s6 and os.path.isdir(s6):
                    for key in ("piano", "other"):
                        f = os.path.join(s6, key + ".wav")
                        if os.path.exists(f):
                            y6, _ = audio_io.load_audio(f, sr=sr)
                            extra_src.append(analysis.hpss(y6, sr)[0])
                if extra_src:
                    for sig in extra_src:
                        for note in neural.transcribe(sig, sr, onset_thresh=0.3,
                                                      note_thresh=0.15, min_len=0.04):
                            if not any(abs(note["start"] - m["start"]) < 0.07
                                       and note["pitch"] == m["pitch"] for m in merged):
                                merged.append(note)
                if mixed_loose is not None:
                    for note in mixed_loose:
                        if not any(abs(note["start"] - m["start"]) < 0.07
                                   and note["pitch"] == m["pitch"] for m in merged):
                            merged.append(note)
                merged.sort(key=lambda n: (n["start"], n["pitch"]))
                log(tr("pipe.max_recall", n=len(merged)))
            poly_notes = merged
            log(tr("pipe.neural", n=len(poly_notes)))
        else:
            poly_notes = poly.transcribe(harm, sr)
            log(tr("pipe.poly", n=len(poly_notes)))
    except Exception as exc:
        log(tr("pipe.poly_failed", err=exc))

    if _high_fill:
        poly_notes.extend(_high_fill)
        poly_notes.sort(key=lambda n: (n["start"], n["pitch"]))

    # instrument-aware pass: transcribe each instrument of a six-stem separation
    # separately with its own register, then merge
    try:
        _s6 = os.environ.get("PF_STEMS6") or os.path.join(_ROOT, "cache", "stems6", name)
        if os.path.isdir(_s6) and poly_notes is not None:
            _priors = {"piano": (33, 96), "guitar": (50, 88), "other": (40, 96),
                       "bass": (28, 60)}
            _added = 0
            for _key, (_lo, _hi) in _priors.items():
                _f = os.path.join(_s6, _key + ".wav")
                if not os.path.exists(_f):
                    continue
                _y6, _ = audio_io.load_audio(_f, sr=sr)
                _h6, _ = analysis.hpss(_y6, sr)
                for _n in neural.transcribe(_h6, sr, onset_thresh=0.65, note_thresh=0.38):
                    if not (_lo <= int(_n["pitch"]) <= _hi):
                        continue
                    if not any(abs(_n["start"] - _m["start"]) < 0.07
                               and int(_n["pitch"]) == int(_m["pitch"]) for _m in poly_notes):
                        poly_notes.append(_n)
                        _added += 1
            poly_notes.sort(key=lambda n: (n["start"], n["pitch"]))
            if _added:
                log(tr("pipe.instrument_pass", n=_added))
    except Exception as _exc:
        log(tr("pipe.instrument_failed", err=_exc))


    if piano_input and poly_notes:
        try:
            tv = melody.top_voice_from_notes(poly_notes)
            if len(tv) >= 8:
                mel_q = quant.quantize_notes(tv, grid, bpm, min_len=min_note)
                log(tr("pipe.piano_mode", n=len(mel_q)))
        except Exception:
            pass

    bass_line = []
    if stems:
        try:
            bass_h, _ = analysis.hpss(stems["bass"], sr)
            if neural.available():
                bass_line = neural.transcribe(bass_h, sr, onset_thresh=0.40,
                                              note_thresh=0.25)
                bass_line = _gate_by_energy(bass_line, bass_h, sr, -26.0)
            else:
                bass_line = poly.transcribe(bass_h, sr, max_poly=1, on_thresh=0.30)
        except Exception:
            bass_line = []
    if len(poly_notes) >= max(24, int(duration * 1.2)):
        mode = os.environ.get("PF_PIANO_MODE", "reduced")
        if (piano_input and mode != "reduced") or mode == "poly":
            up = os.environ.get("PF_MAX_UP", "6" if piano_input else "3")
            lo = os.environ.get("PF_MAX_LO", "2" if piano_input else "1")
            ms = os.environ.get("PF_MIN_STR", "0.12" if piano_input else "0.25")
            # the melody line is taken from these same notes: remove them from the
            # accompaniment source, otherwise every melody note is played twice
            harm_src = [n for n in poly_notes
                        if not any(abs(n["start"] - m["start"]) < 0.08
                                   and int(n["pitch"]) == int(m["pitch"]) for m in mel_q)]
            piano = arrange.build_piano_poly(mel_q, harm_src, tm, bpm, duration,
                                             max_upper_voices=int(up),
                                             max_bass_voices=int(lo),
                                             min_strength=float(ms))
        else:
            piano = arrange.build_piano_reduced(
                mel_q, poly_notes, chord_segments, tm, bpm, duration,
                max_harmony=int(os.environ.get("PF_HARMONY", "4")), bass_notes=bass_line)
        log(tr("pipe.arrange_poly", n=len(piano.events)))
    else:
        piano = arrange.build_piano(mel_q, chord_segments, [], tm, bpm, duration)
    guitar = arrange.build_guitar(mel_q, chord_segments, tm, bpm, duration)
    log(tr("pipe.arrange_result", p=len(piano.events), g=len(guitar.events)))
    log(tr("pipe.transcribe_sec", sec=round(time.time() - _t_arr, 1)))

    try:
        os.makedirs(os.path.join(out_dir, "_analysis"), exist_ok=True)
        with open(os.path.join(out_dir, "_analysis", "transcription.json"), "w",
                  encoding="utf-8") as _f:
            json.dump({"bpm": bpm, "t0": tm.t0, "duration": duration,
                       "notes": [{"start": float(n["start"]), "end": float(n["end"]),
                                  "pitch": int(n["pitch"]),
                                  "strength": float(n.get("strength", 0.2))}
                                 for n in poly_notes],
                       "melody": [{"start": float(m["start"]), "end": float(m["end"]),
                                   "pitch": int(m["pitch"])} for m in mel_q]}, _f)
    except Exception as _exc:
        log("transcription dump failed: %s" % _exc)

    if os.environ.get("PF_DUMP_PART"):
        import pickle
        with open(os.path.join(_ROOT, "cache", "part.pkl"), "wb") as f:
            pickle.dump({"piano": piano, "guitar": guitar, "bpm": bpm, "total_ticks": total_ticks,
                         "fifths": fifths, "duration": duration}, f)

    # ---- closed-loop refinement against the original --------------------
    def _render_part(part):
        return render.render_piano_array([part], tm, duration, sr=44100)

    _t_ref = time.time()
    try:
        piano, y_piano, _ = _refine_against_original(
            piano, harm, sr, tm, bpm, duration, _render_part, log)
    except Exception as exc:
        log(tr("pipe.refine_failed", err=exc))
        y_piano = _render_part(piano)
    log(tr("pipe.refine_sec", sec=round(time.time() - _t_ref, 1)))

    # these passes change the score, so the rendered audio must follow them
    try:
        _moved = _smooth_melody_voice(piano, tm)
        if _moved:
            log(tr("pipe.melody_smoothed", n=_moved))
        _bass = _clamp_bass(piano, int(os.environ.get("PF_BASS_FLOOR", "28")))
        _budget = int(os.environ.get("PF_BUDGET", "0"))
        _dropped = _limit_density(piano, tm, budget=_budget) if _budget > 0 else 0
        if _moved or _bass or _dropped:
            y_piano = _render_part(piano)
            log(tr("pipe.rerender", n=_moved + _bass + _dropped))
    except Exception as exc:
        log("density pass failed: %s" % exc)

    _stage(8)
    try:
        import json as _json
        os.makedirs(os.path.join(out_dir, "_analysis"), exist_ok=True)
        _dump = {"bpm": bpm, "t0": tm.t0, "tracks": []}
        for _part in (piano,):
            _dump["tracks"].append({
                "name": _part.name,
                "events": [{"staff": int(e.staff), "voice": int(e.voice), "start": int(e.start),
                            "dur": int(e.dur), "pitches": [int(x) for x in e.pitches]}
                           for e in _part.events],
            })
        with open(os.path.join(out_dir, "_analysis", "parts.json"), "w", encoding="utf-8") as _f:
            _json.dump(_dump, _f)
    except Exception as _exc:
        log("parts dump failed: %s" % _exc)

    log(tr("pipe.write"))
    score_title = title or name
    # four deliverables at the top level; everything else lives in _analysis so
    # the folder stays readable at a glance
    analysis_dir = os.path.join(out_dir, "_analysis")
    os.makedirs(analysis_dir, exist_ok=True)
    score_path = os.path.join(analysis_dir, "piano.musicxml")
    musicxml.write_score(score_path, [piano], score_title + " - Piano", "pianoforge", bpm,
                         fifths, total_ticks)
    tab_path = os.path.join(analysis_dir, "guitar.musicxml")
    musicxml.write_score(tab_path, [guitar], score_title + " - Fingerstyle Guitar",
                         "pianoforge", bpm, fifths, total_ticks)
    midi_path = os.path.join(analysis_dir, "piano.mid")
    render.write_midi([piano], tm, midi_path, bpm)
    wav_path = os.path.join(out_dir, "audio.wav")
    piano_sr = 44100
    audio_io.write_wav(wav_path, y_piano, piano_sr)
    ogg_path = os.path.join(analysis_dir, "piano.ogg")
    try:
        audio_io.encode_audio(wav_path, ogg_path)
    except Exception as exc:
        log(tr("pipe.encode_failed", err=exc))
    tab_txt = os.path.join(analysis_dir, "tab.txt")
    with open(tab_txt, "w", encoding="utf-8") as f:
        f.write(render.ascii_tab(guitar, tm))
    eng = render.to_pdf_svg(score_path, out_dir, "piano")
    eng.update(render.to_pdf_svg(tab_path, out_dir, "guitar"))
    # a copy of the source audio, so a song folder is self-contained
    try:
        import shutil as _sh
        _ext = os.path.splitext(audio_path)[1].lower() or ".audio"
        _sh.copyfile(audio_path, os.path.join(out_dir, "original" + _ext))
    except Exception as _exc:
        log(tr("pipe.original_copy_failed", err=_exc))

    _stage(9)
    log(tr("pipe.evaluate"))
    metrics = evaluate.compare(y, sr, y_piano, piano_sr, mel_notes, mel_q,
                               y_ref_melody=mel_sig)
    metrics["melody_stem_agreement"] = _stem_agreement(stems, sr) if stems else None

    analysis_dir = os.path.join(out_dir, "_analysis")
    os.makedirs(analysis_dir, exist_ok=True)
    fig_path = os.path.join(analysis_dir, "verification.png")
    try:
        from . import report as report_mod
        report_mod.verification_figure(y, sr, y_piano, piano_sr, mel_sig, metrics, fig_path,
                                       title=os.path.basename(audio_path))
    except Exception as exc:
        log(tr("pipe.fig_skip", err=exc))

    report = {
        "input": os.path.abspath(audio_path),
        "duration_sec": round(duration, 3),
        "tempo_bpm": round(bpm, 2),
        "key": f"{tonic} {mode}",
        "key_correlation": round(float(key_score), 3),
        "beats": len(beat_times),
        "melody_notes": len(mel_q),
        "chord_segments": len(chord_segments),
        "piano_events": len(piano.events),
        "guitar_events": len(guitar.events),
        "separation": bool(stems),
        "vocals": vocals_info,
        "outputs": {
            "piano_wav": wav_path,
            "piano_pdf": os.path.join(out_dir, "piano.pdf"),
            "guitar_pdf": os.path.join(out_dir, "guitar.pdf"),
            "original": os.path.join(out_dir, "original" + (os.path.splitext(audio_path)[1].lower() or ".audio")),
            "score_piano": score_path, "score_guitar_tab": tab_path,
            "midi": midi_path,
            "piano_ogg": ogg_path if os.path.exists(ogg_path) else None,
            "tab_txt": tab_txt, "verification_png": fig_path, "engraving": eng,
        },
        "metrics": metrics,
        "elapsed_sec": round(time.time() - t_start, 1),
        "stage_seconds": {str(i): s for i, s in _timings},
    }
    with open(os.path.join(analysis_dir, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    with open(os.path.join(analysis_dir, "melody.json"), "w", encoding="utf-8") as f:
        json.dump({"notes": mel_notes, "quantised": mel_q,
                   "chords": chord_segments, "bpm": bpm, "key": f"{tonic} {mode}"},
                  f, indent=1)
    with open(os.path.join(analysis_dir, "chords.txt"), "w", encoding="utf-8") as f:
        for seg in chord_segments:
            f.write(f"{seg['start']:8.2f} {seg['end']:8.2f}  "
                    f"{chordlib.chord_label(seg['root'], seg['quality'])}\n")
    # ---- self check: are the produced files actually usable? -------------
    _checks = {}
    try:
        import xml.etree.ElementTree as _ET
        _checks = {}
        try:
            _ET.parse(score_path)
            _checks["musicxml"] = True
        except Exception:
            _checks["musicxml"] = False
        _rms = float(np.sqrt(np.mean(y_piano ** 2))) if len(y_piano) else 0.0
        _checks["audio_rms"] = round(_rms, 4)
        _checks["audio_seconds"] = round(len(y_piano) / float(piano_sr), 2)
        _checks["duration_match"] = abs(len(y_piano) / float(piano_sr) - duration) < 0.05
        _checks["pdf"] = os.path.exists(os.path.join(out_dir, "piano.pdf"))
        _ok = (_checks["musicxml"] and _checks["audio_rms"] > 0.001 and _checks["pdf"]
               and _checks["duration_match"])
        log(tr("pipe.selfcheck", ok=("OK" if _ok else "FAIL"),
               rms=_checks["audio_rms"], sec=_checks["audio_seconds"]))
    except Exception as _exc:
        _checks = {"error": str(_exc)}
        log(tr("pipe.selfcheck_failed", err=_exc))
    try:
        report["selfcheck"] = _checks
        with open(os.path.join(analysis_dir, "report.json"), "w", encoding="utf-8") as _f:
            json.dump(report, _f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    if _timings:
        log(tr("pipe.timing", parts="  ".join(f"{i}:{s}s" for i, s in _timings if s >= 0.05)))
    log(tr("pipe.done", sec=report["elapsed_sec"], dir=out_dir))
    return report