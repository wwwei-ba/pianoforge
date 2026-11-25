"""Download the optional binary assets (piano samples).

Neither weights nor samples are committed to this repository:

  bin/samples/piano_mp3/*.mp3  FluidR3_GM piano (MIDI.js naming: C4.mp3, A1.mp3)
  bin/models/nmp.onnx          Basic Pitch ONNX export

Without them the app still runs: it falls back to the built-in synthesiser and
to the classical DSP transcriber.

    python tools/fetch_assets.py            # samples only
    python tools/fetch_assets.py --check    # report what is missing
"""
from __future__ import annotations

import io
import os
import sys
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE_DIR = os.path.join(ROOT, "bin", "samples", "piano_mp3")
MODEL = os.path.join(ROOT, "bin", "models", "nmp.onnx")

SOUNDFONT = ("https://github.com/gleitz/midi-js-soundfonts/raw/gh-pages/"
             "FluidR3_GM/acoustic_grand_piano-mp3.zip")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def check() -> int:
    have = len([f for f in os.listdir(SAMPLE_DIR) if f.endswith(".mp3")]) \
        if os.path.isdir(SAMPLE_DIR) else 0
    print(f"piano samples : {have} files  ({SAMPLE_DIR})")
    print(f"basic pitch   : {'present' if os.path.exists(MODEL) else 'missing'}  ({MODEL})")
    return 0 if have and os.path.exists(MODEL) else 1


def fetch_samples() -> None:
    if os.path.isdir(SAMPLE_DIR) and len([f for f in os.listdir(SAMPLE_DIR)
                                          if f.endswith(".mp3")]) >= 80:
        print("samples already present ->", SAMPLE_DIR)
        return
    os.makedirs(SAMPLE_DIR, exist_ok=True)
    print("downloading", SOUNDFONT)
    req = urllib.request.Request(SOUNDFONT, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    print(f"  {len(data) / 1e6:.1f} MB")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".mp3")]
        print(f"  {len(names)} mp3 files")
        for n in names:
            base = os.path.basename(n)
            with z.open(n) as src, open(os.path.join(SAMPLE_DIR, base), "wb") as dst:
                dst.write(src.read())
    print("samples ->", SAMPLE_DIR)


def main() -> int:
    if "--check" in sys.argv:
        return check()
    try:
        fetch_samples()
    except Exception as exc:
        print("download failed:", exc)
        print("the app still runs, using the built-in synthesiser")
    if not os.path.exists(MODEL):
        print()
        print("Basic Pitch ONNX model not found. Export the official Spotify")
        print("basic-pitch model and save it as:", MODEL)
        print("Without it the classical DSP transcriber is used.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
