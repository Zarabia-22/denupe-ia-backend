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
OSINERGMIN_TIMEOUT = float(os.getenv("OSINERGMIN_TIMEOUT_SECONDS", "5"))


def normalizar(valor: str) -> str:
    valor = unicodedata.normalize("NFKD", valor.casefold())
    valor = "".join(c for c in valor if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", valor).strip()


def _leer_lista(path: Path) -> list[dict]:
    """Carga y valida el catálogo completo; nunca ignora silenciosamente datos corruptos."""
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8") as archivo:
            data = json.load(archivo)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"No se pudo leer el directorio {path.name}") from exc

    if not isinstance(data, list):
        raise RuntimeError(f"El directorio {path.name} debe ser una lista JSON")

    requeridos = {"id", "nombre", "tipo", "departamento", "provincia", "distrito", "categorias", "palabras_clave"}
    ids = set()
    for indice, entidad in enumerate(data):
        if not isinstance(entidad, dict) or not requeridos.issubset(entidad):
            raise RuntimeError(f"Registro incompleto en {path.name}, posición {indice}")
        for campo in ("id", "nombre", "tipo", "departamento", "provincia", "distrito"):
            if not isinstance(entidad[campo], str) or not entidad[campo].strip():
                raise RuntimeError(f"Campo {campo} inválido en {path.name}, posición {indice}")
        if entidad["id"] in ids:
            raise RuntimeError(f"Identificador duplicado en {path.name}: {entidad['id']}")
        ids.add(entidad["id"])
        for campo in ("categorias", "palabras_clave"):
            valores = entidad[campo]
            if not isinstance(valores, list) or any(not isinstance(v, str) or not v.strip() for v in valores):
                raise RuntimeError(f"Campo {campo} inválido en {path.name}, posición {indice}")
        habilitadas = entidad.get("categorias_habilitadas", [])
        if not isinstance(habilitadas, list) or any(not isinstance(v, str) or not v.strip() for v in habilitadas):
            raise RuntimeError(f"Campo categorias_habilitadas inválido en {path.name}, posición {indice}")
        if entidad.get("habilitada_recomendacion", False) and not entidad.get("verificado_competencias", False):
            raise RuntimeError(f"Entidad habilitada sin competencia verificada: {entidad['id']}")
    return data


@lru_cache(maxsize=1)
def cargar_directorio() -> list[dict]:
    """Carga entidades locales; los registros PNP históricos no se habilitan."""
    return _leer_lista(DIRECTORIO_PATH) + _leer_lista(COMISARIAS_PATH)


MAX_ARCGIS_RESPONSE_BYTES = 1_048_576
ARCGIS_RETRIES = max(0, int(os.getenv("ARCGIS_RETRIES", "2")))


def _leer_atributos_arcgis(response, servicio: str) -> list[dict]:
    """Lee una respuesta acotada y valida la estructura antes de usar sus atributos."""
    raw = response.read(MAX_ARCGIS_RESPONSE_BYTES + 1)
    if len(raw) > MAX_ARCGIS_RESPONSE_BYTES:
        raise RuntimeError(f"La respuesta de {servicio} supera el tamaño permitido")
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"La respuesta de {servicio} no tiene formato JSON de objeto")
    if "error" in payload:
        raise RuntimeError(f"El servicio {servicio} devolvió un error")
    if payload.get("exceededTransferLimit") is True:
        raise RuntimeError(f"La respuesta de {servicio} está truncada por el límite de transferencia")
    features = payload.get("features")
    if not isinstance(features, list):
        raise RuntimeError(f"La respuesta de {servicio} no contiene una lista de resultados")
    atributos = []
    for feature in features:
        if not isinstance(feature, dict) or not isinstance(feature.get("attributes"), dict):
            raise RuntimeError(f"La respuesta de {servicio} contiene un resultado inválido")
        atributos.append(feature["attributes"])
    return atributos


def _consultar_arcgis(url: str, timeout: float, servicio: str) -> list[dict]:
    """Consulta ArcGIS con reintentos acotados ante fallos transitorios."""
    ultimo_error = None
    for intento in range(ARCGIS_RETRIES + 1):
        try:
            with urlopen(url, timeout=timeout) as response:
                return _leer_atributos_arcgis(response, servicio)
        except (URLError, HTTPError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            ultimo_error = exc
            if intento < ARCGIS_RETRIES:
                from time import sleep
                sleep(0.15 * (2 ** intento))
    raise RuntimeError(f"No se pudo consultar el servicio geográfico oficial de {servicio}") from ultimo_error


def _unicos_por_atributo(registros: list[dict], atributo: str) -> list[dict]:
    """Colapsa features duplicadas de una misma entidad, sin ocultar jurisdicciones distintas."""
    unicos = {}
    for registro in registros:
        valor = str(registro.get(atributo) or "").strip().casefold()
        # Un feature sin clave no puede fusionarse de forma segura con otro.
        clave = valor if valor else f"__sin_clave_{len(unicos)}"
        unicos.setdefault(clave, registro)
    return list(unicos.values())


def _arcgis_query(layer: int, params: dict) -> list[dict]:
    query = {"f": "json", "outFields": "*", "returnGeometry": "false", "resultRecordCount": 25, **params}
    url = f"{PNP_MAPSERVER}/{layer}/query?{urlencode(query)}"
    return _consultar_arcgis(url, PNP_TIMEOUT, "MININTER")


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
        jurisdicciones = _unicos_por_atributo(_arcgis_query(2, spatial), "cod_cpnp")
        if len(jurisdicciones) != 1:
            return EntidadSalida(sugerida=False, entidad=None, motivo="La ubicación no intersecta una única jurisdicción policial identificable. Se requiere revisión manual.")
        attrs = jurisdicciones[0]
        codigo = str(attrs.get("cod_cpnp") or attrs.get("codigo") or "").strip()
        nombre = str(attrs.get("comisaria") or attrs.get("nombre") or "").strip()
        if not codigo or not nombre:
            return EntidadSalida(sugerida=False, entidad=None, motivo="La capa de jurisdicciones no devolvió identificadores suficientes de la comisaría.")
        # Confirmar que el código también existe en la capa de comisarías (puntos operativos publicados).
        activos = _unicos_por_atributo(
            _arcgis_query(0, {"where": f"cod_cpnp='{codigo.replace(chr(39), chr(39)*2)}'", "outFields": "comisaria,cod_cpnp,departamento,provincia,distrito", "returnGeometry": "false"}),
            "cod_cpnp",
        )
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
    query = {"f": "json", "outFields": "*", "returnGeometry": "false", "resultRecordCount": 25, **params}
    url = f"{OSINERGMIN_MAPSERVER}/{layer}/query?{urlencode(query)}"
    return _consultar_arcgis(url, OSINERGMIN_TIMEOUT, "OSINERGMIN")


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
        concesiones = _unicos_por_atributo(_arcgis_query_osinergmin(33, spatial), "CODEMP")
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



def _sugerir_sedapal(entrada: EntidadEntrada) -> EntidadSalida:
    """Resuelve agua y saneamiento hacia SEDAPAL dentro de su ámbito documentado."""
    if (normalizar(entrada.departamento), normalizar(entrada.provincia)) not in {
        ("lima", "lima"),
        ("callao", "callao"),
    }:
        return EntidadSalida(
            sugerida=False, entidad=None,
            motivo="La ubicación indicada está fuera del ámbito territorial documentado de SEDAPAL.",
        )

    distrito = normalizar(entrada.distrito)
    municipalidades = [
        item for item in cargar_directorio()
        if item.get("tipo") in {"municipalidad_distrital", "municipalidad_provincial"}
        and item.get("verificado_nombre") is True
        and normalizar(item.get("departamento", "")) == normalizar(entrada.departamento)
        and normalizar(item.get("provincia", "")) == normalizar(entrada.provincia)
        and normalizar(item.get("distrito", "")) == distrito
    ]
    if len(municipalidades) != 1:
        return EntidadSalida(
            sugerida=False, entidad=None,
            motivo="No se pudo validar el distrito en el directorio territorial de Lima y Callao.",
        )

    texto = normalizar(f"{entrada.titulo} {entrada.descripcion}")
    senales = (
        "agua potable", "corte de agua", "sin agua", "falta de agua",
        "fuga", "tuberia", "desague", "alcantarillado", "buzon",
        "aniego", "baja presion", "rotura de tuberia", "colapso",
    )
    if not any(normalizar(senal) in texto for senal in senales):
        return EntidadSalida(
            sugerida=False, entidad=None,
            motivo="El texto no permite confirmar que el incidente corresponda a la red de agua potable o alcantarillado.",
        )

    return EntidadSalida(
        sugerida=True,
        entidad={
            "id": "sedapal-lima-callao",
            "nombre": "Servicio de Agua Potable y Alcantarillado de Lima (SEDAPAL)",
            "tipo": "empresa_saneamiento",
            "direccion": None,
            "telefono": "317-8000",
            "sitio_web": "https://www.gob.pe/sedapal",
            "ambito": {
                "departamento": entrada.departamento,
                "provincia": entrada.provincia,
                "distrito": entrada.distrito,
            },
        },
        motivo=(
            "El distrito está dentro del ámbito de responsabilidad de SEDAPAL para Lima y Callao "
            "y el texto describe una incidencia de agua potable o alcantarillado. La cobertura "
            "efectiva del predio y la conexión al servicio deben confirmarse con SEDAPAL."
        ),
    )

def _sugerir_atu(entrada: EntidadEntrada) -> EntidadSalida:
    """Recomienda ATU solo para la subcategoría explícita de transporte público urbano."""
    departamento = normalizar(entrada.departamento)
    provincia = normalizar(entrada.provincia)
    ambitos_validos = {
        ("lima", "lima"),
        ("callao", "callao"),
    }
    if (departamento, provincia) not in ambitos_validos:
        return EntidadSalida(
            sugerida=False, entidad=None,
            motivo="La denuncia está fuera del ámbito territorial de Lima y Callao de la ATU. Se requiere revisión manual.",
        )
    return EntidadSalida(
        sugerida=True,
        entidad={
            "id": "atu-lima-callao",
            "nombre": "Autoridad de Transporte Urbano para Lima y Callao (ATU)",
            "tipo": "autoridad_transporte_urbano",
            "direccion": None,
            "telefono": None,
            "sitio_web": "https://www.gob.pe/atu",
            "ambito": {
                "departamento": entrada.departamento,
                "provincia": entrada.provincia,
                "distrito": entrada.distrito,
            },
        },
        motivo="La categoría seleccionada corresponde específicamente al transporte público urbano de pasajeros y la provincia indicada está dentro del ámbito de la ATU. La recomendación requiere revisión humana del tipo de incidente.",
    )

def sugerir_entidad(entrada: EntidadEntrada) -> EntidadSalida:
    categoria = normalizar(entrada.categoria)
    if categoria == "alumbrado publico":
        return _sugerir_concesionaria_electrica(entrada)
    if categoria == "agua y saneamiento":
        return _sugerir_sedapal(entrada)
    if categoria == "transporte publico urbano de pasajeros":
        return _sugerir_atu(entrada)
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


def listar_entidades_disponibles(
    categoria: str,
    departamento: str,
    provincia: str,
    distrito: str,
    latitud: float | None = None,
    longitud: float | None = None,
) -> list[dict]:
    """Devuelve opciones manuales con competencia verificable para el lugar.

    No usa similitud de texto ni inventa alternativas: las municipalidades se
    filtran por el directorio oficial y las entidades geoespaciales se incluyen
    únicamente cuando el punto permite resolver una coincidencia única.
    """
    cat = normalizar(categoria)
    dep = normalizar(departamento)
    prov = normalizar(provincia)
    dis = normalizar(distrito)
    resultados: list[dict] = []

    for registro in cargar_directorio():
        if not registro.get("verificado_nombre") or not registro.get("verificado_competencias"):
            continue
        if (
            normalizar(registro.get("departamento", "")) != dep
            or normalizar(registro.get("provincia", "")) != prov
            or normalizar(registro.get("distrito", "")) != dis
        ):
            continue
        categorias = {
            normalizar(item)
            for item in registro.get("categorias_habilitadas", [])
        }
        if cat not in categorias:
            continue
        resultados.append({
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
        })

    # Instituciones cuya competencia depende del punto GPS, no solo del distrito.
    entrada = EntidadEntrada(
        categoria=categoria,
        departamento=departamento,
        provincia=provincia,
        distrito=distrito,
        titulo="Consulta manual de institución competente",
        descripcion="Consulta manual del catálogo de instituciones disponibles.",
        latitud=latitud,
        longitud=longitud,
    )
    resultado_geografico = None
    if cat in {"seguridad ciudadana", "seguridad ciudadana delitos", "delitos", "robo", "asalto", "violencia", "actividad sospechosa"}:
        resultado_geografico = _sugerir_comisaria_por_punto(entrada)
    elif cat == "alumbrado publico":
        resultado_geografico = _sugerir_concesionaria_electrica(entrada)
    elif cat == "agua y saneamiento":
        resultado_geografico = _sugerir_sedapal(entrada)
    elif cat == "transporte publico urbano de pasajeros":
        resultado_geografico = _sugerir_atu(entrada)

    if resultado_geografico and resultado_geografico.sugerida and resultado_geografico.entidad:
        item = resultado_geografico.entidad.model_dump() if hasattr(resultado_geografico.entidad, "model_dump") else dict(resultado_geografico.entidad)
        if not any(actual["id"] == item["id"] for actual in resultados):
            resultados.append(item)

    return sorted(resultados, key=lambda item: normalizar(item["nombre"]))
