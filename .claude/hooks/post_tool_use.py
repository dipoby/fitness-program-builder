#!/usr/bin/env python3
"""
PostToolUse hook for the Fitness Program Builder workflow.

Registered in .claude/settings.json for the Write tool. Reads the standard
Claude Code PostToolUse JSON payload from stdin:
  {"tool_name": "...", "tool_input": {...}, "tool_response": {...}, ...}

Whenever a subagent writes an artifact under runs/<run_id>/artifacts/*.json,
this hook -- automatically, without relying on the model remembering to do it:

1. Runs scripts/validate_artifact.py against the matching JSON Schema plus the
   domain-consistency checks (CLAUDE.md section 3-4).
2. Updates runs/<run_id>/state.json: increments the phase's attempt counter,
   sets its status to completed/failed/blocked, records failure reasons, and
   appends a log entry -- see the workflow-state skill.

For *_review.json artifacts written by quality-reviewer, it validates the
review envelope itself but does NOT touch phase/attempt tracking (reviews are
not one of the six primary phases).

Exit code 0 -> validation passed (or nothing to validate); stdout JSON summary.
Exit code 2 -> validation failed; stderr explains why, so the model sees it
               immediately and knows whether to retry, revise a downstream
               artifact too, or (if attempts are exhausted) stop and report.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import workflow_state as ws  # noqa: E402
import validate_artifact as va  # noqa: E402

ARTIFACT_PATH_PATTERN = re.compile(
    r"runs[/\\](?P<run_id>[^/\\]+)[/\\]artifacts[/\\](?P<stem>[A-Za-z_]+)\.json$"
)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if payload.get("tool_name") != "Write":
        sys.exit(0)

    tool_input = payload.get("tool_input", {}) or {}
    file_path = (tool_input.get("file_path") or "").replace("\\", "/")
    match = ARTIFACT_PATH_PATTERN.search(file_path)
    if not match:
        sys.exit(0)  # not an artifact write; nothing for this hook to do

    run_id = match.group("run_id")
    stem = match.group("stem")
    artifact_abs_path = REPO_ROOT / "runs" / run_id / "artifacts" / f"{stem}.json"
    if not artifact_abs_path.exists():
        sys.exit(0)

    result = va.validate_artifact_file(artifact_abs_path)
    rel_artifact = f"artifacts/{stem}.json"

    is_review = stem.endswith("_review")
    if not is_review and stem in ws.PHASE_ORDER:
        try:
            if result["result"] == "pass":
                ws.set_phase(run_id, stem, "completed", artifact=rel_artifact, increment_attempts=True)
            else:
                ws.set_phase(
                    run_id, stem, "failed",
                    artifact=rel_artifact, failure_reasons=result["errors"],
                    increment_attempts=True,
                )
        except FileNotFoundError:
            pass  # state.json not initialized yet (e.g. ad-hoc test write) -- validation result still reported below
    elif is_review:
        try:
            state = ws.load_state(run_id)
            ws.append_log(state, f"quality-reviewer wrote {stem}: {result['result']}")
            ws.save_state(run_id, state)
        except FileNotFoundError:
            pass

    print(json.dumps(result, indent=2))
    sys.exit(0 if result["result"] == "pass" else 2)


if __name__ == "__main__":
    main()
