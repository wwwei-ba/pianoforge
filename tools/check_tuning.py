"""Is the rendered piano actually in tune with the requested MIDI notes?"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import numpy as np
import librosa
from pianoforge import samples

ok = samples.load_bank()
print("bank loaded:", bool(ok), " entries:", len(getattr(samples, "BANK", {}) or {}))

def measure(pitch, sr=22050):
    ev = [{"start": 0.0, "end": 1.6, "pitch": pitch, "velocity": 0.8}]
    y = samples.render_notes(ev, 1.8, sr=sr)
    seg = y[int(0.15 * sr): int(1.2 * sr)]
    if not np.any(seg):
        return None
    f0 = librosa.yin(seg.astype(np.float32), fmin=50, fmax=2000, sr=sr)
    f0 = f0[np.isfinite(f0)]
    med = float(np.median(f0))
    want = float(librosa.midi_to_hz(pitch))
    cents = 1200 * np.log2(med / want)
    return med, want, cents

print(f"{'midi':>5} {'measured':>9} {'expected':>9} {'cents':>7}")
for p in [36, 48, 55, 60, 64, 67, 72, 76, 79, 84, 88, 91, 96]:
    r = measure(p)
    if r:
        med, want, cents = r
        print(f"{p:5d} {med:9.2f} {want:9.2f} {cents:+7.1f}")
    else:
        print(f"{p:5d} (no sound)")
