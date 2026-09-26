#!/usr/bin/env bash
# Fire 3 parallel /render POSTs; require all 3 Discord-post (status=posted).
set -euo pipefail
BASE="${1:-http://127.0.0.1:8787}"
WEBHOOK="${2:-${DONATE_LOGS_WEBHOOK:-}}"
if [[ -z "$WEBHOOK" ]]; then
  echo "Usage: $0 <baseUrl> <webhookUrl>" >&2
  exit 2
fi
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
echo "Burst test → $BASE (3 parallel)"
for n in 1 2 3; do
  (
    body=$(printf '{"donorId":%d,"receiverId":2,"donorName":"Burst%d","receiverName":"Recv","amount":100000,"tier":"Nuke","accentHex":"FF00F7","content":"`@Burst%d` donated **100,000 Robux** to `@Recv` [burst-test %d]","webhookUrl":"%s"}' "$((3000+n))" "$n" "$n" "$n" "$WEBHOOK")
    curl -sS -o "$TMP/r$n.json" -w "%{http_code} %{time_total}\n" --max-time 15 \
      -X POST "$BASE/render" -H 'Content-Type: application/json' -d "$body" > "$TMP/t$n.txt"
  ) &
done
wait
JOBS=()
for n in 1 2 3; do
  echo -n "accept $n: "; cat "$TMP/t$n.txt"; head -c 200 "$TMP/r$n.json"; echo
  jid=$(python3 -c "import json; print(json.load(open('$TMP/r$n.json'))['jobId'])")
  JOBS+=("$jid")
done
echo "Polling ${JOBS[*]} ..."
deadline=$((SECONDS+90))
while (( SECONDS < deadline )); do
  ok=0
  for jid in "${JOBS[@]}"; do
    st=$(curl -sS "$BASE/jobs/$jid" | python3 -c "import sys,json; print(json.load(sys.stdin)['job']['status'])")
    echo -n "$jid=$st "
    [[ "$st" == posted ]] && ok=$((ok+1))
    [[ "$st" == error ]] && { echo; curl -sS "$BASE/jobs/$jid"; echo; exit 1; }
  done
  echo
  (( ok == 3 )) && { echo "ALL 3 POSTED"; exit 0; }
  sleep 1
done
echo "TIMEOUT"; exit 1
