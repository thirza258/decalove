"""A tiny dependency-free PNG encoder.

Used to synthesise deterministic placeholder art so the whole image pipeline -- prompt
building, cache keys, storage, URL resolution, Ren'Py display -- can be exercised with no
API key and no image model. Pillow would be a heavier dependency for something this small.
"""

from __future__ import annotations

import hashlib
import struct
import zlib


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def encode_png(width: int, height: int, rgb_rows: list[bytes]) -> bytes:
    """Encode 8-bit RGB scanlines (``width * 3`` bytes each) as a PNG."""
    if len(rgb_rows) != height:
        raise ValueError(f"expected {height} rows, got {len(rgb_rows)}")
    raw = b"".join(b"\x00" + row for row in rgb_rows)  # filter type 0 per scanline
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(raw, 6))
        + _chunk(b"IEND", b"")
    )


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    text = value.lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6:
        return (120, 120, 120)
    return tuple(int(text[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def gradient_png(
    width: int,
    height: int,
    top: str,
    bottom: str,
    *,
    seed: str = "",
    grain: int = 10,
) -> bytes:
    """A vertical gradient with reproducible grain, keyed by ``seed``.

    The grain exists so two different scenes never produce byte-identical files, which
    would make the asset cache look like it was working when it was not.
    """
    r0, g0, b0 = _hex_to_rgb(top)
    r1, g1, b1 = _hex_to_rgb(bottom)
    digest = hashlib.blake2b(seed.encode("utf-8"), digest_size=32).digest()

    rows: list[bytes] = []
    for y in range(height):
        t = y / max(1, height - 1)
        base_r = int(r0 + (r1 - r0) * t)
        base_g = int(g0 + (g1 - g0) * t)
        base_b = int(b0 + (b1 - b0) * t)
        row = bytearray()
        for x in range(width):
            jitter = digest[(x * 7 + y * 13) % 32] % (grain * 2 + 1) - grain if grain else 0
            row += bytes(
                (
                    max(0, min(255, base_r + jitter)),
                    max(0, min(255, base_g + jitter)),
                    max(0, min(255, base_b + jitter)),
                )
            )
        rows.append(bytes(row))
    return encode_png(width, height, rows)
