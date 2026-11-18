"""Generate the phone home-screen icons in icons/ (PNG, standard library only).

Run once after changing the design: python tools/make_icons.py
Design: slate square (the header colour) with three rising bars in the dashboard's
series colours, kept inside the central safe zone so the icon also works as "maskable".
"""
import os
import struct
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "icons")
BG = (0x1E, 0x29, 0x3B)
BARS = [((0x1E, 0x40, 0xAF), 0.40), ((0xDC, 0x26, 0x26), 0.58), ((0x16, 0xA3, 0x4A), 0.76)]  # repo, CPI, GDP
LINE = (0xC2, 0x41, 0x0C)  # accent


def render(n):
    px = [[BG] * n for _ in range(n)]
    safe0, safe1 = 0.22 * n, 0.78 * n          # inside the 80% maskable safe circle
    width = (safe1 - safe0) / len(BARS)
    base = safe1
    for i, (col, h) in enumerate(BARS):
        x0 = int(safe0 + i * width + width * 0.14)
        x1 = int(safe0 + (i + 1) * width - width * 0.14)
        y0 = int(base - h * (safe1 - safe0))
        for y in range(y0, int(base)):
            for x in range(x0, x1):
                px[y][x] = col
    t = max(2, n // 40)                        # accent baseline
    for y in range(int(base), int(base) + t):
        for x in range(int(safe0), int(safe1)):
            px[y][x] = LINE
    return px


def png(px):
    n = len(px)
    raw = b"".join(b"\x00" + bytes(c for p in row for c in p) for row in px)

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for size in (180, 192, 512):
        with open(os.path.join(OUT, f"icon-{size}.png"), "wb") as f:
            f.write(png(render(size)))
        print(f"icons/icon-{size}.png")
