# CLAUDE.md — Fitness Program Builder Agentic Workflow

This file documents the workflow architecture, execution rules, and conventions that
every coordinator run and subagent invocation in this repository must follow. It is
loaded automatically by Claude Code for any session rooted in this repository.

## 1. Domain

**Fitness Program Builder** — analyzes a user's fitness goals, training experience,
available equipment, and constraints (injuries, time, schedule) and produces a
structured, periodized training program as a human-readable document.

## 2. Architecture: model-driven hub-and-spoke

- **Hub (coordinator):** the main Claude Code thread started by the
  `/build-fitness-program` slash command (see `.claude/commands/build-fitness-program.md`).
  The coordinator never does domain work itself. It only: gathers/confirms
  requirements, plans which subagents are needed, dispatches subagents (`Task` tool),
  enforces quality gates, enforces the human-approval gate, and persists workflow
  state after every phase.
- **Spokes (subagents):** single-responsibility agents defined under `.claude/agents/`.
  Each subagent owns exactly one artifact type and writes it to
  `runs/<run_id>/artifacts/<phase>.json` using the shared envelope defined in the
  `artifact-schema` skill. Subagents must not write outside their owned artifact.

### Subagent roster (dynamic selection)

| Subagent | Owns artifact | Depends on |
|---|---|---|
| `requirements-analyst` | `requirements.json` | — (root) |
| `research-agent` | `research.json` | `requirements` |
| `program-architect` | `architecture.json` | `requirements` |
| `exercise-selector` | `exercise_selection.json` | `architecture`, `research` |
| `progression-planner` | `progression_plan.json` | `exercise_selection` |
| `quality-reviewer` | `*_review.json` (per gate) | the artifact under review |
| `synthesizer` | `final_draft.json` + `final/program.md` | all validated artifacts above |

The coordinator selects subagents **dynamically** based on confirmed requirements —
e.g. if the user has no equipment constraints and a prior cached `research.json`
for an equivalent profile already exists and passed its gate in this run folder,
`research-agent` may be skipped on resume (see §6). The roster above is the
superset; not every run necessarily invokes every row from scratch.

### Execution graph (sequential vs parallel)

```
requirements-analyst
        │
        ├──────────────┐
        ▼              ▼
  research-agent   program-architect     ← PARALLEL (independent, both depend only on requirements)
        │              │
        └──────┬───────┘
               ▼
       exercise-selector                 ← SEQUENTIAL (depends on both above)
               │
         [quality gate]
               ▼
      progression-planner                ← SEQUENTIAL (depends on exercise_selection)
               │
         [quality gate]
               ▼
          synthesizer
               │
         [quality gate]
               ▼
     HUMAN APPROVAL GATE  ──reject──► synthesizer (revise with feedback) ──► loop
               │ approve
               ▼
     final/program.md (+ optional .html/.pdf)
```

Rule: subagents with no edge between them in this graph (`research-agent` and
`program-architect`) **must** be dispatched in a single `Task` batch (parallel).
Subagents with an edge **must** be dispatched sequentially, and the downstream
subagent must receive the upstream artifact as input context.

## 3. Artifact conventions

All artifacts use the common envelope documented in the `artifact-schema` skill
(`.claude/skills/artifact-schema/SKILL.md`) and are validated against the JSON
Schemas in `schemas/` via `scripts/validate_artifact.py`. An artifact write that
fails schema or domain-consistency validation is **not** considered complete and
must not unblock downstream subagents.

## 4. Quality gates and retries

- Every artifact listed in §2's table (except `requirements.json`, which is
  confirmed interactively instead) passes through `quality-reviewer` before any
  downstream subagent consumes it.
- Retry limit: **3 attempts per phase** (1 initial + 2 retries), tracked in
  `state.json` as `phases.<phase>.attempts`.
- On gate failure, the coordinator re-runs **only** the failing subagent, passing
  the reviewer's specific failure reasons as additional input.
- If a phase is retried and its output changes materially, **all already-produced
  downstream artifacts that depended on it must be regenerated** (not just
  re-validated) before dependent execution continues. Example: if `exercise_selection`
  is revised after `progression_plan` already exists from a stale version,
  `progression_plan` must be regenerated against the corrected `exercise_selection`.
- If attempts for a phase reach the retry limit without passing the gate, the
  coordinator marks that phase `blocked` in `state.json`, **stops all downstream
  execution**, and reports the blocked phase, the attempt history, and the last
  failure reasons to the user in plain language. It does not fabricate a result.

## 5. Human approval gate (deterministic)

- After `synthesizer` produces `final_draft.json` and a readable
  `final/program_preview.md`, the coordinator presents the preview to the user and
  asks for an explicit decision: **approve** or **reject with feedback**.
- Approval is **not** taken on the model's word. The coordinator must invoke
  `scripts/approval_gate.py --run-id <id> --decision approve` which computes a
  verification token (hash of run_id + exact final_draft.json content + timestamp)
  and writes it into `state.json.human_approval`. The `pre_tool_use.py` hook
  (`.claude/hooks/pre_tool_use.py`) independently inspects `state.json` before
  allowing any `Write` to `runs/<run_id>/final/program.md` (or `.html`/`.pdf`) and
  **blocks the write at the tool layer** if the token is missing, malformed, or
  does not match a hash recomputed over the current `final_draft.json`. This means
  approval is enforced outside the model's own reasoning.
- On rejection, feedback is stored in `state.json.human_approval.feedback_history`,
  `synthesizer` is re-run with that feedback, a new `final_draft.json` is produced,
  and the approval step repeats.

## 6. State persistence and resume

- Workflow state lives at `runs/<run_id>/state.json` and is the single source of
  truth for what has been completed. See the `workflow-state` skill for the exact
  schema and the helper library `scripts/workflow_state.py`.
- The `post_tool_use.py` hook automatically updates `state.json` whenever a
  subagent writes an artifact file under `runs/<run_id>/artifacts/`, so state
  tracking does not depend on the model remembering to do it.
- On invocation, `/build-fitness-program` first scans `runs/*/state.json` for a
  run matching the given `--resume <run_id>` argument (or the most recent
  non-`completed` run if `--resume` is passed with no id). It loads the state,
  skips every phase already `completed` and passing its gate, and continues from
  the first `pending`, `failed`, or `blocked` phase. Completed work, including
  prior artifacts and the confirmed-requirements record, is never redone.

## 7. External information sources

The workflow must not answer from model memory alone:

- **Web search** (`research-agent`) is used for current, goal-specific training
  guidance (e.g. evidence-based rep ranges for the user's stated goal, injury
  precautions) that benefits from being checked rather than recalled.
- **MCP server** `exercise-db` (registered in `.mcp.json`, implementation in
  `mcp_servers/exercise_db/`) is the authoritative source for the exercise
  catalogue, equipment tags, and equipment-substitution lookups. `exercise-selector`
  must call its tools (`search_exercises`, `get_equipment_alternatives`,
  `list_equipment_categories`) rather than inventing exercise names or substitutions.

## 8. Reusable skills

- `artifact-schema` — the common artifact envelope, naming conventions, and how to
  validate before considering a phase done. Used by every subagent and by
  `quality-reviewer`.
- `workflow-state` — how to read, update, and resume from `state.json`. Used by the
  coordinator and referenced by both hooks.

## 9. Hooks

- `pre_tool_use.py` — (a) blocks the human-approval bypass described in §5; (b)
  blocks `Bash` calls that attempt to read `.env`/credential files or print
  environment variables, to keep secrets out of transcripts and artifacts.
- `post_tool_use.py` — (a) runs `scripts/validate_artifact.py` against the
  matching schema immediately after any artifact `Write`, recording pass/fail into
  `state.json`; (b) appends a timestamped entry to `state.json.log`.

## 10. Output

The final deliverable is always written to `runs/<run_id>/final/program.md`
(Markdown, required). The same content may additionally be rendered to
`program.html` and/or `program.pdf` on request. The document structure (section
order and headings) is fixed — see `schemas/final_program.schema.json` and the
template in the `synthesizer` agent definition — so repeated runs with equivalent
input produce a comparably structured document.
