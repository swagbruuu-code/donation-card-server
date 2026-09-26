"""Donation card images for Discord.

Live path: serve the exact Nuke/Smite/Starfall reference JPGs from assets/refs
(no redraw). Legacy Pillow renderer kept below for offline experiments only.

Canvas constants below are unused by the live exact-ref path.

Fonts:
  - Amount / "donated to" (legacy path): Prompt ExtraBold
  - @usernames (exact-ref path):
      * Every name (incl. swagbruuu) → exact sticker @ cutout + Plus Jakarta
        ExtraBold letters scaled to sticker *fill* height (not full outline)
        with tight tracking so size/density match across all usernames.
  - Fallbacks: Montserrat ExtraBold, Prompt, Barlow, DejaVu

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
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

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
_MANROPE_VAR = [
    _FONTS_DIR / "Manrope-VariableFont_wght.ttf",
    _GOOGLE / "Manrope" / "Manrope-VariableFont_wght.ttf",
]
_PLUS_JAKARTA_VAR = [
    _FONTS_DIR / "PlusJakartaSans-VariableFont_wght.ttf",
    _GOOGLE / "Plus Jakarta Sans" / "PlusJakartaSans-VariableFont_wght.ttf",
]
_RALEWAY_VAR = [
    _FONTS_DIR / "Raleway-VariableFont_wght.ttf",
    _GOOGLE / "Raleway" / "Raleway-VariableFont_wght.ttf",
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
    weight: int | None = None,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a face.

    family:
      - plus_jakarta / name — Plus Jakarta Sans (default ExtraBold / wght 800)
      - raleway — Raleway (default SemiBold / wght 550) — thin-ring @ glyph
      - amount / prompt_extrabold / donated — Prompt ExtraBold
      - prompt_black — heavier Prompt
      - prompt_bold / prompt_semibold — lighter Prompt
      - barlow_extrabold / barlow_bold — fallback thick sans
      - dejavu_bold / dejavu — system fallbacks

    weight: optional variable-axis wght override (e.g. 550 for @, 800 for letters).
    """
    if family in (
        "plus_jakarta",
        "plus_jakarta_extrabold",
        "name",
        "manrope",  # legacy alias → Plus Jakarta
        "manrope_extrabold",
    ):
        # Plus Jakarta Sans — letters match @iamEvanRBLX ref (square i-dot)
        path = _first_existing(_PLUS_JAKARTA_VAR)
        wght = int(weight) if weight is not None else 800
        if path:
            try:
                font = ImageFont.truetype(path, size=size)
                try:
                    if wght >= 800:
                        font.set_variation_by_name("ExtraBold")
                    elif wght >= 700:
                        font.set_variation_by_name("Bold")
                    elif wght >= 600:
                        font.set_variation_by_name("SemiBold")
                    elif wght >= 500:
                        font.set_variation_by_name("Medium")
                    else:
                        font.set_variation_by_axes([wght])
                except OSError:
                    try:
                        font.set_variation_by_axes([wght])
                    except OSError:
                        try:
                            font.set_variation_by_name("ExtraBold")
                        except OSError:
                            try:
                                font.set_variation_by_axes([800])
                            except OSError:
                                pass
                return font
            except OSError:
                pass
        # geometric fallbacks
        for var_paths, axes in (
            (_MONTSERRAT_VAR, [wght]),
            (_MANROPE_VAR, [wght]),
            (_INTER_VAR, [14, wght]),
        ):
            path = _first_existing(var_paths)
            if not path:
                continue
            try:
                font = ImageFont.truetype(path, size=size)
                try:
                    font.set_variation_by_axes(axes)
                except OSError:
                    try:
                        font.set_variation_by_axes([axes[-1]])
                    except OSError:
                        pass
                return font
            except OSError:
                pass
        family = "prompt_extrabold"

    if family in ("raleway", "raleway_at"):
        # Raleway — ExtraBold @ has a thin outer ring (ref match). Used for '@' only.
        path = _first_existing(_RALEWAY_VAR)
        wght = int(weight) if weight is not None else 550
        if path:
            try:
                font = ImageFont.truetype(path, size=size)
                try:
                    font.set_variation_by_axes([wght])
                except OSError:
                    try:
                        if wght >= 700:
                            font.set_variation_by_name("Bold")
                        elif wght >= 600:
                            font.set_variation_by_name("SemiBold")
                        else:
                            font.set_variation_by_name("Medium")
                    except OSError:
                        pass
                return font
            except OSError:
                pass
        # fall back to Plus Jakarta at same weight if Raleway missing
        return load_font(size, family="plus_jakarta", weight=wght)

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

    if family in ("prompt_extrabold", "fredoka"):
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

    JPEG pixels are re-encoded to PNG for Discord attachment compatibility;
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
# Defaults (Nuke/Smite). Starfall right ring is ~18px left of Nuke's.
REF_LEFT_C = (540, 281)
REF_RIGHT_C = (2307, 281)
REF_AVATAR_R = 172
# Per-tier avatar centers/radii measured from baked ring INNER hole on ref JPGs.
# paste_r is ~2px inside median inner red/magenta stroke so a uniform ring remains.
# cover_r clears leftover placeholder headshot up to (but not over) the stroke.
REF_AVATAR_GEOM = {
    # Multi-angle INNER hole fit. paste = rin_min-5; cover = rin_min-1
    # so placeholder clears without eating dark stroke fringe.
    "Nuke": {
        "left": (539, 280),
        "right": (2307, 281),
        "left_r": 169,
        "right_r": 165,
        "left_cover": 173,
        "right_cover": 169,
    },
    "Smite": {
        "left": (538, 279),
        "right": (2297, 279),
        "left_r": 170,
        "right_r": 169,
        "left_cover": 174,
        "right_cover": 173,
    },
    "Starfall": {
        "left": (540, 281),
        "right": (2289, 282),
        "left_r": 168,
        "right_r": 167,
        "left_cover": 172,
        "right_cover": 171,
    },
}
# Username band measured from ref "User" (left) / "@User" (right) glyphs.
# Right slot is wider because baked text includes the @.
REF_NAME_MID_Y = 562
REF_NAME_BAND = (490, 650)  # y0, y1 — pad beyond glyph bbox ~525-594
REF_NAME_HALF_W = 450  # covers @User (~253px) with margin either side
# Tight hard-wipe core around measured glyph ink (Nuke/Smite/Starfall).
REF_NAME_HARD_BAND = (500, 625)
# Cover full username sprite footprint (long names e.g. TheMan3mad ~562px wide).
REF_NAME_HARD_HALF_W_LEFT = 320
REF_NAME_HARD_HALF_W_RIGHT = 320
# Exact @swagbruuu sticker is native ~392px tall (full outline). Scale so
# letter fill (~270px) matches baked User fill (~65px) on 2816-wide cards.
REF_STICKER_NATIVE_H = 392
REF_STICKER_TARGET_H = 94  # full sticker incl. outer bubble; fits REF_NAME_BAND
# Font letters must match sticker *fill* height, not full outline height.
# Stable sticker letter fills span ~270 of the 392 native canvas → ~65 at target_h;
# this is the measured on-card height of the original whole-sticker word.
REF_NAME_LETTER_H = round(REF_STICKER_TARGET_H * 270 / REF_STICKER_NATIVE_H)  # 65
# All usernames: Plus Jakarta ExtraBold @ sticker fill scale + tight track.
REF_NAME_FONT = 58
REF_NAME_STROKE = 3
# Tight tracking to match sticker letter density (was +7 → looked spaced-out
# once letters were wrongly upscaled to full outline height). Slightly
# negative so fills nearly touch like the cutout (avoid < -4 ghosting).
REF_NAME_TRACKING = -2

_GLYPHS_DIR = Path(__file__).resolve().parent / "assets" / "glyphs"
_STICKER_REF_JPG = (
    Path(__file__).resolve().parent / "assets" / "refs" / "username_sticker_swagbruuu.jpg"
)
_STICKER_FULL_PNG = _GLYPHS_DIR / "sticker_swagbruuu_full.png"
_GLYPHS_META = _GLYPHS_DIR / "glyphs_meta.json"

# Lazy cache: {char: (RGBA sprite, advance, left_bearing)} plus full sticker
_STICKER_CACHE: dict | None = None


def _avatar_geom(tier: str) -> dict:
    return REF_AVATAR_GEOM.get(tier, REF_AVATAR_GEOM["Nuke"])


def _cover_ring_hole(
    canvas: Image.Image,
    center: Tuple[int, int],
    cover_radius: int,
) -> None:
    """Paint opaque black inside the baked ring without touching the stroke.

    Uses a disk of cover_radius, but skips pixels that look like the accent
    ring (red / magenta / pink) so leftover placeholder can be cleared even
    when cover_radius reaches the uneven inner edge of the stroke.
    """
    if cover_radius <= 0:
        return
    cx, cy = center
    cr = int(cover_radius)
    x0, y0 = cx - cr, cy - cr
    x1, y1 = cx + cr, cy + cr
    box = canvas.crop((x0, y0, x1, y1)).convert("RGBA")
    pix = box.load()
    w, h = box.size
    cr2 = cr * cr
    for yy in range(h):
        dy = yy - cr
        for xx in range(w):
            dx = xx - cr
            if dx * dx + dy * dy > cr2:
                continue
            r, g, b, a = pix[xx, yy]
            # Protect accent stroke incl. dark red/magenta fringe (r can be ~30-70).
            if a > 0 and r >= 28 and r - g >= 12 and (r - b >= 10 or b - g >= 12):
                continue
            pix[xx, yy] = (0, 0, 0, 255)
    canvas.paste(box, (x0, y0))


def _paste_circular_avatar(
    canvas: Image.Image,
    avatar: Image.Image,
    center: Tuple[int, int],
    radius: int,
    *,
    cover_radius: int | None = None,
) -> None:
    """Paste a circular headshot centered on the baked ring.

    cover_radius clears leftover placeholder inside the ring WITHOUT painting
    over the red/magenta stroke. paste radius should be <= inner hole so stroke
    thickness stays even all the way around.
    """
    cx, cy = center
    cr = int(cover_radius if cover_radius is not None else radius)
    _cover_ring_hole(canvas, center, cr)
    diam = radius * 2
    av = avatar.convert("RGBA").resize((diam, diam), Image.Resampling.LANCZOS)
    mask = Image.new("L", (diam, diam), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, diam - 1, diam - 1), fill=255)
    canvas.paste(av, (cx - radius, cy - radius), mask)


def _erase_placeholder_names(
    canvas: Image.Image,
    cx: int,
    *,
    hard_half_w: int | None = None,
) -> None:
    """Remove ref User/@User glyphs; rebuild background so glow survives.

    Two passes:
      1) Soft detect near-white / light-gray glyph cores (not pink fade), dilate
         to swallow black stroke + AA, row-median inpaint.
      2) Hard wipe the measured glyph core bbox so any residual ink dies even
         when JPEG noise ducks under the soft threshold.

    Pillow-only (no numpy) so Render free-tier deps stay tiny.
    """
    y0, y1 = REF_NAME_BAND
    x0 = max(0, int(cx) - REF_NAME_HALF_W)
    x1 = min(canvas.size[0], int(cx) + REF_NAME_HALF_W)
    rgba = canvas.convert("RGBA")
    crop = rgba.crop((x0, y0, x1, y1))
    bands = crop.split()
    min_rg = ImageChops.darker(bands[0], bands[1])
    min_rgb = ImageChops.darker(min_rg, bands[2])
    max_rg = ImageChops.lighter(bands[0], bands[1])
    max_rgb = ImageChops.lighter(max_rg, bands[2])
    # Soft mask: near-white OR light-gray low-sat cores (glyph fill + AA).
    # Pink/red fade stays out — those are bright in R but dark in G/B.
    white = Image.new("L", crop.size, 0)
    wp, mn, mx = white.load(), min_rgb.load(), max_rgb.load()
    w, h = crop.size
    for y in range(h):
        for x in range(w):
            a = bands[3].getpixel((x, y)) if len(bands) > 3 else 255
            if a < 8:
                continue
            lo, hi = mn[x, y], mx[x, y]
            sat = hi - lo
            if sat > 50:
                continue  # chromatic = fade / accent, never glyph fill
            if lo >= 130 or (lo >= 90 and hi >= 150):
                wp[x, y] = 255
    # Dilate to swallow black stroke + AA fringe around User/@User
    mask = white
    for _ in range(5):
        mask = mask.filter(ImageFilter.MaxFilter(9))

    # Hard wipe core around this slot (left User narrower than right @User)
    hy0, hy1 = REF_NAME_HARD_BAND
    hw = int(
        hard_half_w
        if hard_half_w is not None
        else REF_NAME_HARD_HALF_W_LEFT
    )
    hx0 = max(0, int(cx) - hw)
    hx1 = min(canvas.size[0], int(cx) + hw)
    mpx = mask.load()
    # Paint hard-rect onto mask in crop-local coords
    for yy in range(max(0, hy0 - y0), min(h, hy1 - y0)):
        for xx in range(max(0, hx0 - x0), min(w, hx1 - x0)):
            mpx[xx, yy] = 255

    # Per-row: solid opaque fill of masked pixels from median of unmasked
    # neighbors (or side samples). Hard-rect rows get a decisive wipe so any
    # baked User/@User ink under the @+letters band is gone before sprites.
    pix = crop.load()
    for row in range(h):
        bg_samples = []
        for col in range(w):
            if mpx[col, row] == 0:
                bg_samples.append(pix[col, row])
        if len(bg_samples) < 8:
            ay = y0 + row
            for sx in range(max(0, x0 - 80), x0):
                bg_samples.append(rgba.getpixel((sx, ay)))
            for sx in range(x1, min(rgba.size[0], x1 + 80)):
                bg_samples.append(rgba.getpixel((sx, ay)))
        if not bg_samples:
            bg = (0, 0, 0, 0)
        else:
            rs = sorted(p[0] for p in bg_samples)
            gs = sorted(p[1] for p in bg_samples)
            bs = sorted(p[2] for p in bg_samples)
            als = sorted((p[3] if len(p) > 3 else 255) for p in bg_samples)
            mid = len(bg_samples) // 2
            bg = (rs[mid], gs[mid], bs[mid], als[mid])
            # Near-black samples → fully transparent void (Nuke) so no grey plate.
            if bg[0] <= 18 and bg[1] <= 18 and bg[2] <= 18 and bg[3] <= 40:
                bg = (0, 0, 0, 0)
        for col in range(w):
            if mpx[col, row] != 0:
                pix[col, row] = bg
    rgba.paste(crop, (x0, y0))
    # Force full overwrite so A=0 clears (Pillow otherwise uses alpha as mask).
    canvas.paste(rgba, (0, 0), Image.new("L", rgba.size, 255))


def _sanitize_at_glyph(img: Image.Image) -> Image.Image:
    """Strip next-letter ink glued to the right of the sticker @ cutout.

    The @ was sliced from @swagbruuu; JPEG/cutout fringe often keeps the leading
    edge of "s" (or similar). That fringe peeks out right after @ under every
    composited username. Zero columns after the first sustained low-ink valley
    past the @ body, then crop transparent right pad.
    """
    px = img.load()
    w, h = img.size
    col_ink = [0] * w
    for x in range(w):
        n = 0
        for y in range(h):
            r, g, b, a = px[x, y]
            if a >= 20 and max(r, g, b) >= 30:
                n += 1
        col_ink[x] = n
    cut = None
    # @ body lives in the left ~85% of a well-cut glyph; search valley after that.
    start = max(0, int(w * 0.55))
    for x in range(start, w - 5):
        if all(col_ink[x + k] <= 8 for k in range(5)):
            cut = x
            break
    if cut is None:
        return img
    keep_w = min(w, cut + 2)
    if keep_w >= w:
        # Still clear any sparse trailing rise beyond valley if width kept.
        return img
    out = img.crop((0, 0, keep_w, h))
    return out


def _load_sticker_glyphs() -> dict:
    """Load RGBA sticker glyphs + advances. @ always from exact cutout."""
    global _STICKER_CACHE
    if _STICKER_CACHE is not None:
        return _STICKER_CACHE

    import json

    meta = {}
    if _GLYPHS_META.is_file():
        meta = json.loads(_GLYPHS_META.read_text())
    metrics = meta.get("metrics") or {}

    glyphs: dict = {"_meta": meta}
    # Map file stem → char
    file_map = {
        "at": "@",
        "a": "a",
        "b": "b",
        "g": "g",
        "r": "r",
        "s": "s",
        "u": "u",
        "w": "w",
    }
    for stem, ch in file_map.items():
        # Prefer cleaned @ cutout (no next-letter fringe) when present.
        if stem == "at":
            fp = _GLYPHS_DIR / "glyph_at_clean.png"
            if not fp.is_file():
                fp = _GLYPHS_DIR / "glyph_at.png"
        else:
            fp = _GLYPHS_DIR / f"glyph_{stem}.png"
        if not fp.is_file():
            continue
        img = Image.open(fp).convert("RGBA")
        if ch == "@":
            img = _sanitize_at_glyph(img)
        m = metrics.get(stem) or {}
        advance = int(m.get("advance") or img.size[0])
        left_bearing = int(m.get("left_bearing") or 0)
        # Advance must not exceed sanitized width (avoids placing letters over
        # cleared right fringe that no longer exists).
        advance = min(advance, img.size[0])
        glyphs[ch] = (img, advance, left_bearing)

    if _STICKER_FULL_PNG.is_file():
        glyphs["_full"] = Image.open(_STICKER_FULL_PNG).convert("RGBA")
    elif _STICKER_REF_JPG.is_file():
        # Fallback: treat ref JPG as opaque white-bg sticker (rare)
        glyphs["_full"] = Image.open(_STICKER_REF_JPG).convert("RGBA")

    if "@" not in glyphs:
        raise FileNotFoundError(
            f"missing exact @ sticker glyph at {_GLYPHS_DIR / 'glyph_at.png'}"
        )

    _STICKER_CACHE = glyphs
    return glyphs


def _normalize_username(name: str) -> str:
    s = str(name).strip()
    if not s:
        s = "User"
    return s if s.startswith("@") else f"@{s}"


def _scale_rgba(img: Image.Image, target_h: int) -> Image.Image:
    if img.size[1] == target_h:
        return img
    scale = target_h / float(img.size[1])
    nw = max(1, int(round(img.size[0] * scale)))
    nh = max(1, int(round(target_h)))
    return img.resize((nw, nh), Image.Resampling.LANCZOS)


def _compose_font_name_only(
    name_no_at: str,
    *,
    font_size: int = REF_NAME_FONT,
    stroke: int = REF_NAME_STROKE,
    tracking: float = REF_NAME_TRACKING,
) -> Image.Image:
    """Draw username letters only (no @) — Plus Jakarta ExtraBold sticker style.

    Preserves Roblox casing. White fill + black stroke. Stroke-then-fill so
    neighbor outlines do not punch letter fills. @ is NEVER drawn here.
    """
    if not name_no_at:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))

    font = load_font(font_size, family="plus_jakarta", weight=800)
    fill = (255, 255, 255, 255)
    stroke_fill = (0, 0, 0, 255)
    pad = stroke + 6

    chars = list(name_no_at)
    advances: list[float] = []
    for ch in chars:
        try:
            advances.append(float(font.getlength(ch)))
        except Exception:
            bb = font.getbbox(ch)
            advances.append(float(bb[2] - bb[0]) if bb else float(font_size))

    probe = Image.new("RGBA", (1, 1))
    dr = ImageDraw.Draw(probe)
    bbox = dr.textbbox((0, 0), "Hg", font=font, stroke_width=stroke)
    content_h = max(1, bbox[3] - bbox[1])
    tracked_w = sum(advances)
    if len(chars) > 1:
        tracked_w += tracking * (len(chars) - 1)

    gw = int(tracked_w) + pad * 2 + stroke * 2 + 2
    gh = int(content_h) + pad * 2 + 2
    sprite = Image.new("RGBA", (gw, gh), (0, 0, 0, 0))
    dr = ImageDraw.Draw(sprite)

    origin_y = pad - bbox[1]
    xs: list[float] = []
    x = float(pad + stroke)
    for i, adv in enumerate(advances):
        xs.append(x)
        x += adv
        if i < len(advances) - 1:
            x += tracking

    for ch, cx in zip(chars, xs):
        dr.text(
            (cx, origin_y),
            ch,
            font=font,
            fill=stroke_fill,
            stroke_width=stroke,
            stroke_fill=stroke_fill,
        )
    for ch, cx in zip(chars, xs):
        dr.text((cx, origin_y), ch, font=font, fill=fill)

    bbox2 = sprite.getbbox()
    if bbox2:
        sprite = sprite.crop(bbox2)
    return sprite


def _compose_sticker_username(
    label: str,
    target_h: int = REF_STICKER_TARGET_H,
    letter_h: int | None = None,
) -> Image.Image:
    """Username sprite — one path for every name (incl. swagbruuu).

    Exact sticker @ cutout + Plus Jakarta ExtraBold letters (no font @).
    Font letters scale to the measured classic-sticker fill height (letter_h),
    not the full outline height, with tight tracking so every username matches
    the original @swagbruuu paste size.
    """
    glyphs = _load_sticker_glyphs()

    if "@" not in glyphs:
        raise RuntimeError("exact sticker @ glyph missing — refuse font @")

    if letter_h is None:
        letter_h = REF_NAME_LETTER_H
    # Keep letter_h proportional if caller overrides target_h.
    if target_h != REF_STICKER_TARGET_H:
        letter_h = max(1, int(round(target_h * 314 / REF_STICKER_NATIVE_H)))

    at_sprite, _adv, _bear = glyphs["@"]
    at_img = _scale_rgba(at_sprite, target_h)
    core = label[1:] if label.startswith("@") else label
    name_img = _compose_font_name_only(core)
    # Match sticker letter *fill* height — NOT full outline.
    if name_img.size[1] != letter_h:
        name_img = _scale_rgba(name_img, letter_h)

    gap = max(1, int(round(target_h * 0.015)))
    total_w = at_img.size[0] + gap + name_img.size[0]
    total_h = max(at_img.size[1], name_img.size[1])
    canvas = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
    ay = (total_h - at_img.size[1]) // 2
    ny = (total_h - name_img.size[1]) // 2
    canvas.alpha_composite(at_img, (0, ay))
    canvas.alpha_composite(name_img, (at_img.size[0] + gap, ny))
    return canvas



def _cover_and_draw_names(
    canvas: Image.Image,
    donor_name: str,
    receiver_name: str,
    tier: str,
) -> None:
    """Erase baked User/@User and draw @names under avatars (sticker or font)."""
    geom = _avatar_geom(tier)
    left_c = geom["left"]
    right_c = geom["right"]
    # Left baked label is "User"; right is wider "@User" — hard wipe both.
    _erase_placeholder_names(
        canvas, left_c[0], hard_half_w=REF_NAME_HARD_HALF_W_LEFT
    )
    _erase_placeholder_names(
        canvas, right_c[0], hard_half_w=REF_NAME_HARD_HALF_W_RIGHT
    )

    if canvas.mode != "RGBA":
        rgba = canvas.convert("RGBA")
    else:
        rgba = canvas

    for name, cx in ((donor_name, left_c[0]), (receiver_name, right_c[0])):
        label = _normalize_username(name)
        sprite = _compose_sticker_username(label, REF_STICKER_TARGET_H)
        tw, th = sprite.size
        x = int(round(cx - tw / 2))
        y = int(round(REF_NAME_MID_Y - th / 2))
        rgba.alpha_composite(sprite, (x, y))

    if canvas is not rgba:
        canvas.paste(rgba)
    else:
        # ensure caller sees updates (in-place on RGBA)
        pass


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
    geom = _avatar_geom(resolved)
    left_r = int(geom.get("left_r", geom.get("r", REF_AVATAR_R)))
    right_r = int(geom.get("right_r", geom.get("r", REF_AVATAR_R)))
    left_cover = int(geom.get("left_cover", left_r))
    right_cover = int(geom.get("right_cover", right_r))
    _paste_circular_avatar(
        canvas, donor_av, geom["left"], left_r, cover_radius=left_cover
    )
    _paste_circular_avatar(
        canvas, recv_av, geom["right"], right_r, cover_radius=right_cover
    )
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
