"""Mutation tests for deploy_wiring.py: each edit of the real deploy.yml must turn it red,
and each harmless reformat must keep it green. An edit that no longer applies fails loudly,
so this file has to be updated whenever deploy.yml drifts.

Run: python deploy/tests/deploy_wiring_mutations.py   (needs PyYAML)
"""

from __future__ import annotations

import re
import sys

from deploy_wiring import DEFAULT_WORKFLOW, check

V = "            bash apply-caddy.sh validate\n"
A = "            bash apply-caddy.sh apply\n"
UP = "            docker compose -f docker-compose.prod.yml --env-file .env up -d --build --remove-orphans\n"
SET_E = "            set -e\n"
COPY_IF = "      - name: Copy stack files\n        if: env.DEPLOY_HOST != ''\n"
ROLL_IF = "      - name: Roll out\n        if: env.DEPLOY_HOST != ''\n"
OVERWRITE = "          overwrite: true\n"
READY_FOR = "            for i in $(seq 1 30); do\n"


def sub(old, new):
    def edit(text):
        if old not in text:
            raise LookupError(f"mutation no longer applies; deploy.yml changed: {old.strip()!r}")
        return text.replace(old, new, 1)
    return edit


def chain(*edits):
    def edit(text):
        for e in edits:
            text = e(text)
        return text
    return edit


def move_copy_after_rollout(text):
    copy = re.search(r"      - name: Copy stack files\n(?:        .*\n|\n)+?(?=      - name: )", text)
    if not copy:
        raise LookupError("copy step not found")
    text = text.replace(copy.group(0), "", 1)
    return text.rstrip("\n") + "\n" + copy.group(0).rstrip("\n") + "\n"


def move_overwrite_to_rollout(text):
    text = sub(OVERWRITE, "")(text)
    return sub("          envs: IMAGE_TAG,GHCR_TOKEN,GHCR_USER\n",
               "          envs: IMAGE_TAG,GHCR_TOKEN,GHCR_USER\n" + OVERWRITE)(text)


MUST_FAIL = {
    "validate deleted": sub(V, ""),
    "validate || true": sub(V, V.rstrip("\n") + " || true\n"),
    "validate || echo": sub(V, V.rstrip("\n") + " || echo 'validate failed'\n"),
    "validate; true": sub(V, V.rstrip("\n") + "; true\n"),
    "validate commented out": sub(V, "            # bash apply-caddy.sh validate\n"),
    "validate wrapped in if !": sub(V, "            if ! bash apply-caddy.sh validate; then echo warn; fi\n"),
    "validate in a dead branch": sub(V, "            if false; then\n" + V + "            fi\n"),
    "validate after up -d": chain(sub(V, ""), sub(UP, UP + V)),
    "comment decoy, validate after up -d": chain(sub(V, "            # bash apply-caddy.sh validate runs later\n"), sub(UP, UP + V)),
    "validate with deploy/ prefix": sub(V, "            bash deploy/apply-caddy.sh validate\n"),
    "exit 0 before validate": sub(V, "            exit 0\n" + V),
    "set +e after set -e": sub(SET_E, SET_E + "            set +e\n"),
    "set -e after validate": chain(sub(SET_E, ""), sub(V, V + SET_E)),
    "set -e removed": sub(SET_E, ""),
    "apply deleted": sub(A, ""),
    "apply || true": sub(A, A.rstrip("\n") + " || true\n"),
    "apply backgrounded": sub(A, A.rstrip("\n") + " &\n"),
    "apply before up -d": chain(sub(A, ""), sub(UP, A + UP)),
    "apply after the readiness check": chain(sub(A, ""), sub("            exit 1\n", A + "            exit 1\n")),
    "continue-on-error on rollout": sub(ROLL_IF, ROLL_IF + "        continue-on-error: true\n"),
    "continue-on-error on copy": sub(COPY_IF, COPY_IF + "        continue-on-error: true\n"),
    "if: false on copy": sub(COPY_IF, "      - name: Copy stack files\n        if: false\n"),
    "if: false on rollout": sub(ROLL_IF, "      - name: Roll out\n        if: false\n"),
    "if: ${{ false }} on rollout": sub(ROLL_IF, "      - name: Roll out\n        if: ${{ false }}\n"),
    "copy step after rollout": move_copy_after_rollout,
    "overwrite removed": sub(OVERWRITE, ""),
    "overwrite: false": sub(OVERWRITE, "          overwrite: false\n"),
    "overwrite moved to the rollout step": move_overwrite_to_rollout,
    "apply-caddy.sh dropped from source": sub("deploy/Caddyfile,deploy/apply-caddy.sh,", "deploy/Caddyfile,"),
}

MUST_PASS = {
    "unchanged": lambda t: t,
    "rollout step renamed": sub("      - name: Roll out\n", "      - name: Rollout to production\n"),
    "copy step renamed": sub("      - name: Copy stack files\n", "      - name: Ship files\n"),
    "./apply-caddy.sh": chain(sub(V, "            bash ./apply-caddy.sh validate\n"), sub(A, "            ./apply-caddy.sh apply\n")),
    "up flags reordered": sub(UP, "            docker compose -f docker-compose.prod.yml --env-file .env up --remove-orphans -d --build\n"),
    "up without --build": sub(UP, "            docker compose -f docker-compose.prod.yml --env-file .env up -d --remove-orphans\n"),
    "dc alias for up": sub(UP, '            dc() { docker compose -f docker-compose.prod.yml --env-file .env "$@"; }\n            dc up -d --build --remove-orphans\n'),
    'overwrite: "true"': sub(OVERWRITE, '          overwrite: "true"\n'),
    "set -euo pipefail": sub(SET_E, "            set -euo pipefail\n"),
    "set -o errexit": sub(SET_E, "            set -o errexit\n"),
    "trailing comment on validate": sub(V, V.rstrip("\n") + "  # refuse a bad Caddyfile\n"),
    "script: |-": sub("          script: |\n", "          script: |-\n"),
}


def main() -> int:
    base = DEFAULT_WORKFLOW.read_text()
    bad = 0
    for expect_ok, cases in ((False, MUST_FAIL), (True, MUST_PASS)):
        for name, edit in cases.items():
            try:
                results = check(edit(base))
            except LookupError as exc:
                print(f"STALE {name}: {exc}")
                bad += 1
                continue
            ok = all(r[1] for r in results)
            if ok == expect_ok:
                why = "" if ok else "; ".join(n for n, passed, _ in results if not passed)
                print(f"ok    {'green' if ok else 'red  '}  {name}" + (f"  ({why})" if why else ""))
            else:
                print(f"WRONG {'green' if ok else 'red  '}  {name} (expected {'green' if expect_ok else 'red'})")
                bad += 1
    print(f"{len(MUST_FAIL)} must-fail, {len(MUST_PASS)} must-pass, {bad} wrong")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
