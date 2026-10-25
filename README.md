# Study Compass

A weekly study planner agent, built twice: on the raw Messages API (`API/`) and on the Claude Agent SDK (`SDK/`).
Domain code (tools, timetable file, planner, memory store) is shared in `shared/`.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # locked versions
```

## Offline tests (no key, no network)

```bash
python -m pytest -q tests
```

## Scenario runs

```bash
# API version - needs a Console key, set ONLY in the terminal
export ANTHROPIC_API_KEY=...
python API/main.py --scenario scenario.json --out results/api.json

# SDK version - runs on your Claude Code login; the key must NOT be set
unset ANTHROPIC_API_KEY
python SDK/main.py --scenario scenario.json --out results/sdk.json

python report_tables.py                  # tables for REPORT.md
```

Each run wipes its own `state/<api|sdk>/` directory first. Both use `claude-opus-5-5` with effort `medium`.

## Interactive use

```bash
python API/main.py                # new conversation, prints its id
python API/main.py --resume <id>  # continue it (history replayed from disk)
python SDK/main.py --resume       # continue the last SDK session (resume=session_id)
```

## Layout

| path | what |
|---|---|
| `shared/domain.py` | the 8 tools + JSON schemas (identical for both versions) |
| `shared/store.py` | tasks / prefs (memory) / plan as JSON files |
| `shared/calendar_file.py` | `.ics` timetable reader (external file) |
| `shared/web.py` | Wikipedia lookup (external internet), trimmed and cached |
| `shared/planner.py` | deterministic weekly scheduler |
| `shared/checks.py` | pass/fail checks used by `scenario.json` |
| `API/harness/*.py` | one file per responsibility; every runtime action is printed as `[file.py] ...` |
| `SDK/*.py` | lines doing a harness job are tagged `# replaces: <part>` |
