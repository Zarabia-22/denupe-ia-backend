"""Pruebas unitarias del lector de UBIGEO para la auditoría real."""
import pytest

from scripts.auditoria_territorial_real import cargar_ubigeos


def test_carga_solo_distritos_y_conserva_ceros_iniciales():
    csv_text = (
        "ubigeo,nivel,nombre,nombre_provincia,nombre_departamento\n"
        "15,departamento,Lima,,\n"
        "1501,provincia,Lima,Lima,Lima\n"
        "010101,distrito,Chachapoyas,Chachapoyas,Amazonas\n"
    )
    assert cargar_ubigeos(csv_text) == [{
        "ubigeo": "010101",
        "distrito": "Chachapoyas",
        "provincia": "Chachapoyas",
        "departamento": "Amazonas",
    }]


@pytest.mark.parametrize("codigo", ["12345", "12A456", "1234567"])
def test_rechaza_ubigeo_distrital_invalido(codigo):
    csv_text = (
        "ubigeo,nivel,nombre,nombre_provincia,nombre_departamento\n"
        f"{codigo},distrito,Ejemplo,Provincia,Departamento\n"
    )
    with pytest.raises(ValueError, match="inválidos"):
        cargar_ubigeos(csv_text)


def test_rechaza_ubigeos_duplicados():
    csv_text = (
        "ubigeo,nivel,nombre,nombre_provincia,nombre_departamento\n"
        "010101,distrito,A,P,D\n"
        "010101,distrito,B,P,D\n"
    )
    with pytest.raises(ValueError, match="duplicados"):
        cargar_ubigeos(csv_text)


def test_rechaza_fuente_sin_distritos():
    csv_text = "ubigeo,nivel,nombre,nombre_provincia,nombre_departamento\n"
    with pytest.raises(ValueError, match="no contiene"):
        cargar_ubigeos(csv_text)
