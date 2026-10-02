#!/usr/bin/env python3
"""
Quality-gate validation: JSON Schema + domain-consistency checks for a single
workflow artifact.

Used by `.claude/hooks/post_tool_use.py` immediately after any artifact Write,
and callable directly by the `quality-reviewer` subagent / the coordinator.

CLI:
  python3 scripts/validate_artifact.py <path/to/artifact.json>

Exit code 0 and prints {"result": "pass", ...} on success.
Exit code 1 and prints {"result": "fail", "errors": [...]} on failure.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError:
    print(json.dumps({
        "result": "fail",
        "errors": ["the 'jsonschema' package is not installed — run: "
                    "pip install -r mcp_servers/exercise_db/requirements.txt"],
    }))
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = REPO_ROOT / "schemas"

PHASE_TO_SCHEMA = {
    "requirements": "requirements.schema.json",
    "research": "research.schema.json",
    "architecture": "program_architecture.schema.json",
    "exercise_selection": "exercise_selection.schema.json",
    "progression_plan": "progression_plan.schema.json",
    "final_draft": "final_program.schema.json",
}


def _schema_for_phase(phase: str) -> Path:
    if phase.endswith("_review"):
        return SCHEMA_DIR / "review.schema.json"
    if phase not in PHASE_TO_SCHEMA:
        raise ValueError(f"no schema mapping for phase {phase!r}")
    return SCHEMA_DIR / PHASE_TO_SCHEMA[phase]


def _domain_consistency_errors(artifact: dict, run_dir: Path) -> list[str]:
    """Checks a plain JSON Schema can't express: cross-artifact consistency."""
    errors: list[str] = []
    phase = artifact.get("phase")
    payload = artifact.get("payload", {})

    def _load_sibling(name: str) -> dict | None:
        p = run_dir / "artifacts" / f"{name}.json"
        if not p.exists():
            return None
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)

    if phase == "exercise_selection":
        requirements = _load_sibling("requirements")
        if requirements:
            allowed_equipment = set(e.lower() for e in requirements["payload"]["equipment"])
            used = set(e.lower() for e in payload.get("equipment_used_overall", []))
            extra = used - allowed_equipment
            if extra:
                errors.append(
                    f"exercise_selection uses equipment not in confirmed requirements: {sorted(extra)}"
                )
            constraint_tags = set()
            for c in requirements["payload"].get("constraints", []):
                constraint_tags.update(t.lower() for t in c.get("contraindication_tags", []))
            if constraint_tags:
                for session in payload.get("sessions", []):
                    for ex in session.get("exercises", []):
                        ex_contra = set(t.lower() for t in ex.get("contraindications", []))
                        hit = constraint_tags.intersection(ex_contra)
                        if hit:
                            errors.append(
                                f"session {session.get('session_id')} exercise "
                                f"{ex.get('exercise_id')} violates constraint tag(s) {sorted(hit)}"
                            )

    if phase == "progression_plan":
        exsel = _load_sibling("exercise_selection")
        if exsel:
            known_ids = {
                ex["exercise_id"]
                for s in exsel["payload"]["sessions"]
                for ex in s["exercises"]
            }
            for week in payload.get("weeks", []):
                for session in week.get("sessions", []):
                    for ex in session.get("exercises", []):
                        if ex["exercise_id"] not in known_ids:
                            errors.append(
                                f"progression_plan week {week.get('week_number')} references "
                                f"exercise_id {ex['exercise_id']!r} not present in exercise_selection"
                            )

    if phase == "final_draft":
        requirements = _load_sibling("requirements")
        if requirements:
            allowed_equipment = set(e.lower() for e in requirements["payload"]["equipment"])
            used = set(e.lower() for e in payload.get("equipment_list", []))
            extra = used - allowed_equipment
            if extra:
                errors.append(f"final_draft equipment_list has items outside confirmed equipment: {sorted(extra)}")

    return errors


def validate_artifact_file(artifact_path: Path) -> dict:
    with open(artifact_path, "r", encoding="utf-8") as f:
        artifact = json.load(f)

    schema_path = _schema_for_phase(artifact.get("phase", ""))
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)

    errors: list[str] = []
    validator = jsonschema.Draft7Validator(schema)
    for err in sorted(validator.iter_errors(artifact), key=str):
        errors.append(f"schema: {'/'.join(str(p) for p in err.absolute_path) or '<root>'}: {err.message}")

    # run_dir = artifacts/<phase>.json -> artifacts/ -> run_dir
    run_dir = artifact_path.parent.parent
    errors.extend(_domain_consistency_errors(artifact, run_dir))

    if errors:
        return {"result": "fail", "artifact": str(artifact_path), "errors": errors}
    return {"result": "pass", "artifact": str(artifact_path), "errors": []}


def _main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({"result": "fail", "errors": ["usage: validate_artifact.py <artifact.json>"]}))
        return 1
    result = validate_artifact_file(Path(sys.argv[1]))
    print(json.dumps(result, indent=2))
    return 0 if result["result"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(_main())
