"""Pruebas de integridad del conjunto de datos y separación sin fuga."""
from collections import Counter

from training.train import leer_datos, dividir_por_grupo
from app.categorias import CATEGORIAS


def test_800_registros_balanceados():
    filas = leer_datos()
    assert len(filas) == 800
    assert Counter(r["codigo_categoria"] for r in filas) == {
        codigo: 100 for codigo in CATEGORIAS
    }


def test_division_sin_grupos_compartidos():
    splits = dividir_por_grupo(leer_datos())
    assert {k: len(v) for k, v in splits.items()} == {
        "entrenamiento": 560, "validacion": 120, "prueba": 120
    }
    grupos = {k: {r["grupo"] for r in v} for k, v in splits.items()}
    assert not (grupos["entrenamiento"] & grupos["validacion"])
    assert not (grupos["entrenamiento"] & grupos["prueba"])
    assert not (grupos["validacion"] & grupos["prueba"])
    for split, cantidad in [
        ("entrenamiento", 70), ("validacion", 15), ("prueba", 15)
    ]:
        assert Counter(r["codigo_categoria"] for r in splits[split]) == {
            codigo: cantidad for codigo in CATEGORIAS
        }


def test_particion_reproducible():
    filas = leer_datos()
    assert dividir_por_grupo(filas) == dividir_por_grupo(filas)
