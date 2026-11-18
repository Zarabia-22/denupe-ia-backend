"""Recomendación de entidades con catálogo local y jurisdicción PNP geoespacial."""
import json
import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

from .schemas import EntidadEntrada, EntidadSalida

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DIRECTORIO_PATH = DATA_DIR / "entidades_publicas.json"
COMISARIAS_PATH = DATA_DIR / "comisarias_pnp_referencia.json"
PNP_MAPSERVER = os.getenv(
    "PNP_MAPSERVER_URL",
    "https://geomininter.mininter.gob.pe/arcgis/rest/services/pnp/policia_nacional_peru/MapServer",
)
PNP_TIMEOUT = float(os.getenv("PNP_TIMEOUT_SECONDS", "5"))
OSINERGMIN_MAPSERVER = os.getenv(
    "OSINERGMIN_MAPSERVER_URL",
    "https://gisem.osinergmin.gob.pe/serverosih/rest/services/Electricidad/ELECTRICIDAD/MapServer",
)


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
    """Carga entidades locales; los registros PNP históricos no se habilitan."""
    return _leer_lista(DIRECTORIO_PATH) + _leer_lista(COMISARIAS_PATH)


def _arcgis_query(layer: int, params: dict) -> list[dict]:
    query = {"f": "json", "outFields": "*", "returnGeometry": "false", **params}
    url = f"{PNP_MAPSERVER}/{layer}/query?{urlencode(query)}"
    try:
        with urlopen(url, timeout=PNP_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError("No se pudo consultar el servicio geográfico oficial de MININTER") from exc
    if "error" in payload:
        raise RuntimeError("El servicio geográfico de MININTER devolvió un error")
    return [feature.get("attributes", {}) for feature in payload.get("features", [])]


def _sugerir_comisaria_por_punto(entrada: EntidadEntrada) -> EntidadSalida:
    if entrada.latitud is None or entrada.longitud is None:
        return EntidadSalida(
            sugerida=False, entidad=None,
            motivo="Para identificar la comisaría competente se necesita la ubicación GPS de la denuncia. El distrito administrativo no basta para determinar la demarcación policial.",
        )

    geometry = json.dumps({"x": entrada.longitud, "y": entrada.latitud, "spatialReference": {"wkid": 4326}})
    spatial = {
        "geometry": geometry,
        "geometryType": "esriGeometryPoint",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "false",
    }
    try:
        jurisdicciones = _arcgis_query(2, spatial)
        if len(jurisdicciones) != 1:
            return EntidadSalida(sugerida=False, entidad=None, motivo="La ubicación no intersecta una única jurisdicción policial identificable. Se requiere revisión manual.")
        attrs = jurisdicciones[0]
        codigo = str(attrs.get("cod_cpnp") or attrs.get("codigo") or "").strip()
        nombre = str(attrs.get("comisaria") or attrs.get("nombre") or "").strip()
        if not codigo or not nombre:
            return EntidadSalida(sugerida=False, entidad=None, motivo="La capa de jurisdicciones no devolvió identificadores suficientes de la comisaría.")
        # Confirmar que el código también existe en la capa de comisarías (puntos operativos publicados).
        activos = _arcgis_query(0, {"where": f"cod_cpnp='{codigo.replace(chr(39), chr(39)*2)}'", "outFields": "comisaria,cod_cpnp,departamento,provincia,distrito", "returnGeometry": "false"})
        if len(activos) != 1:
            return EntidadSalida(sugerida=False, entidad=None, motivo="La comisaría de la jurisdicción no pudo confirmarse en la capa operativa de comisarías. Se requiere revisión manual.")
        activo = activos[0]
        nombre = str(activo.get("comisaria") or nombre)
        distrito = str(activo.get("distrito") or entrada.distrito)
        provincia = str(activo.get("provincia") or entrada.provincia)
        departamento = str(activo.get("departamento") or entrada.departamento)
        return EntidadSalida(
            sugerida=True,
            entidad={
                "id": f"pnp-{codigo}",
                "nombre": f"Comisaría PNP {nombre}",
                "tipo": "comisaria_pnp",
                "direccion": None,
                "telefono": None,
                "sitio_web": "https://www.gob.pe/pnp",
                "ambito": {"departamento": departamento, "provincia": provincia, "distrito": distrito},
            },
            motivo="La coordenada de la denuncia intersecta la capa oficial de jurisdicciones PNP y el código de la comisaría aparece también en la capa oficial de comisarías.",
        )
    except RuntimeError:
        return EntidadSalida(sugerida=False, entidad=None, motivo="No fue posible validar la jurisdicción policial con el servicio oficial. No se asignó una comisaría; se requiere revisión manual.")



def _arcgis_query_osinergmin(layer: int, params: dict) -> list[dict]:
    """Consulta capas públicas de concesiones eléctricas de OSINERGMIN."""
    query = {"f": "json", "outFields": "*", "returnGeometry": "false", **params}
    url = f"{OSINERGMIN_MAPSERVER}/{layer}/query?{urlencode(query)}"
    try:
        with urlopen(url, timeout=PNP_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError("No se pudo consultar el mapa oficial de concesiones eléctricas de OSINERGMIN") from exc
    if "error" in payload:
        raise RuntimeError("El servicio de concesiones eléctricas de OSINERGMIN devolvió un error")
    return [feature.get("attributes", {}) for feature in payload.get("features", [])]


def _sugerir_concesionaria_electrica(entrada: EntidadEntrada) -> EntidadSalida:
    """Resuelve la concesionaria por intersección con el polígono oficial de concesión."""
    if entrada.latitud is None or entrada.longitud is None:
        return EntidadSalida(
            sugerida=False, entidad=None,
            motivo="Para identificar la empresa concesionaria eléctrica se necesita la ubicación GPS. El distrito por sí solo no permite determinar el área de concesión.",
        )

    geometry = json.dumps({"x": entrada.longitud, "y": entrada.latitud, "spatialReference": {"wkid": 4326}})
    spatial = {
        "where": "1=1",
        "geometry": geometry,
        "geometryType": "esriGeometryPoint",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "CODEMP",
        "returnGeometry": "false",
    }
    # Códigos y nombres tomados del dominio CODEMP publicado por la capa 33 de OSINERGMIN.
    empresas = {
        "EDLN": "ENEL", "ELN": "Electro Norte", "COEL": "COELVISAC",
        "ELC": "Electro Centro", "ELDU": "Electro Dunas", "ELNO": "Electro Noroeste",
        "ELOR": "Electro Oriente", "EPAN": "Electro Pangoa", "ELPU": "Electro Puno",
        "ELS": "Electro Sur", "ELSE": "Electro Sur Este", "ELTO": "Electro Tocache",
        "ELUC": "Electro Ucayali", "ELNM": "Hidrandina", "LDS": "Luz del Sur",
        "SEAL": "SEAL", "EMSEMSA": "EMSE", "EMSEUSA": "EMSU",
        "SERSA": "SERS", "EIHC": "Eilhicha",
    }
    try:
        concesiones = _arcgis_query_osinergmin(33, spatial)
        if len(concesiones) != 1:
            return EntidadSalida(
                sugerida=False, entidad=None,
                motivo="La ubicación no intersecta una única área de concesión eléctrica identificable. Se requiere revisión manual.",
            )
        codigo = str(concesiones[0].get("CODEMP") or "").strip().upper()
        empresa = empresas.get(codigo)
        if not empresa:
            return EntidadSalida(
                sugerida=False, entidad=None,
                motivo="El área de concesión no devolvió un código de empresa reconocido en el catálogo oficial. Se requiere revisión manual.",
            )
        return EntidadSalida(
            sugerida=True,
            entidad={
                "id": f"electrica-{codigo.lower()}",
                "nombre": empresa,
                "tipo": "empresa_concesionaria_electrica",
                "direccion": None,
                "telefono": None,
                "sitio_web": None,
                "ambito": {
                    "departamento": entrada.departamento,
                    "provincia": entrada.provincia,
                    "distrito": entrada.distrito,
                },
            },
            motivo="La coordenada de la denuncia intersecta un único polígono del área de concesión eléctrica publicado por OSINERGMIN. La derivación debe ser revisada por el personal responsable.",
        )
    except RuntimeError:
        return EntidadSalida(
            sugerida=False, entidad=None,
            motivo="No fue posible validar el área de concesión eléctrica con el servicio oficial de OSINERGMIN. No se asignó una empresa; se requiere revisión manual.",
        )

def sugerir_entidad(entrada: EntidadEntrada) -> EntidadSalida:
    categoria = normalizar(entrada.categoria)
    if categoria == "alumbrado publico":
        return _sugerir_concesionaria_electrica(entrada)
    if categoria in {"seguridad ciudadana", "seguridad ciudadana delitos", "delitos", "robo", "asalto", "violencia", "actividad sospechosa"}:
        return _sugerir_comisaria_por_punto(entrada)

    distrito = normalizar(entrada.distrito)
    provincia = normalizar(entrada.provincia)
    departamento = normalizar(entrada.departamento)
    texto = normalizar(f"{entrada.titulo} {entrada.descripcion}")
    candidatos = []

    for entidad in cargar_directorio():
        if not entidad.get("habilitada_recomendacion", entidad.get("verificado_competencias", False)):
            continue
        if (
            normalizar(entidad["distrito"]) != distrito
            or normalizar(entidad["provincia"]) != provincia
            or normalizar(entidad["departamento"]) != departamento
        ):
            continue
        categorias = {normalizar(c) for c in entidad.get("categorias_habilitadas", entidad["categorias"])}
        if categoria not in categorias:
            continue
        palabras = {normalizar(p) for p in entidad["palabras_clave"]}
        coincidencias = sorted(p for p in palabras if p and p in texto)
        if palabras and not coincidencias:
            continue
        candidatos.append((len(coincidencias), entidad))

    if not candidatos:
        return EntidadSalida(sugerida=False, entidad=None, motivo="No se encontró una entidad habilitada y verificada para la categoría y jurisdicción indicadas. Se requiere revisión manual.")
    candidatos.sort(key=lambda item: item[0], reverse=True)
    if len(candidatos) > 1 and candidatos[0][0] == candidatos[1][0]:
        return EntidadSalida(sugerida=False, entidad=None, motivo="Hay más de una entidad candidata con evidencia equivalente. Se requiere revisión manual.")

    registro = candidatos[0][1]
    return EntidadSalida(
        sugerida=True,
        entidad={
            "id": registro["id"], "nombre": registro["nombre"], "tipo": registro["tipo"],
            "direccion": registro.get("direccion"), "telefono": registro.get("telefono"),
            "sitio_web": registro.get("sitio_web"),
            "ambito": {"departamento": registro["departamento"], "provincia": registro["provincia"], "distrito": registro["distrito"]},
        },
        motivo="La categoría, la jurisdicción y los términos de la descripción coinciden con el registro habilitado de esta entidad.",
    )
