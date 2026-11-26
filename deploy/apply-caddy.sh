#!/usr/bin/env bash
# Apply the copied Caddyfile to production Caddy. Run from /opt/invoflow.
#   apply-caddy.sh validate   check the new Caddyfile in a throwaway container (before `up -d`)
#   apply-caddy.sh apply      make the running caddy use it (after `up -d`)
# `up -d` keeps the caddy container when its image and service settings are unchanged,
# and the official image does not watch its config, so a changed Caddyfile needs this.
set -euo pipefail

dc() { docker compose -f docker-compose.prod.yml --env-file .env "$@"; }
caddy_cfg=(--config /etc/caddy/Caddyfile --adapter caddyfile)

validate() {
  # First prove a throwaway caddy container can run at all, so a docker, compose or
  # image problem is not reported as a bad Caddyfile.
  if ! dc run --rm --no-deps -T caddy caddy version; then
    echo "caddy: could not start a caddy container to validate (docker, compose or image problem); the new Caddyfile was not checked and the running caddy keeps its current config." >&2
    echo "caddy: the new files are already on disk, so don't restart caddy until a deploy validates them." >&2
    exit 1
  fi
  # A fresh container sees the file on disk now, even if the copy replaced its inode.
  if ! dc run --rm --no-deps -T caddy caddy validate "${caddy_cfg[@]}"; then
    echo "caddy: the new Caddyfile is invalid; the running caddy keeps its current config" >&2
    exit 1
  fi
  echo "caddy: new Caddyfile is valid"
}

# The running container sees the copied file only if the copy kept the inode
# (a single-file bind mount does not follow a replaced file).
in_sync() {
  local host ctr
  host=$(sha256sum Caddyfile | cut -d' ' -f1)
  ctr=$(dc exec -T caddy sha256sum /etc/caddy/Caddyfile 2>/dev/null | cut -d' ' -f1) || return 1
  [ -n "$ctr" ] && [ "$host" = "$ctr" ]
}

apply() {
  if in_sync && dc exec -T caddy caddy reload "${caddy_cfg[@]}"; then
    echo "caddy reloaded"
    return 0
  fi
  echo "caddy: reload not possible; recreating caddy" >&2
  if dc up -d --force-recreate --no-deps caddy; then
    for _ in $(seq 1 "${APPLY_CADDY_TRIES:-10}"); do
      sleep "${APPLY_CADDY_SLEEP:-1}"
      if in_sync; then
        echo "caddy recreated"
        return 0
      fi
    done
  fi
  echo "caddy failed to apply the new Caddyfile" >&2
  dc logs --tail 50 caddy || true
  exit 1
}

case "${1:-}" in
  validate) validate ;;
  apply) apply ;;
  *) echo "usage: $0 validate|apply" >&2; exit 2 ;;
esac
