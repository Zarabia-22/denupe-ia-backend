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
    assert data["categoria"] == "Limpieza y residuos"
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


def test_catalogo_oficial_completo():
    from app.categorias import CATEGORIAS
    assert len(CATEGORIAS) == 8
    assert set(CATEGORIAS) == {
        "alumbrado", "seguridad", "limpieza", "agua",
        "transito", "areas_verdes", "infraestructura", "otros"
    }


def test_categorias_nuevas_sin_reentrenar():
    casos = [
        ("Fuga de agua potable", "Hay una fuga de agua en la tuberia de la avenida", "Agua y saneamiento"),
        ("Semaforo malogrado", "El semaforo no funciona en el cruce peatonal", "Tránsito y transporte"),
        ("Arbol caido en parque", "Un arbol caido bloquea los juegos infantiles", "Parques y áreas verdes"),
        ("Baches en la avenida", "Hay baches y veredas rotas en la via publica", "Vialidad e infraestructura"),
    ]
    with TestClient(app) as client:
        for titulo, descripcion, esperado in casos:
            response = client.post("/api/ia/sugerir-categoria", json={
                "titulo": titulo, "descripcion": descripcion
            })
            assert response.status_code == 200
            result = response.json()
            assert result["sugerida"] is True
            assert result["categoria"] == esperado
            assert result["confianza_modelo"] is None
