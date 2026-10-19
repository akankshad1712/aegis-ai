
from fastapi.testclient import TestClient

from app.main import app
from app import db


def test_incident_log_analysis_is_saved_and_used_in_investigation(
    tmp_path, monkeypatch
):
    # Use a temporary database so this test does not modify aegis.db.
    test_db = tmp_path / "aegis_test.db"
    monkeypatch.setattr(db, "DB_PATH", test_db)
    monkeypatch.setenv("AEGIS_API_KEY", "test-secret-key")

    with TestClient(
        app,
        headers={"X-API-Key": "test-secret-key"},
    ) as client:
        db.init_db()

        incident_response = client.post(
            "/api/incidents",
            json={
                "title": "Checkout database timeout",
                "service": "checkout-api",
                "severity": "high",
                "description": (
                    "Checkout requests fail when the database times out."
                ),
            },
        )
        assert incident_response.status_code == 201
        incident_id = incident_response.json()["id"]

        logs_response = client.post(
            f"/api/incidents/{incident_id}/logs/analyze",
            json={
                "logs": (
                    "2026-10-19T10:15:01Z INFO checkout-api Server started\n"
                    "2026-10-19T10:15:12Z ERROR checkout-api "
                    "Database connection timeout\n"
                    "2026-10-19T10:15:13Z ERROR checkout-api "
                    "HTTP 500 returned\n"
                    "2026-10-19T10:15:14Z WARN checkout-api "
                    "p95 latency increased"
                )
            },
        )
        assert logs_response.status_code == 200

        saved_logs = db.get_latest_log_analysis(incident_id)
        assert saved_logs is not None

        investigation_response = client.post(
            f"/api/incidents/{incident_id}/investigate"
        )
        assert investigation_response.status_code == 200

        report = investigation_response.json()
        findings = report.get("findings", [])

        hypotheses = [
            finding.get("hypothesis", "")
            for finding in findings
        ]

        assert any(
            "Dependency timeout" in hypothesis
            for hypothesis in hypotheses
        )
        assert any(
            "Application error spike" in hypothesis
            for hypothesis in hypotheses
        )
