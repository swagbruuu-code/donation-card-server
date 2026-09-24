"""Flask card server for Hazem-style donation Discord posts.

Preferred flow (game → this server → Discord DonateLogs webhook):
  POST /render  JSON {
      donorId, receiverId, donorName, receiverName,
      amount, tier, accentHex, content?, webhookUrl
  }
  → generate PNG, multipart-post to webhookUrl with content + embed.color
    + embed.footer ("Donated on • …") + attachment
  → { "ok": true, "mode": "posted" }

If webhookUrl is omitted, hosts the PNG briefly and returns:
  { "ok": true, "mode": "hosted", "imageUrl": "http://host/cards/<id>.png" }

Also:
  GET  /health
  POST /render-only  → returns PNG bytes (for local testing)
  GET  /cards/<id>.png
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from threading import Lock
from zoneinfo import ZoneInfo

import requests
from flask import Flask, jsonify, request, send_file

from card_render import render_card_png_bytes, parse_accent, format_amount

app = Flask(__name__)

CARDS_DIR = Path(__file__).resolve().parent / "generated"
CARDS_DIR.mkdir(exist_ok=True)
CARD_TTL_SEC = int(os.environ.get("CARD_TTL_SEC", "600"))
PUBLIC_BASE = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")  # e.g. https://xyz.ngrok.io
LONDON = ZoneInfo("Europe/London")
_lock = Lock()
_meta: dict[str, float] = {}


def format_donated_footer(when: datetime | None = None) -> str:
    """Europe/London local time, matching research samples.

    Example: Donated on • 21/09/2026 10:34 PM
    """
    dt = when or datetime.now(LONDON)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LONDON)
    else:
        dt = dt.astimezone(LONDON)
    hour12 = dt.hour % 12
    if hour12 == 0:
        hour12 = 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return (
        f"Donated on • {dt.day:02d}/{dt.month:02d}/{dt.year} "
        f"{hour12:02d}:{dt.minute:02d} {ampm}"
    )


def _cleanup_old() -> None:
    now = time.time()
    with _lock:
        dead = [k for k, t0 in _meta.items() if now - t0 > CARD_TTL_SEC]
        for k in dead:
            _meta.pop(k, None)
            path = CARDS_DIR / f"{k}.png"
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass


def _save_card(png: bytes) -> str:
    _cleanup_old()
    cid = uuid.uuid4().hex
    (CARDS_DIR / f"{cid}.png").write_bytes(png)
    with _lock:
        _meta[cid] = time.time()
    return cid


def _build_content(data: dict) -> str:
    if isinstance(data.get("content"), str) and data["content"].strip():
        return data["content"]
    donor = data.get("donorName") or data.get("donor_name") or "Donor"
    recv = data.get("receiverName") or data.get("receiver_name") or "Receiver"
    amount = int(data.get("amount") or 0)
    return f"`@{donor}` donated <:robux:1551985051137482762> **{format_amount(amount)} Robux** to `@{recv}`"


def _payload_fields(data: dict) -> dict:
    return {
        "donor_id": int(data.get("donorId") or data.get("donor_id") or 1),
        "receiver_id": int(data.get("receiverId") or data.get("receiver_id") or 1),
        "donor_name": str(data.get("donorName") or data.get("donor_name") or "Donor"),
        "receiver_name": str(data.get("receiverName") or data.get("receiver_name") or "Receiver"),
        "amount": int(data.get("amount") or 0),
        "tier": data.get("tier"),
        "accent_hex": data.get("accentHex") or data.get("accent_hex"),
    }


def _accent_int(data: dict) -> int:
    fields = _payload_fields(data)
    r, g, b = parse_accent(fields["tier"], fields["accent_hex"])
    return (r << 16) + (g << 8) + b


def post_discord_multipart(
    webhook_url: str,
    content: str,
    color: int,
    png: bytes,
    filename: str = "donation_card.png",
    footer_text: str | None = None,
) -> requests.Response:
    footer = footer_text if footer_text is not None else format_donated_footer()
    payload = {
        "content": content,
        "embeds": [
            {
                "color": color,
                "image": {"url": f"attachment://{filename}"},
                "footer": {"text": footer},
            }
        ],
        "allowed_mentions": {"parse": []},
    }
    files = {
        "files[0]": (filename, png, "image/png"),
    }
    return requests.post(
        webhook_url,
        data={"payload_json": json.dumps(payload)},
        files=files,
        timeout=20,
    )


@app.get("/health")
def health():
    return jsonify({"ok": True, "service": "hazem-card-server"})


@app.get("/cards/<cid>.png")
def get_card(cid: str):
    _cleanup_old()
    path = CARDS_DIR / f"{cid}.png"
    if not path.is_file():
        return jsonify({"ok": False, "error": "not found"}), 404
    return send_file(path, mimetype="image/png")


@app.post("/render-only")
def render_only():
    data = request.get_json(force=True, silent=True) or {}
    png = render_card_png_bytes(**_payload_fields(data))
    cid = _save_card(png)
    return send_file(CARDS_DIR / f"{cid}.png", mimetype="image/png")


@app.post("/render")
@app.post("/")
def render():
    """Main entry used by Roblox LogService CardRenderUrl."""
    data = request.get_json(force=True, silent=True) or {}
    fields = _payload_fields(data)
    if fields["amount"] < 100_000:
        return jsonify({"ok": False, "error": "amount below hazem threshold"}), 400

    png = render_card_png_bytes(**fields)
    content = _build_content(data)
    color = _accent_int(data)
    footer = format_donated_footer()
    webhook = data.get("webhookUrl") or data.get("webhook_url") or os.environ.get("DONATE_LOGS_WEBHOOK", "")

    if webhook:
        try:
            resp = post_discord_multipart(webhook, content, color, png, footer_text=footer)
            if resp.status_code >= 300:
                cid = _save_card(png)
                image_url = None
                if PUBLIC_BASE:
                    image_url = f"{PUBLIC_BASE}/cards/{cid}.png"
                return jsonify(
                    {
                        "ok": False,
                        "error": f"discord {resp.status_code}",
                        "discordBody": resp.text[:500],
                        "imageUrl": image_url,
                        "mode": "discord_error",
                    }
                ), 502
            return jsonify({"ok": True, "mode": "posted", "footer": footer})
        except requests.RequestException as exc:
            cid = _save_card(png)
            image_url = f"{PUBLIC_BASE}/cards/{cid}.png" if PUBLIC_BASE else None
            return jsonify(
                {
                    "ok": False,
                    "error": str(exc),
                    "imageUrl": image_url,
                    "mode": "discord_error",
                }
            ), 502

    cid = _save_card(png)
    if not PUBLIC_BASE:
        return jsonify(
            {
                "ok": False,
                "mode": "hosted",
                "cardId": cid,
                "imageUrl": None,
                "error": "no webhookUrl and no PUBLIC_BASE_URL",
                "hint": "Pass webhookUrl (preferred) or set PUBLIC_BASE_URL for hosted imageUrl.",
            }
        ), 503
    return jsonify(
        {
            "ok": True,
            "mode": "hosted",
            "cardId": cid,
            "imageUrl": f"{PUBLIC_BASE}/cards/{cid}.png",
            "footer": footer,
        }
    )


def main():
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8787"))
    print(f"hazem-card-server on http://{host}:{port}")
    print("POST /render  (CardRenderUrl target)")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
