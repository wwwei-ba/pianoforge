"""Every output audio must be exactly as long as its input."""
import json, os
import soundfile as sf

ROOT = r"D:\deepfile\pianoforge"
bad = 0
print(f"{'song':40s}{'input':>9}{'wav':>9}{'diff':>8}  ok")
for name in sorted(os.listdir(os.path.join(ROOT, "out"))):
    d = os.path.join(ROOT, "out", name)
    rep = os.path.join(d, "_analysis", "report.json")
    wav = os.path.join(d, "piano.wav")
    if not (os.path.exists(rep) and os.path.exists(wav)):
        continue
    dur = json.load(open(rep, encoding="utf-8"))["duration_sec"]
    got = sf.info(wav).duration
    diff = got - dur
    ok = abs(diff) < 0.05
    if not ok:
        bad += 1
    print(f"{name[:38]:40s}{dur:9.2f}{got:9.2f}{diff:+8.2f}  {'OK' if ok else 'FAIL'}")
print("mismatched:", bad)
