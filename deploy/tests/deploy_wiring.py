"""Check how .github/workflows/deploy.yml wires deploy/apply-caddy.sh into the rollout.

Run: python deploy/tests/deploy_wiring.py [path/to/deploy.yml]   (needs PyYAML)

Steps are found by what they do, not by name:
  copy step     appleboy/scp-action whose `source` ships deploy/Caddyfile
  rollout step  appleboy/ssh-action whose script runs `compose up -d`
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

DEFAULT_WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/deploy.yml"

KEYWORD_OPENERS = {"if", "for", "while", "until", "case"}
KEYWORD_CLOSERS = {"fi", "done", "esac"}
# Words after which the next word is in command position.
COMMAND_SEPARATORS = {";", "&", "|", "&&", "||", "then", "do", "else", "elif", "{", "(", "!"}
VALIDATE = re.compile(r"^(?:bash\s+|sh\s+)?(?:\./)?apply-caddy\.sh\s+validate$")
APPLY = re.compile(r"^(?:bash\s+|sh\s+)?(?:\./)?apply-caddy\.sh\s+apply$")
UP = re.compile(r"^(?:docker\s+compose|docker-compose|dc)\b.*\sup(?:\s|$)")


def strip_comment(line: str) -> str:
    """Drop a shell comment (a # that starts a word, outside quotes)."""
    quote = None
    prev = " "
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and (prev.isspace() or prev in ";&|("):
            return line[:i].rstrip()
        prev = ch
    return line.rstrip()


def words(line: str) -> list[str]:
    """Split a shell line into words and operators, ignoring quoted text."""
    out, cur, quote = [], "", None
    i = 0
    while i < len(line):
        ch = line[i]
        if quote:
            cur += ch
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
            cur += ch
        elif ch.isspace():
            if cur:
                out.append(cur)
            cur = ""
        elif ch in ";&|()":
            if cur:
                out.append(cur)
            cur = ""
            two = line[i : i + 2]
            if two in ("&&", "||", ";;"):
                out.append(two)
                i += 1
            else:
                out.append(ch)
        else:
            cur += ch
        i += 1
    if cur:
        out.append(cur)
    return out


def command_words(ws: list[str]) -> list[str]:
    """The words in command position (first word, and the first after each separator)."""
    cmds, at_start = [], True
    for w in ws:
        if at_start:
            cmds.append(w)
        at_start = w in COMMAND_SEPARATORS
    return cmds


class Script:
    """The Roll out script as top-level statements, with errexit tracked line by line."""

    def __init__(self, text: str):
        self.lines = []  # (index, code, top_level, errexit_before, exits_before)
        depth, errexit, exited = 0, False, False
        for idx, raw in enumerate(text.splitlines()):
            code = strip_comment(raw).strip()
            if not code:
                continue
            ws = words(code)
            cmds = command_words(ws)
            # Reserved words count in command position; braces and parens count anywhere
            # outside quotes (`$(...)`, `name() { ...; }`), so one-liners balance out.
            opens = sum(1 for w in cmds if w in KEYWORD_OPENERS) + sum(1 for w in ws if w in ("{", "("))
            closes = sum(1 for w in cmds if w in KEYWORD_CLOSERS) + sum(1 for w in ws if w in ("}", ")"))
            top = depth == 0 and opens == 0 and closes == 0
            self.lines.append((idx, code, top, errexit, exited))
            errexit = self._errexit_after(cmds, ws, errexit)
            if depth == 0 and "exit" in cmds:
                exited = True
            depth = max(0, depth + opens - closes)

    @staticmethod
    def _errexit_after(cmds, ws, state):
        if "set" not in cmds:
            return state
        args = ws[ws.index("set") + 1 :]
        for i, a in enumerate(args):
            if a in ("-o", "+o") and i + 1 < len(args) and args[i + 1] == "errexit":
                state = a == "-o"
            elif re.fullmatch(r"-[a-zA-Z]+", a) and "e" in a:
                state = True
            elif re.fullmatch(r"\+[a-zA-Z]+", a) and "e" in a:
                state = False
        return state

    def find(self, pattern: re.Pattern, top_only=True):
        return [ln for ln in self.lines if pattern.search(ln[1]) and (ln[2] or not top_only)]


def falsy_if(value) -> bool:
    if value is False:
        return True
    if isinstance(value, str):
        v = value.strip()
        m = re.fullmatch(r"\$\{\{\s*(.*?)\s*\}\}", v)
        v = (m.group(1) if m else v).strip().lower()
        return v in ("false", "0", "''", '""', "null")
    return False


def truthy(value) -> bool:
    return value is True or (isinstance(value, str) and value.strip().lower() == "true")


def check(workflow_text: str) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []

    def add(name, ok, why=""):
        results.append((name, bool(ok), "" if ok else why))
        return ok

    try:
        wf = yaml.safe_load(workflow_text)
    except yaml.YAMLError as exc:
        add("deploy.yml is valid YAML", False, str(exc).splitlines()[0])
        return results

    found = None
    for job_id, job in (wf.get("jobs") or {}).items():
        steps = job.get("steps") or []
        copies = [
            i for i, s in enumerate(steps)
            if str(s.get("uses", "")).startswith("appleboy/scp-action")
            and "deploy/Caddyfile" in [p.strip() for p in str((s.get("with") or {}).get("source", "")).split(",")]
        ]
        rollouts = [
            i for i, s in enumerate(steps)
            if str(s.get("uses", "")).startswith("appleboy/ssh-action")
            and Script(str((s.get("with") or {}).get("script", ""))).find(UP)
        ]
        if copies or rollouts:
            found = (job_id, job, steps, copies, rollouts)
            break
    if not add("a copy step (scp-action shipping deploy/Caddyfile) exists", found and found[3], "none found"):
        return results
    job_id, job, steps, copies, rollouts = found
    if not add("a rollout step (ssh-action running compose up -d) exists in the same job", rollouts, "none found"):
        return results
    add("exactly one copy step and one rollout step", len(copies) == 1 and len(rollouts) == 1,
        f"{len(copies)} copy, {len(rollouts)} rollout")
    copy, rollout = steps[copies[0]], steps[rollouts[0]]
    add("the copy step runs before the rollout step", copies[0] < rollouts[0],
        "rollout would validate the old files")

    source = [p.strip() for p in str((copy.get("with") or {}).get("source", "")).split(",")]
    add("the copy step ships deploy/apply-caddy.sh", "deploy/apply-caddy.sh" in source, f"source: {source}")
    add("the copy step writes in place (overwrite: true)", truthy((copy.get("with") or {}).get("overwrite")),
        f"overwrite: {(copy.get('with') or {}).get('overwrite')!r}")

    for label, obj in (("deploy job", job), ("copy step", copy), ("rollout step", rollout)):
        add(f"{label} has no continue-on-error", not obj.get("continue-on-error"),
            f"continue-on-error: {obj.get('continue-on-error')!r}")
        add(f"{label} is not disabled (if: false)", not falsy_if(obj.get("if")), f"if: {obj.get('if')!r}")

    script = Script(str((rollout.get("with") or {}).get("script", "")))
    validates, applies = script.find(VALIDATE), script.find(APPLY)
    ups = script.find(UP)
    ready = script.find(re.compile(r"health/detailed"), top_only=False)

    add("validate runs as a plain top-level command", validates,
        "missing, commented out, wrapped (if/||/;/&) or inside a block")
    add("apply runs as a plain top-level command", applies,
        "missing, commented out, wrapped (if/||/;/&) or inside a block")
    add("compose up -d runs at top level", ups, "missing")
    if validates and ups:
        add("validate runs before compose up -d", validates[0][0] < ups[0][0], "validate comes after up -d")
    if applies and ups:
        add("apply runs after compose up -d", applies[0][0] > ups[0][0], "apply comes before up -d")
    if applies:
        add("apply runs before the readiness check", ready and applies[0][0] < ready[0][0],
            "readiness check missing or before apply")
    for label, hits in (("validate", validates), ("apply", applies)):
        if hits:
            _, _, _, errexit, exited = hits[0]
            add(f"errexit (set -e) is on when {label} runs", errexit,
                "set -e is missing, comes later, or set +e turned it off")
            add(f"nothing exits the script before {label}", not exited, "an exit before it makes it unreachable")
    return results


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT_WORKFLOW
    results = check(path.read_text())
    for name, ok, why in results:
        print(f"{'ok  ' if ok else 'FAIL'} {name}" + (f"  ({why})" if why else ""))
    failed = sum(1 for _, ok, _ in results if not ok)
    if failed:
        print(f"{failed} check(s) failed", file=sys.stderr)
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
