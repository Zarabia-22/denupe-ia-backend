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
        insforge_catalog, "_rpc",
        lambda nombre, args: [{"entidad_resolucion_id": "municipalidad_local"}],
    )
    resultado = insforge_catalog.consultar_resolutor_categoria("150122", "limpieza")
    assert resultado["entidad_resolucion_id"] == "municipalidad_local"


def test_rpc_falla_cerrado_si_faltan_credenciales(monkeypatch):
    monkeypatch.delenv("INSFORGE_URL", raising=False)
    monkeypatch.delenv("INSFORGE_API_KEY", raising=False)
    with pytest.raises(insforge_catalog.InsForgeCatalogError):
        insforge_catalog.consultar_matriz_distrital("150122")
