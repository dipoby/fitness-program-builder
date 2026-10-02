#!/usr/bin/env python3
"""
PreToolUse hook for the Fitness Program Builder workflow.

Registered in .claude/settings.json for the Bash, Write, and Edit tools.
Reads the standard Claude Code PreToolUse JSON payload from stdin:
  {"tool_name": "...", "tool_input": {...}, ...}

Enforces two things, independent of what the model believes it has done:

1. Blocks Bash commands that try to read/exfiltrate secrets (.env, API keys,
   private keys, dumping the environment) -- see CLAUDE.md section 9.
2. Blocks any Write/Edit to runs/<run_id>/final/program.(md|html|pdf) unless
   scripts/approval_gate.py independently verifies a valid, non-stale human
   approval token for that exact run -- see CLAUDE.md section 5.

Exit code 0  -> allow the tool call.
Exit code 2  -> block the tool call; stderr text is surfaced to the model as
                the reason, so it can self-correct (e.g. go get approval first).
Any other / malformed input fails OPEN (exit 0) so a hook bug can't wedge the
whole session -- the quality gates and approval gate are the real enforcement;
this hook is defense in depth.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

SECRET_COMMAND_PATTERNS = [
    re.compile(r"\bcat\b[^|&;\n]*\.env\b"),
    re.compile(r"\bprintenv\b"),
    re.compile(r"(^|[;&|]\s*)env\s*($|[;&|])"),
    re.compile(r"\bset\b\s*\|\s*grep", re.IGNORECASE),
    re.compile(r"ANTHROPIC_API_KEY"),
    re.compile(r"\.pem\b"),
    re.compile(r"id_rsa\b"),
    re.compile(r"\bcat\b[^|&;\n]*credentials"),
]

FINAL_OUTPUT_PATTERN = re.compile(r"runs[/\\](?P<run_id>[^/\\]+)[/\\]final[/\\]program\.(md|html|pdf)$")


def _block(reason: str) -> None:
    sys.stderr.write(reason + "\n")
    sys.exit(2)


def _allow() -> None:
    sys.exit(0)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        _allow()
        return

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}

    if tool_name == "Bash":
        command = tool_input.get("command", "") or ""
        for pattern in SECRET_COMMAND_PATTERNS:
            if pattern.search(command):
                _block(
                    "Blocked by pre_tool_use hook: this Bash command looks like it tries to "
                    f"read or print secrets/credentials (matched pattern: {pattern.pattern!r}). "
                    "This workflow must never expose .env or API keys. "
                    f"Command was: {command!r}"
                )
        _allow()
        return

    if tool_name in ("Write", "Edit"):
        file_path = (tool_input.get("file_path") or "").replace("\\", "/")
        match = FINAL_OUTPUT_PATTERN.search(file_path)
        if match:
            run_id = match.group("run_id")
            try:
                import approval_gate  # noqa: PLC0415
                valid = approval_gate.verify(run_id)
            except Exception as exc:  # pragma: no cover - defense in depth
                _block(
                    f"Blocked by pre_tool_use hook: could not verify human approval for run "
                    f"'{run_id}' ({exc}). Refusing to write the final output without a "
                    f"verifiable approval token."
                )
                return
            if not valid:
                _block(
                    f"Blocked by pre_tool_use hook: writing the final output for run "
                    f"'{run_id}' requires a verified human-approval token in state.json, "
                    f"recomputed over the CURRENT runs/{run_id}/artifacts/final_draft.json. "
                    f"None was found, it doesn't match, or final_draft.json changed since "
                    f"approval was granted. Present the preview to the user, get an explicit "
                    f"approve/reject decision, then run: "
                    f"python3 scripts/approval_gate.py --run-id {run_id} --decision approve "
                    f"before writing runs/{run_id}/final/program.*"
                )
                return
        _allow()
        return

    _allow()


if __name__ == "__main__":
    main()
