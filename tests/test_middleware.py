"""Pruebas aisladas de las protecciones HTTP del servicio."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware import RequestProtectionMiddleware


def test_rate_limit_responde_429_al_superar_cuota(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "1")
    api = FastAPI()
    api.add_middleware(RequestProtectionMiddleware)

    @api.get("/ping")
    def ping():
        return {"status": "ok"}

    with TestClient(api) as cliente:
        primera = cliente.get("/ping")
        segunda = cliente.get("/ping")

    assert primera.status_code == 200
    assert segunda.status_code == 429
    assert segunda.headers["retry-after"] == "60"
    assert segunda.headers.get("x-request-id")
