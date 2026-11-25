import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ref_compare2 import load_generated, load_ref

gen = load_generated(sys.argv[1])
ref = load_ref(sys.argv[2])
for i in range(0, 12):
    a, b = sorted(gen.get(i, set())), sorted(ref.get(i, set()))
    print(f"bar {i:3d}")
    print(f"   ours  {a}")
    print(f"   ref   {b}")
