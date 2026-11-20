"""Pruebas de integración del catálogo territorial InsForge."""
import pytest

from app import insforge_catalog


CATEGORIAS = [
    "alumbrado", "seguridad", "limpieza", "agua",
    "transito", "areas_verdes", "infraestructura", "otros",
]


def test_consultar_matriz_exige_ocho_categorias(monkeypatch):
    monkeypatch.setattr(
        insforge_catalog,
        "_rpc",
        lambda nombre, args: [
            {"categoria_code": codigo, "ubigeo": "150122"} for codigo in CATEGORIAS
        ],
    )
    filas = insforge_catalog.consultar_matriz_distrital("150122")
    assert len(filas) == 8


def test_consultar_matriz_rechaza_catalogo_incompleto(monkeypatch):
    monkeypatch.setattr(
        insforge_catalog, "_rpc",
        lambda nombre, args: [{"categoria_code": "limpieza", "ubigeo": "150122"}],
    )
    with pytest.raises(insforge_catalog.InsForgeCatalogError):
        insforge_catalog.consultar_matriz_distrital("150122")


def test_ubigeo_debe_tener_seis_digitos(monkeypatch):
    monkeypatch.setattr(insforge_catalog, "_rpc", lambda *args: [])
    with pytest.raises(ValueError):
        insforge_catalog.consultar_matriz_distrital("15012")


def test_consultar_resolutor_exige_unico_resultado(monkeypatch):
    monkeypatch.setattr(
        insforge_catalog,
        "_rpc",
        lambda nombre, args: [{"entidad_resolucion_id": "municipalidad_local"}],
    )
    resultado = insforge_catalog.consultar_resolutor_categoria("150122", "limpieza")
    assert resultado["entidad_resolucion_id"] == "municipalidad_local"


def test_rpc_falla_cerrado_si_faltan_credenciales(monkeypatch):
    monkeypatch.delenv("INSFORGE_URL", raising=False)
    monkeypatch.delenv("INSFORGE_API_KEY", raising=False)
    with pytest.raises(insforge_catalog.InsForgeCatalogError):
        insforge_catalog.consultar_matriz_distrital("150122")


def test_bateria_estructural_1893_distritos_por_ocho_categorias(monkeypatch):
    """Ejercita 15.144 combinaciones sintéticas; no consulta datos reales de InsForge."""
    llamadas = []

    def rpc(nombre, args):
        llamadas.append((nombre, args))
        return [
            {"categoria_code": codigo, "ubigeo": args["p_ubigeo"]}
            for codigo in CATEGORIAS
        ]

    monkeypatch.setattr(insforge_catalog, "_rpc", rpc)
    ubigeos_fixture = [f"{numero:06d}" for numero in range(1, 1894)]

    for ubigeo in ubigeos_fixture:
        matriz = insforge_catalog.consultar_matriz_distrital(ubigeo)
        assert len(matriz) == 8
        assert {fila["categoria_code"] for fila in matriz} == set(CATEGORIAS)

    assert len(llamadas) == 1893
    assert {args["p_ubigeo"] for _, args in llamadas} == set(ubigeos_fixture)


@pytest.mark.parametrize("filas", [
    [{"categoria_code": codigo} for codigo in CATEGORIAS[:-1]],
    [{"categoria_code": codigo} for codigo in CATEGORIAS] + [{"categoria_code": "extra"}],
    [{"categoria_code": codigo} for codigo in CATEGORIAS[:-1]] + [{"categoria_code": "limpieza"}],
])
def test_matriz_rechaza_faltantes_extras_y_duplicados(monkeypatch, filas):
    monkeypatch.setattr(insforge_catalog, "_rpc", lambda *args: filas)
    with pytest.raises(insforge_catalog.InsForgeCatalogError):
        insforge_catalog.consultar_matriz_distrital("150122")


@pytest.mark.parametrize("ubigeo", ["", "12345", "1234567", "12A456", " 150122"])
def test_ubigeo_invalido_no_consulta_rpc(monkeypatch, ubigeo):
    llamadas = []
    monkeypatch.setattr(insforge_catalog, "_rpc", lambda *args: llamadas.append(args) or [])
    with pytest.raises(ValueError):
        insforge_catalog.consultar_matriz_distrital(ubigeo)
    assert llamadas == []


def test_resolutor_rechaza_cero_o_multiples_resultados(monkeypatch):
    for filas in ([], [{"id": "a"}, {"id": "b"}]):
        monkeypatch.setattr(insforge_catalog, "_rpc", lambda *args: filas)
        with pytest.raises(insforge_catalog.InsForgeCatalogError):
            insforge_catalog.consultar_resolutor_categoria("150122", "limpieza")


def test_rpc_rechaza_payload_no_lista_o_filas_no_objeto(monkeypatch):
    import io

    monkeypatch.setattr(insforge_catalog, "_configuracion", lambda: ("https://example.invalid/", "ik_test"))
    monkeypatch.setattr(insforge_catalog, "urlopen", lambda request, timeout: io.BytesIO(b'{"unexpected": true}'))
    with pytest.raises(insforge_catalog.InsForgeCatalogError, match="respuesta inesperada"):
        insforge_catalog.consultar_matriz_distrital("150122")
