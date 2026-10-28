"""Pruebas de integridad del conjunto de datos y separación sin fuga."""
from collections import Counter

from training.train import leer_datos, dividir_por_grupo
from app.categorias import CATEGORIAS


def test_2400_registros_balanceados():
    filas = leer_datos()
    assert len(filas) == 2400
    assert Counter(r["codigo_categoria"] for r in filas) == {
        codigo: 300 for codigo in CATEGORIAS
    }


def test_division_sin_grupos_compartidos():
    splits = dividir_por_grupo(leer_datos())
    assert {k: len(v) for k, v in splits.items()} == {
        "entrenamiento": 1680, "validacion": 360, "prueba": 360
    }
    grupos = {k: {r["grupo"] for r in v} for k, v in splits.items()}
    assert not (grupos["entrenamiento"] & grupos["validacion"])
    assert not (grupos["entrenamiento"] & grupos["prueba"])
    assert not (grupos["validacion"] & grupos["prueba"])
    for split, cantidad in [
        ("entrenamiento", 210), ("validacion", 45), ("prueba", 45)
    ]:
        assert Counter(r["codigo_categoria"] for r in splits[split]) == {
            codigo: cantidad for codigo in CATEGORIAS
        }


def test_particion_reproducible():
    filas = leer_datos()
    assert dividir_por_grupo(filas) == dividir_por_grupo(filas)


def test_objetivo_minimo_de_exactitud_simulada():
    """Evita publicar modelos inferiores al umbral acordado en este benchmark."""
    import json
    from pathlib import Path

    metricas = json.loads(
        (Path(__file__).resolve().parents[1] / "models" / "metricas.json")
        .read_text(encoding="utf-8")
    )
    assert metricas["datos"] == 2400
    assert metricas["accuracy_prueba_simulada"] >= 0.90
    assert metricas["f1_macro_prueba_simulada"] >= 0.90
    assert metricas["evaluacion_prueba"]["total"] == 360
    assert metricas["origen_datos"].lower().find("sintet") >= 0
