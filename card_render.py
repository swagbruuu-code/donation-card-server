"""Donation card images for Discord.

Live path: serve the exact Nuke/Smite/Starfall reference JPGs from assets/refs
(no redraw). Legacy Pillow renderer kept below for offline experiments only.

Canvas constants below are unused by the live exact-ref path.

Fonts (sharp heavy geometric sans — Prompt):
  - Amount: Prompt ExtraBold + light black stroke
  - "donated to" / @usernames: Prompt Bold/ExtraBold + black stroke
  - Fallbacks: Prompt Black, Barlow ExtraBold, DejaVu Sans Bold

Bottom glow:
  - Starfall (10M): stronger dark-red bottom gradient
  - Smite (1M): soft hot-pink bottom band
  - Nuke: flat — no bottom glow
Footer is NOT drawn in the PNG — Discord embed.footer carries
  "Donated on • DD/MM/YYYY HH:MM AM/PM" (Europe/London)
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Optional, Tuple

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# Template-matched to Hazem refs (scaled 2816×704 → 1179×≈295, cropped to 275)
CARD_W = 1179
CARD_H = 275
BG = (0, 0, 0, 255)  # opaque black plate matching refs / Discord cards
WHITE = (253, 253, 253)  # #FDFDFD

TIER_ACCENTS = {
    "Nuke": (255, 0, 247),  # #FF00F7
    "Smite": (255, 0, 136),  # #FF0088
    "Starfall": (255, 0, 0),  # #FF0000
}

GLOW_TIERS = {"Smite", "Starfall"}

# Layout measured from Hazem refs (isotropic width scale)
LEFT_C = (226, 107)
RIGHT_C = (955, 107)
AVATAR_R = 73
RING_OUTER = 80
RING_WIDTH = 7  # refs ~6–7px; was 10 (too thick)

# Amount tracking (px added to each glyph advance).
AMOUNT_TRACKING = 0
DONATED_TRACKING = 0

# Font sizes — Prompt ExtraBold (best overlay vs Hazem amount+donated)
FONT_AMOUNT = 72
FONT_DONATED = 52
FONT_NAME = 30
DONATED_STROKE = 1
NAME_STROKE = 2
AMOUNT_STROKE = 0  # Nuke/Smite; Starfall uses +1 below
AMOUNT_STROKE_STARFALL = 1
ROBUX_SIZE = 60
ROBUX_GAP = 10
ROBUX_OUTLINE = 2

# Vertical stack
AMOUNT_TOP = 53
DONATED_TOP = 135
NAME_TOP = 212

_FONTS_DIR = Path(__file__).resolve().parent / "fonts"
_GOOGLE = Path("/usr/share/fonts/truetype/sand-box/google")

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
      - amount / prompt_extrabold / donated / name — Prompt ExtraBold (REF match)
      - prompt_black — heavier Prompt
      - prompt_bold / prompt_semibold — lighter Prompt
      - barlow_extrabold / barlow_bold — fallback thick sans
      - dejavu_bold / dejavu — system fallbacks
    """
    if family in ("inter_black", "montserrat_black"):
        path = _first_existing(_INTER_VAR)
        if path:
            try:
                font = ImageFont.truetype(path, size=size)
                try:
                    font.set_variation_by_axes([14, 750])
                except OSError:
                    try:
                        font.set_variation_by_axes([750])
                    except OSError:
                        pass
                return font
            except OSError:
                pass
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

    # Amount: Montserrat ExtraBold (~800) — clean geometric digits matching refs
    if family in ("amount", "donated"):
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
        family = "prompt_extrabold"

    if family in ("prompt_extrabold", "name", "fredoka"):
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


REF_DIR = Path(__file__).resolve().parent / "assets" / "refs"
REF_FILES = {
    "Nuke": REF_DIR / "nuke.png",
    "Smite": REF_DIR / "smite.png",
    "Starfall": REF_DIR / "starfall.png",
}


def resolve_tier(tier: Optional[str], amount: int) -> str:
    """Pick Nuke / Smite / Starfall from explicit tier or amount thresholds."""
    if tier:
        t = str(tier).strip().title()
        if t in REF_FILES:
            return t
    amt = int(amount or 0)
    if amt >= 10_000_000:
        return "Starfall"
    if amt >= 1_000_000:
        return "Smite"
    return "Nuke"


def load_exact_ref_png_bytes(tier: str) -> bytes:
    """Return the user's exact reference photo as PNG bytes (no redraw).

    Exact-ref PNG (transparent void + soft accent fades) for Discord;
    no resize, crop, text, or avatar changes.
    """
    src = REF_FILES[tier]
    if not src.is_file():
        raise FileNotFoundError(f"missing exact ref for {tier}: {src}")
    img = Image.open(src).convert("RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False)
    return buf.getvalue()


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
    exp: float = 1.15,
    blur: int = 3,
) -> None:
    """Bottom-weighted accent glow over opaque black.

    Starfall: higher peak, starts mid-card (dark red wash).
    Smite: softer peak, confined near bottom.
    """
    glow = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    ar, ag, ab = accent
    peak_a = 255.0 * float(strength)
    start_y = int(max(0, min(CARD_H - 2, start_y)))
    denom = float(max(1, CARD_H - 1 - start_y))
    for y in range(CARD_H):
        if y < start_y:
            continue
        t = (y - start_y) / denom
        v = t ** float(exp)
        a = int(round(peak_a * v))
        if a <= 0:
            continue
        gd.line([(0, y), (CARD_W, y)], fill=(ar, ag, ab, min(255, a)))
    if blur > 0:
        glow = glow.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(glow)


def _tier_wants_glow(tier: Optional[str]) -> bool:
    if not tier:
        return False
    return tier.strip().title() in GLOW_TIERS or tier.strip() in GLOW_TIERS


def _glow_strength(tier: Optional[str]) -> float:
    """Peak alpha as fraction of 255, tuned to ref bottom samples."""
    if not tier:
        return 0.45
    t = tier.strip().title()
    if t == "Smite":
        return 0.135  # ref bottom ~ (32,0,16) on black
    if t == "Nuke":
        return 0.0
    return 0.43  # Starfall ref bottom ~ (110,0,0)


def _glow_start_y(tier: Optional[str]) -> int:
    if not tier:
        return 100
    t = tier.strip().title()
    if t == "Smite":
        return 200  # soft band near bottom only
    if t == "Nuke":
        return CARD_H
    return 85  # Starfall — fade begins mid/upper


def _glow_exp(tier: Optional[str]) -> float:
    if not tier:
        return 1.15
    t = tier.strip().title()
    if t == "Smite":
        return 1.45
    return 1.05


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
    # Opaque black plate — matches Hazem refs / Discord dark cards
    canvas = Image.new("RGBA", (CARD_W, CARD_H), BG)

    # Bottom glow: Starfall full fade; Smite soft bottom-only; Nuke none.
    if _tier_wants_glow(tier):
        draw_bottom_glow(
            canvas,
            accent,
            strength=_glow_strength(tier),
            start_y=_glow_start_y(tier),
            exp=_glow_exp(tier),
            blur=3,
        )

    donor_av = donor_avatar or fetch_headshot(int(donor_id))
    recv_av = receiver_avatar or fetch_headshot(int(receiver_id))

    for av, center in ((donor_av, LEFT_C), (recv_av, RIGHT_C)):
        cx, cy = center

        # Thin solid ring only (no outer bloom — refs are crisp)
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
    font_donated = load_font(FONT_DONATED, family="donated")
    font_name = load_font(FONT_NAME, family="prompt_extrabold")

    aw = tracked_text_width(amount_text, font_amount, AMOUNT_TRACKING)
    bbox = draw.textbbox((0, 0), amount_text, font=font_amount)
    glyph_h = bbox[3] - bbox[1]

    robux_size = ROBUX_SIZE
    gap = ROBUX_GAP
    pair_w = robux_size + gap + aw
    pair_left = (CARD_W - int(round(pair_w))) // 2

    amount_top = AMOUNT_TOP
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
    amount_stroke = AMOUNT_STROKE_STARFALL if tier == "Starfall" else AMOUNT_STROKE
    draw_text_tracked(
        draw,
        (amount_x, amount_y),
        amount_text,
        font_amount,
        fill=(*accent, 255),
        tracking=AMOUNT_TRACKING,
        stroke_width=amount_stroke,
        stroke_fill=(0, 0, 0, 255),
    )

    donated = "donated to"
    dw = tracked_text_width(donated, font_donated, DONATED_TRACKING)
    db = draw.textbbox(
        (0, 0), donated, font=font_donated, stroke_width=DONATED_STROKE
    )
    donated_top = DONATED_TOP
    draw_text_tracked(
        draw,
        ((CARD_W - dw) // 2, donated_top - db[1]),
        donated,
        font_donated,
        fill=(*WHITE, 255),
        tracking=DONATED_TRACKING,
        stroke_width=DONATED_STROKE,
        stroke_fill=(0, 0, 0, 255),
    )

    name_top = NAME_TOP
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

    return canvas


# Exact-ref canvas geometry (2816×704). Rings/amount/"donated to"/glow stay
# as in the user's photo; only Roblox headshots + @names are composited on.
REF_LEFT_C = (540, 280)
REF_RIGHT_C = (2307, 281)
REF_AVATAR_R = 172
# Username band measured from ref "User"/"@User" glyphs
REF_NAME_MID_Y = 560
REF_NAME_FONT = 46
REF_NAME_STROKE = {"Nuke": 2, "Smite": 3, "Starfall": 5}
REF_NAME_BAND = (500, 620)  # y0, y1
REF_NAME_HALF_W = 340


def _paste_circular_avatar(
    canvas: Image.Image,
    avatar: Image.Image,
    center: Tuple[int, int],
    radius: int,
) -> None:
    cx, cy = center
    diam = radius * 2
    av = avatar.convert("RGBA").resize((diam, diam), Image.Resampling.LANCZOS)
    mask = Image.new("L", (diam, diam), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, diam - 1, diam - 1), fill=255)
    canvas.paste(av, (cx - radius, cy - radius), mask)


def _erase_placeholder_names(canvas: Image.Image, cx: int) -> None:
    """Remove ref User/@User glyphs; rebuild background so glow survives."""
    import numpy as np

    y0, y1 = REF_NAME_BAND
    arr = np.array(canvas.convert("RGBA"))
    x0 = max(0, int(cx) - REF_NAME_HALF_W)
    x1 = min(arr.shape[1], int(cx) + REF_NAME_HALF_W)
    region = arr[y0:y1, x0:x1].copy()
    lum = region[:, :, :3].max(axis=2)
    white = lum >= 180
    # Dilate to swallow black stroke + AA fringe around glyphs
    mimg = Image.fromarray((white.astype(np.uint8) * 255), mode="L")
    for _ in range(3):
        mimg = mimg.filter(ImageFilter.MaxFilter(9))
    mask = np.array(mimg) > 0
    for row in range(region.shape[0]):
        m = mask[row]
        if not m.any():
            continue
        if (~m).sum() >= 8:
            bg = np.median(region[row][~m], axis=0)
        else:
            # sample just outside the name window on this row
            left = arr[y0 + row, max(0, x0 - 60) : x0]
            right = arr[y0 + row, x1 : min(arr.shape[1], x1 + 60)]
            samples = []
            if left.size:
                samples.append(left)
            if right.size:
                samples.append(right)
            if samples:
                bg = np.median(np.concatenate(samples, axis=0), axis=0)
            else:
                bg = np.array([0, 0, 0, 0], dtype=np.float64)
        region[row][m] = bg
    arr[y0:y1, x0:x1] = region
    # Force full overwrite (Pillow otherwise uses alpha as mask and skips A=0).
    out = Image.fromarray(arr)
    canvas.paste(out, (0, 0), Image.new("L", out.size, 255))


def _cover_and_draw_names(
    canvas: Image.Image,
    donor_name: str,
    receiver_name: str,
    tier: str,
) -> None:
    for cx, _cy in (REF_LEFT_C, REF_RIGHT_C):
        _erase_placeholder_names(canvas, cx)
    draw = ImageDraw.Draw(canvas)
    font = load_font(REF_NAME_FONT, family="prompt_extrabold")
    stroke = REF_NAME_STROKE.get(tier, 3)
    for name, cx in ((donor_name, REF_LEFT_C[0]), (receiver_name, REF_RIGHT_C[0])):
        label = name if str(name).startswith("@") else f"@{name}"
        bbox = draw.textbbox((0, 0), label, font=font, stroke_width=stroke)
        tw = bbox[2] - bbox[0]
        th = bbox[1] + bbox[3]
        x = cx - tw / 2 - bbox[0]
        y = REF_NAME_MID_Y - th / 2
        draw.text(
            (x, y),
            label,
            font=font,
            fill=(255, 255, 255, 255),
            stroke_width=stroke,
            stroke_fill=(0, 0, 0, 255),
        )


def render_from_exact_ref(
    *,
    donor_id: int,
    receiver_id: int,
    donor_name: str,
    receiver_name: str,
    amount: int,
    tier: Optional[str] = None,
    donor_avatar: Optional[Image.Image] = None,
    receiver_avatar: Optional[Image.Image] = None,
    **_ignored,
) -> Image.Image:
    """Exact reference photo + real Roblox headshots + @names only."""
    resolved = resolve_tier(tier, amount)
    src = REF_FILES[resolved]
    if not src.is_file():
        raise FileNotFoundError(f"missing exact ref for {resolved}: {src}")
    canvas = Image.open(src).convert("RGBA")
    donor_av = donor_avatar or fetch_headshot(int(donor_id))
    recv_av = receiver_avatar or fetch_headshot(int(receiver_id))
    _paste_circular_avatar(canvas, donor_av, REF_LEFT_C, REF_AVATAR_R)
    _paste_circular_avatar(canvas, recv_av, REF_RIGHT_C, REF_AVATAR_R)
    _cover_and_draw_names(canvas, donor_name, receiver_name, resolved)
    return canvas


def render_card_png_bytes(**kwargs) -> bytes:
    """Live path: exact Nuke/Smite/Starfall photo + real avatars/names."""
    img = render_from_exact_ref(**kwargs)
    buf = io.BytesIO()
    img.convert("RGBA").save(buf, format="PNG", optimize=False)
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
