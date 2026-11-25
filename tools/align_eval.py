"""Time-aligned pitch/rhythm agreement between a rendered piano track and the original."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import numpy as np
import librosa
import soundfile as sf
from pianoforge import audio_io

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SONG = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "out", "fukashigi_lofi")
ORIG = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "samples", "ref", "fukashigi_lofi.ogg")

y_o, sr = audio_io.load_audio(ORIG, sr=22050)
y_p, _ = sf.read(os.path.join(SONG, "piano.wav"), dtype="float32", always_2d=False)
if y_p.ndim > 1:
    y_p = y_p.mean(axis=1)
y_p = librosa.resample(y_p, orig_sr=44100, target_sr=22050)
n = min(len(y_o), len(y_p))
y_o, y_p = y_o[:n], y_p[:n]

hop = 512
def chroma(y):
    c = librosa.feature.chroma_cqt(y=y.astype(np.float32), sr=22050, hop_length=hop)
    return c / (np.linalg.norm(c, axis=0, keepdims=True) + 1e-9)

co, cp = chroma(y_o), chroma(y_p)
def pcs(vec, k=3, thr=0.25):
    idx = np.argsort(-vec)[:k]
    return {int(i) for i in idx if vec[i] > thr}

# per-frame pitch-class F1
f1s = []
for i in range(co.shape[1]):
    a, b = pcs(co[:, i]), pcs(cp[:, i])
    if not a and not b:
        continue
    tp = len(a & b)
    f1s.append(2 * tp / (len(a) + len(b)) if (a or b) else 0.0)
f1s = np.array(f1s)

# onsets
oe_o = librosa.onset.onset_detect(y=y_o, sr=22050, hop_length=hop, units="time")
oe_p = librosa.onset.onset_detect(y=y_p, sr=22050, hop_length=hop, units="time")
def onset_pr(a, b, tol=0.06):
    used = set(); tp = 0
    for t in a:
        for j, u in enumerate(b):
            if j in used:
                continue
            if abs(u - t) <= tol:
                used.add(j); tp += 1; break
    p = tp / max(1, len(a)); r = tp / max(1, len(b))
    return p, r, 2 * p * r / max(1e-9, p + r)

print(f"frames={len(f1s)} mean pitch-class F1={f1s.mean():.4f}")
print("onset P/R/F1 = %.3f / %.3f / %.3f (orig %d, piano %d)" %
      (*onset_pr(oe_o, oe_p), len(oe_o), len(oe_p)))

# per-10s detail
fps = 22050 / hop
print("\n window   pitchF1")
worst = []
for t0 in range(0, int(n / 22050), 10):
    i0, i1 = int(t0 * fps), int((t0 + 10) * fps)
    seg = f1s[i0:i1]
    if len(seg) == 0:
        continue
    m = float(seg.mean())
    worst.append((m, t0))
    if t0 >= 100:
        flag = "  <-- 2-6min" if 120 <= t0 < 360 else ""
        print(f"{t0:6d}s  {m:.3f}{flag}")
worst.sort()
print("\nworst windows:", [(t, round(m, 3)) for m, t in worst[:8]])
