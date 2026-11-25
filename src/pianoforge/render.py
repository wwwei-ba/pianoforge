"""Render arrangements to audio, MIDI and printable scores."""
from __future__ import annotations

import os
import subprocess

import numpy as np

from . import audio_io, synth
from .musicxml import DIVISIONS

# rendering balance; the pipeline overrides it for vocal-led songs
SETTINGS = {"melody_gain": 1.15, "accomp_gain": 0.6}


def part_to_notes(part, tm, velocity_by_staff=None) -> list[dict]:
    """Flatten score events into renderable notes; the melody stays on top."""
    notes = []
    for ev in part.events:
        start = tm.sec(ev.start)
        end = tm.sec(ev.start + ev.dur)
        if ev.staff == 1 and ev.voice == 1:
            base, role = 0.95, "melody"
        elif ev.staff == 1:
            base, role = 0.72, "harmony"
        else:
            base, role = 0.62, "bass"
        # a pianist leans on the downbeat and lightens the off-beats
        beat = 60.0 / max(1e-6, getattr(tm, "bpm", 120.0))
        pos = (start - tm.t0) % (4 * beat) / beat
        accent = 1.10 if pos < 0.12 else (0.96 if abs(pos - round(pos)) > 0.2 else 1.0)
        for i, p in enumerate(ev.pitches):
            vel = base - 0.08 * (len(ev.pitches) - 1 - i) if ev.staff == 1 else base
            notes.append({"start": start, "end": end, "pitch": int(p),
                          "velocity": max(0.2, min(1.0, vel * accent)), "role": role})
    return notes


def _mix_balanced(melody: np.ndarray, accomp: np.ndarray, melody_gain: float = 1.0,
                  accomp_gain: float = 0.70) -> np.ndarray:
    """Mix melody and accompaniment without flattening their dynamics.

    Normalising each group to a fixed RMS made every accompaniment note as loud as
    the last one, which measurably hurt the match with the original; the per-note
    velocities already carry the balance.
    """
    n = max(len(melody), len(accomp))
    out = np.zeros(n, dtype=np.float32)
    if len(melody):
        out[: len(melody)] += (melody * melody_gain).astype(np.float32)
    if len(accomp):
        out[: len(accomp)] += (accomp * accomp_gain).astype(np.float32)
    return out


def render_piano_array(parts, tm, total_sec: float, sr: int = 44100,
                       reverb: float = 0.22, engine: str = "auto",
                       return_notes: bool = False):
    """Render the parts to a float array without writing anything."""
    from . import samples as samplebank

    notes = []
    for part in parts:
        notes.extend(part_to_notes(part, tm))
    engine = engine or "auto"
    y = None
    melody = [n for n in notes if n.get("role") == "melody"]
    accomp = [n for n in notes if n.get("role") != "melody"]
    if engine in ("auto", "samples"):
        try:
            if samplebank.load_bank():
                y_m = samplebank.render_notes(melody, total_sec + 1.5, sr=sr)
                y_a = samplebank.render_notes(accomp, total_sec + 1.5, sr=sr)
                y = _mix_balanced(y_m, y_a,
                                  melody_gain=SETTINGS.get("melody_gain", 1.15),
                                  accomp_gain=SETTINGS.get("accomp_gain", 0.6))
        except Exception as exc:  # pragma: no cover
            print("sample engine failed:", exc)
    if y is None or not np.any(y):
        y = synth.render_notes(notes, total_sec + 1.5, sr=sr)
    y = synth.add_reverb(y, sr=sr, wet=reverb)
    # the reverb tail and the extra render headroom must not lengthen the track:
    # the output has to be exactly as long as the input audio
    want = int(round(float(total_sec) * sr))
    if len(y) > want:
        y = y[:want]
    elif len(y) < want:
        y = np.pad(y, (0, want - len(y)))
    y = synth.normalize(y)
    return (y, notes) if return_notes else y


def render_piano(parts, tm, total_sec: float, out_wav: str, sr: int = 44100,
                 reverb: float = 0.22, engine: str = "auto") -> np.ndarray:
    y = render_piano_array(parts, tm, total_sec, sr=sr, reverb=reverb, engine=engine)
    audio_io.write_wav(out_wav, y, sr)
    return y


def write_midi(parts, tm, path: str, bpm: float, program: int = 0) -> str:
    import pretty_midi
    pm = pretty_midi.PrettyMIDI(initial_tempo=bpm)
    for part in parts:
        inst = pretty_midi.Instrument(program=program, name=part.name)
        for ev in part.events:
            start = tm.sec(ev.start)
            end = tm.sec(ev.start + ev.dur)
            for p in ev.pitches:
                inst.notes.append(pretty_midi.Note(velocity=96 if ev.staff == 1 else 74,
                                                   pitch=int(p), start=start, end=max(end, start + 0.02)))
        pm.instruments.append(inst)
    pm.write(path)
    return path


def to_pdf_svg(musicxml_path: str, out_dir: str, name: str) -> dict:
    """Engrave with verovio if available: SVG always, PDF when a converter exists."""
    out = {}
    try:
        import verovio
        tk = verovio.toolkit()
        tk.setOptions({
            "pageWidth": 2100, "pageHeight": 2970, "scale": 45,
            "adjustPageHeight": True, "footer": "none", "header": "none",
        })
        if not tk.loadData(open(musicxml_path, encoding="utf-8").read()):
            return out
        pages = tk.getPageCount()
        page_dir = os.path.join(out_dir, "_analysis", "svg", name)
        os.makedirs(page_dir, exist_ok=True)
        svg_files, pdf_files = [], []
        for i in range(1, pages + 1):
            svg = tk.renderToSVG(i)
            p = os.path.join(page_dir, f"page{i:02d}.svg")
            with open(p, "w", encoding="utf-8") as f:
                f.write(svg)
            svg_files.append(p)
            try:
                from svglib.svglib import svg2rlg
                from reportlab.graphics import renderPDF
                drawing = svg2rlg(p)
                if drawing is not None:
                    pdf_one = p.replace(".svg", ".pdf")
                    renderPDF.drawToFile(drawing, pdf_one)
                    pdf_files.append(pdf_one)
            except Exception:
                pass
        out["svg"] = svg_files[0] if svg_files else None
        out["svg_pages"] = svg_files
        if pdf_files:
            try:
                import pymupdf
                merged = pymupdf.open()
                for pf in pdf_files:
                    src = pymupdf.open(pf)
                    merged.insert_pdf(src)
                    src.close()
                pdf_path = os.path.join(out_dir, name + ".pdf")
                merged.save(pdf_path)
                merged.close()
                out["pdf"] = pdf_path
            except Exception:
                out["pdf"] = pdf_files[0]
    except Exception as exc:
        out["error"] = f"verovio failed: {exc}"
    return out


def ascii_tab(part, tm, beats_per_bar: int = 4, bars_per_line: int = 4) -> str:
    """Render ASCII tablature: one column per sixteenth note, 6 string lines."""
    names = ["e", "B", "G", "D", "A", "E"]
    if not part.events:
        return "(no notes)"
    total_ticks = max(e.start + e.dur for e in part.events)
    step = DIVISIONS // 4  # sixteenth note
    n_cols = int(total_ticks // step) + 1
    cols_per_bar = beats_per_bar * 4
    per_line = cols_per_bar * bars_per_line
    cells = [[["---"] for _ in range(n_cols)] for _ in range(6)]
    for ev in sorted(part.events, key=lambda e: e.start):
        col = int(round(ev.start / step))
        if not (0 <= col < n_cols):
            continue
        for (string, fret) in (ev.string_frets or []):
            row = int(string) - 1
            if not (0 <= row < 6):
                continue
            cells[row][col].append(f"{int(fret):>2}".replace(" ", "-") + "-")
    out = []
    for start in range(0, n_cols, per_line):
        end = min(start + per_line, n_cols)
        for r in range(6):
            body = ""
            for c in range(start, end):
                cell = cells[r][c]
                body += cell[-1] if len(cell) == 1 else max(cell[1:], key=len)
                if (c + 1) % cols_per_bar == 0 and c + 1 < end:
                    body += "|"
            out.append(f"{names[r]}|{body}|")
        out.append("")
    return "\n".join(out)