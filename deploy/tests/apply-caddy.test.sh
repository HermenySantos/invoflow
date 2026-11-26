#!/usr/bin/env bash
# Tests deploy/apply-caddy.sh against a fake `docker`. Run: bash deploy/tests/apply-caddy.test.sh
set -euo pipefail

script="$(cd "$(dirname "$0")/.." && pwd)/apply-caddy.sh"
failures=0

# Fake docker. State lives in $WORK:
#   ctr_caddyfile   what the running container sees at /etc/caddy/Caddyfile (absent = not running)
#   calls           one line per docker invocation
# Knobs: RUN_RC (throwaway container fails to start), VALIDATE_RC, RELOAD_RC, RECREATE_RC, RECREATE_STARTS (1 = new container comes up).
make_fake_docker() {
  mkdir -p "$WORK/bin"
  cat > "$WORK/bin/docker" <<'FAKE'
#!/usr/bin/env bash
echo "$*" >> "$WORK/calls"
args=" $* "
case "$args" in
  *" run --rm --no-deps -T caddy caddy version "*) exit "${RUN_RC:-0}" ;;
  *" run --rm --no-deps -T caddy caddy validate "*) exit "${VALIDATE_RC:-0}" ;;
  *" exec -T caddy sha256sum "*)
    [ -f "$WORK/ctr_caddyfile" ] || exit 1
    sha256sum "$WORK/ctr_caddyfile" | cut -d' ' -f1 ;;
  *" exec -T caddy caddy reload "*) exit "${RELOAD_RC:-0}" ;;
  *" up -d --force-recreate --no-deps caddy "*)
    rm -f "$WORK/ctr_caddyfile"
    [ "${RECREATE_STARTS:-1}" = 1 ] && cp Caddyfile "$WORK/ctr_caddyfile"
    exit "${RECREATE_RC:-0}" ;;
  *" logs "*) echo "(caddy logs)" ;;
  *) echo "fake docker: unexpected: $*" >&2; exit 99 ;;
esac
FAKE
  chmod +x "$WORK/bin/docker"
}

# scenario NAME MODE CONTAINER_VIEW EXPECTED_RC EXPECTED_TEXT [MUST_NOT_CALL] -- VAR=VALUE...
scenario() {
  local name=$1 mode=$2 view=$3 want_rc=$4 want_text=$5 forbid=${6:-}
  shift 6 || shift $#
  WORK=$(mktemp -d)
  export WORK
  make_fake_docker
  (cd "$WORK" && echo "new config" > Caddyfile)
  case "$view" in
    same) cp "$WORK/Caddyfile" "$WORK/ctr_caddyfile" ;;
    stale) echo "old config" > "$WORK/ctr_caddyfile" ;;
    down) ;;
  esac
  local out rc=0
  out=$(cd "$WORK" && env "$@" PATH="$WORK/bin:$PATH" APPLY_CADDY_SLEEP=0 APPLY_CADDY_TRIES=3 bash "$script" "$mode" 2>&1) || rc=$?
  local ok=1
  [ "$rc" = "$want_rc" ] || ok=0
  grep -qF -- "$want_text" <<<"$out" || ok=0
  if [ -n "$forbid" ] && grep -qF -- "$forbid" "$WORK/calls" 2>/dev/null; then ok=0; fi
  if [ "$ok" = 1 ]; then
    echo "ok   $name"
  else
    echo "FAIL $name (rc=$rc, want $want_rc)"; printf "     %s\n" "$out"
    failures=$((failures + 1))
  fi
  rm -rf "$WORK"
}

scenario "valid Caddyfile passes"                 validate same 0 "new Caddyfile is valid"            ""                 --
scenario "invalid Caddyfile fails, no recreate"   validate same 1 "is invalid"                        "force-recreate"   -- VALIDATE_RC=1
scenario "docker problem: says the Caddyfile was not checked" validate same 1 "the new Caddyfile was not checked and the running caddy keeps its current config" "caddy validate" -- RUN_RC=1
scenario "docker problem: warns not to restart caddy"   validate same 1 "don't restart caddy until a deploy validates them" "caddy validate" -- RUN_RC=1
scenario "same file in container: reload"         apply    same 0 "caddy reloaded"                    "force-recreate"   --
scenario "stale file in container: recreate"      apply    stale 0 "caddy recreated"                  "caddy reload"     --
scenario "reload fails: recreate"                 apply    same 0 "caddy recreated"                   ""                 -- RELOAD_RC=1
scenario "container down: recreate"               apply    down 0 "caddy recreated"                   ""                 --
scenario "recreate fails: deploy fails with logs" apply    stale 1 "(caddy logs)"                     ""                 -- RECREATE_RC=1 RECREATE_STARTS=0
scenario "new container never comes up: fails"    apply    stale 1 "caddy failed to apply"            ""                 -- RECREATE_STARTS=0
scenario "no argument: usage"                     ""       same 2 "usage:"                            ""                 --

if [ "$failures" -gt 0 ]; then
  echo "$failures scenario(s) failed" >&2
  exit 1
fi
echo "all scenarios passed"
