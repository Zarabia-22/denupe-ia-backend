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
