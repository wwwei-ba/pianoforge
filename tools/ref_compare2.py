"""Reference comparison with bar-offset search."""
import json, os, sys
import xml.etree.ElementTree as ET

SEMI = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def load_generated(out_dir):
    d = json.load(open(os.path.join(out_dir, "_analysis", "parts.json"), encoding="utf-8"))
    tick = 60.0 / d["bpm"] / 480.0
    beat = 60.0 / d["bpm"]
    bars = {}
    for e in d["tracks"][0]["events"]:
        t = e["start"] * tick
        bar = int(t / (4 * beat))
        bars.setdefault(bar, set()).update(int(p) for p in e["pitches"])
    return bars


def load_ref(path):
    root = ET.parse(path).getroot()
    bars = {}
    for part in root.iter("part"):
        for mi, measure in enumerate(part.iter("measure")):
            s = bars.setdefault(mi, set())
            for note in measure.iter("note"):
                if note.find("rest") is not None:
                    continue
                p = note.find("pitch")
                if p is None:
                    continue
                step = p.find("step").text
                octv = int(p.find("octave").text)
                alt = p.find("alter")
                s.add(12 * (octv + 1) + SEMI[step] + (int(alt.text) if alt is not None else 0))
    return bars


def score(gen, ref, off, use_class=False):
    sims = []
    for i in range(len(gen)):
        a, b = gen.get(i, set()), ref.get(i + off, set())
        if use_class:
            a = {p % 12 for p in a}
            b = {p % 12 for p in b}
        if not a and not b:
            continue
        sims.append(len(a & b) / len(a | b) if (a | b) else 1.0)
    return (sum(sims) / len(sims) if sims else 0.0), sims


gen = load_generated(sys.argv[1])
ref = load_ref(sys.argv[2])
print("ours bars:", len(gen), " ref bars:", len(ref))
best = None
for off in range(-12, 13):
    s, sims = score(gen, ref, off)
    hits = 100.0 * sum(1 for x in sims if x >= 0.8) / max(1, len(sims))
    if best is None or s > best[0]:
        best = (s, off, hits)
    if s > 0.3:
        print(f"  offset {off:+3d}: jaccard={s:.3f} bars>=0.8: {hits:.1f}%")
print("best offset %+d -> jaccard=%.3f, bars>=0.8=%.1f%%" % (best[1], best[0], best[2]))
bestc = max((score(gen, ref, off, True)[0], off) for off in range(-6, 7))
print("pitch-class jaccard (best offset %+d) = %.3f" % (bestc[1], bestc[0]))
