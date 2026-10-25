# Study Compass

A weekly study planner agent, built twice: on the raw Gemini REST API (`API/`) and on the `google-genai` SDK (`SDK/`).
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

Get a free key at https://aistudio.google.com/apikey, then `cp .env.example .env` and paste it after
`GEMINI_API_KEY=` (`.env` is git-ignored; or export the variable in the terminal). Never put it in code.

```bash
python API/main.py --scenario scenario.json --out results/api.json   # raw REST harness
python SDK/main.py --scenario scenario.json --out results/sdk.json   # google-genai Chat + automatic function calling
python report_tables.py                                              # tables for REPORT.md
```

Each run wipes its own `state/<api|sdk>/` directory first. Both use `gemini-3.6-flash` with thinking level `medium`
(`--model` / `--effort` override). Cost columns are notional paid-tier prices; the free tier bills nothing.

## Interactive use

```bash
python API/main.py                # new conversation, prints its id
python API/main.py --resume <id>  # continue it (history replayed from disk)
python SDK/main.py --resume       # continue the saved SDK chat history
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
| `API/harness/*.py` | one file per responsibility (incl. `client.py`, the HTTP call); every runtime action is printed as `[file.py] ...` |
| `SDK/*.py` | lines doing a harness job are tagged `# replaces: <part>` |
