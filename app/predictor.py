"""Predicción de ocho categorías oficiales con rechazo de textos ambiguos.

Clasificador entrenado: TF-IDF (palabras y caracteres) + regresión logística.
No usa reglas de clasificación. El valor predict_proba no está calibrado.
"""
from functools import lru_cache
import json
from pathlib import Path

import joblib
import numpy as np

from .categorias import CATEGORIAS
from .schemas import SugerenciaSalida
from .text_processing import cobertura_vocabulario, normalizar_texto

MODELS = Path(__file__).resolve().parent.parent / "models"


@lru_cache(maxsize=1)
def cargar_modelo():
    """Carga artefactos versionados y evita servir accidentalmente el modelo viejo."""
    with (MODELS / "metricas.json").open(encoding="utf-8") as f:
        metricas = json.load(f)
    if metricas.get("version") != 2:
        raise RuntimeError("Falta entrenar el modelo de ocho categorías (version 2)")
    modelo = joblib.load(MODELS / "modelo_categorias.joblib.gz")
    vectorizador = joblib.load(MODELS / "vectorizador_tfidf.joblib.gz")
    if set(modelo.classes_) != set(CATEGORIAS):
        raise RuntimeError("El modelo no coincide con las ocho categorías de DenuPe")
    return modelo, vectorizador, metricas


def sugerir_categoria(titulo: str, descripcion: str) -> SugerenciaSalida:
    modelo, vectorizador, metricas = cargar_modelo()
    texto = titulo.strip() + ". " + descripcion.strip()
    texto_normalizado = normalizar_texto(texto)
    cobertura, reconocidos, _ = cobertura_vocabulario(texto_normalizado, vectorizador)
    if (
        not texto_normalizado
        or reconocidos < int(metricas["terminos_minimos"])
        or cobertura < float(metricas["cobertura_minima"])
    ):
        return SugerenciaSalida(
            sugerida=False, categoria=None, confianza_modelo=None,
            cobertura_vocabulario=round(cobertura, 4),
            motivo="No se reconocen suficientes términos relevantes. Elige la categoría manualmente.",
        )

    matriz = vectorizador.transform([texto_normalizado])
    probabilidades = modelo.predict_proba(matriz)[0]
    indices = np.argsort(probabilidades)
    posicion = int(indices[-1])
    puntaje = float(probabilidades[posicion])
    margen = float(probabilidades[posicion] - probabilidades[int(indices[-2])])
    confianza = round(puntaje, 4)
    if (
        puntaje < float(metricas["umbral_confianza"])
        or margen < float(metricas["margen_minimo"])
    ):
        return SugerenciaSalida(
            sugerida=False, categoria=None, confianza_modelo=confianza,
            cobertura_vocabulario=round(cobertura, 4),
            motivo="La predicción es incierta o ambigua. Selecciona una categoría manualmente.",
        )

    codigo = str(modelo.classes_[posicion])
    return SugerenciaSalida(
        sugerida=True,
        categoria=CATEGORIAS[codigo],
        confianza_modelo=confianza,
        cobertura_vocabulario=round(cobertura, 4),
        motivo=None,
    )
