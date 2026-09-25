#!/usr/bin/env python3
"""Rebuild assets/refs/{nuke,smite,starfall}.png from JPGs with transparent void + soft fade.

Void (near-black, untinted) -> A=0
Fade (red/magenta tint, not hot content) -> accent RGB * soft alpha from R
Content (hot accent / avatars / white text) -> original RGB A=255
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
REFS = ROOT / "assets" / "refs"

ACCENT = {
    "nuke": (255, 0, 220),
    "smite": (255, 0, 130),
    "starfall": (255, 10, 0),
}
SCALE = {"nuke": 2.4, "smite": 2.6, "starfall": 1.6}


def rebuild(tier: str) -> Image.Image:
    jpg = np.array(Image.open(REFS / f"{tier}.jpg").convert("RGB"), dtype=np.float32)
    R, G, B = jpg[:, :, 0], jpg[:, :, 1], jpg[:, :, 2]
    mx = jpg.max(2)
    mn = jpg.min(2)
    sat = mx - mn

    red_dom = (R >= G + 8) & (R >= B + 8)
    mag_dom = (R >= G + 12) & (B >= G + 12) & (np.maximum(R, B) >= 30)
    tint = red_dom | mag_dom

    is_white = (mn >= 85) & (sat <= 45)
    is_hot_accent = tint & (mx >= 150)
    is_avatarish = (~tint) & (mx >= 28) & (sat >= 8)
    is_bright_any = mx >= 175
    is_content = is_white | is_hot_accent | is_avatarish | is_bright_any

    is_void = ((mx <= 18) & (sat <= 10) & ~tint) | (mx <= 8)
    is_fade = tint & ~is_content & ~is_void
    weak = is_fade & (R < 12) & (mx < 14)
    is_void = is_void | weak
    is_fade = is_fade & ~weak

    out = np.zeros((jpg.shape[0], jpg.shape[1], 4), dtype=np.float32)
    out[:, :, :3] = jpg
    out[:, :, 3] = 255
    out[is_void, :3] = 0
    out[is_void, 3] = 0

    accent = np.array(ACCENT[tier], dtype=np.float32)
    a_fade = np.clip(R * SCALE[tier], 10, 210)
    out[is_fade, 0] = accent[0]
    out[is_fade, 1] = accent[1]
    out[is_fade, 2] = accent[2]
    out[is_fade, 3] = a_fade[is_fade]

    out[is_content, :3] = jpg[is_content]
    out[is_content, 3] = 255
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")


def main() -> None:
    for tier in ("nuke", "smite", "starfall"):
        im = rebuild(tier)
        dest = REFS / f"{tier}.png"
        im.save(dest)
        a = np.array(im)[:, :, 3]
        print(
            f"{tier}: wrote {dest.name} A0={(a==0).mean()*100:.1f}% "
            f"soft={((a>0)&(a<255)).mean()*100:.1f}% "
            f"corners={[int(a[0,0]),int(a[0,-1]),int(a[-1,0]),int(a[-1,-1])]}"
        )


if __name__ == "__main__":
    main()
