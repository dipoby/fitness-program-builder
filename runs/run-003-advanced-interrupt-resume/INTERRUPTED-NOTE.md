# Simulated interruption

At this point in the run, `requirements`, `research`, and `architecture` had
all completed and passed their quality gates (see
`state.snapshot-before-interrupt.json` — a copy of `state.json` taken at
exactly this moment). The coordinator was about to dispatch
`exercise-selector` next when the Claude Code process was interrupted
(terminal closed / machine restarted — the specific cause doesn't matter to
the workflow; the point is that nothing more ran).

## Resuming

The user re-opened Claude Code in this repo and ran:

```
/build-fitness-program --resume run-003-advanced-interrupt-resume
```

The coordinator:

1. Loaded `runs/run-003-advanced-interrupt-resume/state.json` (confirm this is
   identical to the snapshot above at resume time).
2. Reported back: *"Resuming run-003-advanced-interrupt-resume. requirements,
   research, and architecture are already completed and gate-passed. I'll
   continue from exercise_selection."*
3. Did **not** re-run `requirements-analyst`, `research-agent`, or
   `program-architect` — their artifacts and gate passes were reused as-is.
4. Dispatched `exercise-selector` next, and the run proceeded normally from
   there — see `run-log.md` for the rest, including a human-rejection round
   at the approval gate.

Compare `state.snapshot-before-interrupt.json` (3 of 6 phases completed) with
the final `state.json` in this folder (all 6 completed, plus the approval
block showing one rejection followed by an approval) to see exactly what
resuming added.
