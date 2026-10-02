#!/usr/bin/env python3
"""
Deterministic human-approval gate.

Approval of the final program is never inferred from the model's own words.
This script is the *only* way `state.json.human_approval` is written, and the
token it writes is a hash over the run_id + the exact bytes of
`final_draft.json` at approval time + the approval timestamp. `pre_tool_use.py`
independently recomputes that hash before allowing the final `program.md`
(or `.html`/`.pdf`) to be written, so a stale approval (e.g. the model edited
final_draft.json after approval without re-running this script) is rejected
rather than silently honored.

CLI:
  python3 scripts/approval_gate.py --run-id <id> --decision approve
  python3 scripts/approval_gate.py --run-id <id> --decision reject --feedback "..."
  python3 scripts/approval_gate.py --run-id <id> --verify     # used by the hook
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import workflow_state as ws  # noqa: E402


def _final_draft_path(run_id: str) -> Path:
    return REPO_ROOT / "runs" / run_id / "artifacts" / "final_draft.json"


def _canonical_bytes(run_id: str) -> bytes:
    p = _final_draft_path(run_id)
    with open(p, "rb") as f:
        raw = f.read()
    # Re-serialize canonically so incidental whitespace/formatting changes don't
    # matter, but any real content change invalidates the token.
    obj = json.loads(raw)
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _compute_token(run_id: str, approved_at: str) -> str:
    h = hashlib.sha256()
    h.update(run_id.encode("utf-8"))
    h.update(_canonical_bytes(run_id))
    h.update(approved_at.encode("utf-8"))
    return h.hexdigest()


def approve(run_id: str) -> dict:
    approved_at = datetime.now(timezone.utc).isoformat()
    token = _compute_token(run_id, approved_at)
    draft = json.loads(_final_draft_path(run_id).read_text(encoding="utf-8"))

    state = ws.load_state(run_id)
    state["human_approval"] = {
        "status": "approved",
        "token": token,
        "token_approved_at": approved_at,
        "token_source_phase_version": draft.get("version"),
        "feedback_history": state["human_approval"].get("feedback_history", []),
    }
    ws.append_log(state, f"human approval granted for final_draft version {draft.get('version')}")
    if all(state["phases"][p]["status"] == "completed" for p in ws.PHASE_ORDER):
        state["status"] = "completed"
    ws.save_state(run_id, state)
    return state


def reject(run_id: str, feedback: str) -> dict:
    state = ws.load_state(run_id)
    state["human_approval"]["status"] = "rejected"
    state["human_approval"]["token"] = None
    state["human_approval"]["token_approved_at"] = None
    state["human_approval"].setdefault("feedback_history", []).append({
        "ts": datetime.now(timezone.utc).isoformat(),
        "feedback": feedback,
    })
    ws.append_log(state, f"human approval rejected: {feedback!r}")
    ws.save_state(run_id, state)
    return state


def verify(run_id: str) -> bool:
    """Re-derive whether the currently-stored approval token is still valid
    for the current contents of final_draft.json. Used by pre_tool_use.py."""
    try:
        state = ws.load_state(run_id)
    except FileNotFoundError:
        return False
    approval = state.get("human_approval", {})
    if approval.get("status") != "approved" or not approval.get("token"):
        return False
    recomputed = _compute_token(run_id, approval["token_approved_at"])
    return recomputed == approval["token"]


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--decision", choices=["approve", "reject"])
    parser.add_argument("--feedback", default="")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    if args.verify:
        ok = verify(args.run_id)
        print(json.dumps({"run_id": args.run_id, "approval_valid": ok}))
        return 0 if ok else 1

    if args.decision == "approve":
        state = approve(args.run_id)
    elif args.decision == "reject":
        if not args.feedback:
            print(json.dumps({"error": "--feedback is required when --decision reject"}))
            return 1
        state = reject(args.run_id, args.feedback)
    else:
        print(json.dumps({"error": "must pass --decision approve|reject or --verify"}))
        return 1

    print(json.dumps(state["human_approval"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
