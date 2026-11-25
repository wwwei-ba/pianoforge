"""Move older song folders to the four-file layout."""
import json, os, shutil, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out")

RENAMES = {
    "piano.wav": "audio.wav",
    "score_piano.pdf": "piano.pdf",
    "score_guitar_tab.pdf": "guitar.pdf",
}
INTO_ANALYSIS = ("piano.mid", "piano.ogg", "tab.txt", "score_piano.musicxml",
                 "score_guitar_tab.musicxml", "piano.musicxml", "guitar.musicxml",
                 "chords.txt", "verification.png")

moved = 0
for name in sorted(os.listdir(OUT)):
    d = os.path.join(OUT, name)
    if not os.path.isdir(d):
        continue
    ana = os.path.join(d, "_analysis")
    os.makedirs(ana, exist_ok=True)
    for src, dst in RENAMES.items():
        p = os.path.join(d, src)
        if os.path.exists(p) and not os.path.exists(os.path.join(d, dst)):
            shutil.move(p, os.path.join(d, dst))
            moved += 1
    for f in INTO_ANALYSIS:
        p = os.path.join(d, f)
        if os.path.exists(p):
            shutil.move(p, os.path.join(ana, f))
            moved += 1
    # keep a copy of the source audio next to the score
    rep = os.path.join(ana, "report.json")
    if os.path.exists(rep) and not any(x.lower().startswith("original.")
                                       for x in os.listdir(d)):
        try:
            data = json.load(open(rep, encoding="utf-8"))
            src = data.get("input")
            if src and os.path.exists(src):
                ext = os.path.splitext(src)[1].lower() or ".audio"
                shutil.copyfile(src, os.path.join(d, "original" + ext))
                moved += 1
        except Exception:
            pass
    # fix report paths that still point at the old names
    if os.path.exists(rep):
        try:
            data = json.load(open(rep, encoding="utf-8"))
            outs = data.get("outputs", {})
            for key, new in (("piano_wav", "audio.wav"), ("piano_pdf", "piano.pdf"),
                             ("guitar_pdf", "guitar.pdf")):
                p = os.path.join(d, new)
                if os.path.exists(p):
                    outs[key] = p
            data["outputs"] = outs
            with open(rep, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=1)
        except Exception:
            pass
    print(name, "->", sorted(x for x in os.listdir(d)))
print("moved", moved)
