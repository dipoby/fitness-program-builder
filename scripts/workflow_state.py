#!/usr/bin/env python3
"""
Shared workflow-state persistence library.

Single source of truth for `runs/<run_id>/state.json`. Used by:
  - the coordinator (via the `workflow-state` skill instructions, which tell it
    to shell out to this script's CLI rather than hand-edit JSON itself)
  - `.claude/hooks/post_tool_use.py` (auto-updates state after artifact writes)
  - `.claude/hooks/pre_tool_use.py` (reads state to enforce the approval gate)
  - `scripts/approval_gate.py` (reads/writes the human_approval block)

See `.claude/skills/workflow-state/SKILL.md` for the human-readable contract.

CLI usage:
  python3 scripts/workflow_state.py init <run_id> --input "<free text>"
  python3 scripts/workflow_state.py show <run_id>
  python3 scripts/workflow_state.py set-phase <run_id> <phase> <status>
        [--artifact PATH] [--failure "reason one" --failure "reason two"]
  python3 scripts/workflow_state.py latest-incomplete
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = REPO_ROOT / "runs"

PHASE_ORDER = [
    "requirements",
    "research",
    "architecture",
    "exercise_selection",
    "progression_plan",
    "final_draft",
]
MAX_ATTEMPTS_DEFAULT = 3


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def state_path(run_id: str) -> Path:
    return RUNS_DIR / run_id / "state.json"


def load_state(run_id: str) -> dict:
    p = state_path(run_id)
    if not p.exists():
        raise FileNotFoundError(f"no state.json for run_id={run_id!r} at {p}")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(run_id: str, state: dict) -> None:
    p = state_path(run_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = _now()
    tmp = p.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=False)
    tmp.replace(p)  # atomic on POSIX; avoids a half-written state.json on crash


def init_state(run_id: str, input_summary: str) -> dict:
    now = _now()
    state = {
        "run_id": run_id,
        "status": "running",
        "created_at": now,
        "updated_at": now,
        "input_summary": input_summary,
        "phases": {
            phase: {
                "status": "pending",
                "attempts": 0,
                "max_attempts": MAX_ATTEMPTS_DEFAULT,
                "artifact": None,
                "last_failure": None,
            }
            for phase in PHASE_ORDER
        },
        "human_approval": {
            "status": "pending",
            "token": None,
            "token_source_phase_version": None,
            "approved_at": None,
            "feedback_history": [],
        },
        "log": [{"ts": now, "event": f"run {run_id} initialized"}],
    }
    save_state(run_id, state)
    return state


def append_log(state: dict, event: str) -> None:
    state["log"].append({"ts": _now(), "event": event})


def set_phase(
    run_id: str,
    phase: str,
    status: str,
    artifact: str | None = None,
    failure_reasons: list[str] | None = None,
    increment_attempts: bool = False,
) -> dict:
    if phase not in PHASE_ORDER:
        raise ValueError(f"unknown phase {phase!r}, expected one of {PHASE_ORDER}")
    if status not in {"pending", "running", "completed", "failed", "blocked"}:
        raise ValueError(f"unknown status {status!r}")

    state = load_state(run_id)
    entry = state["phases"][phase]
    if increment_attempts:
        entry["attempts"] += 1
    entry["status"] = status
    if artifact is not None:
        entry["artifact"] = artifact
    if failure_reasons is not None:
        entry["last_failure"] = failure_reasons
    elif status == "completed":
        entry["last_failure"] = None

    if status == "blocked" or (status == "failed" and entry["attempts"] >= entry["max_attempts"]):
        entry["status"] = "blocked"
        state["status"] = "blocked"
        append_log(state, f"phase {phase} BLOCKED after {entry['attempts']} attempts: {failure_reasons}")
    else:
        append_log(state, f"phase {phase} -> {status} (attempt {entry['attempts']})")

    if all(state["phases"][p]["status"] == "completed" for p in PHASE_ORDER) and \
       state["human_approval"]["status"] == "approved":
        state["status"] = "completed"

    save_state(run_id, state)
    return state


def latest_incomplete_run() -> str | None:
    if not RUNS_DIR.exists():
        return None
    candidates = []
    for state_file in RUNS_DIR.glob("*/state.json"):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                s = json.load(f)
        except Exception:
            continue
        if s.get("status") != "completed":
            candidates.append((s.get("updated_at", ""), s.get("run_id")))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def first_actionable_phase(state: dict) -> str | None:
    """First phase that is not `completed`, for resume logic."""
    for phase in PHASE_ORDER:
        if state["phases"][phase]["status"] != "completed":
            return phase
    return None  # all phases done; only human_approval / final output may remain


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init")
    p_init.add_argument("run_id")
    p_init.add_argument("--input", default="")

    p_show = sub.add_parser("show")
    p_show.add_argument("run_id")

    p_set = sub.add_parser("set-phase")
    p_set.add_argument("run_id")
    p_set.add_argument("phase")
    p_set.add_argument("status")
    p_set.add_argument("--artifact")
    p_set.add_argument("--failure", action="append", dest="failures")
    p_set.add_argument("--increment-attempts", action="store_true")

    sub.add_parser("latest-incomplete")

    args = parser.parse_args()

    if args.cmd == "init":
        state = init_state(args.run_id, args.input)
        print(json.dumps(state, indent=2))
    elif args.cmd == "show":
        state = load_state(args.run_id)
        print(json.dumps(state, indent=2))
    elif args.cmd == "set-phase":
        state = set_phase(
            args.run_id, args.phase, args.status,
            artifact=args.artifact, failure_reasons=args.failures,
            increment_attempts=args.increment_attempts,
        )
        print(json.dumps(state, indent=2))
    elif args.cmd == "latest-incomplete":
        run_id = latest_incomplete_run()
        print(run_id or "")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
