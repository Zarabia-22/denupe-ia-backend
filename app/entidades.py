"""Recomendación territorial de entidades a partir de un directorio verificable.

La recomendación no crea instituciones ni infiere competencias fuera del catálogo.
Solo considera entidades registradas para el ámbito territorial indicado.
"""
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from .schemas import EntidadEntrada, EntidadSalida

DIRECTORIO_PATH = Path(__file__).resolve().parent.parent / "data" / "entidades_publicas.json"


def normalizar(valor: str) -> str:
    valor = unicodedata.normalize("NFKD", valor.casefold())
    valor = "".join(c for c in valor if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", valor).strip()


@lru_cache(maxsize=1)
def cargar_directorio() -> list[dict]:
    """Carga el directorio local; un catálogo vacío produce abstención segura."""
    if not DIRECTORIO_PATH.exists():
        return []
    with DIRECTORIO_PATH.open(encoding="utf-8") as archivo:
        data = json.load(archivo)
    if not isinstance(data, list):
        raise RuntimeError("El directorio de entidades debe ser una lista JSON")
    requeridos = {"id", "nombre", "tipo", "departamento", "provincia", "distrito", "categorias", "palabras_clave"}
    for entidad in data:
        if not isinstance(entidad, dict) or not requeridos.issubset(entidad):
            raise RuntimeError("Registro incompleto en el directorio de entidades")
    return data


def sugerir_entidad(entrada: EntidadEntrada) -> EntidadSalida:
    distrito = normalizar(entrada.distrito)
    provincia = normalizar(entrada.provincia)
    departamento = normalizar(entrada.departamento)
    categoria = normalizar(entrada.categoria)
    texto = normalizar(f"{entrada.titulo} {entrada.descripcion}")
    candidatos = []

    for entidad in cargar_directorio():
        if (
            normalizar(entidad["distrito"]) != distrito
            or normalizar(entidad["provincia"]) != provincia
            or normalizar(entidad["departamento"]) != departamento
        ):
            continue

        categorias = {normalizar(c) for c in entidad["categorias"]}
        if categoria not in categorias:
            continue

        palabras = {normalizar(p) for p in entidad["palabras_clave"]}
        coincidencias = sorted(p for p in palabras if p and p in texto)
        # Categoría + jurisdicción son obligatorias; descripción aporta evidencia adicional.
        if palabras and not coincidencias:
            continue

        candidatos.append((len(coincidencias), entidad, coincidencias))

    if not candidatos:
        return EntidadSalida(
            sugerida=False,
            entidad=None,
            motivo="No se encontró una entidad registrada para la categoría y jurisdicción indicadas. Verifica los datos o deriva el caso para revisión manual.",
        )

    candidatos.sort(key=lambda item: item[0], reverse=True)
    mejor = candidatos[0]
    if len(candidatos) > 1 and candidatos[0][0] == candidatos[1][0]:
        return EntidadSalida(
            sugerida=False,
            entidad=None,
            motivo="Hay más de una entidad candidata con evidencia equivalente. Se requiere revisión manual.",
        )

    registro = mejor[1]
    return EntidadSalida(
        sugerida=True,
        entidad={
            "id": registro["id"],
            "nombre": registro["nombre"],
            "tipo": registro["tipo"],
            "direccion": registro.get("direccion"),
            "telefono": registro.get("telefono"),
            "sitio_web": registro.get("sitio_web"),
            "ambito": {
                "departamento": registro["departamento"],
                "provincia": registro["provincia"],
                "distrito": registro["distrito"],
            },
        },
        motivo="La categoría, la jurisdicción y los términos de la descripción coinciden con el registro de esta entidad.",
    )
