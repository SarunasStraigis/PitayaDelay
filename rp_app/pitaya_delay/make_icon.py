#!/usr/bin/env python3
"""Write the menu icons. No third-party dependencies."""

import os
import struct
import zlib

ROOT = os.path.dirname(os.path.abspath(__file__))


def png(width, height, pixel):
    rows = []
    for y in range(height):
        row = bytearray(b"\x00")
        for x in range(width):
            row.extend(pixel(x, y, width, height))
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag, data):
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def pixel(x, y, width, height):
    nx = x / (width - 1)
    ny = y / (height - 1)
    bg = (18, 22, 28, 255)
    # Rounded dark tile.
    inset = 0.08
    if nx < inset or nx > 1 - inset or ny < inset or ny > 1 - inset:
        return bg
    # Two traces: a step (held DAC) and a thinner reference.
    mid = 0.62
    step = 0.38 if nx < 0.48 else 0.58
    trace = abs(ny - step) < 0.035
    axis = abs(ny - mid) < 0.012 and 0.16 < nx < 0.84
    if trace:
        return (109, 190, 122, 255)
    if axis:
        return (60, 70, 82, 255)
    return (24, 30, 38, 255)


def write(path, size):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(png(size, size, pixel))


def main():
    write(os.path.join(ROOT, "icon.png"), 256)
    write(os.path.join(ROOT, "info", "icon.png"), 256)
    for size in (128, 256, 512):
        write(os.path.join(ROOT, "info", "icon", "%d.png" % size), size)


if __name__ == "__main__":
    main()
