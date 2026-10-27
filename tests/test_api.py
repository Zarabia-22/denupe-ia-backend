"""Pruebas del contrato de predicción y errores del microservicio."""
from fastapi.testclient import TestClient
from app.main import app


def test_health():
    with TestClient(app) as client:
        result = client.get("/health")
    assert result.status_code == 200
    assert result.json()["status"] == "ok"


def test_basura():
    with TestClient(app) as client:
        result = client.post("/api/ia/sugerir-categoria", json={
            "titulo": "Basura acumulada en mi calle",
            "descripcion": "Hay bolsas de basura y residuos que no han sido recogidos durante varios dias"
        })
    assert result.status_code == 200
    data = result.json()
    assert data["sugerida"] is True
    assert data["categoria"] == "Limpieza"
    assert 0 <= data["confianza_modelo"] <= 1


def test_input_validation():
    with TestClient(app) as client:
        result = client.post("/api/ia/sugerir-categoria", json={
            "titulo": "a", "descripcion": "corta"
        })
    assert result.status_code == 422


def test_out_of_domain_is_not_guessed():
    with TestClient(app) as client:
        result = client.post("/api/ia/sugerir-categoria", json={
            "titulo": "Quiero realizar una consulta",
            "descripcion": "Necesito ayuda con mi constancia de estudios universitarios"
        })
    assert result.status_code == 200
    assert result.json()["sugerida"] is False
    assert result.json()["categoria"] is None


def test_no_extra_fields():
    with TestClient(app) as client:
        result = client.post("/api/ia/sugerir-categoria", json={
            "titulo": "Basura acumulada",
            "descripcion": "Se acumula basura en la avenida",
            "dni": "12345678",
        })
    assert result.status_code == 422
