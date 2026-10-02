#!/usr/bin/env python3
"""
exercise-db MCP server.

A small, self-contained MCP server exposing a local exercise catalogue so that
the `exercise-selector` subagent (and anyone else) selects real exercises and
real equipment substitutions instead of inventing them from model memory. The
dataset is bundled at data/exercises.json and requires no external API or key,
so the workflow stays fully reproducible.

Tools exposed:
  - search_exercises(muscle_group=None, equipment=None, difficulty=None,
                      movement_pattern=None, exclude_contraindications=None)
  - get_equipment_alternatives(exercise_id, available_equipment=None)
  - list_equipment_categories()

Run normally (stdio MCP transport, used by Claude Code via .mcp.json):
    python3 server.py

Run a quick standalone sanity check (no stdio transport, exits immediately):
    python3 server.py --selftest
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

DATA_PATH = Path(__file__).parent / "data" / "exercises.json"


def _load_db() -> dict:
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _search_exercises(
    db: dict,
    muscle_group: Optional[str] = None,
    equipment: Optional[list[str]] = None,
    difficulty: Optional[str] = None,
    movement_pattern: Optional[str] = None,
    exclude_contraindications: Optional[list[str]] = None,
) -> list[dict]:
    results = []
    equipment_set = set(e.lower() for e in equipment) if equipment else None
    exclude_set = set(c.lower() for c in exclude_contraindications) if exclude_contraindications else set()

    for ex in db["exercises"]:
        if muscle_group and muscle_group.lower() not in [m.lower() for m in ex["muscle_groups"]]:
            continue
        if difficulty and ex["difficulty"].lower() != difficulty.lower():
            continue
        if movement_pattern and ex["movement_pattern"].lower() != movement_pattern.lower():
            continue
        if equipment_set is not None:
            # exercise is usable if every piece of equipment it needs is available
            if not set(e.lower() for e in ex["equipment"]).issubset(equipment_set):
                continue
        if exclude_set and exclude_set.intersection(set(c.lower() for c in ex.get("contraindications", []))):
            continue
        results.append(ex)
    return results


def _get_equipment_alternatives(
    db: dict, exercise_id: str, available_equipment: Optional[list[str]] = None
) -> dict:
    by_id = {ex["id"]: ex for ex in db["exercises"]}
    if exercise_id not in by_id:
        return {"error": f"unknown exercise_id '{exercise_id}'", "known_ids_sample": list(by_id.keys())[:10]}

    candidate_ids = db.get("substitution_links", {}).get(exercise_id, [])
    candidates = [by_id[cid] for cid in candidate_ids if cid in by_id]

    if available_equipment:
        avail = set(e.lower() for e in available_equipment)
        candidates = [c for c in candidates if set(e.lower() for e in c["equipment"]).issubset(avail)]

    return {
        "exercise_id": exercise_id,
        "exercise_name": by_id[exercise_id]["name"],
        "alternatives": candidates,
    }


def _list_equipment_categories(db: dict) -> list[str]:
    cats = set()
    for ex in db["exercises"]:
        cats.update(ex["equipment"])
    return sorted(cats)


def _selftest() -> int:
    db = _load_db()
    assert len(db["exercises"]) >= 20, "dataset looks too small"
    pushups = _search_exercises(db, equipment=["bodyweight"], movement_pattern="push")
    assert any(e["id"] == "bw_pushup" for e in pushups), "expected bw_pushup in bodyweight push search"
    alts = _get_equipment_alternatives(db, "bb_overhead_press", available_equipment=["dumbbell", "bench"])
    assert alts["alternatives"], "expected at least one alternative for bb_overhead_press with dumbbell+bench"
    cats = _list_equipment_categories(db)
    assert "dumbbell" in cats and "bodyweight" in cats
    print(f"OK: {len(db['exercises'])} exercises, {len(cats)} equipment categories, "
          f"{len(db.get('substitution_links', {}))} substitution entries.")
    print(f"Sample search_exercises(equipment=['bodyweight'], movement_pattern='push') -> "
          f"{[e['id'] for e in pushups]}")
    print(f"Sample get_equipment_alternatives('bb_overhead_press', ['dumbbell','bench']) -> "
          f"{[a['id'] for a in alts['alternatives']]}")
    return 0


def main() -> None:
    if "--selftest" in sys.argv:
        sys.exit(_selftest())

    # Imported lazily so --selftest works even before `mcp` is installed.
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("exercise-db")
    db = _load_db()

    @mcp.tool()
    def search_exercises(
        muscle_group: Optional[str] = None,
        equipment: Optional[list[str]] = None,
        difficulty: Optional[str] = None,
        movement_pattern: Optional[str] = None,
        exclude_contraindications: Optional[list[str]] = None,
    ) -> list[dict]:
        """Search the exercise catalogue by muscle group, available equipment,
        difficulty, movement pattern, and/or contraindications to exclude.

        `equipment` should be the full list of equipment the trainee has access
        to (e.g. ["dumbbell", "bench"]) — only exercises fully coverable by that
        set are returned. `exclude_contraindications` filters out any exercise
        tagged with a matching contraindication (e.g. "shoulder_overhead",
        "knee_deep_flexion", "lower_back_loaded_flexion", "wrist_loaded_extension").
        """
        return _search_exercises(db, muscle_group, equipment, difficulty, movement_pattern, exclude_contraindications)

    @mcp.tool()
    def get_equipment_alternatives(exercise_id: str, available_equipment: Optional[list[str]] = None) -> dict:
        """Given an exercise id, return curated substitute exercises (same or
        similar movement pattern, different equipment or safer variant).
        Optionally filter substitutes to only those usable with
        `available_equipment`.
        """
        return _get_equipment_alternatives(db, exercise_id, available_equipment)

    @mcp.tool()
    def list_equipment_categories() -> list[str]:
        """List every equipment tag present in the exercise catalogue."""
        return _list_equipment_categories(db)

    mcp.run()


if __name__ == "__main__":
    main()
