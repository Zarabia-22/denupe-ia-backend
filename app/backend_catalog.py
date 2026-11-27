"""Cliente HTTP para el catálogo territorial del backend principal DenuPe."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen


class BackendCatalogError(RuntimeError):
    """Error de configuración o comunicación con el catálogo PostgreSQL central."""


CATEGORIAS_ESPERADAS = {
    "alumbrado",
    "seguridad",
    "limpieza",
    "agua",
    "transito",
    "areas_verdes",
    "infraestructura",
    "otros",
}


def _configuracion() -> tuple[str, float]:
    base_url = os.getenv(
        "DENUPE_BACKEND_BASE_URL",
        "https://denupe-backend.onrender.com",
    ).strip().rstrip("/") + "/"
    timeout = float(os.getenv("DENUPE_BACKEND_TIMEOUT_SECONDS", "12"))
    if not base_url.startswith(("https://", "http://")):
        raise BackendCatalogError("DENUPE_BACKEND_BASE_URL debe ser una URL HTTP(S) válida.")
    return base_url, timeout


def _get_catalogo(params: dict[str, str]) -> list[dict]:
    base_url, timeout = _configuracion()
    query = urlencode(params)
    url = urljoin(base_url, "api/v1/catalogos/matriz-territorial") + f"?{query}"
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "DenuPe-IA/2.0",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read(1_048_577).decode("utf-8"))
    except HTTPError as exc:
        raise BackendCatalogError(
            f"El backend principal devolvió HTTP {exc.code} al consultar el catálogo territorial."
        ) from exc
    except (URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BackendCatalogError(
            "No se pudo consultar el catálogo territorial del backend principal."
        ) from exc

    if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
        raise BackendCatalogError("El backend principal devolvió una respuesta territorial inesperada.")
    return payload


def consultar_matriz_distrital(ubigeo: str) -> list[dict]:
    """Obtiene y valida las ocho reglas territoriales del UBIGEO."""
    if len(ubigeo) != 6 or not ubigeo.isdigit():
        raise ValueError("UBIGEO inválido.")

    filas = _get_catalogo({"ubigeo": ubigeo})
    categorias = {fila.get("categoria_code") for fila in filas}
    if len(filas) != 8 or categorias != CATEGORIAS_ESPERADAS:
        raise BackendCatalogError(
            "El distrito no tiene una matriz completa de ocho categorías en el backend principal."
        )
    if any(
        fila.get("ubigeo") != ubigeo
        or not fila.get("entidad_resolucion_id")
        or not fila.get("entidad_nombre")
        for fila in filas
    ):
        raise BackendCatalogError(
            "La matriz territorial contiene reglas sin UBIGEO o resolutor asociado."
        )
    return filas


def consultar_resolutor_categoria(ubigeo: str, categoria_code: str) -> dict:
    """Devuelve el resolutor sectorial asociado al distrito y categoría."""
    if len(ubigeo) != 6 or not ubigeo.isdigit():
        raise ValueError("UBIGEO inválido.")
    if categoria_code not in CATEGORIAS_ESPERADAS:
        raise ValueError("Categoría territorial inválida.")

    filas = _get_catalogo({"ubigeo": ubigeo, "categoria_code": categoria_code})
    if len(filas) != 1:
        raise BackendCatalogError(
            "No existe un resolutor único para el distrito y la categoría en el backend principal."
        )
    fila = filas[0]
    if (
        fila.get("ubigeo") != ubigeo
        or fila.get("categoria_code") != categoria_code
        or not fila.get("entidad_resolucion_id")
        or not fila.get("entidad_nombre")
    ):
        raise BackendCatalogError("El resolutor territorial está incompleto o no coincide con la consulta.")
    return fila
