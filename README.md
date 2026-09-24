# Hazem card server (Nuke / Smite / Starfall)

Generates the dual-avatar donation PNG and (preferably) multipart-posts the full
Hazem-style Discord message to your **DonateLogs** webhook.

Used by `LogService:LogDonation` when `CardRenderUrl` is set and amount ≥ 100,000.

## Tiers

| Tier     | Amount        | Accent   |
|----------|---------------|----------|
| Nuke     | ≥ 100,000     | `#FF00F7` |
| Smite    | ≥ 1,000,000   | `#FF0088` |
| Starfall | ≥ 10,000,000  | `#FF0000` |

## Run locally

```bash
cd research/hazem-card-server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Optional: default webhook if game payload omits webhookUrl
# export DONATE_LOGS_WEBHOOK='https://discord.com/api/webhooks/...'

# If you want hosted imageUrl mode instead of server-side Discord post:
# export PUBLIC_BASE_URL='https://your-public-https-host'

python app.py
# listens on 0.0.0.0:8787
```

Generate a PNG without Discord:

```bash
python card_render.py --donor-id 1 --receiver-id 1 \
  --donor-name swagbruuu --receiver-name theman3mad \
  --amount 10000000 --tier Starfall -o /tmp/card.png
```

## Wire into the Roblox place

1. Host this server on a **public HTTPS** URL Roblox `HttpService` can reach
   (ngrok, Cloudflare Tunnel, Fly.io, etc.).
2. In `LogService.module.lua` set:

```lua
local CardRenderUrl = "https://YOUR_HOST/render"
```

3. Paste leading tier emojis when ready:

```lua
local TierLeadingEmoji = {
  Nuke = "",      -- e.g. <:nuke:123>
  Smite = "",
  Starfall = "",
}
```

4. Keep `Webhooks.DonateLogs` as the destination (already in LogService). The
   game sends that URL in the JSON `webhookUrl` field; **do not hardcode a test
   webhook** into the card server unless you set `DONATE_LOGS_WEBHOOK` for local
   experiments.

5. Republish / load the packaged place
   `out/UNLIMITED_DONATION_RUSH_hazem_dono_logs.rbxl`.

## Preferred architecture

```
Game LogDonation (≥100k)
  → POST CardRenderUrl  { donorId, receiverId, donorName, receiverName,
                          amount, tier, accentHex, content, webhookUrl }
  → card server renders PNG
  → multipart POST to webhookUrl:
        content = "@Donor donated **amount** Robux to @Receiver"
        embed.color = tier accent
        embed.image = attachment://donation_card.png
  → { ok: true, mode: "posted" }
```

If `CardRenderUrl` is empty or the request fails, the game falls back to
**text + embed.color only** (still Hazem text format; **no** old `dononoto.png`).

## Local test without spamming prod

```bash
# Terminal A
python app.py

# Terminal B — dry render (no Discord)
curl -s -X POST http://127.0.0.1:8787/render-only \
  -H 'content-type: application/json' \
  -d '{"donorId":1,"receiverId":1,"donorName":"A","receiverName":"B","amount":1000000,"tier":"Smite"}' \
  -o /tmp/smite.png

# Only hit a webhook you own / a throwaway channel — never prod DonateLogs for spam tests.
```

## Payload (from game)

```json
{
  "donorId": 123,
  "receiverId": 456,
  "donorName": "Donor",
  "receiverName": "Receiver",
  "amount": 1000000,
  "tier": "Smite",
  "accentHex": "FF0088",
  "content": "@Donor donated **1,000,000** Robux to @Receiver",
  "webhookUrl": "https://discord.com/api/webhooks/..."
}
```
