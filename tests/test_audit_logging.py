
import pytest

from app import db


def setup_test_db(monkeypatch, tmp_path):
    test_db_path = tmp_path / "aegis_test.db"
    monkeypatch.setattr(db, "DB_PATH", test_db_path)
    db.init_db()
    return test_db_path


def test_status_change_is_audited_and_persists(
    monkeypatch, tmp_path
):
    setup_test_db(monkeypatch, tmp_path)

    incident = db.create_incident(
        title="Database latency",
        service="payments",
        severity="high",
        description="Database requests are timing out.",
    )
    incident_id = incident["id"]

    updated = db.update_incident_status(
        incident_id, "investigating"
    )

    assert updated is not None
    assert updated["status"] == "investigating"

    events = db.list_audit_events(incident_id=incident_id)
    status_events = [
        event
        for event in events
        if event["event_type"] == "incident.status_changed"
    ]

    assert len(status_events) == 1
    assert status_events[0]["details"] == {
        "previous_status": "open",
        "new_status": "investigating",
    }

    # Re-initializing the schema must not erase audit history.
    db.init_db()

    persisted = db.list_audit_events(incident_id=incident_id)

    assert any(
        event["event_type"] == "incident.status_changed"
        for event in persisted
    )


def test_action_proposal_and_simulation_are_audited(
    monkeypatch, tmp_path
):
    setup_test_db(monkeypatch, tmp_path)

    incident = db.create_incident(
        title="API errors",
        service="api",
        severity="high",
        description="Elevated API error rate.",
    )
    incident_id = incident["id"]

    action = db.create_action(
        incident_id=incident_id,
        action_type="restart_simulation",
        rationale="Test the proposed recovery workflow.",
    )

    assert action["status"] == "proposed"

    approved = db.approve_simulated_action(action["id"])

    assert approved is not None
    assert approved["status"] == "simulated"
    assert "SIMULATION ONLY" in approved["result"]

    events = db.list_audit_events(incident_id=incident_id)
    event_types = [
        event["event_type"] for event in events
    ]

    assert "incident.created" in event_types
    assert "action.proposed" in event_types
    assert event_types.count("action.simulation_approved") == 1

    # Re-approving a simulated action must fail without
    # creating another approval audit event.
    with pytest.raises(
        ValueError, match="already simulated"
    ):
        db.approve_simulated_action(action["id"])

    events_after_repeat = db.list_audit_events(
        incident_id=incident_id
    )
    approval_events = [
        event
        for event in events_after_repeat
        if event["event_type"] == "action.simulation_approved"
    ]

    assert len(approval_events) == 1


def test_invalid_status_does_not_change_incident(
    monkeypatch, tmp_path
):
    setup_test_db(monkeypatch, tmp_path)

    incident = db.create_incident(
        title="Worker unavailable",
        service="worker",
        severity="medium",
        description="Worker is not responding.",
    )

    with pytest.raises(ValueError):
        db.update_incident_status(
            incident["id"], "invalid"
        )

    current = db.get_incident(incident["id"])

    assert current is not None
    assert current["status"] == "open"

    events = db.list_audit_events(
        incident_id=incident["id"]
    )

    assert not any(
        event["event_type"] == "incident.status_changed"
        for event in events
    )
