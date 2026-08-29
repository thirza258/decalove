"""Transparent sprite background extraction — PRD §18/§26.

Converts character generation outputs into transparent PNGs with alpha channel
so character sprites cleanly overlay on backgrounds in the visual novel client.
"""

from __future__ import annotations

import io
import logging
from collections import deque

log = logging.getLogger(__name__)


def make_transparent_character_png(data: bytes, white_threshold: int = 235) -> bytes:
    """Take generated image bytes (JPEG/PNG) and remove solid/near-white background."""
    try:
        from PIL import Image, ImageFilter
        import numpy as np
    except ImportError:  # pragma: no cover
        return data

    try:
        img = Image.open(io.BytesIO(data)).convert("RGBA")
        arr = np.array(img)
        h, w, _ = arr.shape

        r = arr[:, :, 0].astype(float)
        g = arr[:, :, 1].astype(float)
        b = arr[:, :, 2].astype(float)

        is_white = (r >= white_threshold) & (g >= white_threshold) & (b >= white_threshold)

        # BFS Flood fill from outer edges to isolate only the connected background
        bg_mask = np.zeros((h, w), dtype=bool)
        visited = np.zeros((h, w), dtype=bool)
        queue = deque()

        for x in range(w):
            for y in (0, h - 1):
                if is_white[y, x] and not visited[y, x]:
                    visited[y, x] = True
                    queue.append((y, x))
        for y in range(h):
            for x in (0, w - 1):
                if is_white[y, x] and not visited[y, x]:
                    visited[y, x] = True
                    queue.append((y, x))

        while queue:
            cy, cx = queue.popleft()
            bg_mask[cy, cx] = True

            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < h and 0 <= nx < w:
                    if not visited[ny, nx] and is_white[ny, nx]:
                        visited[ny, nx] = True
                        queue.append((ny, nx))

        # If no background pixels detected, return unchanged
        if not np.any(bg_mask):
            return data

        alpha = np.full((h, w), 255, dtype=np.uint8)
        alpha[bg_mask] = 0

        alpha_img = Image.fromarray(alpha, mode="L")
        blurred_alpha = alpha_img.filter(ImageFilter.GaussianBlur(radius=0.8))
        blurred_arr = np.array(blurred_alpha)

        final_alpha = np.where(bg_mask, np.minimum(alpha, blurred_arr), 255).astype(np.uint8)
        arr[:, :, 3] = final_alpha
        result_img = Image.fromarray(arr, mode="RGBA")

        out = io.BytesIO()
        result_img.save(out, format="PNG")
        return out.getvalue()
    except Exception as exc:  # pragma: no cover
        log.warning("transparent character sprite processing failed: %s", exc)
        return data
