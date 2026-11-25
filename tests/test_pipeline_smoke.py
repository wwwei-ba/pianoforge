"""End-to-end smoke test on a synthetic input: valid, non-silent output."""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import xml.etree.ElementTree as ET
import numpy as np
import soundfile as sf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from pianoforge import pipeline, synth

WORK = os.path.join(ROOT, "cache", "smoke")
os.makedirs(WORK, exist_ok=True)
SRC = os.path.join(WORK, "input.wav")
OUT = os.path.join(WORK, "out")

if not os.path.exists(SRC):
    # a short C - Am - F - G progression with a melody on top
    notes = []
    for bar, (root, third, fifth) in enumerate([(48, 52, 55), (45, 48, 52), (41, 45, 48), (43, 47, 50)]):
        t = bar * 2.0
        for p in (root, third, fifth):
            notes.append({"start": t, "end": t + 1.9, "pitch": p, "velocity": 0.5})
        for i, p in enumerate((72, 74, 76, 74)):
            notes.append({"start": t + i * 0.5, "end": t + i * 0.5 + 0.45, "pitch": p, "velocity": 0.85})
    y = synth.render_notes(notes, 8.4, sr=22050)
    sf.write(SRC, synth.normalize(y), 22050)

rep = pipeline.run(SRC, out_dir=OUT, use_separation=False, log=lambda m: None)

checks = []
ET.parse(rep["outputs"]["score_piano"])
checks.append(("musicxml parses", True))

wav, sr = sf.read(rep["outputs"]["piano_wav"], dtype="float32")
rms = float((wav ** 2).mean() ** 0.5)
checks.append(("audio non-silent", rms > 0.001))
checks.append(("audio length", abs(len(wav) / sr - rep["duration_sec"]) < 5))
checks.append(("pdf exists", os.path.exists(os.path.join(OUT, "score_piano.pdf"))))
checks.append(("selfcheck", bool(rep.get("selfcheck", {}).get("musicxml"))))

data = json.load(open(os.path.join(OUT, "_analysis", "report.json"), encoding="utf-8"))
checks.append(("report has timings", len(data.get("stage_seconds", {})) >= 3))

bad = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(("OK   " if ok else "FAIL ") + n)
print("problems:", len(bad))
sys.exit(1 if bad else 0)
