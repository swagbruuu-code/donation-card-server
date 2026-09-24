"""Hazem-style dual-avatar donation card PNG generator.

Canvas 1179×275 RGBA — transparent base (no solid black plate), bottom accent
glow only. Template-matched to research/references/exact_donation_card_ref.jpg
(Discord light-theme screenshot of Starfall 10M; white→red is theme+glow, NOT
an opaque white background).

Fonts (sharp heavy geometric sans — NOT Fredoka):
  - Amount: Prompt ExtraBold + black stroke (~3px, ref-matched)
  - "donated to" / @usernames: Prompt ExtraBold + black stroke
  - Fallbacks: Prompt Black, Barlow ExtraBold, DejaVu Sans Bold

White text ("donated to", @names) and red amount both use black stroke outlines.
"donated to" is large (~40–50%+ of amount glyph height) on ALL tiers.

Bottom glow:
  - Starfall (10M): full-card bottom-weighted accent glow (ref-matched)
  - Smite (1M): softer glow, slightly higher start
  - Nuke: flat — no bottom glow (matches original 100k)
Footer is NOT drawn in the PNG — Discord embed.footer carries
  "Donated on • DD/MM/YYYY HH:MM AM/PM" (Europe/London)
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Optional, Tuple

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# Template-matched to exact_donation_card_ref.jpg (1179×275)
CARD_W = 1179
CARD_H = 275
BG = (0, 0, 0, 0)  # fully transparent RGBA base (no solid black/white plate)
WHITE = (253, 253, 253)  # #FDFDFD

TIER_ACCENTS = {
    "Nuke": (255, 0, 247),  # #FF00F7
    "Smite": (255, 0, 136),  # #FF0088
    "Starfall": (255, 0, 0),  # #FF0000
}

GLOW_TIERS = {"Smite", "Starfall"}

# Layout measured from exact_donation_card_ref.jpg
LEFT_C = (224, 104)
RIGHT_C = (955, 104)
AVATAR_R = 72
RING_OUTER = 82
RING_WIDTH = 10

# Amount tracking (px added to each glyph advance).
# Prompt ExtraBold @76 / stroke 3 needs slight NEGATIVE tracking to match REF.
AMOUNT_TRACKING = 0

# Font sizes — Prompt ExtraBold for ALL text (sharp heavy sans, not Fredoka).
# Locked vs exact_donation_card_ref.jpg overlays:
#   amount outer ≈73px; donated outer ≈46px; name outer ≈33px.
#   amount stroke ≈3–4px (NOT 8); wdth normal (static face).
FONT_AMOUNT = 71
FONT_DONATED = 52
FONT_NAME = 29
DONATED_STROKE = 1
NAME_STROKE = 3
AMOUNT_STROKE = 3  # slightly thinner than REF lock
ROBUX_SIZE = 64
ROBUX_OUTLINE = 2

_FONTS_DIR = Path(__file__).resolve().parent / "fonts"
_GOOGLE = Path("/usr/share/fonts/truetype/sand-box/google")

# Primary: Prompt ExtraBold (closest glyph match to REF amount digits)
_MONTSERRAT_VAR = [
    _FONTS_DIR / "Montserrat-VariableFont_wght.ttf",
    _GOOGLE / "Montserrat" / "Montserrat-VariableFont_wght.ttf",
]
_INTER_VAR = [
    _FONTS_DIR / "Inter-VariableFont_opsz,wght.ttf",
    _GOOGLE / "Inter" / "Inter-VariableFont_opsz,wght.ttf",
]
_PROMPT_EXTRABOLD = [
    _FONTS_DIR / "Prompt-ExtraBold.ttf",
    _GOOGLE / "Prompt" / "Prompt-ExtraBold.ttf",
]
_PROMPT_BLACK = [
    _FONTS_DIR / "Prompt-Black.ttf",
    _GOOGLE / "Prompt" / "Prompt-Black.ttf",
]
_PROMPT_BOLD = [
    _FONTS_DIR / "Prompt-Bold.ttf",
    _GOOGLE / "Prompt" / "Prompt-Bold.ttf",
]
_PROMPT_SEMIBOLD = [
    _FONTS_DIR / "Prompt-SemiBold.ttf",
    _GOOGLE / "Prompt" / "Prompt-SemiBold.ttf",
]
_BARLOW_EXTRABOLD = [
    _FONTS_DIR / "Barlow-ExtraBold.ttf",
    _GOOGLE / "Barlow" / "Barlow-ExtraBold.ttf",
    _FONTS_DIR / "Barlow-Black.ttf",
    _GOOGLE / "Barlow" / "Barlow-Black.ttf",
]
_BARLOW_BOLD = [
    _FONTS_DIR / "Barlow-Bold.ttf",
    _GOOGLE / "Barlow" / "Barlow-Bold.ttf",
]
_DEJAVU_BOLD = [
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
]
_DEJAVU_REG = [
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
]


def _first_existing(paths: list[Path]) -> str:
    for p in paths:
        if p.is_file():
            return str(p)
    return ""


def load_font(
    size: int,
    *,
    family: str = "prompt_extrabold",
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a face.

    family:
      - prompt_extrabold / amount / donated / name — Prompt ExtraBold (REF match)
      - prompt_black — heavier Prompt
      - prompt_bold / prompt_semibold — lighter Prompt
      - barlow_extrabold / barlow_bold — fallback thick sans
      - dejavu_bold / dejavu — system fallbacks
    """
    if family in ("inter_black", "montserrat_black", "amount"):
        # Amount: Inter (wght=750) — slightly thinner — sharp sans; REF '1' has no foot (Montserrat does)
        # axes: Optical Size, Weight
        path = _first_existing(_INTER_VAR)
        if path:
            try:
                font = ImageFont.truetype(path, size=size)
                try:
                    # Inter variable: opsz, wght
                    font.set_variation_by_axes([14, 750])
                except OSError:
                    try:
                        font.set_variation_by_axes([750])
                    except OSError:
                        pass
                return font
            except OSError:
                pass
        # fallback Montserrat Black
        path = _first_existing(_MONTSERRAT_VAR)
        if path:
            try:
                font = ImageFont.truetype(path, size=size)
                try:
                    font.set_variation_by_axes([750])
                except OSError:
                    pass
                return font
            except OSError:
                pass
        family = "prompt_extrabold"

    if family in ("prompt_extrabold", "donated", "name", "fredoka"):
        path = (
            _first_existing(_PROMPT_EXTRABOLD)
            or _first_existing(_PROMPT_BLACK)
            or _first_existing(_BARLOW_EXTRABOLD)
            or _first_existing(_DEJAVU_BOLD)
        )
        if path:
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                pass
        return ImageFont.load_default()

    if family == "prompt_black":
        path = _first_existing(_PROMPT_BLACK) or _first_existing(_PROMPT_EXTRABOLD)
    elif family == "prompt_bold":
        path = _first_existing(_PROMPT_BOLD) or _first_existing(_PROMPT_EXTRABOLD)
    elif family == "prompt_semibold":
        path = _first_existing(_PROMPT_SEMIBOLD) or _first_existing(_PROMPT_BOLD)
    elif family == "barlow_extrabold":
        path = _first_existing(_BARLOW_EXTRABOLD) or _first_existing(_DEJAVU_BOLD)
    elif family == "barlow_bold":
        path = _first_existing(_BARLOW_BOLD) or _first_existing(_BARLOW_EXTRABOLD)
    elif family == "dejavu":
        path = _first_existing(_DEJAVU_REG) or _first_existing(_DEJAVU_BOLD)
    else:
        path = _first_existing(_DEJAVU_BOLD) or _first_existing(_BARLOW_EXTRABOLD)
    if path:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            pass
    return ImageFont.load_default()


def parse_accent(tier: Optional[str], accent_hex: Optional[str]) -> Tuple[int, int, int]:
    if accent_hex:
        h = accent_hex.strip().lstrip("#")
        if len(h) == 6:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    if tier and tier in TIER_ACCENTS:
        return TIER_ACCENTS[tier]
    return TIER_ACCENTS["Nuke"]


def format_amount(amount: int) -> str:
    return f"{int(amount):,}"


def fetch_headshot(user_id: int, size: int = 420) -> Image.Image:
    """Fetch Roblox headshot; fall back to a neutral placeholder."""
    urls = [
        f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size=420x420&format=Png&isCircular=false",
        f"https://www.roblox.com/headshot-thumbnail/image?userId={user_id}&width=420&height=420&format=png",
    ]
    try:
        r = requests.get(urls[0], timeout=8)
        if r.ok:
            data = r.json()
            img_url = (data.get("data") or [{}])[0].get("imageUrl")
            if img_url:
                ir = requests.get(img_url, timeout=8)
                if ir.ok:
                    return Image.open(io.BytesIO(ir.content)).convert("RGBA")
    except Exception:
        pass
    try:
        ir = requests.get(urls[1], timeout=8)
        if ir.ok and ir.headers.get("content-type", "").startswith("image"):
            return Image.open(io.BytesIO(ir.content)).convert("RGBA")
    except Exception:
        pass
    ph = Image.new("RGBA", (size, size), (40, 40, 48, 255))
    d = ImageDraw.Draw(ph)
    d.ellipse((8, 8, size - 9, size - 9), fill=(70, 70, 80, 255))
    return ph


def _circle_mask(size: int) -> Image.Image:
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).ellipse((0, 0, size - 1, size - 1), fill=255)
    return m


def _resize(av: Image.Image, diam: int) -> Image.Image:
    return av.resize((diam, diam), Image.Resampling.LANCZOS)


_ROBUX_ICON_PATH = Path(__file__).resolve().parent / "assets" / "robux_icon.png"
_ROBUX_ICON_CACHE: Optional[Image.Image] = None


def _load_robux_icon_mask() -> Image.Image:
    """Load the official Robux hex PNG (white RGB + alpha; square hole)."""
    global _ROBUX_ICON_CACHE
    if _ROBUX_ICON_CACHE is None:
        if not _ROBUX_ICON_PATH.is_file():
            raise FileNotFoundError(f"Robux icon asset missing: {_ROBUX_ICON_PATH}")
        _ROBUX_ICON_CACHE = Image.open(_ROBUX_ICON_PATH).convert("RGBA")
    return _ROBUX_ICON_CACHE


def make_robux_icon(size: int, color: Tuple[int, int, int]) -> Image.Image:
    """Tier-recolored Robux glyph from assets/robux_icon.png."""
    base = _load_robux_icon_mask()
    bw, bh = base.size
    scale = float(size) / max(bw, bh)
    nw = max(1, int(round(bw * scale)))
    nh = max(1, int(round(bh * scale)))
    resized = base.resize((nw, nh), Image.Resampling.LANCZOS)
    r, g, b = color
    alpha = resized.getchannel("A")
    colored = Image.new("RGBA", (nw, nh), (r, g, b, 255))
    colored.putalpha(alpha)
    out = Image.new("RGBA", (int(size), int(size)), (0, 0, 0, 0))
    out.alpha_composite(colored, ((int(size) - nw) // 2, (int(size) - nh) // 2))
    return out


def _outline_icon(icon: Image.Image, stroke: int = 3) -> Image.Image:
    """Black silhouette outline behind a transparent icon (dilated alpha)."""
    if stroke <= 0:
        return icon
    alpha = icon.getchannel("A")
    dilated = alpha
    for _ in range(stroke):
        dilated = dilated.filter(ImageFilter.MaxFilter(3))
    outline = Image.new("RGBA", icon.size, (0, 0, 0, 0))
    outline.putalpha(dilated)
    out = Image.new("RGBA", icon.size, (0, 0, 0, 0))
    out.alpha_composite(outline)
    out.alpha_composite(icon)
    return out


def paste_robux_hex(
    canvas: Image.Image,
    cx: int,
    cy: int,
    size: int,
    color: Tuple[int, int, int],
    *,
    outline: int = ROBUX_OUTLINE,
) -> None:
    icon = _outline_icon(make_robux_icon(size, color), outline)
    canvas.alpha_composite(
        icon, (int(cx - icon.size[0] // 2), int(cy - icon.size[1] // 2))
    )


def draw_bottom_glow(
    canvas: Image.Image,
    accent: Tuple[int, int, int],
    *,
    strength: float = 1.0,
    start_y: int = 50,
) -> None:
    """Bottom-weighted accent glow on a transparent canvas.

    Draws semi-transparent accent rows (alpha ramp), not an opaque plate.
    Starfall: start_y≈45 (full fade up the card, peak alpha ≈150).
    Smite: start_y near the bottom only (softer band).
    """
    glow = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    ar, ag, ab = accent
    # Reference Starfall PNG: alpha 0→~150, RGB stays near accent red
    peak_a = 150.0 * float(strength)
    start_y = int(max(0, min(CARD_H - 2, start_y)))
    denom = float(max(1, CARD_H - 1 - start_y))
    for y in range(CARD_H):
        if y < start_y:
            continue
        t = (y - start_y) / denom
        v = t ** 1.05
        a = int(round(peak_a * v))
        if a <= 0:
            continue
        # Slight warm lift toward bottom (matches ref mid/bot samples)
        g = min(255, int(ag + 8 * v))
        b = min(255, int(ab + 4 * v))
        gd.line([(0, y), (CARD_W, y)], fill=(ar, g, b, min(255, a)))
    glow = glow.filter(ImageFilter.GaussianBlur(2))
    canvas.alpha_composite(glow)


def _tier_wants_glow(tier: Optional[str]) -> bool:
    if not tier:
        return False
    return tier.strip().title() in GLOW_TIERS or tier.strip() in GLOW_TIERS


def _glow_strength(tier: Optional[str]) -> float:
    if not tier:
        return 1.0
    t = tier.strip().title()
    if t == "Smite":
        return 0.40  # lighter 1M fade
    if t == "Nuke":
        return 0.85  # medium — same style family, accent differs
    return 1.0  # Starfall


def _glow_start_y(tier: Optional[str]) -> int:
    """Starfall: full fade from ~y40. Smite/Nuke: start a bit lower (softer band)."""
    if not tier:
        return 40
    t = tier.strip().title()
    if t == "Smite":
        return int(CARD_H * 0.72)  # confine Smite glow near bottom
    if t == "Nuke":
        return int(CARD_H * 0.45)
    return 40  # Starfall — fade begins near top padding (H=275 ref)


def tracked_text_width(text: str, font: ImageFont.ImageFont, tracking: float) -> float:
    """Width of text drawn with per-glyph advance += tracking."""
    if not text:
        return 0.0
    w = 0.0
    for i, ch in enumerate(text):
        try:
            adv = float(font.getlength(ch))
        except Exception:
            bb = font.getbbox(ch)
            adv = float(bb[2] - bb[0]) if bb else 0.0
        w += adv
        if i < len(text) - 1:
            w += tracking
    return w


def draw_text_tracked(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[float, float],
    text: str,
    font: ImageFont.ImageFont,
    fill,
    tracking: float = 0.0,
    *,
    stroke_width: int = 0,
    stroke_fill=None,
) -> float:
    """Draw text char-by-char with reduced/increased advance. Returns final width."""
    x, y = float(xy[0]), float(xy[1])
    x0 = x
    for i, ch in enumerate(text):
        kwargs = {"font": font, "fill": fill}
        if stroke_width and stroke_fill is not None:
            kwargs["stroke_width"] = stroke_width
            kwargs["stroke_fill"] = stroke_fill
        draw.text((x, y), ch, **kwargs)
        try:
            adv = float(font.getlength(ch))
        except Exception:
            bb = font.getbbox(ch)
            adv = float(bb[2] - bb[0]) if bb else 0.0
        x += adv
        if i < len(text) - 1:
            x += tracking
    return x - x0


def render_card(
    *,
    donor_id: int,
    receiver_id: int,
    donor_name: str,
    receiver_name: str,
    amount: int,
    tier: Optional[str] = None,
    accent_hex: Optional[str] = None,
    donor_avatar: Optional[Image.Image] = None,
    receiver_avatar: Optional[Image.Image] = None,
    **_ignored,
) -> Image.Image:
    accent = parse_accent(tier, accent_hex)
    # Transparent base — only content + bottom accent glow have alpha
    canvas = Image.new("RGBA", (CARD_W, CARD_H), BG)

    # Bottom glow: Starfall full fade; Smite soft bottom-only; Nuke none.
    if _tier_wants_glow(tier):
        draw_bottom_glow(canvas, accent, strength=_glow_strength(tier), start_y=_glow_start_y(tier))

    donor_av = donor_avatar or fetch_headshot(int(donor_id))
    recv_av = receiver_avatar or fetch_headshot(int(receiver_id))

    for av, center in ((donor_av, LEFT_C), (recv_av, RIGHT_C)):
        cx, cy = center

        bloom_r = RING_OUTER + 6
        bloom = Image.new("RGBA", (bloom_r * 2, bloom_r * 2), (0, 0, 0, 0))
        bd = ImageDraw.Draw(bloom)
        for i, alpha in enumerate((28, 16, 8)):
            inset = i * 3
            bd.ellipse(
                (inset, inset, bloom_r * 2 - 1 - inset, bloom_r * 2 - 1 - inset),
                outline=(*accent, alpha),
                width=5,
            )
        bloom = bloom.filter(ImageFilter.GaussianBlur(5))
        canvas.alpha_composite(bloom, (cx - bloom_r, cy - bloom_r))

        pad = 2
        ring = Image.new(
            "RGBA",
            (RING_OUTER * 2 + pad * 2, RING_OUTER * 2 + pad * 2),
            (0, 0, 0, 0),
        )
        rd = ImageDraw.Draw(ring)
        rd.ellipse(
            (pad, pad, pad + RING_OUTER * 2, pad + RING_OUTER * 2),
            outline=(*accent, 255),
            width=RING_WIDTH,
        )
        canvas.alpha_composite(ring, (cx - RING_OUTER - pad, cy - RING_OUTER - pad))

        diam = AVATAR_R * 2
        av_r = _resize(av.convert("RGBA"), diam)
        masked = Image.new("RGBA", (diam, diam), (0, 0, 0, 0))
        masked.paste(av_r, (0, 0), _circle_mask(diam))
        canvas.alpha_composite(masked, (cx - AVATAR_R, cy - AVATAR_R))

    draw = ImageDraw.Draw(canvas)

    amount_text = format_amount(amount)
    font_amount = load_font(FONT_AMOUNT, family="amount")
    font_donated = load_font(FONT_DONATED, family="prompt_semibold")
    font_name = load_font(FONT_NAME, family="prompt_extrabold")

    aw = tracked_text_width(amount_text, font_amount, AMOUNT_TRACKING)
    bbox = draw.textbbox((0, 0), amount_text, font=font_amount)
    glyph_h = bbox[3] - bbox[1]

    robux_size = ROBUX_SIZE
    gap = 4
    pair_w = robux_size + gap + aw
    pair_left = (CARD_W - int(round(pair_w))) // 2

    # Extra top padding vs original 86 — breathing room from top edge
    amount_top = 47
    amount_y = amount_top - bbox[1]
    glyph_cy = amount_top + glyph_h / 2.0

    paste_robux_hex(
        canvas,
        pair_left + robux_size // 2,
        int(round(glyph_cy)),
        robux_size,
        accent,
    )

    draw = ImageDraw.Draw(canvas)
    amount_x = pair_left + robux_size + gap
    draw_text_tracked(
        draw,
        (amount_x, amount_y),
        amount_text,
        font_amount,
        fill=(*accent, 255),
        tracking=AMOUNT_TRACKING,
        stroke_width=AMOUNT_STROKE,
        stroke_fill=(0, 0, 0, 255),
    )

    donated = "donated to"
    db = draw.textbbox(
        (0, 0), donated, font=font_donated, stroke_width=DONATED_STROKE
    )
    dw = db[2] - db[0]
    # Shifted with amount (+12) for top padding
    donated_top = 132
    draw.text(
        ((CARD_W - dw) // 2, donated_top - db[1]),
        donated,
        font=font_donated,
        fill=(*WHITE, 255),
        stroke_width=DONATED_STROKE,
        stroke_fill=(0, 0, 0, 255),
    )

    name_top = 204
    for name, cx in ((donor_name, LEFT_C[0]), (receiver_name, RIGHT_C[0])):
        label = name if name.startswith("@") else f"@{name}"
        nb = draw.textbbox((0, 0), label, font=font_name, stroke_width=NAME_STROKE)
        nw = nb[2] - nb[0]
        draw.text(
            (cx - nw // 2, name_top - nb[1]),
            label,
            font=font_name,
            fill=(*WHITE, 255),
            stroke_width=NAME_STROKE,
            stroke_fill=(0, 0, 0, 255),
        )

    # Keep RGBA so Discord/PNG alpha (transparent corners + glow) is preserved
    return canvas


def render_card_png_bytes(**kwargs) -> bytes:
    img = render_card(**kwargs)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Generate a Hazem-style donation card PNG")
    ap.add_argument("--donor-id", type=int, default=1)
    ap.add_argument("--receiver-id", type=int, default=1)
    ap.add_argument("--donor-name", default="Donor")
    ap.add_argument("--receiver-name", default="Receiver")
    ap.add_argument("--amount", type=int, default=10_000_000)
    ap.add_argument("--tier", default="Starfall", choices=["Nuke", "Smite", "Starfall"])
    ap.add_argument("-o", "--out", default="card_demo.png")
    args = ap.parse_args()
    img = render_card(
        donor_id=args.donor_id,
        receiver_id=args.receiver_id,
        donor_name=args.donor_name,
        receiver_name=args.receiver_name,
        amount=args.amount,
        tier=args.tier,
    )
    img.save(args.out)
    print("wrote", args.out, img.size)
