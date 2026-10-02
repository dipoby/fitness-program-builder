# 10-Week Intermediate Upper/Lower Strength Program (Shoulder-Safe)

*Approved. Run: `run-002-intermediate-gym-strength-injury`, final_draft version 1, approved 2026-02-03.*

## Summary

A 4-day/week, 10-week upper/lower strength program for an intermediate
lifter with full gym access, built around heavy compound lifts in the 3-8
rep range. All overhead pressing is excluded and replaced with a landmine
press variant due to a confirmed shoulder impingement.

## Confirmed Requirements

| Field | Value |
|---|---|
| Goal | Strength |
| Experience level | Intermediate |
| Equipment | Barbell, Dumbbell, Bench, Squat rack, Cable machine |
| Days per week | 4 |
| Session length | ~60 minutes |
| Constraints / injuries | Shoulder impingement — avoid overhead pressing |

## Weekly Schedule Overview

| Session | Focus |
|---|---|
| Day 1 — Upper A | Horizontal Push + Pull + Accessory |
| Day 2 — Lower A | Squat + Hinge + Core |
| Day 3 — Upper B | Push + Pull + Accessory |
| Day 4 — Lower B | Squat + Hinge + Core |

## Session-by-Session Program

### Day 1 — Upper A (~55 min)

| Exercise | Sets | Reps | Rest |
|---|---|---|---|
| Barbell Bench Press | 4 | 5-6 | 150s |
| Barbell Bent-Over Row | 4 | 6-8 | 120s |
| Dumbbell Biceps Curl | 3 | 10-12 | 60s |

### Day 2 — Lower A (~55 min)

| Exercise | Sets | Reps | Rest |
|---|---|---|---|
| Barbell Back Squat | 4 | 5-6 | 150s |
| Barbell Deadlift | 3 | 5-6 | 180s |
| Cable Woodchopper | 3 | 12 each side | 60s |

### Day 3 — Upper B (~55 min)

| Exercise | Sets | Reps | Rest |
|---|---|---|---|
| Dumbbell Landmine Press *(substituted — see note below)* | 4 | 8-10 each arm | 120s |
| Cable Seated Row | 4 | 8-10 | 90s |
| Cable Triceps Pushdown | 3 | 10-12 | 60s |

### Day 4 — Lower B (~55 min)

| Exercise | Sets | Reps | Rest |
|---|---|---|---|
| Dumbbell Bulgarian Split Squat | 3 | 6-8 each leg | 120s |
| Barbell Hip Thrust | 4 | 6-8 | 120s |
| Cable Woodchopper | 3 | 12 each side | 60s |

## Progression Plan

**Strategy:** Linear load progression on the main compound lifts (bench,
squat, deadlift, landmine press, hip thrust, bent-over row), double
progression on accessories, with a week-6 deload and a week-10 peak.

| Weeks | Intensity | What changes |
|---|---|---|
| 1-3 | RPE 7 | Establish working weights, 2-3 reps in reserve on main lifts. |
| 4-5 | RPE 7.5-8 | Approach recent top weights on main lifts. |
| 6 (deload) | Reduced | One fewer set per exercise, same or ~10% lighter load — recovery week. |
| 7-9 | RPE 8-9 | Genuine strength-building intensity; add load when all sets hit the top of the rep range with good bar speed. |
| 10 (peak) | RPE 9 | Heaviest clean sets of the block on main lifts; accessories stay moderate. |

*(Full week-by-week, exercise-by-exercise detail is in `artifacts/progression_plan.json`.)*

## Equipment & Substitutions

Equipment used: **barbell, dumbbell, bench, squat-rack, cable-machine** —
matches what you confirmed having access to.

**One substitution was made:** Day 3's press was originally selected as
Barbell Overhead Press by the exercise-selection step, but that was caught by
the quality gate as violating your confirmed shoulder-impingement constraint
before you ever saw it. It was replaced with **Dumbbell Landmine Press** — a
non-overhead, angled pressing pattern that still trains the same muscles —
found via the `exercise-db` MCP server's equipment-alternatives lookup.

## Safety Notes

- Overhead pressing is intentionally excluded from this entire program due to
  your confirmed shoulder impingement.
- Day 3's press was substituted to Dumbbell Landmine Press for this reason
  (see above).
- If any exercise still provokes shoulder pain, stop and consult a physical
  therapist or physician before continuing that movement.

## Sources

- NSCA Essentials of Strength Training and Conditioning, 4th ed. (summaries)
  — rep ranges/rest for intermediate strength goals; 4-day upper/lower
  periodization.
- Physiopedia: Shoulder Impingement Syndrome — exercise considerations
  (summary) — basis for avoiding overhead pressing and using landmine/
  horizontal pressing instead.
- Exercise catalogue and equipment-substitution logic: `exercise-db` MCP
  server (local, versioned dataset).
