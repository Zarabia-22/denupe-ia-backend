"""Cliente servidor para consultar el catálogo territorial de InsForge."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


class InsForgeCatalogError(RuntimeError):
    """Error de configuración o comunicación con el catálogo InsForge."""


def _configuracion() -> tuple[str, str]:
    base_url = os.getenv("INSFORGE_URL", "").strip().rstrip("/") + "/"
    api_key = os.getenv("INSFORGE_API_KEY", "").strip()
    if not base_url.strip("/") or not api_key:
        raise InsForgeCatalogError(
            "El catálogo nacional requiere INSFORGE_URL e INSFORGE_API_KEY configuradas en el backend."
        )
    if not api_key.startswith("ik_"):
        raise InsForgeCatalogError("INSFORGE_API_KEY debe ser la API Key administrativa de InsForge (ik_...).")
    return base_url, api_key


def _rpc(nombre: str, argumentos: dict) -> list[dict]:
    base_url, api_key = _configuracion()
    url = urljoin(base_url, f"api/database/rpc/{nombre}")
    request = Request(
        url,
        data=json.dumps(argumentos).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=float(os.getenv("INSFORGE_TIMEOUT_SECONDS", "8"))) as response:
            payload = json.loads(response.read(1_048_577).decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InsForgeCatalogError(f"No se pudo consultar la RPC {nombre} de InsForge.") from exc
    if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
        raise InsForgeCatalogError(f"La RPC {nombre} devolvió una respuesta inesperada.")
    return payload


def consultar_matriz_distrital(ubigeo: str) -> list[dict]:
    """Obtiene las ocho reglas del distrito previamente resuelto por GPS."""
    if len(ubigeo) != 6 or not ubigeo.isdigit():
        raise ValueError("UBIGEO inválido.")
    filas = _rpc("consultar_matriz_distrital_por_ubigeo", {"p_ubigeo": ubigeo})
    categorias = {fila.get("categoria_code") for fila in filas}
    esperadas = {
        "alumbrado", "seguridad", "limpieza", "agua",
        "transito", "areas_verdes", "infraestructura", "otros",
    }
    if categorias != esperadas or len(filas) != 8:
        raise InsForgeCatalogError("El distrito no tiene una matriz completa de ocho categorías en InsForge.")
    return filas


def consultar_resolutor_categoria(ubigeo: str, categoria_code: str) -> dict:
    """Devuelve la regla sectorial, no una entidad pública concreta."""
    filas = _rpc(
        "consultar_entidades_por_ubigeo",
        {"p_ubigeo": ubigeo, "p_categoria_code": categoria_code},
    )
    if len(filas) != 1:
        raise InsForgeCatalogError("No existe un resolutor único para el distrito y la categoría.")
    return filas[0]
