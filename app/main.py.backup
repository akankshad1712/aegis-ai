from dotenv import load_dotenv

load_dotenv()

import json
import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app import db
from app.engine import investigate
from app.limiter import limiter
from app.log_analyzer import analyze_logs

BASE_DIR = Path(__file__).resolve().parent


class JsonLogFormatter(logging.Formatter):
    """Emit compact JSON logs for easier parsing and aggregation."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in ("request_id", "method", "path", "status_code", "duration_ms"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


_handler = logging.StreamHandler()
_handler.setFormatter(JsonLogFormatter())
_root_logger = logging.getLogger()
if not any(getattr(handler, "_aegis_json_handler", False) for handler in _root_logger.handlers):
    _handler._aegis_json_handler = True  # type: ignore[attr-defined]
    _root_logger.addHandler(_handler)
_root_logger.setLevel(logging.INFO)
logger = logging.getLogger("aegis.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the database when the application starts."""
    db.init_db()
    yield


app = FastAPI(
    title="AEGIS AI",
    description="Evidence-first incident investigation and safe recovery simulator.",
    version="0.6.1",
    lifespan=lifespan,
)


@app.middleware("http")
async def api_key_authentication_middleware(request: Request, call_next):
    """Require X-API-Key for API routes, except the public health endpoint."""
    path = request.url.path

    # Keep the health check public for Docker and deployment health probes.
    if path.startswith("/api/") and path != "/api/health":
        expected_key = os.getenv("AEGIS_API_KEY")
        if not expected_key:
            return JSONResponse(
                status_code=503,
                content={"detail": "API authentication is not configured."},
            )

        supplied_key = request.headers.get("X-API-Key")
        if not supplied_key or not secrets.compare_digest(supplied_key, expected_key):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key."},
                headers={"WWW-Authenticate": "ApiKey"},
            )

    return await call_next(request)


# Rate limiting for resource-intensive and state-changing endpoints.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.middleware("http")
async def request_observability_middleware(request: Request, call_next):
    """Attach a request ID and log request outcome and latency."""
    request_id = str(uuid4())
    request.state.request_id = request_id
    started = perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((perf_counter() - started) * 1000, 2)
        logger.exception(
            "request_failed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "duration_ms": duration_ms,
            },
        )
        raise

    duration_ms = round((perf_counter() - started) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_completed",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response


app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


# -------------------------------------------------------------------
# Request models
# -------------------------------------------------------------------

class IncidentCreate(BaseModel):
    title: str = Field(min_length=4, max_length=160)
    service: str = Field(min_length=2, max_length=80)
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    description: str = Field(min_length=5, max_length=2000)


class IncidentStatusUpdate(BaseModel):
    status: Literal["open", "investigating", "resolved"]


class ActionCreate(BaseModel):
    action_type: Literal["restart_simulation", "rollback_simulation", "scale_simulation"]
    rationale: str = Field(min_length=5, max_length=500)


class LogAnalysisRequest(BaseModel):
    logs: str = Field(min_length=1, max_length=50000)


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def _rank_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort findings by heuristic score without changing their contents."""
    return sorted(findings, key=lambda item: item.get("score", 0), reverse=True)


def _tag_findings(findings: list[dict[str, Any]], source: str) -> list[dict[str, Any]]:
    """Copy findings and identify their evidence source."""
    tagged: list[dict[str, Any]] = []
    for finding in findings:
        item = dict(finding)
        item.setdefault("source", source)
        tagged.append(item)
    return tagged


# -------------------------------------------------------------------
# Dashboard and health
# -------------------------------------------------------------------

@app.get("/", include_in_schema=False)
def home():
    """Serve the AEGIS AI dashboard."""
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/health")
def health():
    """Return basic application health information."""
    return {"status": "ok", "service": "aegis-ai", "mode": "simulation"}


# -------------------------------------------------------------------
# Standalone log analysis
# -------------------------------------------------------------------

@app.post("/api/logs/analyze")
@limiter.limit("10/minute")
def analyze_log_evidence(request: Request, payload: LogAnalysisRequest):
    """Analyze logs without attaching them to an incident."""
    return analyze_logs(payload.logs)


# -------------------------------------------------------------------
# Incident management
# -------------------------------------------------------------------

@app.get("/api/incidents")
def get_incidents():
    """Return all incidents."""
    return {"items": db.list_incidents()}


@app.post("/api/incidents", status_code=201)
@limiter.limit("20/minute")
def post_incident(request: Request, payload: IncidentCreate):
    """Create an incident and its audit event."""
    return db.create_incident(payload.title, payload.service, payload.severity, payload.description)


@app.post("/api/demo/seed")
@limiter.limit("3/minute")
def seed_demo(request: Request):
    """Create synthetic incidents if the database is empty."""
    existing = db.list_incidents()
    if existing:
        return {
            "message": "Database already contains incidents; no new demo data added.",
            "items": existing,
        }

    samples = [
        (
            "Checkout API latency after release",
            "checkout-api",
            "high",
            "p95 latency increased and requests timeout after deployment version v1.8.2.",
        ),
        (
            "Payments service 5xx spike",
            "payments-api",
            "critical",
            "Error rate and HTTP 500 exceptions increased after release.",
        ),
        (
            "Worker memory pressure",
            "invoice-worker",
            "medium",
            "Memory usage rises continuously and the worker reports OOM restarts.",
        ),
    ]
    created = [db.create_incident(*sample) for sample in samples]
    return {"message": "Synthetic demo incidents created.", "items": created}


@app.get("/api/incidents/{incident_id}")
def get_incident(incident_id: int):
    """Return one incident by ID."""
    item = db.get_incident(incident_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return item


@app.patch("/api/incidents/{incident_id}/status")
def update_incident_status(incident_id: int, payload: IncidentStatusUpdate):
    """Update an incident's lifecycle status."""
    try:
        incident = db.update_incident_status(incident_id, payload.status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


# -------------------------------------------------------------------
# Incident log analysis
# -------------------------------------------------------------------

@app.post("/api/incidents/{incident_id}/logs/analyze")
@limiter.limit("10/minute")
def analyze_incident_logs(request: Request, incident_id: int, payload: LogAnalysisRequest):
    """Analyze and persist log evidence for an incident."""
    if db.get_incident(incident_id) is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    analysis = analyze_logs(payload.logs)
    return db.save_log_analysis(incident_id=incident_id, logs_text=payload.logs, analysis=analysis)


# -------------------------------------------------------------------
# Incident investigation
# -------------------------------------------------------------------

@app.post("/api/incidents/{incident_id}/investigate")
@limiter.limit("20/minute")
def investigate_incident(request: Request, incident_id: int):
    """Combine incident-text hypotheses with the latest saved log findings.

    Findings remain heuristic hypotheses, not confirmed root causes.
    """
    incident = db.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")

    incident_report = investigate(incident)
    findings = _tag_findings(incident_report.get("findings", []), source="incident_text")
    summary_parts = [incident_report["summary"]]
    log_record = db.get_latest_log_analysis(incident_id)

    if log_record:
        log_analysis = log_record.get("analysis") or {}
        log_findings = _tag_findings(log_analysis.get("findings", []), source="application_logs")
        findings.extend(log_findings)
        event_count = log_analysis.get("event_count", 0)
        malformed_count = log_analysis.get("malformed_line_count", 0)
        summary_parts.append(f"Log evidence included: {event_count} parsed events.")
        if malformed_count:
            summary_parts.append(f"{malformed_count} log line(s) could not be parsed.")
    else:
        summary_parts.append(
            "No saved log analysis was available; findings are based on incident text only."
        )

    findings = _rank_findings(findings)
    return db.save_investigation(
        incident_id=incident_id,
        summary=" ".join(summary_parts),
        findings=findings,
    )


@app.get("/api/incidents/{incident_id}/investigations")
def get_investigations(incident_id: int):
    """Return investigation history for an incident."""
    if db.get_incident(incident_id) is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {"items": db.list_investigations(incident_id)}


# -------------------------------------------------------------------
# Simulated recovery actions
# -------------------------------------------------------------------

@app.post("/api/incidents/{incident_id}/actions", status_code=201)
@limiter.limit("10/minute")
def propose_action(request: Request, incident_id: int, payload: ActionCreate):
    """Propose a recovery action without executing real infrastructure work."""
    if db.get_incident(incident_id) is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return db.create_action(incident_id, payload.action_type, payload.rationale)


@app.post("/api/actions/{action_id}/approve-simulation")
@limiter.limit("10/minute")
def approve_action(request: Request, action_id: int):
    """Approve a proposed action in simulation mode only."""
    try:
        action = db.approve_simulated_action(action_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if action is None:
        raise HTTPException(status_code=404, detail="Action not found")
    return action


# -------------------------------------------------------------------
# Audit history
# -------------------------------------------------------------------

@app.get("/api/audit-events")
def get_audit_events(
    incident_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=500),
):
    """Return recent audit events, optionally filtered by incident."""
    if incident_id is not None and db.get_incident(incident_id) is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {"items": db.list_audit_events(incident_id=incident_id, limit=limit)}


@app.get("/api/incidents/{incident_id}/audit-events")
def get_incident_audit_events(
    incident_id: int,
    limit: int = Query(default=100, ge=1, le=500),
):
    """Return audit history for a single incident."""
    if db.get_incident(incident_id) is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {"items": db.list_audit_events(incident_id=incident_id, limit=limit)}
