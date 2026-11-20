"""Batería unitaria de resolución GPS contra polígonos distritales."""
import json

import pytest

from app import entidades


def test_resuelve_punto_con_ubigeo_y_metadatos_completos(monkeypatch):
    consultas = []

    def fake_query(params):
        consultas.append(params)
        return [{
            "UBIGEO": "150122",
            "NOMBDEP": "LIMA",
            "NOMBPROV": "LIMA",
            "NOMBDIST": "MIRAFLORES",
        }]

    monkeypatch.setattr(entidades, "_arcgis_query_distritos", fake_query)
    resultado = entidades.resolver_distrito_por_punto(-12.12, -77.03)

    assert resultado["ubigeo"] == "150122"
    assert resultado["distrito"] == "Miraflores"
    assert resultado["provincia"] == "Lima"
    assert resultado["departamento"] == "Lima"
    geometry = json.loads(consultas[0]["geometry"])
    assert geometry["x"] == -77.03
    assert geometry["y"] == -12.12
    assert consultas[0]["spatialRel"] == "esriSpatialRelIntersects"


@pytest.mark.parametrize("features", [
    [],
    [
        {"UBIGEO": "150122", "NOMBDEP": "Lima", "NOMBPROV": "Lima", "NOMBDIST": "Miraflores"},
        {"UBIGEO": "150123", "NOMBDEP": "Lima", "NOMBPROV": "Lima", "NOMBDIST": "Otro"},
    ],
])
def test_se_abstiene_si_no_hay_unico_poligono(features, monkeypatch):
    monkeypatch.setattr(entidades, "_arcgis_query_distritos", lambda params: features)
    with pytest.raises(RuntimeError, match="único polígono"):
        entidades.resolver_distrito_por_punto(-12.12, -77.03)


@pytest.mark.parametrize("feature", [
    {"UBIGEO": "15012", "NOMBDEP": "Lima", "NOMBPROV": "Lima", "NOMBDIST": "Miraflores"},
    {"UBIGEO": "15A122", "NOMBDEP": "Lima", "NOMBPROV": "Lima", "NOMBDIST": "Miraflores"},
])
def test_rechaza_ubigeo_malformado(feature, monkeypatch):
    monkeypatch.setattr(entidades, "_arcgis_query_distritos", lambda params: [feature])
    with pytest.raises(RuntimeError, match="UBIGEO válido"):
        entidades.resolver_distrito_por_punto(-12.12, -77.03)


@pytest.mark.parametrize("feature", [
    {"UBIGEO": "150122", "NOMBDEP": "", "NOMBPROV": "Lima", "NOMBDIST": "Miraflores"},
    {"UBIGEO": "150122", "NOMBDEP": "Lima", "NOMBPROV": None, "NOMBDIST": "Miraflores"},
    {"UBIGEO": "150122", "NOMBDEP": "Lima", "NOMBPROV": "Lima", "NOMBDIST": ""},
])
def test_rechaza_poligono_sin_nombres_territoriales(feature, monkeypatch):
    monkeypatch.setattr(entidades, "_arcgis_query_distritos", lambda params: [feature])
    with pytest.raises(RuntimeError, match="departamento, provincia y distrito"):
        entidades.resolver_distrito_por_punto(-12.12, -77.03)


def test_colapsa_features_repetidas_del_mismo_ubigeo():
    registros = [
        {"UBIGEO": "150122", "NOMBDIST": "Miraflores"},
        {"UBIGEO": "150122", "NOMBDIST": "Miraflores"},
    ]
    assert len(entidades._unicos_por_atributo(registros, "UBIGEO")) == 1


def test_no_colapsa_dos_ubigeos_distintos():
    registros = [
        {"UBIGEO": "150122"},
        {"UBIGEO": "150123"},
    ]
    assert len(entidades._unicos_por_atributo(registros, "UBIGEO")) == 2


def test_fallo_del_servicio_geografico_no_se_convierte_en_distrito(monkeypatch):
    def fallo(params):
        raise RuntimeError("servicio no disponible")

    monkeypatch.setattr(entidades, "_arcgis_query_distritos", fallo)
    with pytest.raises(RuntimeError, match="servicio no disponible"):
        entidades.resolver_distrito_por_punto(-12.12, -77.03)
