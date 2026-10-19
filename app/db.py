
"""AEGIS AI database layer.

Uses SQLite with transaction handling, foreign-key enforcement,
incident history, simulated actions, and audit events.
"""

import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "aegis.db"

# Supports Docker volumes and custom local database locations.
DB_PATH = Path(
    os.getenv("AEGIS_DB_PATH", str(DEFAULT_DB_PATH))
).expanduser()

ALLOWED_STATUSES = {"open", "investigating", "resolved"}


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Open a SQLite connection with transaction handling."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row

    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 10000")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create application tables and indexes if they do not exist."""
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                service TEXT NOT NULL,
                severity TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                description TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS incident_log_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id INTEGER NOT NULL REFERENCES incidents(id),
                logs_text TEXT NOT NULL,
                analysis_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS investigations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id INTEGER NOT NULL REFERENCES incidents(id),
                summary TEXT NOT NULL,
                findings_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id INTEGER NOT NULL REFERENCES incidents(id),
                action_type TEXT NOT NULL,
                rationale TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'proposed',
                result TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
CREATE TABLE IF NOT EXISTS investigations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id INTEGER NOT NULL REFERENCES incidents(id),
    summary TEXT NOT NULL,
    findings_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_investigations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id INTEGER NOT NULL REFERENCES incidents(id),
    agent TEXT NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    report TEXT NOT NULL,
    analysis_method TEXT NOT NULL,
    root_cause_confirmed INTEGER NOT NULL DEFAULT 0,
    recovery_executed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agent_investigations_incident
    ON agent_investigations(incident_id, id DESC);

            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id INTEGER NOT NULL,
                incident_id INTEGER REFERENCES incidents(id),
                details_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_audit_events_incident
                ON audit_events(incident_id, id DESC);

            CREATE INDEX IF NOT EXISTS idx_audit_events_type
                ON audit_events(event_type, id DESC);

            CREATE INDEX IF NOT EXISTS idx_log_analyses_incident
                ON incident_log_analyses(incident_id, id DESC);

            CREATE INDEX IF NOT EXISTS idx_investigations_incident
                ON investigations(incident_id, id DESC);
            """
        )


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a SQLite row into a dictionary."""
    return dict(row)


def _record_audit_event(
    conn: sqlite3.Connection,
    event_type: str,
    entity_type: str,
    entity_id: int,
    incident_id: int | None,
    details: dict[str, Any] | None = None,
) -> None:
    """Insert an audit event in the caller's transaction."""
    conn.execute(
        """
        INSERT INTO audit_events (
            event_type,
            entity_type,
            entity_id,
            incident_id,
            details_json
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            event_type,
            entity_type,
            entity_id,
            incident_id,
            json.dumps(details or {}, ensure_ascii=False),
        ),
    )


def list_audit_events(
    incident_id: int | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return newest audit events first."""
    if not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")

    with connect() as conn:
        if incident_id is None:
            rows = conn.execute(
                """
                SELECT *
                FROM audit_events
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT *
                FROM audit_events
                WHERE incident_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (incident_id, limit),
            ).fetchall()

    events = []

    for row in rows:
        event = row_to_dict(row)
        event["details"] = json.loads(event.pop("details_json"))
        events.append(event)

    return events


def get_incident(incident_id: int) -> dict[str, Any] | None:
    """Get one incident by ID."""
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM incidents WHERE id = ?",
            (incident_id,),
        ).fetchone()

    return row_to_dict(row) if row else None


def list_incidents() -> list[dict[str, Any]]:
    """List incidents, newest first."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM incidents ORDER BY id DESC"
        ).fetchall()

    return [row_to_dict(row) for row in rows]


def create_incident(
    title: str,
    service: str,
    severity: str,
    description: str,
) -> dict[str, Any]:
    """Create an incident and its audit event atomically."""
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO incidents (
                title, service, severity, description
            )
            VALUES (?, ?, ?, ?)
            """,
            (title, service, severity, description),
        )
        incident_id = int(cur.lastrowid)

        _record_audit_event(
            conn=conn,
            event_type="incident.created",
            entity_type="incident",
            entity_id=incident_id,
            incident_id=incident_id,
            details={
                "service": service,
                "severity": severity,
            },
        )

        row = conn.execute(
            "SELECT * FROM incidents WHERE id = ?",
            (incident_id,),
        ).fetchone()

        if row is None:
            raise RuntimeError("Created incident could not be retrieved")

        return row_to_dict(row)


def update_incident_status(
    incident_id: int,
    status: str,
) -> dict[str, Any] | None:
    """Update incident status and audit actual changes."""
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"Invalid incident status: {status}")

    with connect() as conn:
        row = conn.execute(
            "SELECT status FROM incidents WHERE id = ?",
            (incident_id,),
        ).fetchone()

        if row is None:
            return None

        previous_status = row["status"]

        if previous_status != status:
            conn.execute(
                """
                UPDATE incidents
                SET status = ?
                WHERE id = ?
                """,
                (status, incident_id),
            )

            _record_audit_event(
                conn=conn,
                event_type="incident.status_changed",
                entity_type="incident",
                entity_id=incident_id,
                incident_id=incident_id,
                details={
                    "previous_status": previous_status,
                    "new_status": status,
                },
            )

        updated = conn.execute(
            "SELECT * FROM incidents WHERE id = ?",
            (incident_id,),
        ).fetchone()

        return row_to_dict(updated) if updated else None


def save_investigation(
    incident_id: int,
    summary: str,
    findings: list[dict[str, Any]],
) -> dict[str, Any]:
    """Persist an investigation report."""
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO investigations (
                incident_id, summary, findings_json
            )
            VALUES (?, ?, ?)
            """,
            (
                incident_id,
                summary,
                json.dumps(findings, ensure_ascii=False),
            ),
        )

        row = conn.execute(
            "SELECT * FROM investigations WHERE id = ?",
            (cur.lastrowid,),
        ).fetchone()

        if row is None:
            raise RuntimeError("Saved investigation could not be retrieved")

        result = row_to_dict(row)

    result["findings"] = json.loads(result.pop("findings_json"))
    return result


def list_investigations(
    incident_id: int,
) -> list[dict[str, Any]]:
    """List investigation history for one incident."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM investigations
            WHERE incident_id = ?
            ORDER BY id DESC
            """,
            (incident_id,),
        ).fetchall()

    results = []

    for row in rows:
        item = row_to_dict(row)
        item["findings"] = json.loads(item.pop("findings_json"))
        results.append(item)

    return results


def save_log_analysis(
    incident_id: int,
    logs_text: str,
    analysis: dict[str, Any],
) -> dict[str, Any]:
    """Persist parsed log evidence for an incident."""
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO incident_log_analyses (
                incident_id, logs_text, analysis_json
            )
            VALUES (?, ?, ?)
            """,
            (
                incident_id,
                logs_text,
                json.dumps(analysis, ensure_ascii=False),
            ),
        )

        row = conn.execute(
            "SELECT * FROM incident_log_analyses WHERE id = ?",
            (cur.lastrowid,),
        ).fetchone()

        if row is None:
            raise RuntimeError("Saved log analysis could not be retrieved")

        result = row_to_dict(row)

    result["analysis"] = json.loads(result.pop("analysis_json"))
    return result


def get_latest_log_analysis(
    incident_id: int,
) -> dict[str, Any] | None:
    """Return the most recently saved log analysis."""
    with connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM incident_log_analyses
            WHERE incident_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (incident_id,),
        ).fetchone()

    if row is None:
        return None

    result = row_to_dict(row)
    result["analysis"] = json.loads(result.pop("analysis_json"))
    return result


def create_action(
    incident_id: int,
    action_type: str,
    rationale: str,
) -> dict[str, Any]:
    """Create a proposed simulated action and audit the proposal."""
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO actions (
                incident_id, action_type, rationale
            )
            VALUES (?, ?, ?)
            """,
            (incident_id, action_type, rationale),
        )
        action_id = int(cur.lastrowid)

        _record_audit_event(
            conn=conn,
            event_type="action.proposed",
            entity_type="action",
            entity_id=action_id,
            incident_id=incident_id,
            details={"action_type": action_type},
        )

        row = conn.execute(
            "SELECT * FROM actions WHERE id = ?",
            (action_id,),
        ).fetchone()

        if row is None:
            raise RuntimeError("Created action could not be retrieved")

        return row_to_dict(row)


def approve_simulated_action(
    action_id: int,
) -> dict[str, Any] | None:
    """
    Approve a proposed action exactly once.

    No real infrastructure action is executed.
    """
    result_text = (
        "SIMULATION ONLY: action recorded as executed. "
        "No real service, deployment, server, or production "
        "system was changed."
    )

    with connect() as conn:
        # Acquire a write lock before checking action status.
        conn.execute("BEGIN IMMEDIATE")

        action = conn.execute(
            "SELECT * FROM actions WHERE id = ?",
            (action_id,),
        ).fetchone()

        if action is None:
            return None

        if action["status"] != "proposed":
            raise ValueError(f"Action is already {action['status']}")

        cur = conn.execute(
            """
            UPDATE actions
            SET status = 'simulated', result = ?
            WHERE id = ? AND status = 'proposed'
            """,
            (result_text, action_id),
        )

        if cur.rowcount != 1:
            current = conn.execute(
                "SELECT status FROM actions WHERE id = ?",
                (action_id,),
            ).fetchone()

            if current is None:
                return None

            raise ValueError(f"Action is already {current['status']}")

        _record_audit_event(
            conn=conn,
            event_type="action.simulation_approved",
            entity_type="action",
            entity_id=action_id,
            incident_id=action["incident_id"],
            details={"action_type": action["action_type"]},
        )

        updated = conn.execute(
            "SELECT * FROM actions WHERE id = ?",
            (action_id,),
        ).fetchone()

        return row_to_dict(updated) if updated else None

def save_agent_report(
    incident_id: int,
    report: dict[str, Any],
) -> dict[str, Any]:
    """Persist an AI-agent investigation report."""
    import json

    with connect() as conn:
        incident = conn.execute(
            "SELECT id FROM incidents WHERE id = ?",
            (incident_id,),
        ).fetchone()

        if incident is None:
            raise ValueError(f"Incident {incident_id} not found")

        cur = conn.execute(
            """
            INSERT INTO agent_investigations (
                incident_id,
                agent,
                mode,
                status,
                report,
                analysis_method,
                root_cause_confirmed,
                recovery_executed
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                incident_id,
                report.get("agent", "AEGIS Reliability Investigation Agent"),
                report.get("mode", "llm_tool_using"),
                report.get("status", "completed"),
                json.dumps(report, ensure_ascii=False),
                report.get("analysis_method", "openai_agents_sdk_with_deterministic_tools"),
                int(bool(report.get("root_cause_confirmed", False))),
                int(bool(report.get("recovery_executed", False))),
            ),
        )

        return {
            "id": cur.lastrowid,
            "incident_id": incident_id,
            **report,
        }


def list_agent_reports(
    incident_id: int,
) -> list[dict[str, Any]]:
    """Return saved AI-agent investigation reports."""
    import json

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, incident_id, report, created_at
            FROM agent_investigations
            WHERE incident_id = ?
            ORDER BY id DESC
            """,
            (incident_id,),
        ).fetchall()

    results = []
    for row in rows:
        item = dict(row)
        saved_report = json.loads(item.pop("report"))
        results.append({
            **saved_report,
            "id": item["id"],
            "incident_id": item["incident_id"],
            "created_at": item["created_at"],
        })

    return results
