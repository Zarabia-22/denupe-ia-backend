"""Clasificador original de Colab: TF-IDF + DecisionTreeClassifier.

Los valores predict_proba son proporciones de hojas, NO confianza calibrada.
Los modelos comprimidos proceden del notebook de la sesión 9 y se cargan sólo
desde archivos controlados del repositorio.
"""
from functools import lru_cache
import re
import unicodedata
from pathlib import Path
import gzip

import joblib

from .schemas import SugerenciaSalida
from .categorias import CATEGORIAS, ETIQUETAS_MODELO, PATRONES_ADICIONALES

MODELS = Path(__file__).resolve().parent.parent / "models"

# Evita clasificar a partir de palabras genéricas o sólo referencias espaciales.
PALABRAS_COMUNES = frozenset("""
a al algo ante bajo cerca con contra cual cuando de del desde donde durante el ella en entre era es
esta estan este esto estos fue ha hay la las le les lo los mas me mi mis mucho muy ni no nos
nuestro o para pero por que se ser si sin sobre su sus te tiene toda todo todos un una unas uno unos
vecino vecinos vivienda casas casa calle avenida parque mercado colegio barrio zona urbanizacion distrito
esquina frente principal problema reporto reportan sucede hace dias dia varios varias aqui alli
""".split())


@lru_cache(maxsize=1)
def cargar_modelo():
    with gzip.open(MODELS / "modelo_categorias.joblib.gz", "rb") as file:
        modelo = joblib.load(file)
    with gzip.open(MODELS / "vectorizador_tfidf.joblib.gz", "rb") as file:
        vectorizador = joblib.load(file)
    return modelo, vectorizador


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip()


def _categoria_explicita(texto: str) -> str | None:
    """Reglas para categorías nuevas: abstenerse si hay varias coincidencias."""
    normalizado = f" {_normalizar(texto)} "
    coincidencias = [
        codigo
        for codigo, patrones in PATRONES_ADICIONALES.items()
        if any(f" {_normalizar(patron)} " in normalizado for patron in patrones)
    ]
    return CATEGORIAS[coincidencias[0]] if len(coincidencias) == 1 else None


def sugerir_categoria(titulo: str, descripcion: str) -> SugerenciaSalida:
    modelo, vectorizador = cargar_modelo()
    texto = f"{titulo.strip()} {descripcion.strip()}"
    categoria_explicita = _categoria_explicita(texto)
    if categoria_explicita is not None:
        return SugerenciaSalida(
            sugerida=True,
            categoria=categoria_explicita,
            confianza_modelo=None,  # Regla explícita, no predicción del árbol.
            cobertura_vocabulario=0.0,  # No interviene en esta decisión.
            motivo=None,
        )
    matriz = vectorizador.transform([texto])

    # Emplear el mismo tokenizador/preprocesador que el vectorizador entrenado.
    tokens = vectorizador.build_tokenizer()(
        vectorizador.build_preprocessor()(texto)
    )
    significativos = [t for t in tokens if t not in PALABRAS_COMUNES and len(t) > 2]
    reconocidos = [t for t in significativos if t in vectorizador.vocabulary_]
    cobertura = len(reconocidos) / len(significativos) if significativos else 0.0

    if matriz.nnz == 0 or len(reconocidos) < 2 or cobertura < 0.25:
        return SugerenciaSalida(
            sugerida=False,
            categoria=None,
            confianza_modelo=None,
            cobertura_vocabulario=round(cobertura, 4),
            motivo="No hay suficientes términos reconocidos para sugerir una categoría con fiabilidad.",
        )

    categoria = str(modelo.predict(matriz)[0])
    clases = list(modelo.classes_)
    prob = float(modelo.predict_proba(matriz)[0][clases.index(categoria)])

    # Umbral heurístico, no validado en denuncias reales.
    if prob < 0.75:
        return SugerenciaSalida(
            sugerida=False,
            categoria=None,
            confianza_modelo=round(prob, 4),
            cobertura_vocabulario=round(cobertura, 4),
            motivo="La predicción es ambigua. Selecciona una categoría manualmente.",
        )

    etiqueta_oficial = ETIQUETAS_MODELO.get(categoria)
    if etiqueta_oficial is None:
        return SugerenciaSalida(
            sugerida=False,
            categoria=None,
            confianza_modelo=round(prob, 4),
            cobertura_vocabulario=round(cobertura, 4),
            motivo="El modelo devolvió una categoría fuera del catálogo.",
        )

    return SugerenciaSalida(
        sugerida=True,
        categoria=etiqueta_oficial,
        confianza_modelo=round(prob, 4),
        cobertura_vocabulario=round(cobertura, 4),
        motivo=None,
    )
