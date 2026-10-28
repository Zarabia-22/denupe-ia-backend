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
