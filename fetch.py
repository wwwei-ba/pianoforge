"""Download helper that works around the host's PowerShell TLS problems."""
import os
import sys
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def fetch(url: str, dest: str) -> None:
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    tmp = dest + ".part"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r{done/1e6:.1f}/{total/1e6:.1f} MB", end="", flush=True)
    os.replace(tmp, dest)
    print(f"\nOK {dest} {os.path.getsize(dest)} bytes")


if __name__ == "__main__":
    fetch(sys.argv[1], sys.argv[2])
