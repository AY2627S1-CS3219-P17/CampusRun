#!/usr/bin/env bash
# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
# Scope: AI-generated D3 demo of the errand lifecycle and its credit operations through the gateway: registration
#        and wallets, reserve, racing accepts, transfer, a repeated completion, the credit worker stopped and
#        restarted, expiry and release, and the credit audit.
# Author review: <to be completed by author>
#
# Runs against the full stack (docker compose up --build), from the repository root:
#
#     order-service/scripts/demo.sh            # all steps, without stopping
#     order-service/scripts/demo.sh --pause    # wait for Enter before each step (for presenting)
#
# It registers three new students (A requests, B and C are couriers) and creates errands for them, so it can be run
# any number of times. Needs curl, jq and python3. For a faster expiry step, set ORDER_SWEEP_SECONDS=5 in the root
# .env before starting the stack (the default sweep is every 30 seconds).
# Bash only: zsh treats some names specially (e.g. `path` is tied to PATH), so re-run under bash if started otherwise
if [ -z "${BASH_VERSION:-}" ]; then exec bash "$0" "$@"; fi
set -euo pipefail

API=${API:-http://localhost:8080/api}
PAUSE=false
[[ "${1:-}" == "--pause" ]] && PAUSE=true
PASSWORD='Demo-pass-123!'
SUFFIX=$(python3 -c 'import secrets; print(secrets.token_hex(3))')
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

# ---------------------------------------------------------------- helpers

BOLD=$(printf '\033[1m'); PLAIN=$(printf '\033[0m')

step() {
  echo
  if $PAUSE; then read -r -p "${BOLD}[Enter] $1${PLAIN} "; else printf '%s%s%s\n' "$BOLD" "$1" "$PLAIN"; fi
}

# api METHOD ROUTE TOKEN [JSON]: prints the body; the status code goes to $WORK/status
api() {
  local method=$1 route=$2 token=$3 body=${4:-}
  local args=(-s -o "$WORK/body" -w '%{http_code}' -X "$method" -H "Authorization: Bearer $token")
  [[ -n "$body" ]] && args+=(-H 'Content-Type: application/json' -d "$body")
  curl "${args[@]}" "$API$route" > "$WORK/status"
  cat "$WORK/body"
}

last_status() { cat "$WORK/status"; }

register() {  # register NAME -> prints a token
  local name="demo_${1}_$SUFFIX"
  curl -s -f -X POST "$API/users/auth/register" -H 'Content-Type: application/json' \
    -d "{\"email\":\"$name@u.nus.edu\",\"username\":\"$name\",\"password\":\"$PASSWORD\"}" > /dev/null
  curl -s -f -X POST "$API/users/auth/login" --data-urlencode "username=$name" \
    --data-urlencode "password=$PASSWORD" | jq -r .access_token
}

user_id() { api GET /users/users/me "$1" | jq -r .id; }

balances() {  # balances "LABEL TOKEN" ...
  for pair in "$@"; do
    read -r label token <<< "$pair"
    api GET /credits/wallets/me "$token" \
      | jq -r --arg who "$label" '"    \($who): \(.status) — available \(.available // "-"), reserved \(.reserved // "-")"'
  done
}

show() {  # show TOKEN ERRAND_ID
  api GET "/orders/$2" "$1" \
    | jq -r '"    errand \(.id): \(.state), credits \(.creditStatus)\(if .creditRejection then " (\(.creditRejection))" else "" end), courier \(.courierName // "none")"'
}

wait_for() {  # wait_for TOKEN ERRAND_ID JQ_CONDITION DESCRIPTION
  local token=$1 errand=$2 condition=$3 what=$4
  for _ in $(seq 1 120); do
    if api GET "/orders/$errand" "$token" | jq -e "$condition" > /dev/null; then
      echo "    → $what"
      return
    fi
    sleep 1
  done
  echo "    ✗ timed out waiting for: $what" >&2
  exit 1
}

wait_for_wallet() {
  for _ in $(seq 1 60); do
    [[ $(api GET /credits/wallets/me "$1" | jq -r .status) == ACTIVE ]] && return
    sleep 0.5
  done
  echo "    ✗ the wallet was never opened; is credit-worker running?" >&2
  exit 1
}

create_errand() {  # create_errand TOKEN TITLE CREDITS -> prints the errand id
  local deliver_by
  deliver_by=$(python3 -c 'from datetime import datetime, timedelta, UTC; print((datetime.now(UTC) + timedelta(hours=1)).isoformat())')
  api POST /orders "$1" "$(jq -n --arg title "$2" --argjson credits "$3" --argjson supplier "$SUPPLIER_ID" \
    --arg by "$deliver_by" '{title: $title, supplierId: $supplier, building: "COM3", floor: "1",
      description: "Main entrance", latitude: 1.29494, longitude: 103.77438, deliverBy: $by, credits: $credits}')" \
    | jq -r .id
}

# ------------------------------------------------------------------- demo

step "1. Register three students. Each wallet opens with the initial credits, asynchronously (OpenWallet over RabbitMQ)."
A=$(register a); B=$(register b); C=$(register c)
for t in "$A" "$B" "$C"; do wait_for_wallet "$t"; done
balances "A $A" "B $B" "C $C"
SUPPLIER_ID=$(api GET "/suppliers/?pageSize=1" "$A" | jq -r '.items[0].id')

step "2. A requests an errand for 15 credits. It starts OPEN with credits PENDING; the Credit Service reserves them."
ERRAND=$(create_errand "$A" "Collect printed notes" 15)
show "$A" "$ERRAND"
wait_for "$A" "$ERRAND" '.creditStatus == "HELD"' "credits HELD: now visible to couriers in Explore"
balances "A $A"

step "3. B and C accept at the same moment: exactly one wins, the other gets 409."
curl -s -o /dev/null -w '%{http_code}' -X POST -H "Authorization: Bearer $B" "$API/orders/$ERRAND/accept" > "$WORK/b" &
curl -s -o /dev/null -w '%{http_code}' -X POST -H "Authorization: Bearer $C" "$API/orders/$ERRAND/accept" > "$WORK/c" &
wait
echo "    B: $(cat "$WORK/b"), C: $(cat "$WORK/c")"
if [[ $(cat "$WORK/b") == 200 ]]; then COURIER=$B; COURIER_LABEL=B; else COURIER=$C; COURIER_LABEL=C; fi
show "$A" "$ERRAND"

step "4. The courier picks up and delivers; A confirms. The reserved credits are transferred to the courier."
api POST "/orders/$ERRAND/pickup" "$COURIER" > /dev/null
api POST "/orders/$ERRAND/deliver" "$COURIER" > /dev/null
api POST "/orders/$ERRAND/complete" "$A" > /dev/null
show "$A" "$ERRAND"
wait_for "$A" "$ERRAND" '.creditStatus == "TRANSFERRED"' "credits TRANSFERRED"
balances "A $A" "$COURIER_LABEL $COURIER"

step "5. A confirms again: refused, and nobody is paid twice."
api POST "/orders/$ERRAND/complete" "$A" | jq -r '"    \(.detail)"'
echo "    status $(last_status)"
balances "A $A" "$COURIER_LABEL $COURIER"

step "6. The credit worker stops; a second errand is completed meanwhile. The order completes at once; the transfer waits in RabbitMQ."
SECOND=$(create_errand "$A" "Bring lunch" 10)
wait_for "$A" "$SECOND" '.creditStatus == "HELD"' "credits HELD"
api POST "/orders/$SECOND/accept" "$COURIER" > /dev/null
api POST "/orders/$SECOND/pickup" "$COURIER" > /dev/null
api POST "/orders/$SECOND/deliver" "$COURIER" > /dev/null
docker compose stop credit-worker > /dev/null 2>&1
api POST "/orders/$SECOND/complete" "$A" > /dev/null
sleep 2
show "$A" "$SECOND"
echo "    Credit commands waiting in RabbitMQ:"
docker compose exec -T rabbitmq rabbitmqctl -q list_queues name messages \
  | awk '$1 == "credit-service.commands" { print "      " $1 ": " $2 " message(s)" }'
balances "A $A" "$COURIER_LABEL $COURIER"

step "7. The credit worker starts again: the waiting transfer is applied, and the courier is paid."
docker compose start credit-worker > /dev/null 2>&1
wait_for "$A" "$SECOND" '.creditStatus == "TRANSFERRED"' "credits TRANSFERRED"
balances "A $A" "$COURIER_LABEL $COURIER"

step "8. An accepted errand passes its deadline: the sweeper expires it and A's credits are released."
THIRD=$(create_errand "$A" "Pick up a parcel" 20)
wait_for "$A" "$THIRD" '.creditStatus == "HELD"' "credits HELD"
api POST "/orders/$THIRD/accept" "$COURIER" > /dev/null
balances "A $A"
echo "    Moving errand $THIRD's deadline into the past (instead of waiting for it):"
docker compose exec -T order-db sh -c \
  "psql -q -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -c \"UPDATE errands SET deliver_by = now() - interval '1 minute' WHERE id = $THIRD\""
wait_for "$A" "$THIRD" '.state == "EXPIRED"' "EXPIRED by the sweeper"
wait_for "$A" "$THIRD" '.creditStatus == "RELEASED"' "credits RELEASED"
balances "A $A" "$COURIER_LABEL $COURIER"

step "9. The credit audit: balances match the ledger, and no credits were created or lost."
docker compose exec -T credit-worker credit-audit \
  | jq -r '"    ok: \(.ok), wallets: \(.wallets), allocated: \(.totalAllocated), in circulation: \(.totalInCirculation)\n    problems: \(.problems)"'
