# Fitness Program Builder — Agentic Workflow (Claude Code)

A reliable, model-driven, hub-and-spoke agentic workflow built on Claude Code that
turns a short description of someone's fitness goals, experience, equipment, and
constraints into a structured, periodized training program — with quality gates,
a deterministic human-approval gate, and crash-safe resumable state.

See `CLAUDE.md` for the full architecture and execution rules. This file covers
setup, running, and resuming.

## 1. Prerequisites

- **Claude Code CLI** installed and authenticated (`claude --version` works, and
  you're logged in or have `ANTHROPIC_API_KEY` set).
- **Python 3.10+** on `PATH` (used by the MCP server, hooks, and validation
  scripts — Claude Code shells out to `python3`).
- `pip install -r mcp_servers/exercise_db/requirements.txt` (installs the `mcp`
  Python SDK and `jsonschema`, used by the MCP server and the hooks/scripts).

No other third-party accounts or API keys are required. The exercise catalogue
used by the MCP server is a bundled local dataset
(`mcp_servers/exercise_db/data/exercises.json`), so the workflow is fully
reproducible offline except for the `research-agent`'s web search step.

## 2. One-time setup

```bash
git clone <this-repo-url>
cd fitness-program-builder

cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY if you authenticate Claude Code via env var
# instead of `claude login`

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r mcp_servers/exercise_db/requirements.txt
```

Claude Code will auto-discover `.mcp.json` and `.claude/settings.json` the first
time you launch it inside this directory. On first launch it will ask you to
approve the project-scoped `exercise-db` MCP server — approve it.

## 3. Running the workflow

Start Claude Code in the repo root:

```bash
claude
```

Then, inside the Claude Code session, run the slash command with a free-text
description of the person you're building a program for:

```
/build-fitness-program I'm a complete beginner, I only have dumbbells and a
pull-up bar at home, I can train 3 days a week for about 45 minutes, and my
main goal is fat loss while keeping some muscle.
```

The coordinator will:

1. Ask clarifying questions for anything required but missing (experience level,
   equipment, days/week, session length, injuries/limitations, goal) and have you
   confirm the captured requirements before proceeding.
2. Create `runs/<new-run-id>/` and persist state after every phase.
3. Run research and architecture planning in parallel, then exercise selection and
   progression planning in sequence, validating each against a quality gate.
4. Show you a preview and ask for **approve** or **reject with feedback**. On
   reject, it revises and asks again.
5. On approval, write the final document to `runs/<run-id>/final/program.md`.

Watch `runs/<run-id>/state.json` to see phase-by-phase progress at any time.

## 4. Resuming an interrupted run

If Claude Code, your terminal, or your machine is interrupted mid-workflow, no
state is lost — everything already written has a passing quality-gate record in
`state.json`. To resume:

```
/build-fitness-program --resume
```

or, to resume a specific run by id:

```
/build-fitness-program --resume run-20260115-143200-a1b2
```

The coordinator reads `runs/<run_id>/state.json`, skips every phase already marked
`completed`, and continues from the first `pending`, `failed`, or `blocked` phase.
See `runs/run-003-advanced-interrupt-resume/` for a worked example, including the
state file as it looked right before the interruption and right after resuming.

## 5. Example runs included in this repo

| Run | Demonstrates |
|---|---|
| `runs/run-001-beginner-home-fatloss/` | Full happy path: parallel research/architecture, sequential selection/progression, one approval round. |
| `runs/run-002-intermediate-gym-strength-injury/` | Quality-gate failure + targeted retry (an unsafe exercise choice is caught and corrected), MCP `get_equipment_alternatives` tool use. |
| `runs/run-003-advanced-interrupt-resume/` | Interruption after two phases, resume from persisted state, plus one human-rejection → revision → re-approval loop. |

Each run folder contains `input.md` (the original request), `state.json`
(workflow state at completion), `artifacts/*.json` (every subagent's output),
and `final/` (the approved document plus the pre-approval preview).

## 6. Repository layout

```
.claude/
  commands/build-fitness-program.md   # the slash command = coordinator entry point
  agents/                             # 7 subagent definitions
  skills/                             # 2 reusable skills (artifact-schema, workflow-state)
  hooks/                              # pre_tool_use.py, post_tool_use.py
  settings.json                       # hook registration
.mcp.json                             # registers the exercise-db MCP server
mcp_servers/exercise_db/              # custom MCP server + bundled dataset
schemas/                              # JSON Schemas for every artifact type
scripts/                              # workflow_state.py, validate_artifact.py, approval_gate.py
runs/                                 # one folder per workflow run (see §5)
CLAUDE.md                             # architecture & execution rules (read this)
```

## 7. Security notes

- No credentials are committed. `.env` is git-ignored; `.env.example` documents
  what's needed.
- `pre_tool_use.py` actively blocks `Bash` commands that try to read `.env` or
  dump environment variables, and blocks writes to any `final/` output unless a
  verified approval token is present in `state.json` — see `CLAUDE.md` §5 and §9.

## 8. Troubleshooting

- **MCP server doesn't show up / tools unavailable:** confirm
  `pip install -r mcp_servers/exercise_db/requirements.txt` ran inside the same
  Python environment Claude Code is invoking, and that you approved the server
  when prompted. You can test it standalone with
  `python3 mcp_servers/exercise_db/server.py --selftest`.
- **A phase is stuck `blocked` in `state.json`:** this is intentional — it means
  the retry limit (3 attempts) was reached without passing its quality gate.
  Read `state.json.phases.<phase>.last_failure` for the reviewer's reasons, fix
  the underlying input if needed (e.g. clarify a requirement), and re-run
  `/build-fitness-program --resume <run_id>`.
