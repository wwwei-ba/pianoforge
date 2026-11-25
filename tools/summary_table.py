import json, os
ROOT = r"D:\deepfile\pianoforge"
rows = []
for name in sorted(os.listdir(os.path.join(ROOT, "out"))):
    p = os.path.join(ROOT, "out", name, "_analysis", "report.json")
    if not os.path.exists(p):
        continue
    d = json.load(open(p, encoding="utf-8"))
    m = d.get("metrics", {})
    sc = d.get("selfcheck", {})
    rows.append((name, round(float(m.get("chroma_similarity", 0)), 4),
                 round(float(m.get("melody_pitch_exact_pct", 0)), 1),
                 round(float(m.get("score_note_recall_pct", 0)), 1),
                 d.get("elapsed_sec"), sc.get("musicxml"), sc.get("audio_rms")))
print(f"{'song':<38}{'chroma':>8}{'melody':>8}{'recall':>8}{'sec':>7}  selfcheck")
for r in rows:
    print(f"{r[0][:36]:<38}{r[1]:>8.4f}{r[2]:>8.1f}{r[3]:>8.1f}{r[4]:>7}{'  OK' if r[5] else '  FAIL'} rms={r[6]}")
