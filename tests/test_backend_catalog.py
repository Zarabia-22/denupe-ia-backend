"""Pruebas del catálogo territorial servido por el backend principal DenuPe."""
import io
import json

import pytest

from app import backend_catalog


CATEGORIAS = [
    "alumbrado", "seguridad", "limpieza", "agua",
    "transito", "areas_verdes", "infraestructura", "otros",
]


def filas_completas(ubigeo="150122"):
    return [
        {
            "ubigeo": ubigeo,
            "categoria_code": codigo,
            "entidad_resolucion_id": f"resolutor-{codigo}",
            "entidad_nombre": f"Entidad {codigo}",
            "entidad_tipo": "entidad_sectorial",
            "metodo_resolucion": "validación territorial",
            "estado_validacion": "requiere_validacion",
            "entidad_activa": True,
            "requiere_gps": True,
            "asignar_solo_tras_gps": True,
        }
        for codigo in CATEGORIAS
    ]


def test_consultar_matriz_exige_ocho_categorias(monkeypatch):
    filas = filas_completas()
    monkeypatch.setattr(backend_catalog, "_get_catalogo", lambda params: filas)
    resultado = backend_catalog.consultar_matriz_distrital("150122")
    assert len(resultado) == 8
    assert {fila["categoria_code"] for fila in resultado} == set(CATEGORIAS)


def test_consultar_matriz_rechaza_catalogo_incompleto(monkeypatch):
    monkeypatch.setattr(
        backend_catalog,
        "_get_catalogo",
        lambda params: filas_completas()[:-1],
    )
    with pytest.raises(backend_catalog.BackendCatalogError):
        backend_catalog.consultar_matriz_distrital("150122")


def test_consultar_matriz_rechaza_duplicados(monkeypatch):
    filas = filas_completas()
    filas[-1] = dict(filas[0])
    monkeypatch.setattr(backend_catalog, "_get_catalogo", lambda params: filas)
    with pytest.raises(backend_catalog.BackendCatalogError):
        backend_catalog.consultar_matriz_distrital("150122")


def test_consultar_matriz_rechaza_regla_sin_resolutor(monkeypatch):
    filas = filas_completas()
    filas[0]["entidad_nombre"] = ""
    monkeypatch.setattr(backend_catalog, "_get_catalogo", lambda params: filas)
    with pytest.raises(backend_catalog.BackendCatalogError):
        backend_catalog.consultar_matriz_distrital("150122")


def test_ubigeo_debe_tener_seis_digitos_y_no_consulta_backend(monkeypatch):
    llamadas = []
    monkeypatch.setattr(
        backend_catalog,
        "_get_catalogo",
        lambda params: llamadas.append(params) or [],
    )
    with pytest.raises(ValueError):
        backend_catalog.consultar_matriz_distrital("15012")
    assert llamadas == []


def test_consultar_resolutor_exige_unico_resultado(monkeypatch):
    fila = filas_completas()[2]
    monkeypatch.setattr(backend_catalog, "_get_catalogo", lambda params: [fila])
    resultado = backend_catalog.consultar_resolutor_categoria("150122", "limpieza")
    assert resultado["entidad_resolucion_id"] == "resolutor-limpieza"
    assert resultado["entidad_nombre"] == "Entidad limpieza"


@pytest.mark.parametrize("filas", [[], [filas_completas()[0], filas_completas()[1]]])
def test_resolutor_rechaza_cero_o_multiples_resultados(monkeypatch, filas):
    monkeypatch.setattr(backend_catalog, "_get_catalogo", lambda params: filas)
    with pytest.raises(backend_catalog.BackendCatalogError):
        backend_catalog.consultar_resolutor_categoria("150122", "limpieza")


def test_resolutor_rechaza_categoria_no_registrada(monkeypatch):
    llamadas = []
    monkeypatch.setattr(
        backend_catalog,
        "_get_catalogo",
        lambda params: llamadas.append(params) or [],
    )
    with pytest.raises(ValueError):
        backend_catalog.consultar_resolutor_categoria("150122", "categoria_inexistente")
    assert llamadas == []


def test_cliente_consulta_endpoint_rest_del_backend_principal(monkeypatch):
    filas = filas_completas()
    capturado = {}
    monkeypatch.setenv("DENUPE_BACKEND_BASE_URL", "https://backend.example.test")
    monkeypatch.setenv("DENUPE_BACKEND_TIMEOUT_SECONDS", "9")

    def fake_urlopen(request, timeout):
        capturado["url"] = request.full_url
        capturado["method"] = request.get_method()
        capturado["accept"] = request.get_header("Accept")
        capturado["timeout"] = timeout
        return io.BytesIO(json.dumps(filas).encode("utf-8"))

    monkeypatch.setattr(backend_catalog, "urlopen", fake_urlopen)
    resultado = backend_catalog.consultar_matriz_distrital("150122")

    assert len(resultado) == 8
    assert capturado == {
        "url": "https://backend.example.test/api/v1/catalogos/matriz-territorial?ubigeo=150122",
        "method": "GET",
        "accept": "application/json",
        "timeout": 9.0,
    }


def test_cliente_rechaza_payload_no_lista(monkeypatch):
    monkeypatch.setenv("DENUPE_BACKEND_BASE_URL", "https://backend.example.test")
    monkeypatch.setattr(
        backend_catalog,
        "urlopen",
        lambda request, timeout: io.BytesIO(b'{"unexpected": true}'),
    )
    with pytest.raises(backend_catalog.BackendCatalogError, match="respuesta territorial inesperada"):
        backend_catalog.consultar_matriz_distrital("150122")


def test_bateria_estructural_1893_distritos_por_ocho_categorias(monkeypatch):
    llamadas = []

    def catalogo(params):
        ubigeo = params["ubigeo"]
        llamadas.append(ubigeo)
        filas = filas_completas(ubigeo)
        if "categoria_code" in params:
            return [fila for fila in filas if fila["categoria_code"] == params["categoria_code"]]
        return filas

    monkeypatch.setattr(backend_catalog, "_get_catalogo", catalogo)
    ubigeos = [f"{numero:06d}" for numero in range(1, 1894)]

    for ubigeo in ubigeos:
        matriz = backend_catalog.consultar_matriz_distrital(ubigeo)
        assert len(matriz) == 8
        assert {fila["categoria_code"] for fila in matriz} == set(CATEGORIAS)

    assert len(llamadas) == 1893
    assert set(llamadas) == set(ubigeos)
