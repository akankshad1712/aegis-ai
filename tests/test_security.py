
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.security import require_api_key


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AEGIS_API_KEY", "test-secret-key")

    app = FastAPI()

    @app.get("/protected", dependencies=[Depends(require_api_key)])
    def protected():
        return {"authenticated": True}

    return TestClient(app)


def test_missing_key_is_rejected(client):
    response = client.get("/protected")
    assert response.status_code == 401


def test_invalid_key_is_rejected(client):
    response = client.get(
        "/protected",
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 401


def test_valid_key_is_accepted(client):
    response = client.get(
        "/protected",
        headers={"X-API-Key": "test-secret-key"},
    )
    assert response.status_code == 200
    assert response.json() == {"authenticated": True}
