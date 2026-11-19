"""Prueba integral 50 distritos x 8 categorías (400 casos) con puntos interiores reales.

Ejecutar desde la raíz del proyecto:
    python scripts/prueba_cobertura_geografica_400.py

La geometría distrital se obtiene en tiempo de ejecución del servicio ArcGIS
del MINSA (UBIGEO, polígonos WGS84). Los resultados se guardan en artifacts/.
Las consultas PNP y OSINERGMIN son reales para las categorías que dependen
de su jurisdicción espacial. El fallback revision_competencia se contabiliza
como cobertura de derivación, nunca como identificación de entidad pública.
"""
from __future__ import annotations

import csv
import json
import sys
import time
import unicodedata
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.entidades import normalizar, sugerir_entidad  # noqa: E402
from app.schemas import EntidadEntrada  # noqa: E402

CATALOG_PATH = ROOT / "data" / "entidades_publicas.json"
GEOSERVICE = (
    "https://geominsa.minsa.gob.pe/geominsaserver/rest/services/"
    "SRV_DGAIN_DIPOS/SRV_DIPOS_GeoRIS_BaseGeneral/MapServer/5/query"
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


def _fetch_polygons(districts):
    codes = sorted(districts)
    params = {
        "where": "UBIGEO IN (" + ",".join("'" + c + "'" for c in codes) + ")",
        "outFields": "UBIGEO,NOMBDIST,NOMBPROV,NOMBDEP",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
    }
    url = GEOSERVICE + "?" + urlencode(params)
    request = Request(url, headers={"User-Agent": "DenuPe-geospatial-coverage-tests/1.0"})
    with urlopen(request, timeout=45) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("error"):
        raise RuntimeError(f"MINSA ArcGIS devolvió error: {payload['error']}")
    features = payload.get("features")
    if not isinstance(features, list):
        raise RuntimeError("La capa MINSA no devolvió features GeoJSON.")
    polygons = {}
    for feature in features:
        props = feature.get("properties") or {}
        code = str(props.get("UBIGEO") or "").zfill(6)
        if code in districts:
            polygons[code] = feature.get("geometry")
    missing = sorted(set(districts) - set(polygons))
    if missing:
        raise RuntimeError(
            "No se encontraron polígonos para estos UBIGEO: " + ", ".join(missing)
        )
    return polygons


def _ring_area(ring):
    return abs(sum(
        ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1]
        for i in range(len(ring) - 1)
    )) / 2.0


def _inside_ring(point, ring):
    x, y = point
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-30) + xi
        ):
            inside = not inside
        j = i
    return inside


def _inside_polygon(point, rings):
    return bool(rings) and _inside_ring(point, rings[0]) and not any(
        _inside_ring(point, hole) for hole in rings[1:]
    )


def _point_in_geometry(point, geometry):
    kind = geometry["type"]
    coords = geometry["coordinates"]
    polygons = [coords] if kind == "Polygon" else coords if kind == "MultiPolygon" else []
    return any(_inside_polygon(point, polygon) for polygon in polygons)


def _interior_point_polygon(rings):
    outer = rings[0]
    ys = [p[1] for p in outer]
    min_y, max_y = min(ys), max(ys)
    # Scan multiple horizontal sections and select the widest valid interior span.
    best = None
    for step in range(1, 100):
        y = min_y + (max_y - min_y) * step / 100
        xs = []
        for i in range(len(outer) - 1):
            x1, y1 = outer[i]
            x2, y2 = outer[i + 1]
            if (y1 > y) != (y2 > y):
                xs.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
        xs.sort()
        for left, right in zip(xs[::2], xs[1::2]):
            candidate = ((left + right) / 2, y)
            if right > left and _inside_polygon(candidate, rings):
                width = right - left
                if best is None or width > best[0]:
                    best = (width, candidate)
    if best is None:
        raise RuntimeError("No se pudo encontrar un punto interior del polígono.")
    return best[1]


def _representative_point(geometry):
    kind = geometry["type"]
    coords = geometry["coordinates"]
    polygons = [coords] if kind == "Polygon" else coords if kind == "MultiPolygon" else []
    if not polygons:
        raise RuntimeError(f"Geometría no soportada: {kind}")
    # Use the largest polygon component to avoid selecting a tiny detached island.
    rings = max(polygons, key=lambda p: _ring_area(p[0]))
    point = _interior_point_polygon(rings)
    if not _point_in_geometry(point, geometry):
        raise RuntimeError("El punto calculado no está dentro del polígono distrital.")
    return point


def run():
    output_dir = ROOT / "artifacts"
    output_dir.mkdir(exist_ok=True)
    districts = _load_municipalities()
    polygons = _fetch_polygons(districts)
    points = {
        code: _representative_point(polygons[code])
        for code in districts
    }

    rows = []
    failures = []
    for code, district in sorted(districts.items()):
        longitude, latitude = points[code]
        for category in CATEGORIES:
            title, description = SAMPLES[category]
            payload = EntidadEntrada(
                categoria=category,
                departamento=district["departamento"],
                provincia=district["provincia"],
                distrito=district["distrito"],
                titulo=title,
                descripcion=description,
                latitud=latitude,
                longitud=longitude,
            )
            started = time.perf_counter()
            try:
                result = sugerir_entidad(payload)
                entity = result.entidad
                entity_type = entity.tipo if entity else ""
                entity_id = entity.id if entity else ""
                ok = bool(result.sugerida and entity)
                row = {
                    **district,
                    "longitud": f"{longitude:.7f}",
                    "latitud": f"{latitude:.7f}",
                    "categoria": category,
                    "sugerida": result.sugerida,
                    "entidad_id": entity_id,
                    "entidad_nombre": entity.nombre if entity else "",
                    "tipo_resultado": entity_type,
                    "resultado": "OK" if ok else "SIN_DERIVACION",
                    "motivo": result.motivo,
                    "duracion_ms": round((time.perf_counter() - started) * 1000, 2),
                }
                rows.append(row)
                if not ok:
                    failures.append(row)
            except Exception as exc:  # se conserva el caso fallido en el reporte
                row = {
                    **district,
                    "longitud": f"{longitude:.7f}",
                    "latitud": f"{latitude:.7f}",
                    "categoria": category,
                    "sugerida": False,
                    "entidad_id": "",
                    "entidad_nombre": "",
                    "tipo_resultado": "ERROR",
                    "resultado": "ERROR",
                    "motivo": f"{type(exc).__name__}: {exc}",
                    "duracion_ms": round((time.perf_counter() - started) * 1000, 2),
                }
                rows.append(row)
                failures.append(row)
            # Small pause to avoid hammering public ArcGIS services.
            if category in {"Alumbrado público", "Seguridad ciudadana"}:
                time.sleep(0.12)

    csv_path = output_dir / "cobertura_geografica_400.csv"
    json_path = output_dir / "cobertura_geografica_400.json"
    fields = list(rows[0].keys())
    with csv_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    counts = {}
    for row in rows:
        counts[row["tipo_resultado"]] = counts.get(row["tipo_resultado"], 0) + 1
    summary = {
        "total_pruebas": len(rows),
        "total_distritos": len(districts),
        "total_categorias": len(CATEGORIES),
        "derivaciones_correctas": len(rows) - len(failures),
        "fallos": len(failures),
        "entidades_publicas_especificas": sum(
            r["resultado"] == "OK" and r["tipo_resultado"] != "revision_competencia"
            for r in rows
        ),
        "revision_competencia": counts.get("revision_competencia", 0),
        "resultados_por_tipo": counts,
        "fallos_detalle": failures,
        "fuente_geometrica": GEOSERVICE,
        "nota": (
            "La revisión_competencia cuenta como destino de derivación, no como "
            "identificación de una entidad pública específica."
        ),
    }
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "fallos_detalle"}, ensure_ascii=False, indent=2))
    print(f"CSV: {csv_path}")
    print(f"JSON: {json_path}")
    if len(rows) != 400 or failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run()
