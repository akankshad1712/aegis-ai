# AEGIS AI — lightweight incident intelligence MVP

A Windows-friendly, zero-cost starter for an evidence-first incident investigation and safe recovery simulator.

## Current capabilities

- Dark browser dashboard served by FastAPI (no Node.js process required in MVP)
- Create/list incidents using SQLite
- Seed synthetic incident examples
- Run a deterministic diagnostic engine for timeout/latency, application errors, deployment regression, and memory pressure
- Save investigation reports
- Propose recovery actions and approve a simulation
- Tests for the core API flow

**Safety boundary:** this starter only creates a simulated recovery record. It does not restart services, deploy code, access production telemetry, or execute shell commands. Heuristic scores are ranking hints, not calibrated probabilities. The engine is deterministic, not an LLM agent yet.

## 1. Prerequisites

- Windows 11
- Python 3.11 or 3.12 recommended
- Docker Desktop installed (not required for this first SQLite-based MVP)

Check Python in PowerShell:

```powershell
py --version
```

If `py` is not found, install Python from https://www.python.org/downloads/windows/ and select **Add python.exe to PATH**. Reopen PowerShell after installing.

## 2. Extract and enter the project

Extract `aegis-ai-starter.zip`, then open PowerShell in the extracted `aegis-ai-starter` folder.

```powershell
cd path\to\aegis-ai-starter
```

## 3. Create a virtual environment

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks activation, use this for the current terminal only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## 4. Run the API and dashboard

```powershell
uvicorn app.main:app --reload
```

Open:
- Dashboard: http://127.0.0.1:8000
- Interactive API docs: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/api/health

Stop the server with `Ctrl+C`.

## 5. Try the demo

1. Open the dashboard.
2. Click **Load synthetic incidents**.
3. Click **Investigate** on an incident.
4. Read the ranked hypotheses and evidence.
5. Select the incident for recovery.
6. Propose a simulated rollback/restart/scale action.
7. Click **Approve simulation** and confirm the result says `SIMULATION ONLY`.

You can also call the API from PowerShell:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/demo/seed
Invoke-RestMethod http://127.0.0.1:8000/api/incidents
```

## 6. Run tests

Stop the dev server first, then run:

```powershell
pytest -q
```

Expected: 3 tests pass. If you already have a `test_aegis.db` file from a previous interrupted run, stop the server and delete that test file before retrying.

## Folder structure

```text
aegis-ai-starter/
├── app/
│   ├── __init__.py
│   ├── db.py                 # SQLite persistence and audit records
│   ├── engine.py             # Transparent deterministic diagnostic rules
│   ├── main.py               # FastAPI routes and startup
│   └── static/
│       └── index.html        # Lightweight dashboard
├── tests/
│   └── test_api.py
├── .gitignore
├── requirements.txt
└── README.md
```

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Health check |
| GET | `/api/incidents` | List incidents |
| POST | `/api/incidents` | Create incident |
| POST | `/api/demo/seed` | Add synthetic demo data |
| GET | `/api/incidents/{id}` | Read one incident |
| POST | `/api/incidents/{id}/investigate` | Run and save investigation |
| GET | `/api/incidents/{id}/investigations` | Read saved reports |
| POST | `/api/incidents/{id}/actions` | Propose a safe simulation |
| POST | `/api/actions/{id}/approve-simulation` | Approve simulated action |

## Build roadmap

1. **MVP (now):** API, dashboard, SQLite, synthetic incidents, diagnostic rules, action audit, tests.
2. **Evidence ingestion:** parse user-supplied sample logs and attach timestamped evidence objects.
3. **Evaluation lab:** create labeled incidents and measure top-1 root-cause accuracy, evidence coverage, and unsafe-action prevention.
4. **Agent orchestration:** add a constrained tool-calling loop with explicit tool schemas, max-step limits, and logged inputs/outputs.
5. **Optional AI model:** test a free-tier hosted provider or a small local model only if memory permits. Do not make the app depend on a paid API.
6. **Observability:** later add OpenTelemetry/Prometheus or simple local metric fixtures. Avoid running a full monitoring stack on 8 GB RAM initially.
7. **Frontend upgrade:** if desired, replace the served HTML with Next.js after the backend is stable.

## Portfolio integrity

Only claim features that you have implemented and tested. Describe the initial engine as a deterministic incident triage engine, not a fully autonomous AI agent. Use synthetic data or systems you are authorized to inspect.
