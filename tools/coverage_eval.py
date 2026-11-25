"""Per-bar pitch-class coverage of a reference score by different stem fusions."""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import numpy as np
import xml.etree.ElementTree as ET
from collections import defaultdict
from pianoforge import audio_io, analysis, neural, separate, pipeline

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEMI = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def load_ref(path):
    root = ET.parse(path).getroot()
    bars = defaultdict(set)
    for part in root.iter("part"):
        for mi, measure in enumerate(part.iter("measure")):
            for note in measure.iter("note"):
                if note.find("rest") is not None:
                    continue
                p = note.find("pitch")
                if p is None:
                    continue
                step = p.find("step").text
                octv = int(p.find("octave").text)
                alt = p.find("alter")
                bars[mi].add(12 * (octv + 1) + SEMI[step] + (int(alt.text) if alt is not None else 0))
    return bars


def transcribe_sig(y, sr=22050):
    h, _ = analysis.hpss(y, sr)
    return neural.transcribe(h, sr)


def bars_of(notes, bpm):
    beat = 60.0 / bpm
    bars = defaultdict(set)
    for n in notes:
        bars[int(n["start"] / (4 * beat))].add(int(n["pitch"]) % 12)
    return bars


def coverage(cand_bars, ref_bars, offset=0):
    hits = tot = 0
    for i, r in ref_bars.items():
        c = cand_bars.get(i + offset, set())
        for p in {p % 12 for p in r}:
            tot += 1
            if p in c:
                hits += 1
    return hits / max(1, tot)


song = sys.argv[1]
ref_name = sys.argv[2]
bpm = float(sys.argv[3])
audio = song
ref = load_ref(os.path.join(ROOT, "cache", "omr", "out", ref_name + ".musicxml"))

name = sys.argv[4] if len(sys.argv) > 4 else ""
stems4 = os.path.join(ROOT, "cache", "stems", name) if name else ""
stems6 = os.path.join(ROOT, "cache", "stems6", name) if name else ""

ya, sr = audio_io.load_audio(audio, sr=22050)

def load_stems(d, keys):
    out = {}
    for k in keys:
        p = os.path.join(d, k + ".wav")
        if os.path.exists(p):
            y, _ = audio_io.load_audio(p, sr=22050)
            out[k] = y
    return out

s4 = load_stems(stems4, ["other", "vocals", "bass", "drums"])
print("4-stem available:", list(s4))
s6 = load_stems(stems6, ["piano", "other", "bass", "guitar"])
print("6-stem available:", list(s6))

variants = {}
if s4:
    mix4 = s4["other"] + 0.6 * s4.get("vocals", 0) + 0.5 * s4["bass"]
    variants["4stem mix"] = transcribe_sig(mix4)
    variants["4stem per-stem"] = (transcribe_sig(s4["other"]) + transcribe_sig(s4["bass"]) +
                                  transcribe_sig(s4["vocals"]))
if s6:
    variants["6stem piano+other+bass"] = (transcribe_sig(s6["piano"]) + transcribe_sig(s6["other"]) +
                                          transcribe_sig(s6["bass"]))
if s4 and s6:
    variants["union 4+6"] = (transcribe_sig(s4["other"]) + transcribe_sig(s4["bass"]) +
                             transcribe_sig(s6["piano"]) + transcribe_sig(s6["other"]))
    # maximise recall: loose thresholds on the full harmonic mix as well
    mix_all = s4["other"] + 0.6 * s4.get("vocals", 0) + 0.5 * s4["bass"] + 0.8 * s6["piano"]
    h, _ = analysis.hpss(mix_all, 22050)
    loose = neural.transcribe(h, 22050, onset_thresh=0.32, note_thresh=0.18, min_len=0.05)
    variants["union + loose"] = (transcribe_sig(s4["other"]) + transcribe_sig(s4["bass"]) +
                                 transcribe_sig(s6["piano"]) + transcribe_sig(s6["other"]) + loose)
    pn = neural.transcribe(s6["piano"], 22050, onset_thresh=0.3, note_thresh=0.15, min_len=0.04)
    variants["union + loose + piano-loose"] = (transcribe_sig(s4["other"]) + transcribe_sig(s4["bass"]) +
                                               transcribe_sig(s6["other"]) + loose + pn)

for label, notes in variants.items():
    b = bars_of(notes, bpm)
    best = max(range(-3, 4), key=lambda o: coverage(b, ref, o))
    print(f"{label:26s} notes={len(notes):5d} coverage={coverage(b, ref, best):.3f} offset={best}")
