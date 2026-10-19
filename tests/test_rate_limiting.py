from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address


def test_rate_limit_returns_429():
    limiter = Limiter(
        key_func=get_remote_address,
        storage_uri="memory://",
    )

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(
        RateLimitExceeded,
        _rate_limit_exceeded_handler,
    )

    @app.get("/limited")
    @limiter.limit("2/minute")
    def limited_endpoint(request: Request):
        return {"status": "ok"}

    with TestClient(app) as client:
        assert client.get("/limited").status_code == 200
        assert client.get("/limited").status_code == 200
        assert client.get("/limited").status_code == 429
