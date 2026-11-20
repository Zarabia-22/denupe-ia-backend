"""Audita el directorio de entidades concretas sin inferir competencias."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

CATEGORIAS = {
    "Alumbrado público", "Seguridad ciudadana", "Limpieza y residuos",
    "Agua y saneamiento", "Tránsito y transporte", "Parques y áreas verdes",
    "Vialidad e infraestructura", "Otros",
}


def auditar(registros: list[dict]) -> dict:
    errores: list[str] = []
    ids: set[str] = set()
    claves: set[tuple[str, str]] = set()
    distritos: set[str] = set()
    cobertura = Counter()
    entidades_verificadas = 0

    for i, r in enumerate(registros):
        prefijo = f"registro[{i}]"
        for campo in ("id", "nombre", "tipo", "codigo_ubigeo", "fuente", "fuente_url"):
            if not str(r.get(campo, "")).strip():
                errores.append(f"{prefijo}: falta {campo}")
        ubigeo = str(r.get("codigo_ubigeo", ""))
        if len(ubigeo) != 6 or not ubigeo.isdigit():
            errores.append(f"{prefijo}: UBIGEO inválido")
        else:
            distritos.add(ubigeo)
        ident = str(r.get("id", ""))
        if ident in ids:
            errores.append(f"{prefijo}: id duplicado {ident}")
        ids.add(ident)
        clave = (ubigeo, str(r.get("nombre", "")).strip().casefold())
        if clave in claves:
            errores.append(f"{prefijo}: entidad duplicada en el mismo UBIGEO")
        claves.add(clave)

        habilitadas = r.get("categorias_habilitadas", [])
        if not isinstance(habilitadas, list):
            errores.append(f"{prefijo}: categorias_habilitadas debe ser una lista")
            habilitadas = []
        desconocidas = set(habilitadas) - CATEGORIAS
        if desconocidas:
            errores.append(f"{prefijo}: categorías desconocidas {sorted(desconocidas)}")
        if habilitadas and not (r.get("verificado_nombre") and r.get("verificado_competencias")):
            errores.append(f"{prefijo}: categoría habilitada sin verificaciones de nombre y competencia")
        if r.get("verificado_nombre") and r.get("verificado_competencias"):
            entidades_verificadas += 1
        for categoria in set(habilitadas) & CATEGORIAS:
            cobertura[categoria] += 1

    return {
        "total_registros": len(registros),
        "distritos_con_entidad": len(distritos),
        "entidades_con_nombre_y_competencia_verificados": entidades_verificadas,
        "cobertura_por_categoria": dict(sorted(cobertura.items())),
        "errores": errores,
        "valido": not errores,
        "nota": "La presencia de una municipalidad en el directorio no demuestra competencia para todas las categorías.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/entidades_publicas.json")
    parser.add_argument("--output", default="artifacts/auditoria-directorio-entidades.json")
    args = parser.parse_args()
    registros = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if not isinstance(registros, list):
        raise ValueError("El directorio debe ser una lista JSON.")
    resultado = auditar(registros)
    destino = Path(args.output)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0 if resultado["valido"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
