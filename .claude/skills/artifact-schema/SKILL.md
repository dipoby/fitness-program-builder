---
name: artifact-schema
description: Use whenever you (as any subagent, or the coordinator) are about to write or read a workflow artifact under runs/<run_id>/artifacts/. Defines the common artifact envelope, which schema file governs which phase, and how to self-check an artifact before considering a phase done.
---

# Artifact Schema skill

Every artifact this workflow produces -- regardless of which subagent writes it --
uses the same JSON envelope and lives at `runs/<run_id>/artifacts/<phase>.json`.
This skill is the one place that convention is documented; every subagent
definition refers back to it instead of restating it.

## 1. The envelope

```json
{
  "run_id": "run-20260115-143200-a1b2",
  "phase": "exercise_selection",
  "produced_by": "exercise-selector",
  "version": 1,
  "status": "draft",
  "created_at": "2026-01-15T14:35:02+00:00",
  "payload": { }
}
```

- `run_id` -- the folder name under `runs/`.
- `phase` -- one of: `requirements`, `research`, `architecture`,
  `exercise_selection`, `progression_plan`, `final_draft`, or `<phase>_review`
  for quality-reviewer outputs (e.g. `exercise_selection_review`).
- `produced_by` -- the subagent name that wrote it.
- `version` -- starts at `1`; increment every time this phase is regenerated
  (retry after a gate failure, or revision after upstream changed). Never
  overwrite history silently -- a new version number makes retries legible in
  the artifact itself, not just in `state.json`.
- `status` -- set to `"draft"` when you write it; the quality gate (or the
  `post_tool_use.py` hook, which runs automatically on every artifact `Write`)
  is what ultimately decides whether it becomes effectively validated.
- `payload` -- phase-specific content. See section 2.

## 2. Which schema file governs which phase

| phase | schema file |
|---|---|
| `requirements` | `schemas/requirements.schema.json` |
| `research` | `schemas/research.schema.json` |
| `architecture` | `schemas/program_architecture.schema.json` |
| `exercise_selection` | `schemas/exercise_selection.schema.json` |
| `progression_plan` | `schemas/progression_plan.schema.json` |
| `final_draft` | `schemas/final_program.schema.json` |
| `*_review` | `schemas/review.schema.json` |

Open the relevant schema file before writing a payload for a phase you haven't
produced before in this session -- it documents required fields, enums, and
nesting precisely. Don't guess field names from memory.

## 3. Self-check before you report a phase done

After writing `runs/<run_id>/artifacts/<phase>.json`, the `post_tool_use.py`
hook runs `scripts/validate_artifact.py` on it automatically and updates
`state.json` for you -- you do not need to call it yourself for the six primary
phases. But if you want to check your own work *before* writing the final
version (e.g. while drafting), you can run it directly:

```bash
python3 scripts/validate_artifact.py runs/<run_id>/artifacts/<phase>.json
```

It checks two layers:
1. **JSON Schema** -- required fields, types, enums, nesting.
2. **Domain consistency** -- e.g. `exercise_selection` can only use equipment
   present in the confirmed `requirements` artifact and must not include any
   exercise matching a confirmed constraint's `contraindication_tags`;
   `progression_plan` can only reference `exercise_id`s that exist in
   `exercise_selection`.

A phase is only safe to build on top of once this reports `"result": "pass"`.

## 4. quality-reviewer artifacts

`quality-reviewer` writes `<phase>_review.json` next to the phase it reviewed,
using the same envelope but with a payload of:

```json
{
  "phase_reviewed": "exercise_selection",
  "phase_reviewed_version": 2,
  "result": "pass",
  "checks": [{"name": "equipment_subset", "passed": true}],
  "failure_reasons": []
}
```

`result: "fail"` plus a non-empty `failure_reasons` is what tells the
coordinator which subagent to re-run and why.
