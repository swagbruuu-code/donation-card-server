#!/usr/bin/env python3
"""Rebuild assets/refs/{nuke,smite,starfall}.png from JPGs.

Goals:
  - Outer void transparent (edge-flood near-black, tint-protected)
  - Placeholder User/@User erased BEFORE keying (avoids chewed name-band)
  - Smite/Starfall: soft accent bottom glow WITHOUT JPEG-noise chew holes
    (replace noisy JPG fade with a smooth synthetic gradient matched to
    Hazem on-black brightness)
  - Nuke: no bottom glow
  - Hot content (rings, amount, avatars, white text) stays opaque JPG RGB
"""
from __future__ import annotations

from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
REFS = ROOT / "assets" / "refs"

ACCENT = {
    "nuke": (255, 0, 220),
    "smite": (220, 60, 145),  # muted pink; less neon than the source accent
    "starfall": (255, 10, 0),
}

# Synthetic soft glow (replaces speckled JPG fade). strength ≈ peak alpha/255
# tuned so on-black appearance ≈ Hazem JPG bottom samples.
FADE = {
    "smite": dict(start_y=460, strength=0.28, exp=1.25, blur=12),
    "starfall": dict(start_y=240, strength=0.55, exp=1.05, blur=10),
}

NAME_CENTERS = (540, 2307)
NAME_BAND = (500, 640)
NAME_HALF_W = 400


def erase_names(jpg: np.ndarray) -> np.ndarray:
    """Remove baked User/@User glyphs; keep surrounding fade RGB."""
    arr = jpg.copy()
    h, w = arr.shape[:2]
    y0, y1 = NAME_BAND
    for cx in NAME_CENTERS:
        x0, x1 = max(0, cx - NAME_HALF_W), min(w, cx + NAME_HALF_W)
        region = arr[y0:y1, x0:x1].copy()
        lum = region.max(2)
        white = lum >= 160
        mimg = Image.fromarray((white.astype(np.uint8) * 255), "L")
        for _ in range(4):
            mimg = mimg.filter(ImageFilter.MaxFilter(9))
        mask = np.array(mimg) > 0
        for row in range(region.shape[0]):
            m = mask[row]
            if not m.any():
                continue
            if (~m).sum() >= 8:
                bg = np.median(region[row][~m], axis=0)
            else:
                left = arr[y0 + row, max(0, x0 - 60) : x0]
                right = arr[y0 + row, x1 : min(w, x1 + 60)]
                samples = [s for s in (left, right) if s.size]
                bg = (
                    np.median(np.concatenate(samples, 0), 0)
                    if samples
                    else np.array([0.0, 0.0, 0.0])
                )
            region[row][m] = bg
        arr[y0:y1, x0:x1] = region
    return arr


def classify(jpg: np.ndarray):
    R, G, B = jpg[:, :, 0], jpg[:, :, 1], jpg[:, :, 2]
    mx = jpg.max(2)
    mn = jpg.min(2)
    sat = mx - mn
    # Broad tint so dark maroon/pink fade is never void-keyed
    red_dom = (R >= G + 4) & (R >= B) & (R >= 6)
    mag_dom = (R >= G + 8) & (B >= G + 8) & (np.maximum(R, B) >= 20)
    tint = red_dom | mag_dom
    is_white = (mn >= 85) & (sat <= 45)
    is_hot = tint & (mx >= 140)
    is_avatarish = (~tint) & (mx >= 28) & (sat >= 8)
    is_bright = mx >= 175
    is_content = is_white | is_hot | is_avatarish | is_bright
    return tint, is_content, mx, sat, R


def edge_void(jpg, tint, is_content):
    mx = jpg.max(2)
    sat = mx - jpg.min(2)
    is_void_cand = (((mx <= 16) & (sat <= 8)) | (mx <= 5)) & ~tint
    h, w = mx.shape
    visited = np.zeros((h, w), dtype=bool)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if is_void_cand[y, x]:
                visited[y, x] = True
                q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if is_void_cand[y, x] and not visited[y, x]:
                visited[y, x] = True
                q.append((y, x))
    while q:
        y, x = q.popleft()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx] and is_void_cand[ny, nx]:
                visited[ny, nx] = True
                q.append((ny, nx))
    is_void = visited & ~is_content & ~tint
    # Close tiny void speckles inside solid
    solid = Image.fromarray(((~is_void).astype(np.uint8) * 255), "L")
    solid = solid.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))
    is_void = (np.array(solid) == 0) & ~is_content & ~tint
    return is_void


def synth_fade(h, w, accent, start_y, strength, exp, blur):
    glow = np.zeros((h, w, 4), dtype=np.float32)
    ar, ag, ab = accent
    denom = float(max(1, h - 1 - start_y))
    for y in range(start_y, h):
        t = (y - start_y) / denom
        a = int(round(255 * strength * (t ** exp)))
        if a <= 0:
            continue
        glow[y, :, 0] = ar
        glow[y, :, 1] = ag
        glow[y, :, 2] = ab
        glow[y, :, 3] = min(255, a)
    for c in range(4):
        glow[:, :, c] = np.array(
            Image.fromarray(glow[:, :, c].astype(np.uint8), "L").filter(
                ImageFilter.GaussianBlur(blur)
            )
        )
    return glow


def rebuild(tier: str) -> Image.Image:
    jpg0 = np.array(Image.open(REFS / f"{tier}.jpg").convert("RGB"), dtype=np.float32)
    jpg = erase_names(jpg0)
    tint, is_content, mx, sat, R = classify(jpg)
    is_void = edge_void(jpg, tint, is_content)

    h, w = mx.shape
    out = np.zeros((h, w, 4), dtype=np.float32)
    out[:, :, :3] = jpg
    out[:, :, 3] = 255
    out[is_void] = 0

    if tier in FADE:
        cfg = FADE[tier]
        # Strip noisy JPG fade / dark plate in lower card (non-content)
        is_old_fade = tint & ~is_content
        out[is_old_fade] = 0
        start = cfg["start_y"]
        lower = np.zeros((h, w), dtype=bool)
        lower[start:, :] = True
        dark = (
            (out[:, :, :3].max(2) < 30)
            & (out[:, :, 3] > 0)
            & lower
            & ~is_content
        )
        out[dark] = 0

        glow = synth_fade(
            h,
            w,
            ACCENT[tier],
            cfg["start_y"],
            cfg["strength"],
            cfg["exp"],
            cfg["blur"],
        )
        glow[is_content] = 0
        place_y = np.zeros((h, w), dtype=bool)
        place_y[max(0, start - cfg["blur"] * 3) :, :] = True
        place = (~is_content) & (out[:, :, 3] == 0) & place_y
        out[place] = glow[place]

    out[is_content, :3] = jpg[is_content]
    out[is_content, 3] = 255
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")


def main() -> None:
    for tier in ("nuke", "smite", "starfall"):
        im = rebuild(tier)
        dest = REFS / f"{tier}.png"
        im.save(dest)
        a = np.array(im)[:, :, 3]
        arr = np.array(im)
        h, w = a.shape
        print(
            f"{tier}: wrote {dest.name} A0={(a==0).mean()*100:.1f}% "
            f"soft={((a>0)&(a<255)).mean()*100:.1f}% "
            f"bot={arr[h-5, w//2].tolist()} y580={arr[580, w//2].tolist()} "
            f"corners={[int(a[0,0]), int(a[0,-1]), int(a[-1,0]), int(a[-1,-1])]}"
        )


if __name__ == "__main__":
    main()
