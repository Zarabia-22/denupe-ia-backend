"""Entrena y evalúa el clasificador de ocho categorías, sin fugas por paráfrasis.

Ejecutar desde la raíz: python -m training.train
Los 800 ejemplos son sintéticos. El test agrupa casos de origen y
no proporciona una estimación de precisión en denuncias reales.
"""
from collections import Counter
import csv
import gzip
import json
from pathlib import Path
import random

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, classification_report, confusion_matrix, f1_score
)
from sklearn.pipeline import FeatureUnion

from app.categorias import CATEGORIAS
from app.text_processing import cobertura_vocabulario, normalizar_texto

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data" / "denuncias_simuladas_800.csv"
MODELS = BASE / "models"
SEED = 2026
MARGEN_MINIMO = 0.10
COBERTURA_MINIMA = 0.25
TERMINOS_MINIMOS = 2


def leer_datos():
    with DATA.open(encoding="utf-8-sig", newline="") as f:
        filas = list(csv.DictReader(f))
    cantidades = Counter(r["codigo_categoria"] for r in filas)
    if len(filas) != 800 or set(cantidades) != set(CATEGORIAS):
        raise ValueError(f"Se esperan 800 denuncias en 8 categorías: {cantidades}")
    if any(n != 100 for n in cantidades.values()):
        raise ValueError(f"Se requieren 100 ejemplos por categoría: {cantidades}")
    identificadores = [r["id"] for r in filas]
    if len(identificadores) != len(set(identificadores)):
        raise ValueError("Identificadores duplicados en el dataset")
    vistos = set()
    grupos = {}
    for r in filas:
        codigo = r["codigo_categoria"]
        if r["categoria"] != CATEGORIAS[codigo] or r["origen"] != "simulada":
            raise ValueError("Nombre de categoría u origen no coincide con el catálogo")
        texto = normalizar_texto(r["titulo"] + " " + r["descripcion"])
        if not texto or texto in vistos:
            raise ValueError("Texto vacío o duplicado en el dataset")
        vistos.add(texto)
        grupo = r["grupo"]
        if not grupo.startswith(codigo + "-"):
            raise ValueError("Grupo de paráfrasis no pertenece a su categoría")
        grupos.setdefault(grupo, []).append(r)
    for categoria in CATEGORIAS:
        de_categoria = [g for g in grupos if g.startswith(categoria + "-")]
        if len(de_categoria) != 20 or any(len(grupos[g]) != 5 for g in de_categoria):
            raise ValueError(f"Se esperan 20 casos con 5 variantes en {categoria}")
    return filas


def dividir_por_grupo(filas):
    """14 casos entrenamiento, 3 validación, 3 prueba POR categoría (70/15/15)."""
    seleccion = {}
    for indice, codigo in enumerate(CATEGORIAS):
        grupos = sorted({r["grupo"] for r in filas if r["codigo_categoria"] == codigo})
        random.Random(SEED + indice).shuffle(grupos)
        seleccion.update({grupo: "entrenamiento" for grupo in grupos[:14]})
        seleccion.update({grupo: "validacion" for grupo in grupos[14:17]})
        seleccion.update({grupo: "prueba" for grupo in grupos[17:]})
    resultado = {
        split: [r for r in filas if seleccion[r["grupo"]] == split]
        for split in ("entrenamiento", "validacion", "prueba")
    }
    assert [len(resultado[s]) for s in resultado] == [560, 120, 120]
    return resultado


def textos_y_etiquetas(filas):
    return (
        [r["titulo"] + ". " + r["descripcion"] for r in filas],
        [r["codigo_categoria"] for r in filas],
    )


def vectorizador_nuevo():
    """Palabras + fragmentos de caracteres: robustez ante variaciones ortográficas."""
    return FeatureUnion(
        transformer_list=[
            ("palabras", TfidfVectorizer(
                preprocessor=normalizar_texto,
                lowercase=False,
                ngram_range=(1, 2),
                min_df=1,
                max_df=0.98,
                sublinear_tf=True,
            )),
            ("caracteres", TfidfVectorizer(
                preprocessor=normalizar_texto,
                lowercase=False,
                analyzer="char_wb",
                ngram_range=(3, 5),
                min_df=2,
                sublinear_tf=True,
            )),
        ],
        transformer_weights={"palabras": 1.5, "caracteres": 1.0},
    )


def evaluar_abstencion(textos, etiquetas, modelo, vectorizador, umbral):
    matriz = vectorizador.transform(textos)
    probabilidades = modelo.predict_proba(matriz)
    orden = np.argsort(probabilidades, axis=1)
    clases = modelo.classes_
    predicciones = clases[orden[:, -1]]
    aciertos = np.asarray(etiquetas) == predicciones
    aceptadas = []
    for i, texto in enumerate(textos):
        cobertura, reconocidos, _ = cobertura_vocabulario(texto, vectorizador)
        margen = float(probabilidades[i, orden[i, -1]] - probabilidades[i, orden[i, -2]])
        aceptadas.append(
            float(probabilidades[i, orden[i, -1]]) >= umbral
            and margen >= MARGEN_MINIMO
            and reconocidos >= TERMINOS_MINIMOS
            and cobertura >= COBERTURA_MINIMA
        )
    aceptadas = np.asarray(aceptadas)
    total = int(aceptadas.sum())
    return {
        "sugeridas": total,
        "total": len(etiquetas),
        "cobertura_sugerencias": round(float(aceptadas.mean()), 4),
        "precision_sugerencias": round(float(aciertos[aceptadas].mean()), 4) if total else None,
    }


def seleccionar_umbral(textos, etiquetas, modelo, vectorizador):
    """El umbral se escoge SOLO con validación, nunca con prueba."""
    opciones = [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]
    resultados = [
        (umbral, evaluar_abstencion(textos, etiquetas, modelo, vectorizador, umbral))
        for umbral in opciones
    ]
    aptos = [(t, v) for t, v in resultados
             if v["sugeridas"] >= 20
             and v["precision_sugerencias"] is not None
             and v["precision_sugerencias"] >= 0.90]
    if aptos:
        return max(aptos, key=lambda x: (x[1]["sugeridas"], -x[0]))[0]
    return 0.80  # Conservador si el conjunto de validación no alcanza el objetivo.


def main():
    datos = leer_datos()
    divisiones = dividir_por_grupo(datos)
    x_train, y_train = textos_y_etiquetas(divisiones["entrenamiento"])
    x_val, y_val = textos_y_etiquetas(divisiones["validacion"])
    x_test, y_test = textos_y_etiquetas(divisiones["prueba"])

    vectorizador = vectorizador_nuevo()
    z_train = vectorizador.fit_transform(x_train)
    modelo = LogisticRegression(
        C=5.0, max_iter=2500, class_weight="balanced", random_state=SEED
    )
    modelo.fit(z_train, y_train)
    if set(modelo.classes_) != set(CATEGORIAS):
        raise RuntimeError("El modelo no aprendió las ocho clases oficiales")

    umbral = seleccionar_umbral(x_val, y_val, modelo, vectorizador)
    z_test = vectorizador.transform(x_test)
    pred_test = modelo.predict(z_test)
    labels = list(CATEGORIAS)
    metricas = {
        "version": 2,
        "origen_datos": "800 denuncias simuladas, NO denuncias ciudadanas reales",
        "datos": len(datos),
        "categorias": CATEGORIAS,
        "distribucion": {codigo: 100 for codigo in CATEGORIAS},
        "metodologia": "Separación por grupo de 5 paráfrasis del mismo caso; sin grupos compartidos entre particiones.",
        "semilla": SEED,
        "entrenamiento": len(x_train),
        "validacion": len(x_val),
        "prueba": len(x_test),
        "modelo": "TF-IDF palabras 1-2 + caracteres 3-5 + LogisticRegression",
        "umbral_confianza": umbral,
        "margen_minimo": MARGEN_MINIMO,
        "cobertura_minima": COBERTURA_MINIMA,
        "terminos_minimos": TERMINOS_MINIMOS,
        "accuracy_prueba_simulada": round(float(accuracy_score(y_test, pred_test)), 4),
        "f1_macro_prueba_simulada": round(float(f1_score(
            y_test, pred_test, labels=labels, average="macro"
        )), 4),
        "evaluacion_validacion": evaluar_abstencion(
            x_val, y_val, modelo, vectorizador, umbral
        ),
        "evaluacion_prueba": evaluar_abstencion(
            x_test, y_test, modelo, vectorizador, umbral
        ),
        "reporte_por_categoria": classification_report(
            y_test, pred_test, labels=labels, output_dict=True, zero_division=0
        ),
        "matriz_confusion": {
            "orden_categorias": labels,
            "valores": confusion_matrix(y_test, pred_test, labels=labels).tolist(),
        },
        "advertencia": (
            "Las métricas describen solamente textos artificiales. El puntaje de "
            "predict_proba no es confianza calibrada ni garantiza exactitud real."
        ),
    }
    MODELS.mkdir(exist_ok=True)
    joblib.dump(modelo, MODELS / "modelo_categorias.joblib.gz", compress=("gzip", 3))
    joblib.dump(vectorizador, MODELS / "vectorizador_tfidf.joblib.gz", compress=("gzip", 3))
    (MODELS / "metricas.json").write_text(
        json.dumps(metricas, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "datos": metricas["datos"],
        "particiones": [len(x_train), len(x_val), len(x_test)],
        "accuracy_prueba_simulada": metricas["accuracy_prueba_simulada"],
        "f1_macro_prueba_simulada": metricas["f1_macro_prueba_simulada"],
        "umbral": umbral,
        "validacion": metricas["evaluacion_validacion"],
        "prueba": metricas["evaluacion_prueba"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
