"""Auditoría de solo lectura de la matriz territorial del backend principal.

La lista de UBIGEO se obtiene del CSV territorial 2026 citado por la migración
de DenuPe. Las consultas usan únicamente el endpoint REST de lectura.
"""
from __future__ import annotations

import csv
import io
import json
import os
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

from app.backend_catalog import BackendCatalogError, consultar_matriz_distrital

UBIGEO_CSV_URL = (
    "https://raw.githubusercontent.com/Rodasluis/Peru-maps/"
    "main/salida/ubigeos_2026.csv"
)
CATEGORIAS = {
    "alumbrado", "seguridad", "limpieza", "agua",
    "transito", "areas_verdes", "infraestructura", "otros",
}


def cargar_ubigeos(contenido: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(contenido))
    distritos = [
        {
            "ubigeo": (row.get("ubigeo") or "").strip(),
            "distrito": (row.get("nombre") or "").strip(),
            "provincia": (row.get("nombre_provincia") or "").strip(),
            "departamento": (row.get("nombre_departamento") or "").strip(),
        }
        for row in reader
        if (row.get("nivel") or "").strip().casefold() == "distrito"
    ]
    invalidos = [d for d in distritos if len(d["ubigeo"]) != 6 or not d["ubigeo"].isdigit()]
    if invalidos:
        raise ValueError(f"La fuente contiene {len(invalidos)} UBIGEO distritales inválidos.")
    codigos = [d["ubigeo"] for d in distritos]
    if len(codigos) != len(set(codigos)):
        raise ValueError("La fuente territorial contiene UBIGEO duplicados.")
    if not distritos:
        raise ValueError("La fuente no contiene filas de nivel distrito.")
    return distritos


def consultar_distrito(distrito: dict) -> dict:
    filas = consultar_matriz_distrital(distrito["ubigeo"])
    errores = []
    codigos = [fila.get("categoria_code") for fila in filas]
    if len(filas) != 8:
        errores.append(f"se esperaban 8 filas y llegaron {len(filas)}")
    if set(codigos) != CATEGORIAS:
        faltan = sorted(CATEGORIAS - set(codigos))
        sobran = sorted(set(codigos) - CATEGORIAS)
        errores.append(f"categorías faltantes={faltan}; inválidas={sobran}")
    if len(codigos) != len(set(codigos)):
        errores.append("categorías duplicadas")
    for fila in filas:
        if fila.get("ubigeo") != distrito["ubigeo"]:
            errores.append(f"UBIGEO de respuesta no coincide: {fila.get('ubigeo')!r}")
        if not fila.get("entidad_resolucion_id") or not fila.get("entidad_nombre"):
            errores.append(f"resolutor ausente para categoría {fila.get('categoria_code')}")
        if fila.get("requiere_gps") is not True:
            errores.append(f"requiere_gps no es true para {fila.get('categoria_code')}")
        if fila.get("asignar_solo_tras_gps") is not True:
            errores.append(f"asignar_solo_tras_gps no es true para {fila.get('categoria_code')}")
    return {
        **distrito,
        "filas_recibidas": len(filas),
        "categorias_recibidas": sorted(str(c) for c in codigos),
        "resolutores": [
            {
                "categoria": f.get("categoria_code"),
                "id": f.get("entidad_resolucion_id"),
                "nombre": f.get("entidad_nombre"),
                "tipo": f.get("entidad_tipo"),
                "metodo": f.get("metodo_resolucion"),
            }
            for f in filas
        ],
        "errores": sorted(set(errores)),
        # La endpoint REST devuelve resolutores sectoriales, no un padrón de instituciones
        # concretas. No se debe presentar esto como entidad pública verificada.
        "entidad_concreta_verificada": False,
    }


def main() -> int:
    backend_url = os.getenv(
        "DENUPE_BACKEND_BASE_URL",
        "https://denupe-backend.onrender.com",
    ).strip()
    if not backend_url.startswith(("https://", "http://")):
        print("ERROR: DENUPE_BACKEND_BASE_URL debe ser una URL HTTP(S) válida.", file=sys.stderr)
        return 2

    with urlopen(UBIGEO_CSV_URL, timeout=30) as response:
        fuente = response.read().decode("utf-8-sig")
    distritos = cargar_ubigeos(fuente)
    resultados = []
    fallos_consulta = []

    workers = max(1, min(int(os.getenv("AUDIT_WORKERS", "4")), 8))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futuros = {executor.submit(consultar_distrito, d): d for d in distritos}
        for futuro in as_completed(futuros):
            distrito = futuros[futuro]
            try:
                resultados.append(futuro.result())
            except (BackendCatalogError, OSError, ValueError, RuntimeError) as exc:
                fallos_consulta.append({
                    **distrito,
                    "error": f"{type(exc).__name__}: {exc}",
                })

    resultados.sort(key=lambda x: x["ubigeo"])
    fallos_consulta.sort(key=lambda x: x["ubigeo"])
    con_errores = [r for r in resultados if r["errores"]]
    conteo_resolutores = Counter(
        (r["categoria"], r["id"], r["nombre"])
        for distrito in resultados for r in distrito["resolutores"]
    )
    informe = {
        "generado_en_utc": datetime.now(timezone.utc).isoformat(),
        "fuente_ubigeos": UBIGEO_CSV_URL,
        "modo": "solo_lectura",\n        "backend_catalogo": backend_url,
        "ubigeos_fuente": len(distritos),
        "ubigeos_consultados_con_respuesta": len(resultados),
        "ubigeos_con_error_consulta": len(fallos_consulta),
        "distritos_con_matriz_invalida": len(con_errores),
        "combinaciones_esperadas": len(distritos) * 8,
        "combinaciones_recibidas": sum(r["filas_recibidas"] for r in resultados),
        "categorias_esperadas": sorted(CATEGORIAS),
        "distribucion_resolutores_por_categoria": [
            {"categoria": k[0], "resolutor_id": k[1], "nombre": k[2], "distritos": v}
            for k, v in sorted(conteo_resolutores.items())
        ],
        "entidades_concretas_verificadas": 0,
        "nota_entidades": (
            "La endpoint REST consultada devuelve resolutores sectoriales. Esta auditoría "
            "no acredita una entidad pública concreta ni su competencia individual."
        ),
        "errores_matriz": con_errores,
        "errores_consulta": fallos_consulta,
    }
    salida = Path(os.getenv("AUDIT_OUTPUT", "artifacts/auditoria-territorial-real.json"))
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in informe.items() if k not in {"errores_matriz", "errores_consulta"}}, ensure_ascii=False, indent=2))
    print(f"Informe detallado: {salida}")
    return 0 if not fallos_consulta and not con_errores and len(distritos) == 1893 else 1


if __name__ == "__main__":
    raise SystemExit(main())
