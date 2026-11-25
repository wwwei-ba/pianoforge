"""Draw the PianoForge app icon from scratch (no third-party artwork).

Everything here is generated with PIL primitives: a rounded slab, a five-line
staff, a piano keyboard and a rising melody curve that ends in a note head.
Rendered at 1024 px, then downsampled into a multi-resolution .ico.
"""
from __future__ import annotations

import io
import os
import struct

from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
os.makedirs(ASSETS, exist_ok=True)

S = 1024
RADIUS = 224          # squircle corner radius


def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def vertical_gradient(size, top, bottom):
    w, h = size
    img = Image.new("RGB", (1, h))
    px = img.load()
    for y in range(h):
        px[0, y] = lerp(top, bottom, y / max(1, h - 1))
    return img.resize((w, h), Image.BILINEAR)


def radial_glow(size, center, radius, color, strength=1.0):
    w, h = size
    layer = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(layer)
    steps = 60
    for i in range(steps, 0, -1):
        t = i / steps
        r = radius * t
        alpha = int(255 * strength * (1 - t) ** 2)
        d.ellipse([center[0] - r, center[1] - r, center[0] + r, center[1] + r], fill=alpha)
    glow = Image.new("RGBA", (w, h), color + (0,))
    glow.putalpha(layer)
    return glow


def bezier(p0, p1, p2, p3, n=260):
    pts = []
    for i in range(n + 1):
        t = i / n
        mt = 1 - t
        x = (mt ** 3) * p0[0] + 3 * (mt ** 2) * t * p1[0] + 3 * mt * (t ** 2) * p2[0] + (t ** 3) * p3[0]
        y = (mt ** 3) * p0[1] + 3 * (mt ** 2) * t * p1[1] + 3 * mt * (t ** 2) * p2[1] + (t ** 3) * p3[1]
        pts.append((x, y))
    return pts


def draw_curve(draw, pts, width, c0, c1):
    """Solid gradient stroke: overlapping discs avoid gaps and colour banding."""
    n = len(pts)
    r = width / 2.0
    for i, (x, y) in enumerate(pts):
        t = i / max(1, n - 1)
        col = lerp(c0, c1, t)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=col + (255,))


def rounded_mask(size, radius):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255)
    return m


def build_master():
    bg = vertical_gradient((S, S), (34, 40, 74), (82, 46, 122)).convert("RGBA")
    # soft highlight
    bg = Image.alpha_composite(bg, radial_glow((S, S), (300, 240), 620, (120, 200, 255), 0.45))
    bg = Image.alpha_composite(bg, radial_glow((S, S), (820, 780), 520, (255, 190, 120), 0.18))

    d = ImageDraw.Draw(bg, "RGBA")

    # ---- five staff lines under everything ---------------------------------
    staff_top, staff_gap = 250, 62
    for i in range(5):
        y = staff_top + i * staff_gap
        d.line([(120, y), (904, y)], fill=(255, 255, 255, 34), width=6)

    # ---- piano keyboard band -----------------------------------------------
    kb_left, kb_right = 112, 912
    kb_top, kb_bottom = 646, 868
    n_white = 10
    key_w = (kb_right - kb_left) / n_white
    # shadow under the keyboard
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle([kb_left - 10, kb_top + 18, kb_right + 10, kb_bottom + 26],
                         radius=34, fill=(0, 0, 0, 90))
    shadow = shadow.filter(ImageFilter.GaussianBlur(22))
    bg = Image.alpha_composite(bg, shadow)
    d = ImageDraw.Draw(bg, "RGBA")

    d.rounded_rectangle([kb_left, kb_top, kb_right, kb_bottom], radius=28, fill=(12, 15, 26, 255))
    for i in range(n_white):
        x0 = kb_left + 10 + i * (key_w - 0.0) + 3
        x1 = kb_left + 10 + (i + 1) * key_w - 6
        if x1 > kb_right - 8:
            x1 = kb_right - 8
        d.rounded_rectangle([x0, kb_top + 10, x1, kb_bottom - 10], radius=10,
                            fill=(246, 241, 230, 255))
        # subtle shading between keys
        d.line([(x1, kb_top + 14), (x1, kb_bottom - 14)], fill=(206, 198, 183, 255), width=3)

    black_pattern = [0, 1, 0, 1, 0, 0, 1, 0, 1, 0]
    for i in range(n_white):
        if not black_pattern[i % 10]:
            continue
        cx = kb_left + 10 + (i + 1) * key_w - 6
        d.rounded_rectangle([cx - 19, kb_top + 10, cx + 19, kb_top + 10 + 118], radius=8,
                            fill=(17, 20, 30, 255))
        d.rounded_rectangle([cx - 13, kb_top + 18, cx + 13, kb_top + 92], radius=6,
                            fill=(30, 35, 52, 255))

    # ---- melody curve -------------------------------------------------------
    pts = bezier((168, 604), (352, 596), (556, 438), (792, 350))
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow, "RGBA")
    draw_curve(gd, pts, 46, (94, 231, 255), (255, 209, 102))
    glow = glow.filter(ImageFilter.GaussianBlur(26))
    bg = Image.alpha_composite(bg, glow)
    d = ImageDraw.Draw(bg, "RGBA")
    draw_curve(d, pts, 30, (94, 231, 255), (255, 209, 102))

    # ---- note head + stem + flag -------------------------------------------
    head = Image.new("RGBA", (150, 120), (0, 0, 0, 0))
    hd = ImageDraw.Draw(head)
    hd.ellipse([4, 24, 138, 112], fill=(255, 214, 120, 255))
    head = head.rotate(-22, resample=Image.BICUBIC, expand=True)
    bg.alpha_composite(head, (792 - 42, 350 - 48))
    d = ImageDraw.Draw(bg, "RGBA")
    d.line([(858, 366), (858, 188)], fill=(255, 214, 120, 255), width=18)
    d.line([(858, 188), (936, 236)], fill=(255, 214, 120, 255), width=18, joint="curve")

    # ---- inner rim ----------------------------------------------------------
    mask = rounded_mask((S, S), RADIUS)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(bg, (0, 0), mask)

    rim = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    rd = ImageDraw.Draw(rim)
    rd.rounded_rectangle([6, 6, S - 7, S - 7], radius=RADIUS - 4,
                         outline=(255, 255, 255, 60), width=8)
    rim.putalpha(Image.composite(rim.split()[3], Image.new("L", (S, S), 0), mask))
    out = Image.alpha_composite(out, rim)
    return out


def _dib_entry(img: Image.Image) -> bytes:
    """32-bit bottom-up DIB + AND mask, the layout Explorer expects in an .ico."""
    w, h = img.size
    rgba = img.convert("RGBA")
    px = rgba.load()
    xor = bytearray()
    for y in range(h - 1, -1, -1):
        row = bytearray()
        for x in range(w):
            r, g, b, a = px[x, y]
            row += bytes((b, g, r, a))
        xor += row
    # AND mask: 1 bit per pixel, rows padded to 32 bits
    stride = ((w + 31) // 32) * 4
    and_mask = bytearray()
    for y in range(h - 1, -1, -1):
        row = bytearray(stride)
        for x in range(w):
            if px[x, y][3] == 0:
                row[x // 8] |= 0x80 >> (x % 8)
        and_mask += row
    header = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, len(xor), 0, 0, 0, 0)
    return header + bytes(xor) + bytes(and_mask)


def write_ico(master: Image.Image, path: str, sizes=(16, 24, 32, 40, 48, 64, 96, 128, 256)):
    """Write a Windows .ico with BMP(DIB) entries only, smallest first.

    PNG-compressed entries (which Pillow writes for large sizes) are rejected by
    the shell's shortcut-icon loader, so everything stays in DIB form here.
    """
    entries = []
    for s in sizes:
        img = master.resize((s, s), Image.LANCZOS)
        entries.append((s, _dib_entry(img)))
    header = struct.pack("<HHH", 0, 1, len(entries))
    offset = 6 + 16 * len(entries)
    directory = b""
    blob = b""
    for s, data in entries:
        directory += struct.pack("<BBBBHHII", s if s < 256 else 0, s if s < 256 else 0,
                                 0, 0, 1, 32, len(data), offset)
        blob += data
        offset += len(data)
    with open(path, "wb") as f:
        f.write(header + directory + blob)


def main():
    master = build_master()
    png = os.path.join(ASSETS, "pianoforge_icon.png")
    master.resize((512, 512), Image.LANCZOS).save(png)
    ico = os.path.join(ASSETS, "pianoforge.ico")
    write_ico(master, ico)
    print("wrote", png, os.path.getsize(png))
    print("wrote", ico, os.path.getsize(ico))


if __name__ == "__main__":
    main()
