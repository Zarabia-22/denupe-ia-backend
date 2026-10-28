"""Entrenamiento reproducible: 2400 reportes sintéticos, ocho categorías.

Selección del modelo exclusivamente con validación. Evaluación de prueba una sola
vez después de elegir hiperparámetros. Grupos de paráfrasis no se comparten.
"""
from collections import Counter
import csv
import json
from pathlib import Path
import random

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import ComplementNB, MultinomialNB
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.pipeline import FeatureUnion

from app.categorias import CATEGORIAS
from app.text_processing import cobertura_vocabulario, normalizar_texto

BASE = Path(__file__).resolve().parents[1]
DATA = (
    BASE / "data" / "denuncias_simuladas_800.csv",
    BASE / "data" / "denuncias_simuladas_adicionales_1600.csv",
)
MODELS = BASE / "models"
SEED = 2026
MARGEN_MINIMO = 0.10
COBERTURA_MINIMA = 0.25
TERMINOS_MINIMOS = 2
EXPECTED_PER_CLASS = 300
GROUPS_PER_CLASS = 60


def leer_datos():
    filas = []
    for path in DATA:
        with path.open(encoding="utf-8-sig", newline="") as archivo:
            filas.extend(csv.DictReader(archivo))
    cantidades = Counter(r["codigo_categoria"] for r in filas)
    if len(filas) != 2400 or cantidades != Counter({
        codigo: EXPECTED_PER_CLASS for codigo in CATEGORIAS
    }):
        raise ValueError(f"Se esperan 2400 registros equilibrados: {cantidades}")
    ids = [r["id"] for r in filas]
    if len(ids) != len(set(ids)):
        raise ValueError("IDs repetidos en los datasets")
    vistos = set()
    grupos = {}
    for fila in filas:
        codigo = fila["codigo_categoria"]
        if fila["categoria"] != CATEGORIAS[codigo] or fila["origen"] != "simulada":
            raise ValueError(f"Catálogo u origen incorrecto: {fila['id']}")
        texto = normalizar_texto(fila["titulo"] + " " + fila["descripcion"])
        if len(texto.split()) < 5 or texto in vistos:
            raise ValueError(f"Texto vacío, demasiado corto o duplicado: {fila['id']}")
        vistos.add(texto)
        grupo = fila["grupo"]
        if not grupo.startswith(codigo + "-"):
            raise ValueError(f"Grupo inválido para {fila['id']}")
        grupos.setdefault(grupo, []).append(fila)
    for codigo in CATEGORIAS:
        por_categoria = [g for g in grupos if g.startswith(codigo + "-")]
        if len(por_categoria) != GROUPS_PER_CLASS or any(
            len(grupos[g]) != 5 for g in por_categoria
        ):
            raise ValueError(f"Se esperan 60 incidentes con 5 versiones para {codigo}")
    return filas


def dividir_por_grupo(filas):
    """42 incidentes de entrenamiento, 9 de validación y 9 de prueba por clase."""
    seleccion = {}
    for indice, codigo in enumerate(CATEGORIAS):
        grupos = sorted({r["grupo"] for r in filas if r["codigo_categoria"] == codigo})
        random.Random(SEED + indice).shuffle(grupos)
        seleccion.update({grupo: "entrenamiento" for grupo in grupos[:42]})
        seleccion.update({grupo: "validacion" for grupo in grupos[42:51]})
        seleccion.update({grupo: "prueba" for grupo in grupos[51:]})
    resultado = {
        split: [r for r in filas if seleccion[r["grupo"]] == split]
        for split in ("entrenamiento", "validacion", "prueba")
    }
    assert [len(resultado[s]) for s in resultado] == [1680, 360, 360]
    grupos_split = {
        name: {r["grupo"] for r in data} for name, data in resultado.items()
    }
    assert not (grupos_split["entrenamiento"] & grupos_split["validacion"])
    assert not (grupos_split["entrenamiento"] & grupos_split["prueba"])
    assert not (grupos_split["validacion"] & grupos_split["prueba"])
    return resultado


def textos_y_etiquetas(filas):
    return ([r["titulo"] + ". " + r["descripcion"] for r in filas],
            [r["codigo_categoria"] for r in filas])


def vectorizador_nuevo():
    """TF-IDF de palabras y fragmentos: soporta variantes y faltas de tildes."""
    return FeatureUnion(
        transformer_list=[
            ("palabras", TfidfVectorizer(
                preprocessor=normalizar_texto, lowercase=False,
                ngram_range=(1, 2), min_df=1, max_df=0.98, sublinear_tf=True,
            )),
            ("caracteres", TfidfVectorizer(
                preprocessor=normalizar_texto, lowercase=False, analyzer="char_wb",
                ngram_range=(3, 5), min_df=2, sublinear_tf=True,
            )),
        ],
        transformer_weights={"palabras": 1.5, "caracteres": 1.0},
    )


def evaluar_abstencion(textos, etiquetas, modelo, vectorizador, umbral):
    probabilidades = modelo.predict_proba(vectorizador.transform(textos))
    orden = np.argsort(probabilidades, axis=1)
    predicciones = modelo.classes_[orden[:, -1]]
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
        "precision_sugerencias": round(float(aciertos[aceptadas].mean()), 4)
        if total else None,
    }


def seleccionar_umbral(textos, etiquetas, modelo, vectorizador):
    """Elegido solo con validación; objetivo: precision >= 90 %, alta cobertura."""
    opciones = [0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]
    candidatos = [
        (t, evaluar_abstencion(textos, etiquetas, modelo, vectorizador, t))
        for t in opciones
    ]
    validos = [
        (t, v) for t, v in candidatos
        if v["sugeridas"] >= 36 and v["precision_sugerencias"] is not None
        and v["precision_sugerencias"] >= 0.90
    ]
    if validos:
        return max(validos, key=lambda pair: (pair[1]["sugeridas"], -pair[0]))[0]
    return 0.80


def seleccionar_modelo(x_train, y_train, x_val, y_val, vectorizador):
    """Hiperparámetros comparados con validación sin consultar la partición test."""
    z_train = vectorizador.fit_transform(x_train)
    z_val = vectorizador.transform(x_val)
    candidatos = [
        ("logistica_C1", LogisticRegression(
            C=1.0, max_iter=1800, class_weight="balanced", random_state=SEED)),
        ("logistica_C5", LogisticRegression(
            C=5.0, max_iter=1800, class_weight="balanced", random_state=SEED)),
        ("logistica_C15", LogisticRegression(
            C=15.0, max_iter=1800, class_weight="balanced", random_state=SEED)),
        ("naive_bayes_025", MultinomialNB(alpha=0.25)),
        ("naive_bayes_complemento", ComplementNB(alpha=0.5)),
    ]
    resultados = []
    mejor = None
    for nombre, modelo in candidatos:
        modelo.fit(z_train, y_train)
        pred = modelo.predict(z_val)
        accuracy = float(accuracy_score(y_val, pred))
        f1 = float(f1_score(y_val, pred, average="macro"))
        resultados.append({
            "modelo": nombre,
            "accuracy_validacion": round(accuracy, 4),
            "f1_macro_validacion": round(f1, 4),
        })
        if mejor is None or (accuracy, f1) > (mejor[0], mejor[1]):
            mejor = (accuracy, f1, nombre, modelo)
    return mejor[3], mejor[2], resultados


def main():
    filas = leer_datos()
    splits = dividir_por_grupo(filas)
    x_train, y_train = textos_y_etiquetas(splits["entrenamiento"])
    x_val, y_val = textos_y_etiquetas(splits["validacion"])
    x_test, y_test = textos_y_etiquetas(splits["prueba"])

    vectorizador = vectorizador_nuevo()
    modelo, nombre_modelo, candidatos = seleccionar_modelo(
        x_train, y_train, x_val, y_val, vectorizador
    )
    if set(modelo.classes_) != set(CATEGORIAS):
        raise RuntimeError("El clasificador no aprendió las ocho categorías")
    umbral = seleccionar_umbral(x_val, y_val, modelo, vectorizador)

    # Conservar la prueba separada y consultarla solo DESPUÉS de elegir modelo y umbral.
    y_pred = modelo.predict(vectorizador.transform(x_test))
    labels = list(CATEGORIAS)
    accuracy = round(float(accuracy_score(y_test, y_pred)), 4)
    f1 = round(float(f1_score(y_test, y_pred, labels=labels, average="macro")), 4)
    metricas = {
        "version": 3,
        "origen_datos": "2400 denuncias sinteticas, no casos ciudadanos reales",
        "datos": len(filas),
        "categorias": CATEGORIAS,
        "distribucion": dict(Counter(r["codigo_categoria"] for r in filas)),
        "metodologia": (
            "60 incidentes por clase, 5 variantes por incidente. "
            "Particiones separadas por incidente y estratificadas por categoria. "
            "Seleccion de modelo y umbral solo con validacion; test reservado."
        ),
        "semilla": SEED,
        "entrenamiento": len(x_train),
        "validacion": len(x_val),
        "prueba": len(x_test),
        "modelo": "TF-IDF palabras 1-2 + caracteres 3-5 + " + nombre_modelo,
        "seleccion_modelo": nombre_modelo,
        "comparacion_validacion": candidatos,
        "umbral_confianza": umbral,
        "margen_minimo": MARGEN_MINIMO,
        "cobertura_minima": COBERTURA_MINIMA,
        "terminos_minimos": TERMINOS_MINIMOS,
        "accuracy_prueba_simulada": accuracy,
        "f1_macro_prueba_simulada": f1,
        "evaluacion_validacion": evaluar_abstencion(
            x_val, y_val, modelo, vectorizador, umbral
        ),
        "evaluacion_prueba": evaluar_abstencion(
            x_test, y_test, modelo, vectorizador, umbral
        ),
        "reporte_por_categoria": classification_report(
            y_test, y_pred, labels=labels, output_dict=True, zero_division=0
        ),
        "matriz_confusion": {
            "orden_categorias": labels,
            "valores": confusion_matrix(y_test, y_pred, labels=labels).tolist(),
        },
        "advertencia": (
            "Los ejemplos se generaron artificialmente mediante plantillas y "
            "pueden compartir vocabulario entre distintos incidentes. "
            "No equivale a precision con denuncias reales. "
            "Las probabilidades son puntuaciones no calibradas."
        ),
    }
    MODELS.mkdir(exist_ok=True)
    joblib.dump(modelo, MODELS / "modelo_categorias.joblib.gz", compress=("gzip", 3))
    joblib.dump(vectorizador, MODELS / "vectorizador_tfidf.joblib.gz", compress=("gzip", 3))
    (MODELS / "metricas.json").write_text(
        json.dumps(metricas, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "datos": len(filas),
        "particiones": [len(x_train), len(x_val), len(x_test)],
        "mejor_modelo": nombre_modelo,
        "validacion": candidatos,
        "accuracy_prueba_simulada": accuracy,
        "f1_macro_prueba_simulada": f1,
        "umbral": umbral,
        "prueba_con_rechazo": metricas["evaluacion_prueba"],
    }, ensure_ascii=False, indent=2))
    # Calidad minima solicitada; no se modifica test ni se entrena con la prueba.
    if accuracy < 0.90:
        print("AVISO: el modelo aun NO alcanza 90% de accuracy en el test sintetico.")


if __name__ == "__main__":
    main()
