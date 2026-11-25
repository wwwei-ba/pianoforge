"""Download the FluidR3_GM acoustic grand piano samples (MIDI.js set) via jsDelivr."""
import concurrent.futures
import os
import time
import urllib.request

ROOT = r"D:\deepfile\pianoforge"
OUT = os.path.join(ROOT, "bin", "samples", "piano_mp3")
UA = {"User-Agent": "Mozilla/5.0"}
BASE = ("https://cdn.jsdelivr.net/gh/gleitz/midi-js-soundfonts@gh-pages/"
        "FluidR3_GM/acoustic_grand_piano-mp3")
NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]


def note_names():
    out = []
    for octave in range(0, 9):
        for n in NAMES:
            if octave == 0 and n in ("A", "Bb", "B"):
                continue
            if octave == 8 and n not in ("C",):
                continue
            out.append(f"{n}{octave}")
    return out


def fetch(name):
    dest = os.path.join(OUT, name + ".mp3")
    if os.path.exists(dest) and os.path.getsize(dest) > 800:
        return name, "cached"
    for attempt in range(4):
        try:
            req = urllib.request.Request(f"{BASE}/{name}.mp3", headers=UA)
            data = urllib.request.urlopen(req, timeout=30).read()
            if len(data) < 500:
                raise IOError("too small")
            with open(dest, "wb") as f:
                f.write(data)
            return name, "ok"
        except Exception as exc:
            time.sleep(1 + attempt)
            err = exc
    return name, f"fail {type(err).__name__}"


def main():
    os.makedirs(OUT, exist_ok=True)
    names = note_names()
    print("notes to fetch:", len(names))
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        for i, (name, status) in enumerate(ex.map(fetch, names)):
            if status not in ("ok", "cached"):
                print(name, status)
    files = [f for f in os.listdir(OUT) if f.endswith(".mp3")]
    total = sum(os.path.getsize(os.path.join(OUT, f)) for f in files)
    print(f"done: {len(files)} files, {total/1e6:.2f} MB")


if __name__ == "__main__":
    main()
