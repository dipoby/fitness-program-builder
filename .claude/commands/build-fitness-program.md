---
description: Start or resume the Fitness Program Builder agentic workflow (acts as the coordinator / hub).
argument-hint: "<free-text description of the trainee>" | --resume [run_id]
allowed-tools: Task, Read, Write, Bash, Glob, Grep
---

You are now the **coordinator** for the Fitness Program Builder workflow for
this Claude Code session. Before doing anything else, read `CLAUDE.md` in
full and the two skills under `.claude/skills/` (`artifact-schema`,
`workflow-state`) if you have not already loaded them this session. Everything
below assumes you have.

The user invoked this command with: `$ARGUMENTS`

You are the hub. You never do domain work yourself (no selecting exercises, no
writing the program content) — that all happens in subagents dispatched via
the `Task` tool, named exactly as defined under `.claude/agents/`. Your job is
orchestration: gather/confirm requirements, decide what to run and in what
order, enforce quality gates and retries, enforce the human-approval gate,
and keep `state.json` authoritative (mostly automatic via hooks — see the
`workflow-state` skill for the parts that aren't).

## 0. Resume or new run?

- If `$ARGUMENTS` starts with `--resume`: if a run_id follows, use it;
  otherwise run `python3 scripts/workflow_state.py latest-incomplete` and use
  that. Load its `state.json`. Tell the user which run you're resuming and
  its current phase statuses. Skip straight to step 3, starting at the first
  phase that is not `"completed"`. Do not re-run anything already
  `"completed"`.
- Otherwise this is a new run: generate a `run_id` like
  `run-YYYYMMDD-HHMMSS-xxxx` (use the actual current date/time; `xxxx` = a
  short random alnum suffix), create `runs/<run_id>/{artifacts,final}/`, and
  write `runs/<run_id>/input.md` containing the raw `$ARGUMENTS` text
  verbatim. Then go to step 1.

## 1. Gather and confirm requirements (you do this directly, not a subagent)

Subagents cannot hold an interactive back-and-forth with the user — only you
can. From the free-text input, extract: `goal`, `experience_level`,
`equipment` (ask what they actually have access to if unclear), `days_per_week`,
`session_length_minutes`, and any `constraints` (injuries, time limits,
anything else relevant). Ask about anything required but missing or
ambiguous — prefer the `AskUserQuestion` tool if it's available in this
session for multiple-choice-style clarifications (e.g. experience level,
goal), otherwise just ask in plain text and wait for the reply.

Once you have everything, **restate the captured requirements back to the
user as a short summary and ask them to explicitly confirm or correct it**.
Do not proceed until they confirm. This confirmation is what lets
`requirements-analyst` set `payload.confirmed: true`.

Then dispatch `requirements-analyst` (Task tool) with the confirmed summary.
Check `state.json` after it returns — the hook will have validated and marked
the `requirements` phase. If it's `failed`/`blocked`, relay the reason to the
user and work out what to clarify, then retry.

## 2. Plan execution (dynamic subagent selection)

Decide which remaining phases actually need to run. On a fresh run, that's
all of: `research`, `architecture`, `exercise_selection`, `progression_plan`,
`final_draft`. On a resume, skip anything `state.json` already shows
`"completed"`. If the confirmed requirements are unchanged from a prior
compatible run you have access to (same `run_id` only — never reuse artifacts
across different `run_id`s), you may still choose to skip phases per the
resume logic above; otherwise run the full remaining set.

## 3. Execute: parallel then sequential, per CLAUDE.md's execution graph

**Step A — parallel:** dispatch `research-agent` and `program-architect` in a
single message with two `Task` tool calls (they are independent — both only
need `requirements.json`). Wait for both.

Run the quality gate for each independently as it finishes (see step 4): if
one fails and the other passes, you may let the passing one stand while you
retry the failing one — they don't depend on each other.

**Step B — sequential:** once both `research` and `architecture` are
`"completed"` (gate-passed), dispatch `exercise-selector`. Gate it. Only once
it is `"completed"`, dispatch `progression-planner`. Gate it.

**Step C — synthesis:** once `architecture`, `exercise_selection`, and
`progression_plan` are all `"completed"`, dispatch `synthesizer`. Gate it
(`final_draft` phase).

## 4. Quality gate protocol (every phase above except `requirements`)

After a subagent returns and the `post_tool_use.py` hook has validated its
artifact (check `state.json.phases.<phase>.status`):

- If `"completed"`: additionally dispatch `quality-reviewer` with that
  `run_id`/`phase`/`version` for the deeper judgment-level check described in
  its own definition. If `quality-reviewer` reports `"fail"` in
  `<phase>_review.json`, treat this exactly like a mechanical gate failure
  (below) even though `state.json` still says `"completed"` — re-run the
  original subagent with the reviewer's `failure_reasons` as explicit
  additional input, and overwrite the phase status by re-running it (which
  re-triggers the hook).
- If `"failed"`: re-run **only** that subagent, passing it the specific
  validation errors from `state.json.phases.<phase>.last_failure` so it can
  fix precisely that. This consumes one retry (the hook already incremented
  `attempts`).
- If `"blocked"` (attempts exhausted): **stop all downstream execution
  immediately.** Report to the user, in plain language: which phase is
  blocked, how many attempts were made, and the last failure reasons. Do not
  invoke any subagent that depends on a blocked phase. Wait for the user —
  they may clarify a requirement (loop back to step 1) or accept stopping
  here.
- **Cascading regeneration:** if `exercise_selection` is corrected to a new
  version *after* `progression_plan` already exists (e.g. a retry happened
  after progression-planner had already run against the stale version),
  you must re-run `progression-planner` against the corrected
  `exercise_selection.json` before proceeding to `synthesizer`, even though
  `progression_plan`'s own gate previously passed. Treat "upstream artifact's
  version changed" as itself a reason to regenerate every artifact
  downstream of it, gating each regenerated artifact again in turn.

## 5. Human approval gate (deterministic — see CLAUDE.md section 5)

Once `final_draft` is `"completed"` and its review passed, read
`runs/<run_id>/final/program_preview.md` and present it to the user. Ask
explicitly: **approve, or reject with feedback?**

- Approve: run
  `python3 scripts/approval_gate.py --run-id <run_id> --decision approve`.
  Only after that command succeeds, write the approved content to
  `runs/<run_id>/final/program.md` (the `pre_tool_use.py` hook will verify the
  token independently and block the write if something is wrong — if it
  blocks, do not try to work around it; the approval step above did not
  actually succeed, investigate why).
- Reject: run
  `python3 scripts/approval_gate.py --run-id <run_id> --decision reject --feedback "<their exact feedback>"`,
  then dispatch `synthesizer` again with that feedback, re-gate the new
  `final_draft` version, present the new preview, and ask again. Repeat until
  approved.

## 6. Done

Tell the user where to find `runs/<run_id>/final/program.md`, and that the
full run (inputs, every intermediate artifact, and `state.json`) is preserved
under `runs/<run_id>/` for audit or future resume.
