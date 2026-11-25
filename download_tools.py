"""Background downloads with resume + retry (host network is slow)."""
import json
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
DL = os.path.join(ROOT, "dl")
os.makedirs(DL, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def size_of(path):
    return os.path.getsize(path) if os.path.exists(path) else 0


def download(url, dest, min_bytes=0, retries=8):
    part = dest + ".part"
    for attempt in range(retries):
        try:
            have = size_of(part)
            headers = dict(UA)
            if have:
                headers["Range"] = f"bytes={have}-"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as r:
                total = int(r.headers.get("Content-Length") or 0) + (have if r.status == 206 else 0)
                mode = "ab" if r.status == 206 else "wb"
                with open(part, mode) as f:
                    last = time.time()
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
                        if time.time() - last > 10:
                            last = time.time()
                            log(f"  {dest}: {size_of(part)/1e6:.1f}/{total/1e6:.1f} MB")
            if total and size_of(part) < total:
                raise IOError(f"incomplete {size_of(part)}/{total}")
            if size_of(part) < min_bytes:
                raise IOError(f"too small: {size_of(part)}")
            os.replace(part, dest)
            log(f"OK {dest} {size_of(dest)/1e6:.1f} MB")
            return True
        except Exception as e:
            log(f"  retry {attempt+1}/{retries} {type(e).__name__}: {str(e)[:100]}")
            time.sleep(2)
    return False


def latest_asset(repo, pattern):
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/releases/latest", headers=UA)
    data = json.load(urllib.request.urlopen(req, timeout=30))
    for a in data.get("assets", []):
        if pattern in a["name"]:
            return a["name"], a["browser_download_url"]
    return None, None


def main():
    jobs = []
    jobs.append(("ffmpeg", "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
                 os.path.join(DL, "ffmpeg.zip"), 50_000_000))
    name, url = latest_asset("FluidSynth/fluidsynth", "win10-x64.zip")
    log(f"fluidsynth asset: {name}")
    if url:
        jobs.append(("fluidsynth", url, os.path.join(DL, "fluidsynth.zip"), 5_000_000))
    jobs.append(("generaluser", "https://github.com/mrbumpy409/GeneralUser-GS/raw/main/GeneralUser-GS.sf2",
                 os.path.join(ROOT, "bin", "soundfonts", "GeneralUser-GS.sf2"), 10_000_000))
    for label, url, dest, minb in jobs:
        if size_of(dest) >= minb:
            log(f"skip {label} (already {size_of(dest)/1e6:.1f} MB)")
            continue
        log(f"downloading {label} -> {dest}")
        download(url, dest, minb)
    log("ALL DOWNLOADS DONE")


if __name__ == "__main__":
    main()
