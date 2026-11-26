#!/usr/bin/env bash
# Checks how .github/workflows/deploy.yml wires deploy/apply-caddy.sh into the rollout.
# Run: bash deploy/tests/deploy-wiring.test.sh [path/to/deploy.yml]
set -euo pipefail

wf=${1:-"$(cd "$(dirname "$0")/../.." && pwd)/.github/workflows/deploy.yml"}
failures=0
# check NAME COMMAND...: passes when COMMAND succeeds.
check() {
  local name=$1
  shift
  if "$@"; then echo "ok   $name"; else echo "FAIL $name"; failures=$((failures + 1)); fi
}

# The Roll out step's script: lines after "script: |" in the "Roll out" step, up to the next step.
script=$(awk '
  /- name: Roll out/ { in_step = 1 }
  in_step && /^      - name:/ && !/Roll out/ { in_step = 0 }
  in_step && /script: \|/ { in_script = 1; next }
  in_step && in_script { print }
' "$wf")
line_of() { { grep -nF -- "$1" <<<"$script" || true; } | head -1 | cut -d: -f1; }
# Line A comes before line B (both present).
before() { [ -n "$1" ] && [ -n "$2" ] && [ "$1" -lt "$2" ]; }
# The command sits on a line of its own (no `|| true`, no `&&` chain that hides a failure).
alone() { grep -E "^[[:space:]]*$1[[:space:]]*\$" <<<"$script" >/dev/null; }
in_workflow() { grep -E -- "$1" "$wf" >/dev/null; }

validate=$(line_of "bash apply-caddy.sh validate")
apply=$(line_of "bash apply-caddy.sh apply")
up=$(line_of " up -d --build")
ready=$(line_of "health/detailed")

check "Roll out script found" test -n "$script"
check "script stops on the first error (set -e)" alone "set -e"
check "validate runs before up -d" before "$validate" "$up"
check "apply runs after up -d" before "$up" "$apply"
check "apply runs before the readiness check" before "$apply" "$ready"
check "validate failure is not swallowed" alone "bash apply-caddy\.sh validate"
check "apply failure is not swallowed" alone "bash apply-caddy\.sh apply"
check "apply-caddy.sh is copied to the server" in_workflow "source: .*deploy/apply-caddy\.sh"
check "files are copied in place (overwrite: true)" in_workflow "^[[:space:]]+overwrite: true"

if [ "$failures" -gt 0 ]; then
  echo "$failures check(s) failed" >&2
  exit 1
fi
echo "all checks passed"
