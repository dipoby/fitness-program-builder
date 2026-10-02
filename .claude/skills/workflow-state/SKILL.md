---
name: workflow-state
description: Use at the start of every /build-fitness-program invocation (new run or resume), and whenever you need to check phase status, retry counts, or the human-approval state. Defines the state.json contract and the CLI for reading/writing it safely.
---

# Workflow State skill

`runs/<run_id>/state.json` is the single source of truth for what has been
completed in a run. It is what makes the workflow resumable after an
interruption and what the quality-gate retry logic is tracked against. Treat
it as authoritative over your own memory of what you "already did" --
especially on resume, where you have no memory of a prior session at all.

Never hand-edit `state.json` with the `Edit` tool. Always go through
`scripts/workflow_state.py` (for phase status) or `scripts/approval_gate.py`
(for the human-approval block) so that updates are atomic and consistent. In
practice you will rarely need to call `workflow_state.py` yourself for the six
primary phases -- `post_tool_use.py` does it automatically right after you
write an artifact. You *do* need it directly for: starting a new run,
checking status before deciding what to run next, and resuming.

## 1. Starting a new run

```bash
python3 scripts/workflow_state.py init <run_id> --input "<the user's raw request>"
```

Creates `runs/<run_id>/state.json` with all six phases `pending` and
`human_approval.status = "pending"`. Use a run id of the form
`run-YYYYMMDD-HHMMSS-xxxx` (short random suffix) so runs sort chronologically
and never collide.

## 2. Checking status

```bash
python3 scripts/workflow_state.py show <run_id>
```

Read `phases.<phase>.status` (`pending|running|completed|failed|blocked`) and
`phases.<phase>.attempts` / `max_attempts` before deciding whether to run a
phase, retry it, or stop and report a block to the user.

## 3. Resuming

```bash
python3 scripts/workflow_state.py latest-incomplete
```

Prints the run_id of the most recently updated run whose `status` is not yet
`"completed"` (empty output if none). The `/build-fitness-program --resume`
command uses this when invoked with no explicit run id. Once you have the
run_id, `show` it, find the first phase that is not `"completed"`
(`workflow_state.first_actionable_phase` if calling from Python, or just scan
the `phases` object in the printed JSON), and continue from there. Do **not**
re-run subagents for phases already `"completed"` -- that would waste work and
risk producing a different artifact than the one downstream phases were
already validated against.

## 4. Human approval

Never set `human_approval` fields yourself. Always:

```bash
python3 scripts/approval_gate.py --run-id <id> --decision approve
# or
python3 scripts/approval_gate.py --run-id <id> --decision reject --feedback "<what to change>"
```

See the `pre_tool_use.py` hook and CLAUDE.md section 5 for why this has to go
through the script rather than a direct state.json edit: the script computes a
verification token tied to the exact bytes of `final_draft.json`, and the hook
independently re-checks that token before allowing the final document to be
written. A hand-written `"status": "approved"` would not carry a valid token
and would still be blocked.

## 5. Blocked phases

If `phases.<phase>.attempts >= phases.<phase>.max_attempts` and the gate still
failed, the hook already set that phase (and the overall run) to `"blocked"`.
When you see this: stop executing anything downstream of that phase, and
report to the user, in plain language: which phase is blocked, how many
attempts were made, and the `last_failure` reasons from `state.json`. Do not
fabricate a passing artifact to move past a block.
