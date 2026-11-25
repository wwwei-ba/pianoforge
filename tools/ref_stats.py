import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ref_compare2 import load_generated, load_ref
import numpy as np

ref = load_ref(sys.argv[2])
gen = load_generated(sys.argv[1])

def stats(bars, label):
    sizes = [len(b) for b in bars.values() if b]
    allp = [p for b in bars.values() for p in b]
    print(f"{label}: bars={len(bars)} mean_pitches/bar={np.mean(sizes):.1f} "
          f"max={max(sizes)} min_range={min(allp)} max_range={max(allp)}")
    low = sum(1 for p in allp if p < 40)
    print(f"   notes below MIDI 40: {low/len(allp)*100:.1f}%")

stats(gen, "ours")
stats(ref, "reference")
