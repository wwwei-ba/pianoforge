import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from pianoforge import separate

audio, name = sys.argv[1], sys.argv[2]
out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache", "stems6", name)
stems = separate.separate_file(audio, sr=44100, model_name="htdemucs_6s")
separate.save_stems(stems, out)
print("saved", list(stems), "->", out)
