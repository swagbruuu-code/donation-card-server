"""Flask card server for Hazem-style donation Discord posts.

Burst-safe flow (game → this server → Discord DonateLogs webhook):
  POST /render  JSON {
      donorId, receiverId, donorName, receiverName,
      amount, tier, accentHex, content?, webhookUrl
  }
  → validate, enqueue render+Discord job on a thread pool
  → return immediately { "ok": true, "mode": "accepted", "jobId": "..." }
  → worker renders PNG and multipart-posts to webhookUrl (retries on 429/5xx)

Sync mode (tests / debugging): POST /render?sync=1 waits for Discord post
  → { "ok": true, "mode": "posted" }

Also:
  GET  /health  /ping
  GET  /jobs/<jobId>
  POST /render-only  → returns PNG bytes (for local testing)
  GET  /cards/<id>.png
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from threading import Lock, Thread
from zoneinfo import ZoneInfo

import requests
from flask import Flask, jsonify, request, send_file

from card_render import render_card_png_bytes, parse_accent, format_amount

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("card-server")

app = Flask(__name__)

CARDS_DIR = Path(__file__).resolve().parent / "generated"
CARDS_DIR.mkdir(exist_ok=True)
CARD_TTL_SEC = int(os.environ.get("CARD_TTL_SEC", "600"))
PUBLIC_BASE = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
LONDON = ZoneInfo("Europe/London")

RENDER_WORKERS = int(os.environ.get("RENDER_WORKERS", "8"))
DISCORD_RETRIES = int(os.environ.get("DISCORD_RETRIES", "4"))
# Serialize Discord posts so burst traffic does not 429-drop messages.
DISCORD_MIN_INTERVAL = float(os.environ.get("DISCORD_MIN_INTERVAL", "0.35"))

_lock = Lock()
_meta: dict[str, float] = {}
_jobs: dict[str, dict] = {}
_jobs_lock = Lock()

_render_pool = ThreadPoolExecutor(max_workers=RENDER_WORKERS, thread_name_prefix="render")
_discord_q: Queue = Queue()
_discord_last_post = 0.0
_discord_rate_lock = Lock()


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


def _set_job(job_id: str, **fields) -> None:
    with _jobs_lock:
        job = _jobs.get(job_id) or {"id": job_id}
        job.update(fields)
        job["updatedAt"] = time.time()
        _jobs[job_id] = job
        # Bound memory: keep last 200 jobs
        if len(_jobs) > 200:
            oldest = sorted(_jobs.items(), key=lambda kv: kv[1].get("createdAt", 0))[:50]
            for k, _ in oldest:
                _jobs.pop(k, None)


def _discord_post_with_retries(
    webhook_url: str,
    content: str,
    color: int,
    png: bytes,
    footer: str,
) -> tuple[bool, str]:
    """Post to Discord with rate-limit spacing and retries. Never silently drop."""
    global _discord_last_post
    last_err = "unknown"
    for attempt in range(1, DISCORD_RETRIES + 1):
        with _discord_rate_lock:
            gap = time.time() - _discord_last_post
            if gap < DISCORD_MIN_INTERVAL:
                time.sleep(DISCORD_MIN_INTERVAL - gap)
            _discord_last_post = time.time()
        try:
            resp = post_discord_multipart(
                webhook_url, content, color, png, footer_text=footer
            )
            if resp.status_code in (200, 204):
                return True, f"discord {resp.status_code}"
            if resp.status_code == 429:
                try:
                    retry_after = float(resp.json().get("retry_after", 1.0))
                except Exception:
                    retry_after = float(resp.headers.get("Retry-After", "1") or 1)
                last_err = f"429 retry_after={retry_after}"
                log.warning("Discord 429 attempt %s: sleep %.2fs", attempt, retry_after)
                time.sleep(min(max(retry_after, 0.5), 10.0))
                continue
            last_err = f"discord {resp.status_code}: {resp.text[:200]}"
            if resp.status_code >= 500:
                time.sleep(min(0.5 * attempt, 3.0))
                continue
            # 4xx other than 429 — retry once then give up
            if attempt < DISCORD_RETRIES:
                time.sleep(0.4 * attempt)
                continue
            return False, last_err
        except requests.RequestException as exc:
            last_err = str(exc)
            log.warning("Discord post attempt %s failed: %s", attempt, exc)
            time.sleep(min(0.5 * attempt, 3.0))
    return False, last_err


def _process_job(job_id: str, data: dict) -> None:
    _set_job(job_id, status="rendering")
    fields = _payload_fields(data)
    content = _build_content(data)
    color = _accent_int(data)
    footer = format_donated_footer()
    webhook = (
        data.get("webhookUrl")
        or data.get("webhook_url")
        or os.environ.get("DONATE_LOGS_WEBHOOK", "")
    )
    try:
        png = render_card_png_bytes(**fields)
    except Exception as exc:
        log.exception("render failed job=%s", job_id)
        _set_job(job_id, status="error", error=f"render: {exc}")
        return

    if not webhook:
        cid = _save_card(png)
        image_url = f"{PUBLIC_BASE}/cards/{cid}.png" if PUBLIC_BASE else None
        _set_job(
            job_id,
            status="hosted" if image_url else "error",
            mode="hosted",
            cardId=cid,
            imageUrl=image_url,
            error=None if image_url else "no webhookUrl and no PUBLIC_BASE_URL",
        )
        return

    _set_job(job_id, status="posting")
    ok, detail = _discord_post_with_retries(webhook, content, color, png, footer)
    if ok:
        _set_job(job_id, status="posted", mode="posted", detail=detail, footer=footer)
        log.info("job %s posted ok", job_id)
    else:
        cid = _save_card(png)
        image_url = f"{PUBLIC_BASE}/cards/{cid}.png" if PUBLIC_BASE else None
        _set_job(
            job_id,
            status="error",
            mode="discord_error",
            error=detail,
            imageUrl=image_url,
            cardId=cid,
        )
        log.error("job %s discord failed: %s", job_id, detail)


def _discord_queue_worker() -> None:
    """Optional serial path unused when jobs run fully in render pool.
    Kept as a no-op consumer so Queue imports stay meaningful if we switch.
    """
    while True:
        try:
            _discord_q.get(timeout=1.0)
        except Empty:
            continue


def enqueue_render(data: dict) -> str:
    job_id = uuid.uuid4().hex[:12]
    _set_job(job_id, status="queued", mode="accepted", createdAt=time.time())
    _render_pool.submit(_process_job, job_id, data)
    return job_id


@app.get("/health")
@app.get("/ping")
def health():
    with _jobs_lock:
        queued = sum(1 for j in _jobs.values() if j.get("status") in ("queued", "rendering", "posting"))
    return jsonify(
        {
            "ok": True,
            "service": "hazem-card-server",
            "renderWorkers": RENDER_WORKERS,
            "inflightJobs": queued,
        }
    )


@app.get("/jobs/<job_id>")
def get_job(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify({"ok": True, "job": job})


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
    """Main entry used by Roblox LogService CardRenderUrl.

    Default (async): enqueue and return 200 mode=accepted immediately so burst
    donations never block on PNG+Discord. Worker posts Discord with retries.

    ?sync=1: wait for render+Discord (for local tests).
    """
    data = request.get_json(force=True, silent=True) or {}
    fields = _payload_fields(data)
    if fields["amount"] < 100_000:
        return jsonify({"ok": False, "error": "amount below hazem threshold"}), 400

    sync = str(request.args.get("sync", "")).lower() in ("1", "true", "yes")
    job_id = enqueue_render(data)

    if not sync:
        return jsonify({"ok": True, "mode": "accepted", "jobId": job_id}), 200

    # Sync wait (tests): poll job up to 90s
    deadline = time.time() + 90
    while time.time() < deadline:
        with _jobs_lock:
            job = dict(_jobs.get(job_id) or {})
        status = job.get("status")
        if status == "posted":
            return jsonify(
                {"ok": True, "mode": "posted", "jobId": job_id, "footer": job.get("footer")}
            )
        if status in ("hosted",):
            return jsonify(
                {
                    "ok": bool(job.get("imageUrl")),
                    "mode": "hosted",
                    "jobId": job_id,
                    "imageUrl": job.get("imageUrl"),
                    "cardId": job.get("cardId"),
                    "error": job.get("error"),
                }
            ), (200 if job.get("imageUrl") else 503)
        if status == "error":
            return jsonify(
                {
                    "ok": False,
                    "mode": job.get("mode") or "error",
                    "jobId": job_id,
                    "error": job.get("error"),
                    "imageUrl": job.get("imageUrl"),
                }
            ), 502
        time.sleep(0.1)

    return jsonify({"ok": False, "mode": "timeout", "jobId": job_id, "error": "sync wait timeout"}), 504


def main():
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8787"))
    print(f"hazem-card-server on http://{host}:{port}")
    print(f"POST /render  (async accept, {RENDER_WORKERS} render workers)")
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
