"""Pruebas de la API y regresión del clasificador de ocho categorías."""
import json
from pathlib import Path

from fastapi.testclient import TestClient
from app.categorias import CATEGORIAS
from app.main import app
from app.predictor import cargar_modelo

CASOS = [
    ("Poste de alumbrado sin luz", "El foco de la luminaria del poste quedó apagado y la vereda está oscura", "Alumbrado público"),
    ("Intento de robo a vecinos", "Un sujeto trató de asaltar a los peatones y quitarles sus celulares", "Seguridad ciudadana"),
    ("Acumulación de basura", "Hay bolsas de basura y residuos sin recoger en el contenedor", "Limpieza y residuos"),
    ("Fuga de agua potable", "Una tubería rota derrama agua en la avenida y provoca un aniego", "Agua y saneamiento"),
    ("Semáforo del cruce malogrado", "El semáforo no regula los vehículos y provoca congestión vehicular", "Tránsito y transporte"),
    ("Árbol caído en el parque", "Un árbol se derrumbó sobre el jardín y los juegos infantiles", "Parques y áreas verdes"),
    ("Baches en la pista principal", "El pavimento roto tiene baches profundos y las veredas están agrietadas", "Vialidad e infraestructura"),
    ("Ruido intenso durante la noche", "Un local emite música con parlantes muy fuertes hasta la madrugada", "Otros"),
]


def enviar(titulo, descripcion):
    with TestClient(app) as cliente:
        return cliente.post("/api/ia/sugerir-categoria", json={
            "titulo": titulo, "descripcion": descripcion,
        })


def test_salud():
    with TestClient(app) as cliente:
        r = cliente.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["modelo"] == "tfidf_logistic_regression_8"


def test_modelo_entrenado_en_todas_las_categorias():
    modelo, vectorizador, metricas = cargar_modelo()
    assert set(modelo.classes_) == set(CATEGORIAS)
    assert len(vectorizador.transformer_list) == 2
    assert metricas["version"] == 3
    assert metricas["datos"] == 2400
    assert metricas["entrenamiento"] == 1680
    assert metricas["validacion"] == 360
    assert metricas["prueba"] == 360


def test_predicciones_o_abstencion_segun_catalogo():
    modelo, vectorizador, _ = cargar_modelo()
    for titulo, descripcion, esperado in CASOS:
        entrada = titulo + ". " + descripcion
        prediccion = modelo.predict(vectorizador.transform([entrada]))[0]
        assert CATEGORIAS[prediccion] == esperado, (titulo, prediccion)
        r = enviar(titulo, descripcion)
        assert r.status_code == 200
        salida = r.json()
        if salida["sugerida"]:
            assert salida["categoria"] == esperado
            assert 0 <= salida["confianza_modelo"] <= 1
        else:
            assert salida["categoria"] is None
            assert salida["motivo"]


def test_rechazo_fuera_de_dominio():
    r = enviar(
        "Necesito una constancia universitaria",
        "Solicito ayuda para tramitar mi constancia de estudios y mis certificados académicos",
    )
    assert r.status_code == 200
    assert r.json()["sugerida"] is False
    assert r.json()["categoria"] is None


def test_validaciones_422():
    with TestClient(app) as cliente:
        corta = cliente.post("/api/ia/sugerir-categoria", json={
            "titulo": "a", "descripcion": "corta",
        })
        extra = cliente.post("/api/ia/sugerir-categoria", json={
            "titulo": "Basura en la avenida",
            "descripcion": "Hay bolsas de basura acumuladas desde ayer",
            "dni": "12345678",
        })
    assert corta.status_code == 422
    assert extra.status_code == 422


def test_sin_inferir_categoria_ausente():
    for titulo, descripcion, _ in CASOS:
        resultado = enviar(titulo, descripcion).json()
        assert resultado["categoria"] is None or resultado["categoria"] in CATEGORIAS.values()


def test_normalizacion_de_tildes_y_espacios():
    from app.text_processing import normalizar_texto
    assert normalizar_texto(" ÁRBOL  CAÍDO\tEN  EL  PARQUE! ") == "arbol caido en el parque"
    assert "@" not in normalizar_texto("Consulta: vecino@ejemplo.com")



def test_entidad_rechaza_coordenadas_sin_par():
    with TestClient(app) as cliente:
        response = cliente.post("/api/ia/sugerir-entidad", json={
            "categoria": "Seguridad ciudadana",
            "departamento": "Lima",
            "provincia": "Lima",
            "distrito": "Miraflores",
            "titulo": "Robo en la vía pública",
            "descripcion": "Reporto un robo ocurrido cerca del parque.",
            "latitud": -12.12,
        })
    assert response.status_code == 422


def test_entidad_rechaza_campos_extra():
    with TestClient(app) as cliente:
        response = cliente.post("/api/ia/sugerir-entidad", json={
            "categoria": "Limpieza y residuos",
            "departamento": "Lima",
            "provincia": "Lima",
            "distrito": "Miraflores",
            "titulo": "Basura acumulada en la avenida",
            "descripcion": "Hay residuos acumulados en la vía pública.",
            "dni": "12345678",
        })
    assert response.status_code == 422


def test_health_ready_expone_estado_tecnico():
    with TestClient(app) as cliente:
        response = cliente.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["categorias"] == 8



def test_respuestas_incluyen_identificador_y_cabeceras_de_seguridad():
    with TestClient(app) as cliente:
        response = cliente.get("/health")
    assert response.status_code == 200
    assert response.headers.get("x-request-id")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"


def test_solicitud_demasiado_grande_se_rechaza():
    with TestClient(app) as cliente:
        response = cliente.post(
            "/api/ia/sugerir-categoria",
            content=b"x" * 17000,
            headers={"content-type": "application/json"},
        )
    assert response.status_code == 413


def test_health_ready_valida_el_catalogo_de_entidades():
    with TestClient(app) as cliente:
        response = cliente.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["entidades_catalogo"] == 96


def test_entidades_disponibles_exige_gps_antes_de_listar():
    with TestClient(app) as cliente:
        response = cliente.get("/api/entidades/disponibles", params={
            "categoria": "Limpieza y residuos",
            "departamento": "Lima", "provincia": "Lima", "distrito": "Miraflores",
        })
    assert response.status_code == 422


def test_entidades_disponibles_no_expone_categoria_no_habilitada_sin_gps():
    with TestClient(app) as cliente:
        response = cliente.get("/api/entidades/disponibles", params={
            "categoria": "Vialidad e infraestructura",
            "departamento": "Lima", "provincia": "Lima", "distrito": "Miraflores",
        })
    assert response.status_code == 422


def test_listar_entidades_disponibles_rechaza_coordenadas_incompletas():
    with TestClient(app) as cliente:
        response = cliente.get("/api/entidades/disponibles", params={
            "categoria": "Seguridad ciudadana",
            "departamento": "Lima",
            "provincia": "Lima",
            "distrito": "Miraflores",
            "latitud": -12.12,
        })
    assert response.status_code == 422


def test_entidades_disponibles_no_consulta_sedapal_sin_gps():
    with TestClient(app) as cliente:
        response = cliente.get("/api/entidades/disponibles", params={
            "categoria": "Agua y saneamiento",
            "departamento": "Lima", "provincia": "Lima", "distrito": "Miraflores",
        })
    assert response.status_code == 422


def test_entidades_disponibles_no_ofrece_revision_sin_gps():
    with TestClient(app) as cliente:
        response = cliente.get("/api/entidades/disponibles", params={
            "categoria": "Otros",
            "departamento": "Lima", "provincia": "Lima", "distrito": "Miraflores",
        })
    assert response.status_code == 422


def test_entidades_disponibles_consulta_matriz_tras_resolver_gps(monkeypatch):
    from app import main
    from app.schemas import EntidadPublica

    monkeypatch.setattr(main, "resolver_distrito_por_punto", lambda lat, lon: {
        "ubigeo": "150122", "departamento": "Lima", "provincia": "Lima", "distrito": "Miraflores",
    })
    monkeypatch.setattr(main, "consultar_resolutor_categoria", lambda ubigeo, codigo: {
        "requiere_gps": True, "asignar_solo_tras_gps": True,
    })
    monkeypatch.setattr(main, "listar_entidades_disponibles", lambda *args: [
        EntidadPublica(
            id="mun-150122", nombre="Municipalidad Distrital de Miraflores",
            tipo="municipalidad_distrital",
            ambito={"departamento": "Lima", "provincia": "Lima", "distrito": "Miraflores"},
        )
    ])
    with TestClient(app) as cliente:
        response = cliente.get("/api/entidades/disponibles", params={
            "categoria": "Limpieza y residuos",
            "latitud": -12.12, "longitud": -77.03,
        })
    assert response.status_code == 200
    assert response.json()["entidades"][0]["ambito"]["distrito"] == "Miraflores"
