"""Pruebas del recomendador territorial de entidades públicas."""
import json

from app.entidades import cargar_directorio, sugerir_entidad, DIRECTORIO_PATH
from app.schemas import EntidadEntrada


def entrada(**cambios):
    datos = {
        "categoria": "Limpieza y residuos",
        "departamento": "Lima",
        "provincia": "Lima",
        "distrito": "Miraflores",
        "titulo": "Basura acumulada en la avenida",
        "descripcion": "Hay bolsas de residuos y desperdicios sin recoger en la vía pública.",
    }
    datos.update(cambios)
    return EntidadEntrada(**datos)


def test_sin_entidades_registradas_se_abstiene(tmp_path, monkeypatch):
    monkeypatch.setattr("app.entidades.DIRECTORIO_PATH", tmp_path / "no-municipalidades.json")
    monkeypatch.setattr("app.entidades.COMISARIAS_PATH", tmp_path / "no-comisarias.json")
    cargar_directorio.cache_clear()
    salida = sugerir_entidad(entrada())
    assert salida.sugerida is False
    assert salida.entidad is None
    assert salida.motivo


def test_recomienda_entidad_solo_con_coincidencia_territorial_y_tematica(tmp_path, monkeypatch):
    catalogo = [{
        "id": "muni-miraflores",
        "nombre": "Municipalidad Distrital de Miraflores",
        "tipo": "municipalidad",
        "departamento": "Lima",
        "provincia": "Lima",
        "distrito": "Miraflores",
        "categorias": ["Limpieza y residuos"],
        "palabras_clave": ["residuos", "basura", "desperdicios"],
        "habilitada_recomendacion": True,
        "direccion": None,
        "telefono": None,
        "sitio_web": None,
    }]
    archivo = tmp_path / "entidades.json"
    archivo.write_text(json.dumps(catalogo), encoding="utf-8")
    monkeypatch.setattr("app.entidades.DIRECTORIO_PATH", archivo)
    monkeypatch.setattr("app.entidades.COMISARIAS_PATH", tmp_path / "no-comisarias.json")
    cargar_directorio.cache_clear()

    salida = sugerir_entidad(entrada())
    assert salida.sugerida is True
    assert salida.entidad.nombre == "Municipalidad Distrital de Miraflores"
    assert salida.entidad.ambito["distrito"] == "Miraflores"
    cargar_directorio.cache_clear()


def test_no_recomienda_entidad_de_otro_distrito(tmp_path, monkeypatch):
    catalogo = [{
        "id": "muni-surco",
        "nombre": "Municipalidad de Santiago de Surco",
        "tipo": "municipalidad",
        "departamento": "Lima",
        "provincia": "Lima",
        "distrito": "Santiago de Surco",
        "categorias": ["Limpieza y residuos"],
        "palabras_clave": ["residuos", "basura"],
        "habilitada_recomendacion": True,
    }]
    archivo = tmp_path / "entidades.json"
    archivo.write_text(json.dumps(catalogo), encoding="utf-8")
    monkeypatch.setattr("app.entidades.DIRECTORIO_PATH", archivo)
    cargar_directorio.cache_clear()

    salida = sugerir_entidad(entrada())
    assert salida.sugerida is False
    assert salida.entidad is None
    cargar_directorio.cache_clear()



def test_comisaria_historica_no_se_recomienda_automaticamente(tmp_path, monkeypatch):
    catalogo = [{
        "id": "pnp-6000",
        "nombre": "Comisaría PNP Callao",
        "tipo": "comisaria_pnp",
        "departamento": "Callao",
        "provincia": "Callao",
        "distrito": "Callao",
        "categorias": ["Seguridad ciudadana"],
        "palabras_clave": ["robo", "asalto"],
        "habilitada_recomendacion": False,
    }]
    archivo = tmp_path / "entidades.json"
    archivo.write_text(json.dumps(catalogo), encoding="utf-8")
    monkeypatch.setattr("app.entidades.DIRECTORIO_PATH", archivo)
    monkeypatch.setattr("app.entidades.COMISARIAS_PATH", tmp_path / "no-existe.json")
    cargar_directorio.cache_clear()

    denuncia = entrada(
        categoria="Seguridad ciudadana",
        departamento="Callao",
        provincia="Callao",
        distrito="Callao",
        titulo="Robo en la vía pública",
        descripcion="Reporto un robo ocurrido cerca de mi domicilio.",
    )
    salida = sugerir_entidad(denuncia)
    assert salida.sugerida is False
    assert salida.entidad is None
    cargar_directorio.cache_clear()


def test_recomienda_municipalidad_para_limpieza_y_residuos(tmp_path, monkeypatch):
    catalogo = [{
        "id": "muni-miraflores",
        "nombre": "Municipalidad Distrital de Miraflores",
        "tipo": "municipalidad_distrital",
        "departamento": "Lima",
        "provincia": "Lima",
        "distrito": "Miraflores",
        "categorias": ["Limpieza y residuos", "Alumbrado público"],
        "categorias_habilitadas": ["Limpieza y residuos", "Parques y áreas verdes"],
        "palabras_clave": ["residuos", "basura", "desperdicios"],
        "verificado_competencias": True,
    }]
    archivo = tmp_path / "entidades.json"
    archivo.write_text(json.dumps(catalogo), encoding="utf-8")
    monkeypatch.setattr("app.entidades.DIRECTORIO_PATH", archivo)
    monkeypatch.setattr("app.entidades.COMISARIAS_PATH", tmp_path / "no-existe.json")
    cargar_directorio.cache_clear()

    salida = sugerir_entidad(entrada())
    assert salida.sugerida is True
    assert salida.entidad.nombre == "Municipalidad Distrital de Miraflores"
    cargar_directorio.cache_clear()


def test_categoria_sin_competencia_verificada_no_se_recomienda(tmp_path, monkeypatch):
    catalogo = [{
        "id": "muni-miraflores",
        "nombre": "Municipalidad Distrital de Miraflores",
        "tipo": "municipalidad_distrital",
        "departamento": "Lima",
        "provincia": "Lima",
        "distrito": "Miraflores",
        "categorias": ["Limpieza y residuos", "Alumbrado público"],
        "categorias_habilitadas": ["Limpieza y residuos", "Parques y áreas verdes"],
        "palabras_clave": ["luminaria", "poste", "alumbrado"],
        "verificado_competencias": True,
    }]
    archivo = tmp_path / "entidades.json"
    archivo.write_text(json.dumps(catalogo), encoding="utf-8")
    monkeypatch.setattr("app.entidades.DIRECTORIO_PATH", archivo)
    monkeypatch.setattr("app.entidades.COMISARIAS_PATH", tmp_path / "no-existe.json")
    cargar_directorio.cache_clear()

    denuncia = entrada(
        categoria="Alumbrado público",
        titulo="Poste sin iluminación",
        descripcion="La luminaria de la calle no funciona desde ayer.",
    )
    salida = sugerir_entidad(denuncia)
    assert salida.sugerida is False
    assert salida.entidad is None
    cargar_directorio.cache_clear()


def test_pnp_exige_coordenadas_para_resolver_jurisdiccion():
    denuncia = entrada(
        categoria="Seguridad ciudadana",
        titulo="Robo en la calle",
        descripcion="Una persona reporta un robo ocurrido en la vía pública.",
    )
    salida = sugerir_entidad(denuncia)
    assert salida.sugerida is False
    assert "GPS" in salida.motivo


def test_pnp_resuelve_comisaria_con_poligono_y_confirma_capa_operativa(monkeypatch):
    from app import entidades

    calls = []
    def fake_query(layer, params):
        calls.append((layer, params))
        if layer == 2:
            return [{"cod_cpnp": "1234", "comisaria": "Miraflores", "distrito": "Miraflores"}]
        if layer == 0:
            return [{
                "cod_cpnp": "1234", "comisaria": "Miraflores",
                "departamento": "Lima", "provincia": "Lima", "distrito": "Miraflores",
            }]
        return []

    monkeypatch.setattr(entidades, "_arcgis_query", fake_query)
    denuncia = entrada(
        categoria="Seguridad ciudadana",
        titulo="Robo en la calle",
        descripcion="Reporto un robo cerca del parque.",
        latitud=-12.12,
        longitud=-77.03,
    )
    salida = sugerir_entidad(denuncia)
    assert salida.sugerida is True
    assert salida.entidad.id == "pnp-1234"
    assert salida.entidad.nombre == "Comisaría PNP Miraflores"
    assert [call[0] for call in calls] == [2, 0]


def test_pnp_se_abstiene_si_el_codigo_no_aparece_en_capa_operativa(monkeypatch):
    from app import entidades

    def fake_query(layer, params):
        if layer == 2:
            return [{"cod_cpnp": "1234", "comisaria": "Miraflores"}]
        return []

    monkeypatch.setattr(entidades, "_arcgis_query", fake_query)
    denuncia = entrada(
        categoria="Seguridad ciudadana",
        titulo="Robo en la calle",
        descripcion="Reporto un robo ocurrido cerca de mi domicilio.",
        latitud=-12.12,
        longitud=-77.03,
    )
    salida = sugerir_entidad(denuncia)
    assert salida.sugerida is False
    assert salida.entidad is None

def test_alumbrado_exige_coordenadas_para_identificar_concesionaria():
    denuncia = entrada(
        categoria="Alumbrado público",
        titulo="Poste sin iluminación",
        descripcion="La luminaria de la calle no funciona desde hace varios días.",
    )
    salida = sugerir_entidad(denuncia)
    assert salida.sugerida is False
    assert salida.entidad is None
    assert "GPS" in salida.motivo


def test_alumbrado_resuelve_empresa_por_poligono_oficial(monkeypatch):
    from app import entidades

    calls = []

    def fake_query(layer, params):
        calls.append((layer, params))
        return [{"CODEMP": "LDS"}]

    monkeypatch.setattr(entidades, "_arcgis_query_osinergmin", fake_query)
    denuncia = entrada(
        categoria="Alumbrado público",
        titulo="Luminaria apagada",
        descripcion="El poste de alumbrado público no funciona en la avenida.",
        latitud=-12.12,
        longitud=-77.03,
    )
    salida = sugerir_entidad(denuncia)

    assert salida.sugerida is True
    assert salida.entidad.nombre == "Luz del Sur"
    assert salida.entidad.tipo == "empresa_concesionaria_electrica"
    assert calls[0][0] == 33
    assert calls[0][1]["geometryType"] == "esriGeometryPoint"
    assert calls[0][1]["spatialRel"] == "esriSpatialRelIntersects"


def test_alumbrado_se_abstiene_si_no_hay_unico_poligono(monkeypatch):
    from app import entidades

    monkeypatch.setattr(entidades, "_arcgis_query_osinergmin", lambda layer, params: [])
    denuncia = entrada(
        categoria="Alumbrado público",
        titulo="Luminaria apagada",
        descripcion="El poste de alumbrado público no funciona en la avenida.",
        latitud=-12.12,
        longitud=-77.03,
    )
    salida = sugerir_entidad(denuncia)

    assert salida.sugerida is False
    assert salida.entidad is None


def test_alumbrado_se_abstiene_ante_codigo_de_empresa_desconocido(monkeypatch):
    from app import entidades

    monkeypatch.setattr(entidades, "_arcgis_query_osinergmin", lambda layer, params: [{"CODEMP": "NO_EXISTE"}])
    denuncia = entrada(
        categoria="Alumbrado público",
        titulo="Luminaria apagada",
        descripcion="El poste de alumbrado público no funciona en la avenida.",
        latitud=-12.12,
        longitud=-77.03,
    )
    salida = sugerir_entidad(denuncia)

    assert salida.sugerida is False
    assert salida.entidad is None

def test_atu_recomienda_para_transporte_publico_en_lima():
    denuncia = entrada(
        categoria="Transporte público urbano de pasajeros",
        departamento="Lima",
        provincia="Lima",
        distrito="Miraflores",
        titulo="Incumplimiento de frecuencia de buses",
        descripcion="Los buses del servicio urbano no respetan la frecuencia establecida.",
    )
    salida = sugerir_entidad(denuncia)
    assert salida.sugerida is True
    assert salida.entidad.id == "atu-lima-callao"
    assert salida.entidad.tipo == "autoridad_transporte_urbano"


def test_atu_recomienda_para_transporte_publico_en_callao():
    denuncia = entrada(
        categoria="Transporte público urbano de pasajeros",
        departamento="Callao",
        provincia="Callao",
        distrito="Bellavista",
        titulo="Problema con servicio de transporte",
        descripcion="El servicio de transporte urbano presenta incumplimientos.",
    )
    salida = sugerir_entidad(denuncia)
    assert salida.sugerida is True
    assert salida.entidad.id == "atu-lima-callao"


def test_atu_se_abstiene_fuera_de_lima_y_callao():
    denuncia = entrada(
        categoria="Transporte público urbano de pasajeros",
        departamento="Arequipa",
        provincia="Arequipa",
        distrito="Arequipa",
        titulo="Problema con servicio de transporte",
        descripcion="El servicio de transporte urbano presenta incumplimientos.",
    )
    salida = sugerir_entidad(denuncia)
    assert salida.sugerida is False
    assert salida.entidad is None




def test_entidad_rechaza_coordenadas_incompletas():
    from pydantic import ValidationError
    import pytest
    with pytest.raises(ValidationError):
        entrada(categoria="Seguridad ciudadana", latitud=-12.1)


def test_entidad_rechaza_coordenadas_fuera_de_rango():
    from pydantic import ValidationError
    import pytest
    with pytest.raises(ValidationError):
        entrada(categoria="Seguridad ciudadana", latitud=-12.1, longitud=220)


def test_catalogo_rechaza_ids_duplicados(tmp_path, monkeypatch):
    import pytest
    from app.entidades import _leer_lista
    registro = {
        "id": "duplicado", "nombre": "Entidad", "tipo": "municipalidad",
        "departamento": "Lima", "provincia": "Lima", "distrito": "Lima",
        "categorias": ["Limpieza"], "palabras_clave": ["basura"],
    }
    archivo = tmp_path / "duplicados.json"
    archivo.write_text(json.dumps([registro, registro]), encoding="utf-8")
    with pytest.raises(RuntimeError, match="duplicado"):
        _leer_lista(archivo)


def test_catalogo_rechaza_json_corrupto(tmp_path):
    import pytest
    from app.entidades import _leer_lista
    archivo = tmp_path / "corrupto.json"
    archivo.write_text("{ no es json", encoding="utf-8")
    with pytest.raises(RuntimeError, match="No se pudo leer"):
        _leer_lista(archivo)


def test_transito_y_transporte_generico_no_asigna_atu():
    denuncia = entrada(
        categoria="Tránsito y transporte",
        titulo="Semáforo averiado",
        descripcion="El semáforo de la intersección no funciona correctamente.",
    )
    salida = sugerir_entidad(denuncia)
    assert salida.sugerida is False
    assert salida.entidad is None

