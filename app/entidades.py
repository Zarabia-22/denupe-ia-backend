"""Recomendación territorial basada en registros públicos habilitados.

Los registros históricos o pendientes de validación se conservan como referencia,
pero nunca participan en recomendaciones automáticas.
"""
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from .schemas import EntidadEntrada, EntidadSalida

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DIRECTORIO_PATH = DATA_DIR / "entidades_publicas.json"
COMISARIAS_PATH = DATA_DIR / "comisarias_pnp_referencia.json"


def normalizar(valor: str) -> str:
    valor = unicodedata.normalize("NFKD", valor.casefold())
    valor = "".join(c for c in valor if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", valor).strip()


def _leer_lista(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as archivo:
        data = json.load(archivo)
    if not isinstance(data, list):
        raise RuntimeError(f"El directorio {path.name} debe ser una lista JSON")
    requeridos = {"id", "nombre", "tipo", "departamento", "provincia", "distrito", "categorias", "palabras_clave"}
    for entidad in data:
        if not isinstance(entidad, dict) or not requeridos.issubset(entidad):
            raise RuntimeError(f"Registro incompleto en {path.name}")
    return data


@lru_cache(maxsize=1)
def cargar_directorio() -> list[dict]:
    """Carga entidades públicas de ambos catálogos."""
    return _leer_lista(DIRECTORIO_PATH) + _leer_lista(COMISARIAS_PATH)


def sugerir_entidad(entrada: EntidadEntrada) -> EntidadSalida:
    distrito = normalizar(entrada.distrito)
    provincia = normalizar(entrada.provincia)
    departamento = normalizar(entrada.departamento)
    categoria = normalizar(entrada.categoria)
    texto = normalizar(f"{entrada.titulo} {entrada.descripcion}")
    candidatos = []

    for entidad in cargar_directorio():
        # No recomendar registros históricos ni competencias sin validar.
        if not entidad.get("habilitada_recomendacion", entidad.get("verificado_competencias", False)):
            continue
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
        if palabras and not coincidencias:
            continue
        candidatos.append((len(coincidencias), entidad, coincidencias))

    if not candidatos:
        return EntidadSalida(
            sugerida=False,
            entidad=None,
            motivo="No se encontró una entidad habilitada y verificada para la categoría y jurisdicción indicadas. Se requiere revisión manual.",
        )

    candidatos.sort(key=lambda item: item[0], reverse=True)
    if len(candidatos) > 1 and candidatos[0][0] == candidatos[1][0]:
        return EntidadSalida(sugerida=False, entidad=None, motivo="Hay más de una entidad candidata con evidencia equivalente. Se requiere revisión manual.")

    registro = candidatos[0][1]
    return EntidadSalida(
        sugerida=True,
        entidad={
            "id": registro["id"],
            "nombre": registro["nombre"],
            "tipo": registro["tipo"],
            "direccion": registro.get("direccion"),
            "telefono": registro.get("telefono"),
            "sitio_web": registro.get("sitio_web"),
            "ambito": {"departamento": registro["departamento"], "provincia": registro["provincia"], "distrito": registro["distrito"]},
        },
        motivo="La categoría, la jurisdicción y los términos de la descripción coinciden con el registro habilitado de esta entidad.",
    )
