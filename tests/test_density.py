import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import numpy as np
from pianoforge import pipeline
from pianoforge.arrange import TimeMap
from pianoforge.musicxml import Event, Part

OUT = r"D:\deepfile\pianoforge\out\Keyboard 秒針を噛む咬住秒针"
d = json.load(open(os.path.join(OUT, "_analysis", "parts.json"), encoding="utf-8"))
tick = 60.0 / d["bpm"] / 480.0

part = Part(part_id="P1", name="Piano", staves=2, clefs=[("G", 2), ("F", 4)])
for e in d["tracks"][0]["events"]:
    part.events.append(Event(start=e["start"], dur=e["dur"], pitches=list(e["pitches"]),
                             staff=e["staff"], voice=e["voice"]))
tm = TimeMap(d["bpm"], t0=d["t0"])

def stats(label):
    beat = 60.0 / d["bpm"]
    bars = {}
    for ev in part.events:
        b = int((tm.sec(ev.start) - d["t0"]) / (4 * beat))
        bars.setdefault(b, set()).update(int(p) for p in ev.pitches)
    sizes = [len(v) for v in bars.values()]
    print(f"{label}: events={len(part.events)} mean_pitches/bar={np.mean(sizes):.1f}")

stats("before")
pipeline._clamp_bass(part, 40)
pipeline._limit_density(part, tm, budget=9)
stats("after")
