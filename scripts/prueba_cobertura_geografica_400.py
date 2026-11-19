"""Prueba integral 50 distritos x 8 categorías (400 casos) con puntos interiores reales.

Ejecutar desde la raíz del proyecto:
    python scripts/prueba_cobertura_geografica_400.py

La geometría distrital se lee de data/lima_callao_distritos.geojson, una capa
simplificada de 50 polígonos de Lima y Callao atribuida al IGN. Los resultados
se guardan en artifacts/.
Las consultas PNP y OSINERGMIN son reales para las categorías que dependen
de su jurisdicción espacial. El fallback revision_competencia se contabiliza
como cobertura de derivación, nunca como identificación de entidad pública.
"""
from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.entidades import normalizar, sugerir_entidad  # noqa: E402
from app.schemas import EntidadEntrada  # noqa: E402

CATALOG_PATH = ROOT / "data" / "entidades_publicas.json"
GEOMETRY_PATH = ROOT / "data" / "lima_callao_distritos.geojson"
GEOMETRY_SOURCE = (
    "https://github.com/joseluisq/peru-geojson-datasets/blob/master/"
    "lima_callao_distritos_simple.geojson"
)
CATEGORIES = [
    "Alumbrado público",
    "Seguridad ciudadana",
    "Limpieza y residuos",
    "Agua y saneamiento",
    "Tránsito y transporte",
    "Parques y áreas verdes",
    "Vialidad e infraestructura",
    "Otros",
]
SAMPLES = {
    "Alumbrado público": (
        "Luminaria apagada en la vía pública",
        "El poste de alumbrado público permanece apagado durante la noche.",
    ),
    "Seguridad ciudadana": (
        "Robo reportado en la zona",
        "Se produjo un robo en la calle y solicito atención policial.",
    ),
    "Limpieza y residuos": (
        "Acumulación de basura en la calle",
        "Hay residuos sólidos y desperdicios acumulados que requieren recojo municipal.",
    ),
    "Agua y saneamiento": (
        "Fuga en tubería de agua potable",
        "Hay una fuga de agua potable en la tubería y se está formando un aniego.",
    ),
    "Tránsito y transporte": (
        "Problema de tránsito en la avenida",
        "Se presenta congestión vehicular y problemas de circulación en esta vía.",
    ),
    "Parques y áreas verdes": (
        "Parque con áreas verdes descuidadas",
        "El parque necesita mantenimiento de jardines, árboles y áreas verdes.",
    ),
    "Vialidad e infraestructura": (
        "Bache en la calzada de la vía",
        "Existe un hueco y deterioro de la pista que afecta la infraestructura vial.",
    ),
    "Otros": (
        "Incidente no clasificado en el distrito",
        "Se reporta una situación que no corresponde a las categorías disponibles.",
    ),
}


def _load_municipalities():
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    districts = {}
    for item in data:
        if not str(item.get("tipo", "")).startswith("municipalidad_"):
            continue
        if not item.get("verificado_nombre") or not item.get("codigo_ubigeo"):
            continue
        key = item["codigo_ubigeo"]
        districts[key] = {
            "ubigeo": key,
            "departamento": item["departamento"],
            "provincia": item["provincia"],
            "distrito": item["distrito"],
        }
    if len(districts) != 50:
        raise RuntimeError(
            f"Se esperaban 50 distritos municipales únicos; el catálogo contiene {len(districts)}."
        )
    return districts


def _geo_key(value):
    normalized = normalizar(str(value or ""))
    # La fuente IGN tiene una etiqueta con codificación dañada para Mi Perú.
    if normalized.startswith("mi per"):
        return "mi peru"
    return normalized


def _fetch_polygons(districts):
    payload = json.loads(GEOMETRY_PATH.read_text(encoding="utf-8"))
    features = payload.get("features")
    if not isinstance(features, list) or len(features) != 50:
        raise RuntimeError("La capa GeoJSON debe contener exactamente 50 polígonos.")
    expected = {
        (
            normalizar(item["departamento"]),
            normalizar(item["provincia"]),
            normalizar(item["distrito"]),
        ): code
        for code, item in districts.items()
    }
    polygons = {}
    for feature in features:
        props = feature.get("properties") or {}
        key = (
            normalizar(props.get("departamento")),
            normalizar(props.get("provincia")),
            _geo_key(props.get("distrito")),
        )
        code = expected.get(key)
        if code:
            polygons[code] = feature.get("geometry")
    missing = sorted(set(districts) - set(polygons))
    if missing:
        labels = [districts[code]["distrito"] + " (" + code + ")" for code in missing]
        raise RuntimeError("Faltan polígonos distritales: " + ", ".join(labels))
    return polygons
