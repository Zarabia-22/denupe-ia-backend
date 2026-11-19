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
    catalogo_vacio = tmp_path / "no-municipalidades.json"
    catalogo_vacio.write_text("[]", encoding="utf-8")
    monkeypatch.setattr("app.entidades.DIRECTORIO_PATH", catalogo_vacio)
    monkeypatch.setattr("app.entidades.COMISARIAS_PATH", tmp_path / "no-comisarias.json")
    cargar_directorio.cache_clear()
    salida = sugerir_entidad(entrada())
    assert salida.sugerida is True
    assert salida.entidad.tipo == "revision_competencia"
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
        "verificado_competencias": True,
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
        "verificado_competencias": True,
    }]
    archivo = tmp_path / "entidades.json"
    archivo.write_text(json.dumps(catalogo), encoding="utf-8")
    monkeypatch.setattr("app.entidades.DIRECTORIO_PATH", archivo)
    cargar_directorio.cache_clear()

    salida = sugerir_entidad(entrada())
    assert salida.sugerida is True
    assert salida.entidad.tipo == "revision_competencia"
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
    assert salida.sugerida is True
    assert salida.entidad.tipo == "revision_competencia"
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
    assert salida.sugerida is True
    assert salida.entidad.tipo == "revision_competencia"
    cargar_directorio.cache_clear()


def test_pnp_exige_coordenadas_para_resolver_jurisdiccion():
    denuncia = entrada(
        categoria="Seguridad ciudadana",
        titulo="Robo en la calle",
        descripcion="Una persona reporta un robo ocurrido en la vía pública.",
    )
    salida = sugerir_entidad(denuncia)
    assert salida.sugerida is True
    assert salida.entidad.tipo == "revision_competencia"
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
    assert salida.sugerida is True
    assert salida.entidad.tipo == "revision_competencia"

def test_alumbrado_exige_coordenadas_para_identificar_concesionaria():
    denuncia = entrada(
        categoria="Alumbrado público",
        titulo="Poste sin iluminación",
        descripcion="La luminaria de la calle no funciona desde hace varios días.",
    )
    salida = sugerir_entidad(denuncia)
    assert salida.sugerida is True
    assert salida.entidad.tipo == "revision_competencia"
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

    assert salida.sugerida is True
    assert salida.entidad.tipo == "revision_competencia"


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

    assert salida.sugerida is True
    assert salida.entidad.tipo == "revision_competencia"

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
    assert salida.sugerida is True
    assert salida.entidad.tipo == "revision_competencia"




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
    assert salida.sugerida is True
    assert salida.entidad.tipo == "revision_competencia"




def test_arcgis_limita_resultados_y_valida_atributos(monkeypatch):
    import io
    from app import entidades

    captured = {}
    def fake_urlopen(url, timeout):
        captured["url"] = url
        captured["timeout"] = timeout
        return io.BytesIO(b'{"features":[{"attributes":{"cod_cpnp":"123"}}]}')

    monkeypatch.setattr(entidades, "urlopen", fake_urlopen)
    salida = entidades._arcgis_query(2, {"geometryType": "esriGeometryPoint"})
    assert salida == [{"cod_cpnp": "123"}]
    assert "resultRecordCount=25" in captured["url"]


def test_arcgis_rechaza_respuesta_demasiado_grande(monkeypatch):
    import io
    import pytest
    from app import entidades

    monkeypatch.setattr(
        entidades,
        "urlopen",
        lambda url, timeout: io.BytesIO(b" " * (entidades.MAX_ARCGIS_RESPONSE_BYTES + 1)),
    )
    with pytest.raises(RuntimeError, match="supera el tamaño"):
        entidades._arcgis_query(2, {})


def test_arcgis_rechaza_estructura_invalida(monkeypatch):
    import io
    import pytest
    from app import entidades

    monkeypatch.setattr(entidades, "urlopen", lambda url, timeout: io.BytesIO(b'{"features":[{}]}'))
    with pytest.raises(RuntimeError, match="resultado inválido"):
        entidades._arcgis_query(2, {})



def test_pnp_colapsa_features_duplicadas_de_la_misma_jurisdiccion(monkeypatch):
    from app import entidades

    def fake_query(layer, params):
        if layer == 2:
            return [
                {"cod_cpnp": "1234", "comisaria": "Miraflores"},
                {"cod_cpnp": "1234", "comisaria": "Miraflores - registro duplicado"},
            ]
        return [{"cod_cpnp": "1234", "comisaria": "Miraflores", "distrito": "Miraflores"}]

    monkeypatch.setattr(entidades, "_arcgis_query", fake_query)
    denuncia = entrada(categoria="Seguridad ciudadana", titulo="Robo en la calle",
        descripcion="Reporto un robo cerca del parque.", latitud=-12.12, longitud=-77.03)
    salida = sugerir_entidad(denuncia)
    assert salida.sugerida is True
    assert salida.entidad.id == "pnp-1234"


def test_pnp_no_colapsa_jurisdicciones_con_codigos_distintos(monkeypatch):
    from app import entidades

    monkeypatch.setattr(entidades, "_arcgis_query", lambda layer, params: (
        [{"cod_cpnp": "1234"}, {"cod_cpnp": "5678"}] if layer == 2 else []
    ))
    denuncia = entrada(categoria="Seguridad ciudadana", titulo="Robo en la calle",
        descripcion="Reporto un robo cerca del parque.", latitud=-12.12, longitud=-77.03)
    salida = sugerir_entidad(denuncia)
    assert salida.sugerida is True
    assert salida.entidad.tipo == "revision_competencia"


def test_alumbrado_colapsa_poligonos_duplicados_de_la_misma_empresa(monkeypatch):
    from app import entidades

    monkeypatch.setattr(entidades, "_arcgis_query_osinergmin", lambda layer, params: [
        {"CODEMP": "LDS"}, {"CODEMP": "LDS"}
    ])
    denuncia = entrada(categoria="Alumbrado público", titulo="Luminaria apagada",
        descripcion="El poste de alumbrado público no funciona.", latitud=-12.12, longitud=-77.03)
    salida = sugerir_entidad(denuncia)
    assert salida.sugerida is True
    assert salida.entidad.id == "electrica-lds"


def test_arcgis_reintenta_ante_timeout_transitorio(monkeypatch):
    import io
    from socket import timeout as SocketTimeout
    from app import entidades

    llamadas = {"total": 0}
    def fake_urlopen(url, timeout):
        llamadas["total"] += 1
        if llamadas["total"] == 1:
            raise SocketTimeout("timeout temporal")
        return io.BytesIO(b'{"features":[{"attributes":{"cod_cpnp":"123"}}]}')

    monkeypatch.setattr(entidades, "urlopen", fake_urlopen)
    monkeypatch.setattr(entidades, "ARCGIS_RETRIES", 1)
    assert entidades._arcgis_query(2, {}) == [{"cod_cpnp": "123"}]
    assert llamadas["total"] == 2



def test_arcgis_rechaza_resultados_truncados_por_el_servicio(monkeypatch):
    import io
    import pytest
    from app import entidades

    payload = b'{"exceededTransferLimit":true,"features":[{"attributes":{"cod_cpnp":"123"}}]}'
    monkeypatch.setattr(entidades, "urlopen", lambda url, timeout: io.BytesIO(payload))
    with pytest.raises(RuntimeError, match="truncada"):
        entidades._arcgis_query(2, {})


def test_un_resultado_sin_codigo_no_se_descarta_al_resolver_jurisdiccion(monkeypatch):
    from app import entidades

    monkeypatch.setattr(entidades, "_arcgis_query", lambda layer, params: (
        [{"cod_cpnp": "1234"}, {"comisaria": "Registro sin código"}] if layer == 2 else []
    ))
    denuncia = entrada(categoria="Seguridad ciudadana", titulo="Robo en la calle",
        descripcion="Reporto un robo cerca del parque.", latitud=-12.12, longitud=-77.03)
    salida = sugerir_entidad(denuncia)
    assert salida.sugerida is True
    assert salida.entidad.tipo == "revision_competencia"


def test_listar_entidades_disponibles_devuelve_municipalidad_por_categoria_y_territorio():
    from app.entidades import listar_entidades_disponibles

    items = listar_entidades_disponibles(
        "Limpieza y residuos", "Lima", "Lima", "Miraflores"
    )
    assert len(items) == 1
    assert items[0]["id"] == "mun-150122"
    assert items[0]["tipo"] == "municipalidad_distrital"


def test_listar_entidades_disponibles_ofrece_revision_si_no_hay_competencia_habilitada():
    from app.entidades import listar_entidades_disponibles

    items = listar_entidades_disponibles(
        "Vialidad e infraestructura", "Lima", "Lima", "Miraflores"
    )
    assert len(items) == 1
    assert items[0]["tipo"] == "revision_competencia"


def test_listar_entidades_disponibles_ofrece_revision_para_distrito_no_catalogado():
    from app.entidades import listar_entidades_disponibles

    items = listar_entidades_disponibles(
        "Limpieza y residuos", "Lima", "Lima", "Distrito inexistente"
    )
    assert len(items) == 1
    assert items[0]["tipo"] == "revision_competencia"


def test_agua_saneamiento_recomienda_sedapal_en_lima_con_senal_de_red():
    denuncia = entrada(
        categoria="Agua y saneamiento",
        titulo="Fuga de agua potable",
        descripcion="Una tubería rota derrama agua en la avenida y provoca un aniego.",
    )
    salida = sugerir_entidad(denuncia)
    assert salida.sugerida is True
    assert salida.entidad.id == "sedapal-lima-callao"
    assert salida.entidad.tipo == "empresa_saneamiento"


def test_agua_saneamiento_recomienda_sedapal_en_callao():
    denuncia = entrada(
        categoria="Agua y saneamiento",
        departamento="Callao",
        provincia="Callao",
        distrito="Bellavista",
        titulo="Corte de agua en el sector",
        descripcion="Los vecinos reportan que no hay agua potable desde esta mañana.",
    )
    salida = sugerir_entidad(denuncia)
    assert salida.sugerida is True
    assert salida.entidad.id == "sedapal-lima-callao"


def test_agua_saneamiento_no_recomienda_sedapal_fuera_de_su_ambito():
    denuncia = entrada(
        categoria="Agua y saneamiento",
        departamento="Arequipa",
        provincia="Arequipa",
        distrito="Arequipa",
        titulo="Fuga de agua potable",
        descripcion="Una tubería rota provoca un aniego en la avenida.",
    )
    salida = sugerir_entidad(denuncia)
    assert salida.sugerida is True
    assert salida.entidad.tipo == "revision_competencia"


def test_agua_saneamiento_se_abstiene_si_el_texto_no_identifica_red():
    denuncia = entrada(
        categoria="Agua y saneamiento",
        titulo="Problema con el servicio",
        descripcion="Tengo una consulta general sobre mi recibo mensual.",
    )
    salida = sugerir_entidad(denuncia)
    assert salida.sugerida is True
    assert salida.entidad.tipo == "revision_competencia"


def test_catalogo_disponible_incluye_sedapal_para_agua_en_lima():
    from app.entidades import listar_entidades_disponibles

    items = listar_entidades_disponibles(
        "Agua y saneamiento", "Lima", "Lima", "Miraflores"
    )
    assert len(items) == 1
    assert items[0]["id"] == "sedapal-lima-callao"
    assert items[0]["tipo"] == "empresa_saneamiento"


def test_agua_saneamiento_acepta_redaccion_coloquial():
    denuncia = entrada(
        categoria="Agua y saneamiento",
        titulo="No hay agua en mi casa",
        descripcion="Desde ayer no llega agua por la tubería y los vecinos estamos sin servicio.",
    )
    salida = sugerir_entidad(denuncia)
    assert salida.sugerida is True
    assert salida.entidad.id == "sedapal-lima-callao"


def test_catalogo_sedapal_cubre_los_50_distritos_registrados():
    from app.entidades import listar_entidades_disponibles

    municipalidades = [
        item for item in cargar_directorio()
        if item.get("tipo") in {"municipalidad_distrital", "municipalidad_provincial"}
        and item.get("verificado_nombre") is True
    ]
    assert len(municipalidades) == 50
    for item in municipalidades:
        resultado = listar_entidades_disponibles(
            "Agua y saneamiento",
            item["departamento"],
            item["provincia"],
            item["distrito"],
        )
        assert [entity["id"] for entity in resultado] == ["sedapal-lima-callao"]



def test_las_ocho_categorias_tienen_un_destino_de_derivacion():
    casos = [
        ("Alumbrado público", "Poste sin iluminación", "La luminaria de la calle no funciona."),
        ("Seguridad ciudadana", "Robo en la calle", "Reporto un robo cerca del parque."),
        ("Limpieza y residuos", "Basura acumulada", "Hay residuos y bolsas sin recoger en la vía pública."),
        ("Agua y saneamiento", "No hay agua en mi casa", "Desde ayer no llega agua por la tubería."),
        ("Tránsito y transporte", "Semáforo averiado", "El semáforo de la intersección no funciona."),
        ("Parques y áreas verdes", "Parque abandonado", "El parque del barrio tiene jardines descuidados y árboles sin poda."),
        ("Vialidad e infraestructura", "Baches en la pista", "La calzada tiene huecos profundos y veredas rotas."),
        ("Otros", "Ruido por la noche", "Un local emite música con parlantes muy fuertes hasta la madrugada."),
    ]
    for categoria, titulo, descripcion in casos:
        salida = sugerir_entidad(entrada(
            categoria=categoria,
            titulo=titulo,
            descripcion=descripcion,
        ))
        assert salida.sugerida is True, categoria
        assert salida.entidad is not None, categoria
        assert salida.entidad.id, categoria


def test_fallback_de_revision_es_explicito_y_no_se_presenta_como_entidad_externa():
    salida = sugerir_entidad(entrada(
        categoria="Tránsito y transporte",
        titulo="Semáforo averiado",
        descripcion="El semáforo de la intersección no funciona.",
    ))
    assert salida.entidad.tipo == "revision_competencia"
    assert "no una entidad pública externa" in salida.motivo


def test_matriz_distrital_preconfigura_las_ocho_categorias():
    from app.entidades import catalogo_distrital_por_categoria

    matriz = catalogo_distrital_por_categoria("Lima", "Lima", "Miraflores")
    assert matriz["total_categorias"] == 8
    assert {item["categoria"] for item in matriz["categorias"]} == {
        "Alumbrado público", "Seguridad ciudadana", "Limpieza y residuos",
        "Agua y saneamiento", "Tránsito y transporte", "Parques y áreas verdes",
        "Vialidad e infraestructura", "Otros",
    }
    limpieza = next(x for x in matriz["categorias"] if x["categoria"] == "Limpieza y residuos")
    assert limpieza["entidades"][0]["id"] == "mun-150122"
    seguridad = next(x for x in matriz["categorias"] if x["categoria"] == "Seguridad ciudadana")
    assert seguridad["requiere_gps"] is True


def test_resolver_distrito_por_gps_usa_ubigeo_y_catalogo(monkeypatch):
    from app import entidades

    monkeypatch.setattr(entidades, "_arcgis_query_distritos", lambda params: [{
        "UBIGEO": "150122", "NOMBDEP": "LIMA", "NOMBPROV": "LIMA", "NOMBDIST": "MIRAFLORES",
    }])
    territorio = entidades.resolver_distrito_por_punto(-12.12, -77.03)
    assert territorio["ubigeo"] == "150122"
    assert territorio["distrito"] == "Miraflores"


def test_resolver_distrito_por_gps_se_abstiene_si_hay_dos_poligonos(monkeypatch):
    import pytest
    from app import entidades

    monkeypatch.setattr(entidades, "_arcgis_query_distritos", lambda params: [
        {"UBIGEO": "150122"}, {"UBIGEO": "150140"},
    ])
    with pytest.raises(RuntimeError, match="único polígono"):
        entidades.resolver_distrito_por_punto(-12.12, -77.03)


def test_post_recomendacion_usa_distrito_resuelto_por_gps(monkeypatch):
    from app import main

    monkeypatch.setattr(main, "resolver_distrito_por_punto", lambda lat, lon: {
        "ubigeo": "150122", "departamento": "Lima", "provincia": "Lima", "distrito": "Miraflores",
    })
    monkeypatch.setattr(main, "consultar_matriz_distrital", lambda ubigeo: [{"categoria_code": code} for code in (
        "alumbrado", "seguridad", "limpieza", "agua", "transito", "areas_verdes", "infraestructura", "otros"
    )])
    monkeypatch.setattr(main, "consultar_resolutor_categoria", lambda ubigeo, code: {
        "requiere_gps": True, "asignar_solo_tras_gps": True, "entidad_nombre": "Municipalidad local"
    })
    denuncia = entrada(
        distrito="San Isidro",
        latitud=-12.12,
        longitud=-77.03,
    )
    salida = main.predecir_entidad(denuncia)
    assert salida.entidad.ambito["distrito"] == "Miraflores"


def test_catalogo_disponible_usa_distrito_resuelto_por_gps(monkeypatch):
    from app import main

    monkeypatch.setattr(main, "resolver_distrito_por_punto", lambda lat, lon: {
        "ubigeo": "150122", "departamento": "Lima", "provincia": "Lima", "distrito": "Miraflores",
    })
    monkeypatch.setattr(main, "consultar_resolutor_categoria", lambda ubigeo, code: {
        "requiere_gps": True, "asignar_solo_tras_gps": True
    })
    salida = main.entidades_disponibles(
        categoria="Limpieza y residuos",
        departamento="Callao",
        provincia="Callao",
        distrito="Callao",
        latitud=-12.12,
        longitud=-77.03,
    )
    assert salida.entidades[0].ambito["distrito"] == "Miraflores"


def test_catalogo_distrital_relaciona_entidad_con_las_ocho_categorias():
    from app.entidades import catalogo_distrital_por_categoria

    directorio = [
        item for item in cargar_directorio()
        if item.get("tipo") in {"municipalidad_distrital", "municipalidad_provincial"}
        and item.get("verificado_nombre") is True
    ]
    assert len(directorio) == 50

    for municipio in directorio:
        catalogo = catalogo_distrital_por_categoria(
            municipio["departamento"], municipio["provincia"], municipio["distrito"]
        )
        assert catalogo["total_categorias"] == 8
        assert catalogo["categorias_con_entidad_relacionada"] == 8
        for categoria in catalogo["categorias"]:
            assert categoria["entidades"], categoria["categoria"]
            assert categoria["entidad_principal"]["id"]
            assert categoria["entidad_principal"]["nombre"]
            assert categoria["entidad_principal"]["tipo"] != "revision_competencia"

        limpieza = next(c for c in catalogo["categorias"] if c["categoria"] == "Limpieza y residuos")
        assert limpieza["entidad_principal"]["id"] == municipio["id"]

        parques = next(c for c in catalogo["categorias"] if c["categoria"] == "Parques y áreas verdes")
        assert parques["entidad_principal"]["id"] == municipio["id"]


def test_catalogo_distrital_no_presenta_revision_interna_como_entidad_publica():
    from app.entidades import catalogo_distrital_por_categoria

    catalogo = catalogo_distrital_por_categoria("Lima", "Lima", "Miraflores")
    for categoria in catalogo["categorias"]:
        assert all(e["tipo"] != "revision_competencia" for e in categoria["entidades"])
        assert categoria["respaldo"]["tipo"] != "revision_competencia" or categoria["respaldo"]["id"] == "revision-competencia"
