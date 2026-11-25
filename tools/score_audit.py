"""Musical sanity audit of a generated score."""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "out", "fukashigi_lofi")

d = json.load(open(os.path.join(OUT, "_analysis", "parts.json"), encoding="utf-8"))
tick = 60.0 / d["bpm"] / 480.0
events = d["tracks"][0]["events"]
for e in events:
    e["t"] = d["t0"] + e["start"] * tick
    e["end_t"] = e["t"] + e["dur"] * tick

print("events:", len(events), " duration:", round(max(e["end_t"] for e in events), 1), "s")

# 1. duplicate pitches sounding at the same time (doubling = louder, honky)
def active_at(t):
    return [e for e in events if e["t"] <= t < e["end_t"]]

times = [round(d["t0"] + i * 0.25, 2) for i in range(int(72 / 0.25))]
dups = 0
cross = 0
clash = 0
for t in times:
    act = active_at(t)
    pitches = []
    for e in act:
        pitches.extend(e["pitches"])
    if len(pitches) != len(set(pitches)):
        dups += 1
    mel = [p for e in act if e["staff"] == 1 and e["voice"] == 1 for p in e["pitches"]]
    if mel:
        top = max(mel)
        others = [p for e in act if not (e["staff"] == 1 and e["voice"] == 1) for p in e["pitches"]]
        if any(p > top for p in others):
            cross += 1
        if any(abs(p - top) in (1, 11) for p in others):
            clash += 1
print(f"frames with duplicated pitches: {dups}/{len(times)}")
print(f"frames where accompaniment is above the melody (voice crossing): {cross}/{len(times)}")
print(f"frames with a semitone clash against the melody: {clash}/{len(times)}")

# 2. density and range
per_frame = [len(active_at(t)) for t in times]
print("notes sounding per 0.25s: mean %.1f max %d" % (sum(per_frame) / len(per_frame), max(per_frame)))
allp = [p for e in events for p in e["pitches"]]
print("pitch range:", min(allp), max(allp))

# 3. zero/negative durations, identical overlapping events
bad = [e for e in events if e["dur"] <= 0]
print("zero-length events:", len(bad))
same = 0
for i in range(len(events) - 1):
    a, b = events[i], events[i + 1]
    if a["staff"] == b["staff"] and a["voice"] == b["voice"] and a["start"] == b["start"]:
        if set(a["pitches"]) & set(b["pitches"]):
            same += 1
print("same-start duplicate events in one voice:", same)

# 4. melody statistics
mel = [e for e in events if e["staff"] == 1 and e["voice"] == 1]
if len(mel) > 1:
    mel.sort(key=lambda e: e["t"])
    leaps = []
    for a, b in zip(mel, mel[1:]):
        if abs(b["t"] - a["end_t"]) < 0.05:
            leaps.append(abs(b["pitches"][0] - a["pitches"][0]))
    if leaps:
        print("melody intervals: mean %.1f semitones, max %d, leaps>12: %d" %
              (sum(leaps) / len(leaps), max(leaps), sum(1 for x in leaps if x > 12)))
