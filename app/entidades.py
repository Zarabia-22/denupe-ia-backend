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

DISTRITOS_MAPSERVER = os.getenv(
    "DISTRITOS_MAPSERVER_URL",
    "https://ws.mineco.gob.pe/server/rest/services/cartografia_base_limites/MapServer",
)
DISTRITOS_TIMEOUT = float(os.getenv("DISTRITOS_TIMEOUT_SECONDS", "5"))


def _arcgis_query_distritos(params: dict) -> list[dict]:
    query = {
        "f": "json",
        "outFields": "UBIGEO,NOMBDEP,NOMBPROV,NOMBDIST",
        "returnGeometry": "false",
        "resultRecordCount": 5,
        **params,
    }
    url = f"{DISTRITOS_MAPSERVER}/3/query?{urlencode(query)}"
    return _consultar_arcgis(url, DISTRITOS_TIMEOUT, "límites distritales")


def resolver_distrito_por_punto(latitud: float, longitud: float) -> dict:
    """Resuelve el distrito mediante intersección con el polígono y valida UBIGEO."""
    geometry = json.dumps({"x": longitud, "y": latitud, "spatialReference": {"wkid": 4326}})
    features = _arcgis_query_distritos({
        "geometry": geometry,
        "geometryType": "esriGeometryPoint",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "UBIGEO,NOMBDEP,NOMBPROV,NOMBDIST",
        "returnGeometry": "false",
    })
    by_ubigeo = _unicos_por_atributo(features, "UBIGEO")
    if len(by_ubigeo) != 1:
        raise RuntimeError("La coordenada no pertenece a un único polígono distrital identificable.")
    ubigeo = str(by_ubigeo[0].get("UBIGEO") or "").strip()
    if len(ubigeo) != 6 or not ubigeo.isdigit():
        raise RuntimeError("La capa distrital no devolvió un código UBIGEO válido.")
    feature = by_ubigeo[0]
    departamento = str(feature.get("NOMBDEP") or "").strip().title()
    provincia = str(feature.get("NOMBPROV") or "").strip().title()
    distrito = str(feature.get("NOMBDIST") or "").strip().title()
    if not all((departamento, provincia, distrito)):
        raise RuntimeError("La capa distrital no devolvió departamento, provincia y distrito.")
    return {
        "ubigeo": ubigeo,
        "departamento": departamento,
        "provincia": provincia,
        "distrito": distrito,
        "fuente_geografica": "Servicio cartográfico cartografia_base_limites, capa 3",
    }


def catalogo_distrital_por_categoria(departamento: str, provincia: str, distrito: str) -> dict:
    """Relaciona cada categoría con entidades públicas del distrito y rutas sectoriales.

    La matriz siempre contiene al menos una entidad candidata por categoría. Para
    competencias que dependen del punto o del tipo de vía, la entidad se presenta
    como responsable sectorial a resolver, nunca como jurisdicción ya confirmada.
    """
    dep, prov, dis = map(normalizar, (departamento, provincia, distrito))
    municipios = [
        item for item in cargar_directorio()
        if item.get("tipo") in {"municipalidad_distrital", "municipalidad_provincial"}
        and item.get("verificado_nombre") is True
        and normalizar(item.get("departamento", "")) == dep
        and normalizar(item.get("provincia", "")) == prov
        and normalizar(item.get("distrito", "")) == dis
    ]
    if len(municipios) != 1:
        raise ValueError("El distrito no está registrado de forma única en la cobertura actual.")
    muni = municipios[0]
    ambito = {
        "departamento": muni["departamento"],
        "provincia": muni["provincia"],
        "distrito": muni["distrito"],
    }
    municipalidad = {
        "id": muni["id"], "nombre": muni["nombre"],
        "tipo": muni["tipo"], "ambito": ambito,
        "rol": "entidad_local_del_distrito",
    }
    lima_callao = (dep, prov) in {("lima", "lima"), ("callao", "callao")}
    municipalidad_provincial = (
        {"id": "mml-150101", "nombre": "Municipalidad Metropolitana de Lima",
         "tipo": "municipalidad_provincial", "ambito": ambito,
         "rol": "autoridad_vial_y_de_transito_metropolitano"}
        if (dep, prov) == ("lima", "lima") else
        {"id": "mpc-070101", "nombre": "Municipalidad Provincial del Callao",
         "tipo": "municipalidad_provincial", "ambito": ambito,
         "rol": "autoridad_vial_y_de_transito_provincial"}
        if (dep, prov) == ("callao", "callao") else municipalidad
    )
    pnp = {
        "id": "pnp-jurisdiccion-gps",
        "nombre": "Policía Nacional del Perú — comisaría competente por jurisdicción GPS",
        "tipo": "comisaria_pnp_por_resolver",
        "ambito": ambito,
        "rol": "entidad_sectorial_resuelta_por_poligono_pnp",
    }
    electrica = {
        "id": "concesionaria-electrica-gps",
        "nombre": "Empresa concesionaria eléctrica que cubre el punto GPS",
        "tipo": "empresa_concesionaria_electrica_por_resolver",
        "ambito": ambito,
        "rol": "entidad_sectorial_resuelta_por_poligono_osinergmin",
    }
    sedapal = {
        "id": "sedapal-lima-callao",
        "nombre": "Servicio de Agua Potable y Alcantarillado de Lima (SEDAPAL)",
        "tipo": "empresa_saneamiento",
        "ambito": ambito,
        "rol": "empresa_operadora_del_ambito_documentado",
    }
    atu = {
        "id": "atu-lima-callao",
        "nombre": "Autoridad de Transporte Urbano para Lima y Callao (ATU)",
        "tipo": "autoridad_transporte_urbano",
        "ambito": ambito,
        "rol": "sistema_integrado_de_transporte_urbano_de_personas",
    }
    mtc = {
        "id": "mtc-red-vial-nacional",
        "nombre": "Ministerio de Transportes y Comunicaciones (MTC) / Provías, según tramo",
        "tipo": "autoridad_vial_nacional",
        "ambito": ambito,
        "rol": "titular_o_gestor_de_red_vial_nacional",
    }
    gobierno_regional = {
        "id": "gobierno-regional-lima",
        "nombre": "Gobierno Regional correspondiente, según jurisdicción",
        "tipo": "gobierno_regional",
        "ambito": ambito,
        "rol": "titular_o_gestor_de_red_vial_departamental",
    }
    revision = {
        "id": "revision-competencia",
        "nombre": "Revisión de competencia (DenuPe)",
        "tipo": "revision_competencia",
        "ambito": ambito,
        "rol": "respaldo_interno_no_es_entidad_publica",
    }

    categorias = [
        {
            "categoria": "Alumbrado público",
            "ruta": "concesion_electrica_por_poligono",
            "requiere_gps": True,
            "entidades": [electrica],
            "entidad_principal": electrica,
            "respaldo": municipalidad,
            "estado": "entidad_sectorial_preconfigurada_pendiente_de_resolucion_gps",
            "nota": "La concesionaria se identifica intersectando el punto GPS con el polígono oficial de concesiones de OSINERGMIN; la municipalidad queda como canal local de apoyo, no como sustituto de la concesionaria.",
        },
        {
            "categoria": "Seguridad ciudadana",
            "ruta": "comisaria_pnp_por_jurisdiccion",
            "requiere_gps": True,
            "entidades": [pnp],
            "entidad_principal": pnp,
            "respaldo": municipalidad,
            "estado": "entidad_sectorial_preconfigurada_pendiente_de_resolucion_gps",
            "nota": "La comisaría concreta se resuelve con la jurisdicción policial del punto GPS; serenazgo municipal es apoyo preventivo y no reemplaza a la PNP.",
        },
        {
            "categoria": "Limpieza y residuos",
            "ruta": "municipalidad_distrital",
            "requiere_gps": False,
            "entidades": [municipalidad],
            "entidad_principal": municipalidad,
            "respaldo": revision,
            "estado": "competencia_local_verificada",
        },
        {
            "categoria": "Agua y saneamiento",
            "ruta": "empresa_operadora_de_saneamiento",
            "requiere_gps": False,
            "entidades": [sedapal] if lima_callao else [municipalidad],
            "entidad_principal": sedapal if lima_callao else municipalidad,
            "respaldo": revision,
            "estado": "operador_territorial_preconfigurado" if lima_callao else "municipalidad_como_punto_de_entrada_requiere_identificar_operador",
            "nota": "En Lima y Callao se propone SEDAPAL, sujeto a confirmar que el predio y la zona estén dentro de su cobertura efectiva. Fuera de ese ámbito, la municipalidad distrital queda como punto de entrada para identificar la EPS/JASS/operador real; no se afirma que sea la prestadora.",
        },
        {
            "categoria": "Tránsito y transporte",
            "ruta": "clasificacion_por_tipo_de_incidente",
            "requiere_gps": True,
            "entidades": ([atu, municipalidad_provincial, municipalidad] if lima_callao else [municipalidad_provincial, municipalidad]),
            "entidad_principal": atu if lima_callao else municipalidad_provincial,
            "respaldo": municipalidad,
            "estado": "entidades_sectoriales_preconfiguradas_requiere_clasificacion",
            "nota": "ATU para transporte público urbano de pasajeros en Lima/Callao; municipalidad provincial/metropolitana para gestión del tránsito y red vial bajo su competencia; municipalidad distrital para asuntos locales. La incidencia concreta determina cuál corresponde.",
        },
        {
            "categoria": "Parques y áreas verdes",
            "ruta": "municipalidad_distrital",
            "requiere_gps": False,
            "entidades": [municipalidad],
            "entidad_principal": municipalidad,
            "respaldo": revision,
            "estado": "competencia_local_condicionada",
            "nota": "Aplicable a parques y jardines públicos bajo administración local; verificar titularidad o administración del espacio.",
        },
        {
            "categoria": "Vialidad e infraestructura",
            "ruta": "titularidad_y_jerarquia_del_tramo_vial",
            "requiere_gps": True,
            "entidades": [mtc, gobierno_regional, municipalidad_provincial, municipalidad],
            "entidad_principal": municipalidad_provincial,
            "respaldo": municipalidad,
            "estado": "entidades_preconfiguradas_requiere_identificar_tramo",
            "nota": "Se relacionan MTC/Provías (red nacional), Gobierno Regional (red departamental), municipalidad provincial (red provincial) y municipalidad distrital (vías urbanas/locales). El GPS debe cruzarse con inventario vial y concesiones antes de seleccionar la entidad final.",
        },
        {
            "categoria": "Otros",
            "ruta": "municipalidad_como_ventanilla_de_orientacion",
            "requiere_gps": False,
            "entidades": [municipalidad],
            "entidad_principal": municipalidad,
            "respaldo": revision,
            "estado": "entidad_de_entrada_preconfigurada_requiere_clasificacion",
            "nota": "La municipalidad distrital es el primer punto de recepción/orientación local; no se presume que sea la autoridad final si el asunto pertenece a otro sector.",
        },
    ]
    return {
        "ubigeo": muni.get("codigo_ubigeo"),
        "departamento": muni["departamento"],
        "provincia": muni["provincia"],
        "distrito": muni["distrito"],
        "categorias": categorias,
        "total_categorias": len(categorias),
        "categorias_con_entidad_relacionada": sum(1 for item in categorias if item["entidades"]),
        "cobertura": "Lima Metropolitana y Provincia Constitucional del Callao (50 distritos configurados)",
    }

def normalizar(valor: str) -> str:
    valor = unicodedata.normalize("NFKD", valor.casefold())
    valor = "".join(c for c in valor if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", valor).strip()


def _leer_lista(path: Path, *, required: bool = False) -> list[dict]:
    """Carga y valida un catálogo; los archivos requeridos no pueden faltar silenciosamente."""
    if not path.exists():
        if required:
            raise RuntimeError(f"Falta el directorio obligatorio {path.name}")
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
    return _leer_lista(DIRECTORIO_PATH, required=True) + _leer_lista(COMISARIAS_PATH)


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



def _sugerir_sedapal(
    entrada: EntidadEntrada,
    *,
    exigir_senal_textual: bool = True,
) -> EntidadSalida:
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
        "no hay agua", "no llega agua", "agua no llega", "no sale agua",
        "corte", "servicio de agua", "problema de agua",
    )
    if exigir_senal_textual and not any(normalizar(senal) in texto for senal in senales):
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
            "El distrito está dentro del ámbito de responsabilidad de SEDAPAL para Lima y Callao. "
            + (
                "El texto describe una incidencia de agua potable o alcantarillado. "
                if exigir_senal_textual else
                "La categoría corresponde a agua y saneamiento; confirma que el predio está conectado al servicio. "
            )
            + "La cobertura efectiva del predio debe confirmarse con SEDAPAL."
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


def _sugerir_revision_competencia(
    entrada: EntidadEntrada,
    motivo_origen: str,
) -> EntidadSalida:
    """Destino interno seguro cuando no se identifica una entidad pública única."""
    return EntidadSalida(
        sugerida=True,
        entidad={
            "id": "revision-competencia",
            "nombre": "Revisión de competencia (DenuPe)",
            "tipo": "revision_competencia",
            "direccion": None,
            "telefono": None,
            "sitio_web": None,
            "ambito": {
                "departamento": entrada.departamento,
                "provincia": entrada.provincia,
                "distrito": entrada.distrito,
            },
        },
        motivo=(
            "No se pudo confirmar una institución pública específica para esta categoría y ubicación. "
            "Se propone la bandeja interna de Revisión de competencia de DenuPe para que el personal "
            "determine el organismo responsable. Este destino es una cola interna, no una entidad pública externa. "
            + motivo_origen
        ),
    )


def _con_respaldo_revision(
    entrada: EntidadEntrada,
    resultado: EntidadSalida,
) -> EntidadSalida:
    if resultado.sugerida and resultado.entidad is not None:
        return resultado
    return _sugerir_revision_competencia(entrada, resultado.motivo)

def sugerir_entidad(entrada: EntidadEntrada) -> EntidadSalida:
    categoria = normalizar(entrada.categoria)
    if categoria == "alumbrado publico":
        return _con_respaldo_revision(entrada, _sugerir_concesionaria_electrica(entrada))
    if categoria == "agua y saneamiento":
        return _con_respaldo_revision(entrada, _sugerir_sedapal(entrada))
    if categoria == "transporte publico urbano de pasajeros":
        return _con_respaldo_revision(entrada, _sugerir_atu(entrada))
    if categoria in {"seguridad ciudadana", "seguridad ciudadana delitos", "delitos", "robo", "asalto", "violencia", "actividad sospechosa"}:
        return _con_respaldo_revision(entrada, _sugerir_comisaria_por_punto(entrada))

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
        return _sugerir_revision_competencia(
            entrada,
            "No existe una regla habilitada o un registro territorial suficiente para la categoría.",
        )
    candidatos.sort(key=lambda item: item[0], reverse=True)
    if len(candidatos) > 1 and candidatos[0][0] == candidatos[1][0]:
        return _sugerir_revision_competencia(
            entrada,
            "Hay más de una entidad candidata con evidencia equivalente.",
        )

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
    categoria: str | None,
    departamento: str,
    provincia: str,
    distrito: str,
    latitud: float | None = None,
    longitud: float | None = None,
) -> list[dict]:
    """Devuelve todas las entidades registradas para el distrito, sin filtrar por categoría.

    El parámetro categoria se conserva por compatibilidad con clientes antiguos,
    pero deliberadamente no interviene en la consulta. La recomendación específica
    se realiza exclusivamente en /api/ia/sugerir-entidad cuando la persona la solicita.
    """
    dep = normalizar(departamento)
    prov = normalizar(provincia)
    dis = normalizar(distrito)
    resultados: list[dict] = []

    registros_distrito = [
        registro for registro in cargar_directorio()
        if registro.get("verificado_nombre") is True
        and normalizar(registro.get("departamento", "")) == dep
        and normalizar(registro.get("provincia", "")) == prov
        and normalizar(registro.get("distrito", "")) == dis
    ]

    if len([
        registro for registro in registros_distrito
        if registro.get("tipo") in {"municipalidad_distrital", "municipalidad_provincial"}
    ]) != 1:
        entrada = EntidadEntrada(
            categoria=categoria or "Consulta general",
            departamento=departamento,
            provincia=provincia,
            distrito=distrito,
            titulo="Consulta manual de instituciones",
            descripcion="Consulta de entidades registradas para el distrito.",
            latitud=latitud,
            longitud=longitud,
        )
        revision = _sugerir_revision_competencia(
            entrada,
            "No existe un registro territorial único y verificado para este distrito.",
        )
        item = revision.entidad.model_dump() if hasattr(revision.entidad, "model_dump") else dict(revision.entidad)
        return [item]

    def agregar(item: dict | None) -> None:
        if item and not any(actual["id"] == item.get("id") for actual in resultados):
            resultados.append(item)

    # Todas las instituciones verificadas por nombre del distrito, aunque sus
    # categorías habilitadas no coincidan con la denuncia actual.
    for registro in registros_distrito:
        agregar({
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

    entrada = EntidadEntrada(
        categoria=categoria or "Consulta general",
        departamento=departamento,
        provincia=provincia,
        distrito=distrito,
        titulo="Consulta manual de instituciones",
        descripcion="Consulta de todas las entidades registradas para el distrito.",
        latitud=latitud,
        longitud=longitud,
    )

    # Las instituciones que dependen del punto GPS se resuelven al cargar
    # el catálogo completo, sin condicionarlas a la categoría de la denuncia.
    if latitud is not None and longitud is not None:
        for resolver in (_sugerir_comisaria_por_punto, _sugerir_concesionaria_electrica):
            try:
                salida = resolver(entrada)
                if salida.sugerida and salida.entidad is not None:
                    item = salida.entidad.model_dump() if hasattr(salida.entidad, "model_dump") else dict(salida.entidad)
                    agregar(item)
            except (RuntimeError, ValueError):
                continue

    # Se agregan solo dentro de su ámbito territorial documentado.
    for resolver in (
        lambda: _sugerir_sedapal(entrada, exigir_senal_textual=False),
        lambda: _sugerir_atu(entrada),
    ):
        try:
            salida = resolver()
            if salida.sugerida and salida.entidad is not None:
                item = salida.entidad.model_dump() if hasattr(salida.entidad, "model_dump") else dict(salida.entidad)
                agregar(item)
        except (RuntimeError, ValueError):
            continue

    if not resultados:
        revision = _sugerir_revision_competencia(
            entrada,
            "No hay instituciones públicas concretas registradas para este distrito.",
        )
        item = revision.entidad.model_dump() if hasattr(revision.entidad, "model_dump") else dict(revision.entidad)
        agregar(item)

    return sorted(resultados, key=lambda item: normalizar(item["nombre"]))
