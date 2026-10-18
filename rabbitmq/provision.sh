#!/usr/bin/env bash
# AI Assistance Disclosure:
# Tool: Claude (claude.ai, model: Claude Opus 5.5), date: 2026-10-17
# Scope: AI-generated broker start-up wrapper that creates one RabbitMQ user per service from .env
#        and loads the queues, exchanges and permissions in definitions.json.
# Author review: <to be completed by author>

# Entrypoint for the rabbitmq container (official image, unchanged). It starts the broker as usual,
# then, in the background, creates or updates one user per service and loads definitions.json.
# Runs on every start and is idempotent, so a password changed in .env applies on the next restart.
# The healthcheck only passes once /tmp/campusrun-ready exists, so services never connect too early.
set -euo pipefail

READY=/tmp/campusrun-ready

# name, password env var, tags
SERVICE_USERS=(
  "credit-service RABBITMQ_CREDIT_SERVICE_PASSWORD"
  "user-service RABBITMQ_USER_SERVICE_PASSWORD"
  "order-service RABBITMQ_ORDER_SERVICE_PASSWORD"
)

upsert_user() {
  local name=$1 password=$2
  # rabbitmqctl hangs reading a password from stdin in this image, so it's an argument. That's no
  # extra exposure: anything in this container that can see the process list can read the env too.
  if rabbitmqctl -q list_users --no-table-headers | cut -f1 | grep -qx "$name"; then
    rabbitmqctl -q change_password "$name" "$password" >/dev/null
  else
    rabbitmqctl -q add_user "$name" "$password" >/dev/null
  fi
}

provision() {
  # rabbitmqctl authenticates to the broker with the cookie the broker creates on first boot.
  # Waiting for it (instead of letting rabbitmqctl create one) avoids two different cookies.
  until [ -s /var/lib/rabbitmq/.erlang.cookie ]; do sleep 1; done
  # On a restart the cookie already exists, so also wait until the node answers
  until rabbitmq-diagnostics -q ping >/dev/null 2>&1; do sleep 2; done
  rabbitmqctl -q await_startup --timeout 120

  # Admin for the management UI only; no service connects with it
  upsert_user "$RABBITMQ_ADMIN_USER" "$RABBITMQ_ADMIN_PASSWORD"
  rabbitmqctl -q set_user_tags "$RABBITMQ_ADMIN_USER" administrator
  rabbitmqctl -q set_permissions -p / "$RABBITMQ_ADMIN_USER" ".*" ".*" ".*"

  for entry in "${SERVICE_USERS[@]}"; do
    read -r name var <<<"$entry"
    upsert_user "$name" "${!var:?set $var in .env}"
  done

  # Queues, exchanges, bindings, and what each service user may read, write and publish
  rabbitmqctl -q import_definitions /etc/rabbitmq/definitions.json

  # The image would otherwise keep a guest/guest account reachable from any host
  rabbitmqctl -q delete_user guest >/dev/null 2>&1 || true

  touch "$READY"
  echo "campusrun: broker provisioned"
}

if [ "${1:-}" = "--provision" ]; then
  provision
  exit
fi

rm -f "$READY"
# Same user as the broker, so rabbitmqctl can read its cookie. If provisioning fails,
# stop the broker so the failure is visible rather than leaving it half configured.
( gosu rabbitmq bash "$0" --provision || { echo "campusrun: provisioning failed" >&2; kill 1; } ) &

exec docker-entrypoint.sh rabbitmq-server
