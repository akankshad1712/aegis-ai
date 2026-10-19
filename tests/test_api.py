
import os

from fastapi.testclient import TestClient

from app import db
import app.main as main


TEST_API_KEY = "test-secret-key"
_ORIGINAL_API_KEY = os.environ.get("AEGIS_API_KEY")
TEST_DB = db.DB_PATH.parent / "test_aegis.db"


def setup_module():
    os.environ["AEGIS_API_KEY"] = TEST_API_KEY

    db.DB_PATH = TEST_DB
    if TEST_DB.exists():
        TEST_DB.unlink()

    db.init_db()


def teardown_module():
    if TEST_DB.exists():
        TEST_DB.unlink()

    if _ORIGINAL_API_KEY is None:
        os.environ.pop("AEGIS_API_KEY", None)
    else:
        os.environ["AEGIS_API_KEY"] = _ORIGINAL_API_KEY


client = TestClient(
    main.app,
    headers={"X-API-Key": TEST_API_KEY},
)


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_investigate_and_simulate_action():
    created = client.post(
        "/api/incidents",
        json={
            "title": "API timeout after release",
            "service": "checkout-api",
            "severity": "high",
            "description": (
                "Requests timeout after deployment and "
                "5xx errors increased."
            ),
        },
    )
    assert created.status_code == 201
    incident_id = created.json()["id"]

    report = client.post(
        f"/api/incidents/{incident_id}/investigate"
    )
    assert report.status_code == 200
    assert len(report.json()["findings"]) >= 2

    action = client.post(
        f"/api/incidents/{incident_id}/actions",
        json={
            "action_type": "rollback_simulation",
            "rationale": (
                "Test a simulated rollback after reviewing the evidence."
            ),
        },
    )
    assert action.status_code == 201
    action_id = action.json()["id"]

    approved = client.post(
        f"/api/actions/{action_id}/approve-simulation"
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "simulated"
    assert "SIMULATION ONLY" in approved.json()["result"]


def test_unknown_incident_returns_404():
    response = client.post(
        "/api/incidents/999999/investigate"
    )
    assert response.status_code == 404


def test_real_api_rejects_missing_key():
    unauthenticated_client = TestClient(main.app)
    response = unauthenticated_client.get("/api/incidents")
    assert response.status_code == 401


def test_real_api_rejects_invalid_key():
    unauthenticated_client = TestClient(
        main.app,
        headers={"X-API-Key": "wrong-key"},
    )
    response = unauthenticated_client.get("/api/incidents")
    assert response.status_code == 401


def test_health_is_public_without_api_key():
    unauthenticated_client = TestClient(main.app)
    response = unauthenticated_client.get("/api/health")
    assert response.status_code == 200


def test_real_api_fails_closed_without_configured_key(monkeypatch):
    monkeypatch.delenv("AEGIS_API_KEY", raising=False)

    unauthenticated_client = TestClient(main.app)
    response = unauthenticated_client.get("/api/incidents")

    assert response.status_code == 503
